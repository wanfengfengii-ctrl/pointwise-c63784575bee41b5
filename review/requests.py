from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from issue.packet import Packet

if TYPE_CHECKING:
    from review.confirmations import Confirmation


@dataclass(frozen=True)
class OldAnnotation:
    annotation_id: str
    word_id: str


@dataclass(frozen=True)
class ReviewRequest:
    packet_id: str
    annotations: tuple[OldAnnotation, ...]
    confirmations: tuple[Confirmation, ...] = ()


@dataclass(frozen=True)
class BoundRequest:
    packet_id: str
    annotations: tuple[OldAnnotation, ...]
    old_indices: tuple[int, ...]


def bind_request(packet: Packet, request: ReviewRequest) -> BoundRequest:
    if request.packet_id != packet.packet_id:
        raise ValueError('request names a different packet')
    if not isinstance(request.annotations, (tuple, list)) or not request.annotations:
        raise ValueError('at least one old annotation is required')
    lookup = {word.word_id: i for i, word in enumerate(packet.old.words)}
    used = set()
    indices = []
    annotations = tuple(request.annotations)
    for annotation in annotations:
        if not isinstance(annotation, OldAnnotation) or not isinstance(annotation.annotation_id, str) or not annotation.annotation_id.strip():
            raise ValueError('old annotation must have an identifier')
        if annotation.annotation_id in used:
            raise ValueError('duplicate annotation identifier')
        if not isinstance(annotation.word_id, str) or annotation.word_id not in lookup:
            raise ValueError('old annotation does not refer to this packet’s public old side')
        used.add(annotation.annotation_id)
        indices.append(lookup[annotation.word_id])
    return BoundRequest(packet.packet_id, annotations, tuple(indices))
