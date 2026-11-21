"""Prepare fixed V1 parent packets for the offline transfer examples."""
import json
import sqlite3
from contextlib import closing

from archive.transactions import ArchiveStore
from excerpts.policy import PublicationPermission
from excerpts.selection import select_excerpt
from excerpts.store import ExcerptStore
from issue.publish import publish_packet
from issue.receipts import ReceiptStore
from revisions.importer import import_revision
from revisions.model import SourceSegment
from revisions.store import RevisionStore


SAMPLES = (
    {
        "name": "late",
        "old_words": ["A", "X", "X", "B"],
        "new_words": ["X", "X", "A", "B"],
        "delegation": {
            "delegation_id": "desk-late",
            "parent_packet_id": "late",
            "parent_body_digest": "9644195dfa415a181d1fac88087b4ecd01c74c33804de1d83922c262253b5338",
            "old": {"revision_id": "late-old", "first_word_id": "late-old:0", "last_word_id": "late-old:1"},
            "new": {"revision_id": "late-new", "first_word_id": "late-new:1", "last_word_id": "late-new:2"},
        },
        "old_bounds": ("late-old:0", "late-old:0"),
        "new_bounds": ("late-new:2", "late-new:2"),
    },
    {
        "name": "tie",
        "old_words": ["A"],
        "new_words": ["A", "A"],
        "delegation": {
            "delegation_id": "desk-tie",
            "parent_packet_id": "tie",
            "parent_body_digest": "63ae58cdbe6e6e87dd0fd4d4628d621b67460b6b433a8bc2e330799846cc2b3c",
            "old": {"revision_id": "tie-old", "first_word_id": "tie-old:0", "last_word_id": "tie-old:0"},
            "new": {"revision_id": "tie-new", "first_word_id": "tie-new:0", "last_word_id": "tie-new:0"},
        },
        "old_bounds": ("tie-old:0", "tie-old:0"),
        "new_bounds": ("tie-new:0", "tie-new:0"),
    },
)


def prepare_parent(source: sqlite3.Connection, holder: sqlite3.Connection, sample: dict) -> ReceiptStore:
    revisions, excerpts = RevisionStore(source), ExcerptStore(source)
    revisions.initialize()
    excerpts.initialize()
    name = sample["name"]
    excerpt_ids = []
    for side in ("old", "new"):
        revision_id = f"{name}-{side}"
        words = tuple(sample[f"{side}_words"])
        revision = import_revision(revisions, name, revision_id, (SourceSegment(f"{side}-segment", 5, words),))
        first, last = revision.words[0].word_id, revision.words[-1].word_id
        permission = PublicationPermission(f"{revision_id}-permission", revision_id, first, last)
        excerpt_id = f"{revision_id}-excerpt"
        select_excerpt(revisions, excerpts, excerpt_id, revision_id, permission, first, last)
        excerpt_ids.append(excerpt_id)
    envelope = publish_packet(revisions, excerpts, *excerpt_ids, packet_id=name)
    receipts = ReceiptStore(holder)
    receipts.initialize()
    receipts.accept(envelope)
    return receipts


def prepare_reviewer(connection: sqlite3.Connection) -> tuple[ReceiptStore, ArchiveStore]:
    receipts, archive = ReceiptStore(connection), ArchiveStore(connection)
    receipts.initialize()
    archive.initialize()
    return receipts, archive


def main():
    for sample in SAMPLES:
        with closing(sqlite3.connect(":memory:")) as holder, closing(sqlite3.connect(":memory:")) as reviewer:
            with closing(sqlite3.connect(":memory:")) as source:
                receipts = prepare_parent(source, holder, sample)
            review_receipts, _ = prepare_reviewer(reviewer)
            grant = sample["delegation"]
            name = grant["parent_packet_id"]
            parent = receipts.get_received(name)
            if parent is None or parent.receipt.body_digest != grant["parent_body_digest"]:
                raise RuntimeError(f"sample does not identify the prepared parent: {name}")
            if review_receipts.get_received(name) is not None:
                raise RuntimeError(f"sample reviewer already holds the parent: {name}")
            word_counts = [len(parent.packet.old.words), len(parent.packet.new.words)]
            print(json.dumps({"parent_packet_id": name, "parent_body_digest": parent.receipt.body_digest,
                              "parent_word_counts": word_counts, "reviewer_holds_parent": False}, sort_keys=True))


if __name__ == "__main__":
    main()
