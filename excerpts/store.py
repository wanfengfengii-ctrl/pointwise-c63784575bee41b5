import json
import sqlite3
from dataclasses import asdict

from excerpts.policy import PublicationPermission
from excerpts.projection import Excerpt, PublicWord
from revisions.model import SourceOrigin


class ExcerptStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        db = self.connection
        db.execute('PRAGMA foreign_keys = ON')
        db.execute('BEGIN IMMEDIATE')
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS publication_permissions (
                permission_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL REFERENCES revisions(revision_id),
                first_word_id TEXT NOT NULL REFERENCES source_words(word_id),
                last_word_id TEXT NOT NULL REFERENCES source_words(word_id),
                UNIQUE (permission_id, revision_id)
            )''')
            db.execute('''CREATE TABLE IF NOT EXISTS excerpts (
                excerpt_id TEXT PRIMARY KEY NOT NULL,
                revision_id TEXT NOT NULL,
                permission_id TEXT NOT NULL,
                words TEXT NOT NULL,
                FOREIGN KEY (permission_id, revision_id)
                    REFERENCES publication_permissions(permission_id, revision_id)
            )''')

    def insert(self, excerpt: Excerpt, permission: PublicationPermission) -> None:
        if (excerpt.permission_id, excerpt.revision_id) != (permission.permission_id, permission.revision_id):
            raise ValueError('excerpt and publication permission do not agree')
        db = self.connection
        bounds = (permission.revision_id, permission.first_word_id, permission.last_word_id)
        words = json.dumps([asdict(word) for word in excerpt.words], separators=(',', ':'))
        db.execute('BEGIN IMMEDIATE')
        try:
            with db:
                db.execute('''INSERT INTO publication_permissions VALUES (?, ?, ?, ?)
                    ON CONFLICT(permission_id) DO NOTHING''', (permission.permission_id, *bounds))
                stored = db.execute('''SELECT revision_id, first_word_id, last_word_id
                    FROM publication_permissions WHERE permission_id = ?''', (permission.permission_id,)).fetchone()
                if tuple(stored) != bounds:
                    raise ValueError('permission identifier conflicts with a registered range')
                db.execute('INSERT INTO excerpts VALUES (?, ?, ?, ?)',
                           (excerpt.excerpt_id, excerpt.revision_id, excerpt.permission_id, words))
        except sqlite3.IntegrityError as exc:
            raise ValueError('excerpt conflicts with stored data') from exc

    def get(self, excerpt_id: str) -> Excerpt | None:
        row = self.connection.execute('''SELECT revision_id, permission_id, words
            FROM excerpts WHERE excerpt_id = ?''', (excerpt_id,)).fetchone()
        if row is None:
            return None
        revision_id, permission_id, words = row
        return Excerpt(excerpt_id, revision_id, permission_id, tuple(
            PublicWord(word['word_id'], word['ordinal'], word['value'], SourceOrigin(**word['origin']))
            for word in json.loads(words)
        ))
