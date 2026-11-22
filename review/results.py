from dataclasses import dataclass

from issue.packet import DelegatedPacket, Packet, PacketProvenance, PacketWord
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
    delegation: dict | None = None


def build_review_decision(
    packet: Packet | DelegatedPacket,
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
    delegation = None
    if isinstance(packet, DelegatedPacket):
        delegation = {
            'parent_packet_id': packet.parent_packet_id,
            'parent_body_digest': packet.parent_body_digest,
            'delegation_id': packet.delegation_id,
            'delegation_digest': packet.delegation_digest,
        }
    return ReviewDecision(provenance, alignment.cost, request.annotations,
                          tuple(item.confirmation for item in confirmations), tuple(outcomes),
                          delegation)
