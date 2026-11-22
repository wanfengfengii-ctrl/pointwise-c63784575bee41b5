import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.read import read_report
from archive.transactions import ArchiveStore
from excerpts.policy import PublicationPermission
from excerpts.selection import select_excerpt
from excerpts.store import ExcerptStore
from issue.publish import publish_delegated_packet, publish_packet
from issue.receipts import ReceiptStore
from review.confirmations import Confirmation
from review.requests import OldAnnotation, ReviewRequest
from review.submit import submit_review
from revisions.importer import import_revision
from revisions.model import SourceSegment
from revisions.store import RevisionStore
from transfer_sample import SAMPLES, prepare_parent, prepare_reviewer


def _load_revision(store, manuscript, data):
    segments = tuple(SourceSegment(row['segment_id'], row['order'], tuple(row['words'])) for row in data['segments'])
    return import_revision(store, manuscript, data['revision_id'], segments)


def _show(step, **fields):
    print(json.dumps({'step': step, **fields}, ensure_ascii=False, sort_keys=True))


def _landings(entry):
    return [word['word_id'] for word in entry.report.details['outcomes'][0]['targets']]


def _delegated_run(name, directory):
    sample = next(item for item in SAMPLES if item['name'] == name)
    grant = sample['delegation']
    holder_path = Path(directory, f'{name}-holder.sqlite')
    source_path = Path(directory, f'{name}-source.sqlite')
    offline_path = Path(directory, f'{name}-reviewer.sqlite')
    with closing(sqlite3.connect(holder_path)) as holder, closing(sqlite3.connect(source_path)) as source:
        holder_receipts = prepare_parent(source, holder, sample)
        parent = holder_receipts.get_received(name)
        child_id = f'{name}-child'
        envelope = publish_delegated_packet(holder_receipts, name, grant, sample['old_bounds'],
                                            sample['new_bounds'], packet_id=child_id)
    with closing(sqlite3.connect(offline_path)) as offline:
        receipts, archive = prepare_reviewer(offline)
        packet = receipts.get_received(name)
        if packet is not None:
            raise RuntimeError('reviewer library is not isolated from the parent')
        receipt = receipts.accept(envelope, delegation=grant)
        child = receipts.get_received(child_id).packet
        _show(9, parent=parent.receipt.packet_id, parent_body_digest=parent.receipt.body_digest,
              child=receipt.packet_id, delegation=grant['delegation_id'],
              child_words=[len(child.old.words), len(child.new.words)],
              reviewer_holds_parent=receipts.get_received(name) is not None)
        annotations = tuple(OldAnnotation(f'note-{index}', word.word_id)
                            for index, word in enumerate(child.old.words))
        baseline = submit_review(receipts, archive, ReviewRequest(child_id, annotations))
        _show(10, report=baseline.report.report_id, cost=baseline.report.details['cost'],
              landings=_landings(baseline),
              can_have_no_public_landing=baseline.report.details['outcomes'][0]['can_have_no_public_landing'])
        confirmation = Confirmation(child.old.words[0].word_id, child.new.words[0].word_id)
        confirmed = submit_review(receipts, archive, ReviewRequest(child_id, annotations, (confirmation,)))
        _show(11, report=confirmed.report.report_id, cost=confirmed.report.details['cost'],
              landings=_landings(confirmed),
              can_have_no_public_landing=confirmed.report.details['outcomes'][0]['can_have_no_public_landing'],
              delegation=confirmed.report.details['delegation'])
        if receipts.accept(envelope, delegation=grant) != receipt:
            raise RuntimeError('reposted delegated child did not return its original receipt')
    with closing(sqlite3.connect(offline_path)) as offline:
        receipts, archive = ReceiptStore(offline), ArchiveStore(offline)
        receipts.initialize()
        archive.initialize()
        recovered = tuple(read_report(archive, entry.report.report_id) for entry in (baseline, confirmed))
        if recovered != (baseline, confirmed):
            raise RuntimeError('reopened delegated library changed a signed result')
        if receipts.get_received(child_id).receipt != receipt:
            raise RuntimeError('reopened delegated library changed the original receipt')
        _show(12, reports=[entry.report.report_id for entry in recovered],
              original_receipts=[entry.receipt.receipt_id for entry in recovered],
              child_receipt=receipt.receipt_id)


def main():
    sample = json.loads(Path(__file__).with_name('sample_subtitles.json').read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='qingyu-handoff-') as directory:
        source_path, offline_path = Path(directory, 'source.sqlite'), Path(directory, 'offline.sqlite')
        with closing(sqlite3.connect(offline_path)) as offline:
            receipts, archive = ReceiptStore(offline), ArchiveStore(offline)
            receipts.initialize()
            archive.initialize()
            with closing(sqlite3.connect(source_path)) as source:
                revisions, excerpts = RevisionStore(source), ExcerptStore(source)
                revisions.initialize()
                excerpts.initialize()
                old = _load_revision(revisions, sample['manuscript_id'], sample['old'])
                _show(1, revision=old.revision_id, words=len(old.words))
                new = _load_revision(revisions, sample['manuscript_id'], sample['new'])
                _show(2, revision=new.revision_id, words=len(new.words))
                selected = (revisions.get(old.revision_id), revisions.get(new.revision_id))
                _show(3, ordered_revisions=[revision.revision_id for revision in selected])
                chosen = []
                for side, revision in zip(('old', 'new'), selected, strict=True):
                    start, end = sample[side]['public_bounds']
                    first, last = revision.words[start].word_id, revision.words[end].word_id
                    permit = PublicationPermission(f'permit-{side}', revision.revision_id, first, last)
                    chosen.append(select_excerpt(revisions, excerpts, f'excerpt-{side}', revision.revision_id,
                                                 permit, first, last))
                _show(4, excerpts=[excerpt.excerpt_id for excerpt in chosen], public=[[w.value for w in e.words] for e in chosen])
                envelope = publish_packet(revisions, excerpts, chosen[0].excerpt_id, chosen[1].excerpt_id,
                                          packet_id='qy-07-handoff')
                receipt = receipts.accept(envelope)
                _show(5, packet=receipt.packet_id, receipt=receipt.receipt_id)
            packet = receipts.get_received(receipt.packet_id).packet
            annotation = OldAnnotation('opening-note', packet.old.words[0].word_id)
            baseline = submit_review(receipts, archive, ReviewRequest(receipt.packet_id, (annotation,)))
            before = baseline.report.details
            if before['cost'] != 2 or before['outcomes'][0]['targets'] or not before['outcomes'][0]['can_have_no_public_landing']:
                raise RuntimeError('unexpected unconfirmed annotation result')
            _show(6, report=baseline.report.report_id, cost=before['cost'], outcomes=before['outcomes'])
            confirmation = Confirmation(annotation.word_id, packet.new.words[0].word_id)
            confirmed = submit_review(receipts, archive, ReviewRequest(receipt.packet_id, (annotation,), (confirmation,)))
            after = confirmed.report.details
            targets = [word['word_id'] for word in after['outcomes'][0]['targets']]
            if after['cost'] != 4 or targets != [confirmation.new_word_id] or after['outcomes'][0]['can_have_no_public_landing']:
                raise RuntimeError('unexpected confirmed annotation result')
            _show(7, report=confirmed.report.report_id, cost=after['cost'], outcomes=after['outcomes'])
        with closing(sqlite3.connect(source_path)) as source:
            revisions = RevisionStore(source)
            revisions.initialize()
            correction = _load_revision(revisions, sample['manuscript_id'], sample['correction'])
        with closing(sqlite3.connect(offline_path)) as offline:
            archive = ArchiveStore(offline)
            archive.initialize()
            originals = (baseline, confirmed)
            recovered = tuple(read_report(archive, entry.report.report_id) for entry in originals)
            if recovered != originals:
                raise RuntimeError('historical reports or original receipts changed')
            _show(8, later_revision=correction.revision_id,
                  reports=[entry.report.report_id for entry in recovered],
                  original_receipts=[entry.receipt.receipt_id for entry in recovered])
        _delegated_run('late', directory)


if __name__ == '__main__':
    main()
