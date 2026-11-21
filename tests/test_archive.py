import sqlite3
import unittest

from archive.read import read_report
from review.submit import submit_review
from revisions.importer import import_revision
from revisions.model import SourceSegment
from tests.fixtures import DeskCase, scenario


class ArchiveTests(DeskCase):
    def test_sign_failure(self):
        exchange = self.exchange('A', 'A')
        self.close_source()
        original = submit_review(self.receipts, self.archive, exchange.request())
        before = self.ledger_ids()
        # The trigger runs after both production inserts and introduces a
        # deferred violation. SQLite therefore rejects the actual COMMIT.
        self.offline.execute('CREATE TABLE failure_parent (id TEXT PRIMARY KEY)')
        self.offline.execute('''CREATE TABLE failure_child (
            id TEXT REFERENCES failure_parent(id) DEFERRABLE INITIALLY DEFERRED
        )''')
        self.offline.execute('''CREATE TRIGGER fail_archive_commit AFTER INSERT ON archive_receipts
            BEGIN INSERT INTO failure_child VALUES (NEW.report_id); END''')
        statements = []
        self.offline.set_trace_callback(statements.append)
        try:
            with self.assertRaises(sqlite3.IntegrityError) as failure:
                submit_review(self.receipts, self.archive, exchange.request())
        finally:
            self.offline.set_trace_callback(None)
        self.assertEqual(failure.exception.sqlite_errorcode, sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY)
        self.assertIn('COMMIT', statements)
        self.assertIn('ROLLBACK', statements)
        self.assertFalse(self.offline.in_transaction)
        self.assertEqual(self.ledger_ids(), before)
        self.assertEqual(self.offline.execute('SELECT COUNT(*) FROM failure_child').fetchone()[0], 0)
        self.close_offline()
        self.open_offline()
        old = read_report(self.archive, original.report.report_id)
        self.assertEqual(old, original)
        after = self.ledger_ids()
        self.assertEqual(after, before)
        scenario('V8', {'prior_ledger': [1, 1], 'failure': 'deferred foreign key at commit'}, [1, 1],
                 [len(ids) for ids in after], original.receipt.receipt_id, old.receipt.receipt_id,
                 ['archive/sign.py', 'archive/transactions.py', 'archive/read.py'],
                 'A failed SQLite commit must leave the prior pair as the sole report and receipt.')

    def test_reopen_after_source_revision(self):
        exchange = self.exchange('AXX', 'XXA', (0, 0), (2, 2), name='oral')
        received = self.receipts.get_received('oral')
        self.close_source()
        initial = submit_review(self.receipts, self.archive, exchange.request())
        self.open_source()
        import_revision(self.revisions, 'oral', 'oral-corrected', (SourceSegment('recheck', 1, ('Z',)),))
        self.revisions.initialize()
        self.excerpts.initialize()
        self.assertIsNotNone(self.revisions.get('oral-old'))
        self.close_source()
        self.close_offline()
        self.open_offline()
        loaded = read_report(self.archive, initial.report.report_id)
        self.assertEqual(loaded, initial)
        self.assertEqual(read_report(self.archive, initial.report.report_id), loaded)
        self.assertEqual(self.receipts.get_received('oral'), received)
        provenance = loaded.report.details['packet']
        self.assertEqual(provenance['old']['revision_id'], 'oral-old')
        self.assertEqual(provenance['new']['revision_id'], 'oral-new')
        self.assertEqual(provenance['body_digest'], received.receipt.body_digest)
        self.assertEqual(loaded.report.details['cost'], 2)
        self.assertEqual(self.ledger_ids(), ([(initial.report.report_id,)], [(initial.receipt.receipt_id,)]))
        scenario('V9', {'correction': 'oral-corrected', 'packet': 'oral'}, ['oral-old', 'oral-new'],
                 [provenance['old']['revision_id'], provenance['new']['revision_id']],
                 initial.receipt.receipt_id, loaded.receipt.receipt_id,
                 ['revisions/importer.py', 'archive/read.py', 'archive/audit.py'],
                 'Compare against the ordered revision identifiers and the original receipt recorded before correction.')

    def test_unknown_report(self):
        self.assertIsNone(read_report(self.archive, 'unknown'))
        self.assertEqual(self.ledger_ids(), ([], []))
