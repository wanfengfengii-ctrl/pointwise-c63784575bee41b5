from bisect import bisect_right
from dataclasses import dataclass

from issue.packet import EvidencePayload
from review.confirmations import BoundConfirmation


class NoCompatibleAlignment(ValueError):
    pass


@dataclass(frozen=True)
class OptimalAlignment:
    cost: int
    nodes: tuple[tuple[int, int], ...]
    optimal_edges: tuple[tuple[int, int], ...]


def _shortest_distances(edges: tuple, start: int, *, reverse: bool = False) -> dict[int, int]:
    distances = {start: 0}
    if reverse:
        traversal = ((target, source, weight) for source, target, weight in reversed(edges))
    else:
        traversal = iter(edges)
    for source, target, weight in traversal:
        if source not in distances:
            continue
        candidate = distances[source] + weight
        if target not in distances or candidate < distances[target]:
            distances[target] = candidate
    return distances


def resolve_alignment(evidence: EvidencePayload, confirmations: tuple[BoundConfirmation, ...]) -> OptimalAlignment:
    end = len(evidence.nodes) + 1
    indices = {pair: index for index, pair in enumerate(evidence.nodes, start=1)}
    try:
        mandatory = sorted({indices[item.pair] for item in confirmations}) + [end]
    except KeyError as exc:
        raise NoCompatibleAlignment('a confirmed word pair cannot match') from exc

    # Every path increases in node order. Removing edges that jump past a
    # mandatory node forces a path to visit all the mandatory nodes.
    allowed = tuple((source, target, weight) for source, target, weight in evidence.edges
                    if target <= mandatory[bisect_right(mandatory, source)])
    forward = _shortest_distances(allowed, 0)
    if end not in forward:
        raise NoCompatibleAlignment('the confirmations cannot coexist in a complete alignment')
    backward = _shortest_distances(allowed, end, reverse=True)
    cost = forward[end]
    optimal_edges = tuple((source, target) for source, target, weight in allowed
                          if source in forward and target in backward
                          and forward[source] + weight + backward[target] == cost)
    return OptimalAlignment(cost, evidence.nodes, optimal_edges)


def possible_landings(alignment: OptimalAlignment, old_index: int) -> tuple[tuple[int, ...], bool]:
    matching_nodes = {node: new for node, (old, new) in enumerate(alignment.nodes, 1) if old == old_index}
    landings = set()
    reachable_without_match = {0}
    for source, target in alignment.optimal_edges:
        if target in matching_nodes:
            landings.add(matching_nodes[target])
        elif source in reachable_without_match:
            reachable_without_match.add(target)
    return tuple(sorted(landings)), len(alignment.nodes) + 1 in reachable_without_match
