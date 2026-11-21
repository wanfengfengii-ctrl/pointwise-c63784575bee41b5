import sqlite3

from archive.audit import verify_archived_entry
from archive.records import ArchiveEntry, ArchiveReceipt, Report


class ArchiveStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        db = self.connection
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('BEGIN IMMEDIATE')
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS archive_reports (
                report_id TEXT PRIMARY KEY NOT NULL,
                packet_id TEXT NOT NULL,
                packet_digest TEXT NOT NULL,
                snapshot TEXT NOT NULL
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS archive_receipts (
                report_id TEXT PRIMARY KEY NOT NULL REFERENCES archive_reports(report_id),
                receipt_id TEXT UNIQUE NOT NULL,
                packet_id TEXT NOT NULL,
                packet_digest TEXT NOT NULL,
                report_digest TEXT NOT NULL
            )''')

    def commit_signed(self, entry: ArchiveEntry) -> None:
        verify_archived_entry(entry)
        db = self.connection
        report, receipt = entry.report, entry.receipt
        db.execute('BEGIN IMMEDIATE')
        with db:
            db.execute('INSERT INTO archive_reports VALUES (?, ?, ?, ?)',
                       (report.report_id, report.packet_id, report.packet_digest, report.snapshot))
            db.execute('INSERT INTO archive_receipts VALUES (?, ?, ?, ?, ?)',
                       (receipt.report_id, receipt.receipt_id, receipt.packet_id,
                        receipt.packet_digest, receipt.report_digest))

    def get_signed(self, report_id: str) -> ArchiveEntry | None:
        row = self.connection.execute('''SELECT a.report_id, a.packet_id, a.packet_digest, a.snapshot,
            r.receipt_id, r.report_id, r.packet_id, r.packet_digest, r.report_digest
            FROM archive_reports a LEFT JOIN archive_receipts r ON a.report_id = r.report_id
            WHERE a.report_id = ?''', (report_id,)).fetchone()
        if row is None:
            return None
        if row[4] is None:
            raise ValueError('stored report has no original archive receipt')
        return ArchiveEntry(Report(*row[:4]), ArchiveReceipt(*row[4:]))
