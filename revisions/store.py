import sqlite3

from revisions.model import Revision, SourceOrigin, SourceSegment, WordOccurrence


class RevisionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        db = self.connection
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('BEGIN IMMEDIATE')
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS revisions (
                revision_id TEXT PRIMARY KEY NOT NULL,
                manuscript_id TEXT NOT NULL
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS source_segments (
                revision_id TEXT NOT NULL REFERENCES revisions(revision_id),
                segment_id TEXT NOT NULL,
                segment_order INTEGER NOT NULL,
                PRIMARY KEY (revision_id, segment_id),
                UNIQUE (revision_id, segment_order)
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS source_words (
                word_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                value TEXT NOT NULL,
                segment_id TEXT NOT NULL,
                word_index INTEGER NOT NULL,
                FOREIGN KEY (revision_id, segment_id)
                    REFERENCES source_segments(revision_id, segment_id),
                UNIQUE (revision_id, ordinal),
                UNIQUE (revision_id, segment_id, word_index)
            )''')

    def insert(self, revision: Revision) -> None:
        db = self.connection
        db.execute('BEGIN IMMEDIATE')
        try:
            with db:
                db.execute('INSERT INTO revisions VALUES (?, ?)',
                           (revision.revision_id, revision.manuscript_id))
                db.executemany('INSERT INTO source_segments VALUES (?, ?, ?)', (
                    (revision.revision_id, segment.segment_id, segment.order)
                    for segment in revision.segments
                ))
                db.executemany('INSERT INTO source_words VALUES (?, ?, ?, ?, ?, ?)', (
                    (word.word_id, revision.revision_id, word.ordinal, word.value,
                     word.origin.segment_id, word.origin.word_index)
                    for word in revision.words
                ))
        except sqlite3.IntegrityError as exc:
            raise ValueError('revision or source occurrence conflicts with stored data') from exc

    def get(self, revision_id: str) -> Revision | None:
        db = self.connection
        header = db.execute('SELECT manuscript_id FROM revisions WHERE revision_id = ?', (revision_id,)).fetchone()
        if header is None:
            return None
        segments = db.execute('''SELECT segment_id, segment_order FROM source_segments
            WHERE revision_id = ? ORDER BY segment_order''', (revision_id,)).fetchall()
        segment_orders = dict(segments)
        values = {segment_id: [] for segment_id in segment_orders}
        words = []
        for word_id, ordinal, value, segment_id, word_index in db.execute('''
            SELECT word_id, ordinal, value, segment_id, word_index FROM source_words
            WHERE revision_id = ? ORDER BY ordinal''', (revision_id,)):
            values[segment_id].append(value)
            origin = SourceOrigin(segment_id, segment_orders[segment_id], word_index)
            words.append(WordOccurrence(word_id, ordinal, value, origin))
        return Revision(header[0], revision_id, tuple(
            SourceSegment(segment_id, order, tuple(values[segment_id]))
            for segment_id, order in segments
        ), tuple(words))
