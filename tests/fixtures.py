import json
import sqlite3
import unittest
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.transactions import ArchiveStore
from excerpts.policy import PublicationPermission
from excerpts.selection import select_excerpt
from excerpts.store import ExcerptStore
from issue.envelope import open_envelope
from issue.packet import Packet
from issue.publish import publish_packet
from issue.receipts import ReceiptStore
from review.requests import OldAnnotation, ReviewRequest
from revisions.importer import import_revision
from revisions.model import SourceSegment
from revisions.store import RevisionStore


@dataclass(frozen=True)
class Exchange:
    packet: Packet
    envelope: str

    def request(self, confirmations=()):
        annotations = tuple(OldAnnotation(f'note-{i}', word.word_id) for i, word in enumerate(self.packet.old.words))
        return ReviewRequest(self.packet.packet_id, annotations, confirmations)


class DeskCase(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.source_path = Path(directory, 'source.sqlite')
        self.offline_path = Path(directory, 'offline.sqlite')
        self.source = None
        self.offline = None
        self.addCleanup(self.close_source)
        self.addCleanup(self.close_offline)
        self.open_source()
        self.open_offline()

    def open_source(self):
        self.source = sqlite3.connect(self.source_path)
        self.revisions = RevisionStore(self.source)
        self.excerpts = ExcerptStore(self.source)
        self.revisions.initialize()
        self.excerpts.initialize()

    def close_source(self):
        if self.source is not None:
            self.source.close()
            self.source = None

    def open_offline(self):
        self.offline = sqlite3.connect(self.offline_path)
        self.receipts = ReceiptStore(self.offline)
        self.archive = ArchiveStore(self.offline)
        self.receipts.initialize()
        self.archive.initialize()

    def close_offline(self):
        if self.offline is not None:
            self.offline.close()
            self.offline = None

    def exchange(self, old, new, old_bounds=None, new_bounds=None, *, name='case', receive=True):
        excerpts = []
        for side, values, bounds in (('old', old, old_bounds), ('new', new, new_bounds)):
            prefix = f'{name}-{side}'
            revision = import_revision(self.revisions, name, prefix, (SourceSegment(f'{side}-segment', 5, tuple(values)),))
            first, last = bounds if bounds is not None else (0, len(values) - 1)
            start, end = revision.words[first].word_id, revision.words[last].word_id
            permission = PublicationPermission(f'{prefix}-permission', prefix, start, end)
            excerpts.append(select_excerpt(self.revisions, self.excerpts, f'{prefix}-excerpt', prefix, permission, start, end))
        envelope = publish_packet(self.revisions, self.excerpts, excerpts[0].excerpt_id, excerpts[1].excerpt_id, packet_id=name)
        if receive:
            self.receipts.accept(envelope)
        return Exchange(open_envelope(envelope), envelope)

    def ledger_ids(self):
        reports = self.offline.execute('SELECT report_id FROM archive_reports ORDER BY report_id').fetchall()
        receipts = self.offline.execute('SELECT receipt_id FROM archive_receipts ORDER BY receipt_id').fetchall()
        return reports, receipts


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    payload = {
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
        'code_paths': code_paths, 'oracle': oracle,
    }
    print('POINTWISE_SCENARIO ' + json.dumps(payload, sort_keys=True))
