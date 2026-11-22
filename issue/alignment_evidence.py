from issue.packet import EvidencePayload, PublishedExcerpt, ordered_arcs, public_matches
from revisions.model import Revision


def _gap_matches(
    old: tuple[str, ...],
    new: tuple[str, ...],
    old_start: int,
    new_start: int,
    old_public: set[int],
    new_public: set[int],
) -> list[list[int]]:
    """Maximum other matches for every prefix after one graph node."""
    width = len(new) - new_start
    best = [[0] * width]
    for i in range(old_start + 1, len(old)):
        previous = best[-1]
        row = [0] * width
        for j in range(new_start + 1, len(new)):
            column = j - new_start
            score = max(previous[column], row[column - 1])
            if old[i] == new[j] and not (i in old_public and j in new_public):
                score = max(score, previous[column - 1] + 1)
            row[column] = score
        best.append(row)
    return best


def build_evidence(
    old: tuple[str, ...],
    new: tuple[str, ...],
    old_public: set[int],
    new_public: set[int],
    node_positions: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int, int], ...]:
    """Gap costs between ordered public node positions over two word runs.

    Positions are coordinates in the full runs, with the path starting before
    both runs and ending after them. Public coordinate pairs never count as
    hidden matches; every other equal-value pair may contribute.
    """
    positions = ((-1, -1),) + tuple(node_positions) + ((len(old), len(new)),)
    edges = []
    last_source = None
    best = None
    for source, target in ordered_arcs(positions):
        i, j = positions[source]
        if source != last_source:
            best = _gap_matches(old, new, i, j, old_public, new_public)
            last_source = source
        end_i, end_j = positions[target]
        rows, cols = end_i - i - 1, end_j - j - 1
        gap_cost = rows + cols - 2 * best[rows][cols]
        edges.append((source, target, gap_cost))
    return tuple(edges)


def build_alignment_evidence(
    old_revision: Revision,
    new_revision: Revision,
    old_excerpt: PublishedExcerpt,
    new_excerpt: PublishedExcerpt,
) -> EvidencePayload:
    old = tuple(word.value for word in old_revision.words)
    new = tuple(word.value for word in new_revision.words)
    old_ordinals = tuple(word.ordinal for word in old_excerpt.words)
    new_ordinals = tuple(word.ordinal for word in new_excerpt.words)
    old_public, new_public = set(old_ordinals), set(new_ordinals)
    nodes = public_matches(old_excerpt, new_excerpt)
    positions = tuple((old_ordinals[i], new_ordinals[j]) for i, j in nodes)
    return EvidencePayload(nodes, build_evidence(old, new, old_public, new_public, positions))


def build_delegated_evidence(
    old_words: tuple[str, ...],
    new_words: tuple[str, ...],
    child_old: PublishedExcerpt,
    child_new: PublishedExcerpt,
    old_offset: int,
    new_offset: int,
) -> EvidencePayload:
    """Evidence for a narrowed slice inside an already published parent fragment.

    Graph coordinates stay relative to the delivered child slices so reviewers
    can read the packet alone. Costs are computed over the full parent fragment,
    letting words left on the holder side still contribute through gap costs.
    Public word pairs never count as hidden matches; a public word on one side
    may still match an undelivered word on the other.
    """
    nodes = public_matches(child_old, child_new)
    old_public = set(range(old_offset, old_offset + len(child_old.words)))
    new_public = set(range(new_offset, new_offset + len(child_new.words)))
    graph_positions = ((-1, -1),) + nodes + ((len(child_old.words), len(child_new.words)),)
    source_positions = ((-1, -1),) + tuple(
        (old_offset + i, new_offset + j) for i, j in nodes
    ) + ((len(old_words), len(new_words)),)
    edges = []
    last_source = None
    best = None
    for source, target in ordered_arcs(graph_positions):
        i, j = source_positions[source]
        if source != last_source:
            best = _gap_matches(old_words, new_words, i, j, old_public, new_public)
            last_source = source
        end_i, end_j = source_positions[target]
        rows, cols = end_i - i - 1, end_j - j - 1
        edges.append((source, target, rows + cols - 2 * best[rows][cols]))
    return EvidencePayload(nodes, tuple(edges))
