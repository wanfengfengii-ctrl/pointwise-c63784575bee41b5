"""End-to-end check of the offline delegation path for the published samples.

This is the linked verification used by ``check_project.py``: the holder side
issues a narrowed child from a received V1 parent, a separate reviewer database
receives it with only the desk delegation, signs the unconfirmed and confirmed
reviews, then reopens and reclaims the original results.
"""
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.read import read_report
from archive.transactions import ArchiveStore
from issue.envelope import EnvelopeMismatch, open_envelope
from issue.publish import publish_delegated_packet
from issue.receipts import ReceiptStore
from review.confirmations import Confirmation
from review.requests import OldAnnotation, ReviewRequest
from review.submit import submit_review
from transfer_sample import SAMPLES, prepare_parent, prepare_reviewer


def _landings(entry):
    return [word['word_id'] for word in entry.report.details['outcomes'][0]['targets']]


def _can_omit(entry):
    return entry.report.details['outcomes'][0]['can_have_no_public_landing']


def check_sample(sample: dict) -> dict:
    name = sample['name']
    with TemporaryDirectory(prefix=f'qingyu-{name}-') as directory:
        holder_path, source_path = Path(directory, 'holder.sqlite'), Path(directory, 'source.sqlite')
        reviewer_path = Path(directory, 'reviewer.sqlite')
        with closing(sqlite3.connect(holder_path)) as holder, closing(sqlite3.connect(source_path)) as source:
            holder_receipts = prepare_parent(source, holder, sample)
            envelope = publish_delegated_packet(holder_receipts, name, sample['delegation'],
                                                sample['old_bounds'], sample['new_bounds'],
                                                packet_id=f'{name}-child')
        with closing(sqlite3.connect(reviewer_path)) as reviewer:
            receipts, archive = prepare_reviewer(reviewer)
            if receipts.get_received(name) is not None:
                raise AssertionError(f'reviewer already holds parent {name}')
            packet = open_envelope(envelope)
            receipt = receipts.accept(envelope, delegation=sample['delegation'])
            if receipt.packet_id != f'{name}-child':
                raise AssertionError('delegated receipt names the wrong child')
            annotations = tuple(OldAnnotation(f'note-{index}', word.word_id)
                                for index, word in enumerate(packet.old.words))
            baseline = submit_review(receipts, archive, ReviewRequest(receipt.packet_id, annotations))
            confirmation = Confirmation(packet.old.words[0].word_id, packet.new.words[0].word_id)
            confirmed = submit_review(receipts, archive,
                                      ReviewRequest(receipt.packet_id, annotations, (confirmation,)))
            details = confirmed.report.details
            if details['delegation']['parent_packet_id'] != name:
                raise AssertionError('confirmed report does not name its parent packet')
            if details['delegation']['delegation_id'] != sample['delegation']['delegation_id']:
                raise AssertionError('confirmed report does not name its delegation')
            if receipts.accept(envelope, delegation=sample['delegation']) != receipt:
                raise AssertionError('reposting the same child did not return the original receipt')
            try:
                receipts.accept(envelope)
            except EnvelopeMismatch:
                pass
            else:
                raise AssertionError('a delegated child was accepted without its delegation')
        with closing(sqlite3.connect(reviewer_path)) as reviewer:
            receipts, archive = ReceiptStore(reviewer), ArchiveStore(reviewer)
            receipts.initialize()
            archive.initialize()
            restored = tuple(read_report(archive, entry.report.report_id)
                             for entry in (baseline, confirmed))
            if restored != (baseline, confirmed):
                raise AssertionError('reopened review library did not return the original results')
            if receipts.get_received(receipt.packet_id).receipt != receipt:
                raise AssertionError('reopened review library did not return the original receipt')
            reopened = read_report(archive, confirmed.report.report_id)
        return {
            'parent_packet_id': name,
            'child_packet_id': receipt.packet_id,
            'child_words': [len(packet.old.words), len(packet.new.words)],
            'unconfirmed_cost': baseline.report.details['cost'],
            'unconfirmed_landings': _landings(baseline),
            'unconfirmed_can_be_omitted': _can_omit(baseline),
            'confirmed_cost': confirmed.report.details['cost'],
            'confirmed_landings': _landings(confirmed),
            'confirmed_can_be_omitted': _can_omit(confirmed),
            'delegation_id': confirmed.report.details['delegation']['delegation_id'],
            'delegation_digest': confirmed.report.details['delegation']['delegation_digest'],
            'report_ids': [baseline.report.report_id, confirmed.report.report_id],
            'receipt_ids': [baseline.receipt.receipt_id, confirmed.receipt.receipt_id],
            'reopened_report': reopened.report.report_id,
        }


EXPECTED = {
    'late': {'unconfirmed_cost': 2, 'unconfirmed_landings': [], 'unconfirmed_can_be_omitted': True,
             'confirmed_cost': 4, 'confirmed_landings': ['late-new:2'], 'confirmed_can_be_omitted': False},
    'tie': {'unconfirmed_cost': 1, 'unconfirmed_landings': ['tie-new:0'], 'unconfirmed_can_be_omitted': True,
            'confirmed_cost': 1, 'confirmed_landings': ['tie-new:0'], 'confirmed_can_be_omitted': False},
}


def verify() -> list[dict]:
    results = []
    for sample in SAMPLES:
        result = check_sample(sample)
        for key, value in EXPECTED[sample['name']].items():
            if result[key] != value:
                raise AssertionError(f'{sample["name"]} expected {key}={value!r}, observed {result[key]!r}')
        results.append(result)
    return results


if __name__ == '__main__':
    for row in verify():
        print(row)
