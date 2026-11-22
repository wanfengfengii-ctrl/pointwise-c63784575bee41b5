from uuid import uuid4

from excerpts.projection import Excerpt
from excerpts.store import ExcerptStore
from issue.alignment_evidence import build_alignment_evidence, build_delegated_evidence
from issue.delegation import Delegation, parse_delegation
from issue.envelope import seal_delegated_packet, seal_packet
from issue.packet import (
    DelegatedPacket, ExcerptIdentity, Packet, PacketWord, PublishedExcerpt,
)
from issue.receipts import ReceiptStore
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


def _side_positions(words: tuple, bounds: tuple, delegated, parent: PublishedExcerpt) -> tuple[int, int]:
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
        raise ValueError('delegated bounds must be a pair of word identifiers')
    first_id, last_id = bounds
    require_identifier(first_id)
    require_identifier(last_id)
    ids = [word.word_id for word in words]
    for endpoint in (delegated.first_word_id, delegated.last_word_id, first_id, last_id):
        if endpoint not in ids:
            raise ValueError('a delegated endpoint or bound lies outside the parent fragment')
    authorized_start, authorized_end = ids.index(delegated.first_word_id), ids.index(delegated.last_word_id)
    if authorized_start > authorized_end:
        raise ValueError('a delegated range reverses the original word order')
    if parent.identity.revision_id != delegated.revision_id:
        raise ValueError('a delegation names a different revision than the parent fragment')
    start, end = ids.index(first_id), ids.index(last_id)
    if start > end:
        raise ValueError('a delegated bound reverses the original word order')
    if not authorized_start <= start <= end <= authorized_end:
        raise ValueError('the selected interval exceeds the delegated authorization')
    return start, end


def publish_delegated_packet(
    receipts: ReceiptStore,
    parent_packet_id: str,
    delegation: dict,
    old_bounds: tuple[str, str],
    new_bounds: tuple[str, str],
    *,
    packet_id: str | None = None,
) -> str:
    require_identifier(parent_packet_id)
    grant: Delegation = parse_delegation(delegation)
    received = receipts.get_received(parent_packet_id)
    if received is None:
        raise ValueError('the parent packet has not been received')
    parent = received.packet
    if not isinstance(parent, Packet):
        raise ValueError('only a version 1 receipt can serve as a delegated parent')
    if grant.parent_packet_id != parent_packet_id:
        raise ValueError('the delegation names a different parent packet')
    if grant.parent_body_digest != received.receipt.body_digest:
        raise ValueError('the delegation does not bind this parent body')
    old_start, old_end = _side_positions(tuple(parent.old.words), old_bounds, grant.old, parent.old)
    new_start, new_end = _side_positions(tuple(parent.new.words), new_bounds, grant.new, parent.new)
    child_old_words, child_new_words = parent.old.words[old_start:old_end + 1], parent.new.words[new_start:new_end + 1]
    if len(child_old_words) == len(parent.old.words) and len(child_new_words) == len(parent.new.words):
        raise ValueError('a delegated packet must narrow at least one side')
    if packet_id is None:
        packet_id = uuid4().hex
    require_identifier(packet_id)
    if packet_id == parent_packet_id:
        raise ValueError('a delegated packet needs its own packet identifier')
    old = PublishedExcerpt(
        ExcerptIdentity(parent.old.identity.manuscript_id, parent.old.identity.revision_id,
                        f'{packet_id}:old', parent.old.identity.permission_id),
        child_old_words,
    )
    new = PublishedExcerpt(
        ExcerptIdentity(parent.new.identity.manuscript_id, parent.new.identity.revision_id,
                        f'{packet_id}:new', parent.new.identity.permission_id),
        child_new_words,
    )
    evidence = build_delegated_evidence(
        tuple(word.value for word in parent.old.words), tuple(word.value for word in parent.new.words),
        old, new, old_start, new_start,
    )
    packet = DelegatedPacket(packet_id, parent_packet_id, grant.parent_body_digest,
                             grant.delegation_id, grant.digest, old, new, evidence)
    return seal_delegated_packet(packet)
