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
    positions = ((-1, -1),) + tuple((old_ordinals[i], new_ordinals[j]) for i, j in nodes) + ((len(old), len(new)),)
    edges = []
    last_source = None
    for source, target in ordered_arcs(positions):
        i, j = positions[source]
        if source != last_source:
            best = _gap_matches(old, new, i, j, old_public, new_public)
            last_source = source
        end_i, end_j = positions[target]
        rows, cols = end_i - i - 1, end_j - j - 1
        gap_cost = rows + cols - 2 * best[rows][cols]
        edges.append((source, target, gap_cost))
    return EvidencePayload(nodes, tuple(edges))
