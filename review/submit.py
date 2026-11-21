from archive.records import ArchiveEntry
from archive.sign import sign_decision
from archive.transactions import ArchiveStore
from issue.receipts import ReceiptStore
from review.confirmations import bind_confirmations
from review.requests import ReviewRequest, bind_request
from review.resolve import resolve_alignment
from review.results import build_review_decision


def submit_review(receipts: ReceiptStore, archive: ArchiveStore, request: ReviewRequest) -> ArchiveEntry:
    if not isinstance(request, ReviewRequest) or not isinstance(request.packet_id, str) or not request.packet_id.strip():
        raise ValueError('review requires a packet identifier')
    received = receipts.get_received(request.packet_id)
    if received is None:
        raise ValueError('packet has not been received')
    packet = received.packet
    bound = bind_request(packet, request)
    confirmations = bind_confirmations(packet, request.confirmations)
    alignment = resolve_alignment(packet.evidence, confirmations)
    decision = build_review_decision(packet, received.receipt.body_digest, bound, confirmations, alignment)
    return sign_decision(archive, decision)
