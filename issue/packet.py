from dataclasses import dataclass


@dataclass(frozen=True)
class PacketWord:
    word_id: str
    ordinal: int
    value: str
    segment_id: str
    segment_order: int
    word_index: int


@dataclass(frozen=True)
class ExcerptIdentity:
    manuscript_id: str
    revision_id: str
    excerpt_id: str
    permission_id: str


@dataclass(frozen=True)
class PublishedExcerpt:
    identity: ExcerptIdentity
    words: tuple[PacketWord, ...]


@dataclass(frozen=True)
class EvidencePayload:
    # Pairs index the old and new public word lists. Edge endpoints index
    # the graph with start at zero, pairs at one, and end after the last pair.
    nodes: tuple[tuple[int, int], ...]
    edges: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class Packet:
    packet_id: str
    old: PublishedExcerpt
    new: PublishedExcerpt
    evidence: EvidencePayload


@dataclass(frozen=True)
class PacketProvenance:
    packet_id: str
    body_digest: str
    old: ExcerptIdentity
    new: ExcerptIdentity


def public_matches(old: PublishedExcerpt, new: PublishedExcerpt) -> tuple[tuple[int, int], ...]:
    new_positions: dict[str, list[int]] = {}
    for index, word in enumerate(new.words):
        new_positions.setdefault(word.value, []).append(index)
    return tuple((i, j) for i, word in enumerate(old.words) for j in new_positions.get(word.value, ()))


def ordered_arcs(positions: tuple[tuple[int, int], ...]):
    for source, (old_start, new_start) in enumerate(positions[:-1]):
        for target in range(source + 1, len(positions)):
            old_end, new_end = positions[target]
            if old_start < old_end and new_start < new_end:
                yield source, target
