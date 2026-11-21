from dataclasses import dataclass

from issue.packet import Packet, PacketProvenance, PacketWord
from review.confirmations import BoundConfirmation, Confirmation
from review.requests import BoundRequest, OldAnnotation
from review.resolve import OptimalAlignment, possible_landings


@dataclass(frozen=True)
class AnnotationOutcome:
    annotation_id: str
    old_word: PacketWord
    targets: tuple[PacketWord, ...]
    can_have_no_public_landing: bool


@dataclass(frozen=True)
class ReviewDecision:
    packet: PacketProvenance
    cost: int
    annotations: tuple[OldAnnotation, ...]
    confirmations: tuple[Confirmation, ...]
    outcomes: tuple[AnnotationOutcome, ...]


def build_review_decision(
    packet: Packet,
    body_digest: str,
    request: BoundRequest,
    confirmations: tuple[BoundConfirmation, ...],
    alignment: OptimalAlignment,
) -> ReviewDecision:
    outcomes = []
    for annotation, index in zip(request.annotations, request.old_indices, strict=True):
        targets, can_omit = possible_landings(alignment, index)
        outcomes.append(AnnotationOutcome(annotation.annotation_id, packet.old.words[index],
                                          tuple(packet.new.words[j] for j in targets), can_omit))
    provenance = PacketProvenance(request.packet_id, body_digest, packet.old.identity, packet.new.identity)
    return ReviewDecision(provenance, alignment.cost, request.annotations,
                          tuple(item.confirmation for item in confirmations), tuple(outcomes))
