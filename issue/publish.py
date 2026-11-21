from uuid import uuid4

from excerpts.projection import Excerpt
from excerpts.store import ExcerptStore
from issue.alignment_evidence import build_alignment_evidence
from issue.envelope import seal_packet
from issue.packet import ExcerptIdentity, Packet, PacketWord, PublishedExcerpt
from revisions.model import Revision, require_identifier
from revisions.store import RevisionStore


def _published_excerpt(revision: Revision, excerpt: Excerpt) -> PublishedExcerpt:
    return PublishedExcerpt(
        ExcerptIdentity(revision.manuscript_id, revision.revision_id, excerpt.excerpt_id, excerpt.permission_id),
        tuple(PacketWord(word.word_id, word.ordinal, word.value, word.origin.segment_id,
                         word.origin.segment_order, word.origin.word_index) for word in excerpt.words),
    )


def publish_packet(
    revisions: RevisionStore,
    excerpts: ExcerptStore,
    old_excerpt_id: str,
    new_excerpt_id: str,
    *,
    packet_id: str | None = None,
) -> str:
    require_identifier(old_excerpt_id)
    require_identifier(new_excerpt_id)
    if packet_id is None:
        packet_id = uuid4().hex
    require_identifier(packet_id)
    old_excerpt, new_excerpt = excerpts.get(old_excerpt_id), excerpts.get(new_excerpt_id)
    if old_excerpt is None or new_excerpt is None:
        raise ValueError('unknown excerpt')
    old_revision, new_revision = revisions.get(old_excerpt.revision_id), revisions.get(new_excerpt.revision_id)
    if old_revision is None or new_revision is None:
        raise ValueError('excerpt revision is unavailable')
    if old_revision.manuscript_id != new_revision.manuscript_id or old_revision.revision_id == new_revision.revision_id:
        raise ValueError('select two distinct revisions of the same manuscript')
    old = _published_excerpt(old_revision, old_excerpt)
    new = _published_excerpt(new_revision, new_excerpt)
    evidence = build_alignment_evidence(old_revision, new_revision, old, new)
    return seal_packet(Packet(packet_id, old, new, evidence))
