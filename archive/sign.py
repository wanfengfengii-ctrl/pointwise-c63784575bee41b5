from dataclasses import asdict
from uuid import uuid4

from archive.records import ArchiveEntry, ArchiveReceipt, Report
from archive.transactions import ArchiveStore
from issue.envelope import canonical_json
from review.results import ReviewDecision


def sign_decision(store: ArchiveStore, decision: ReviewDecision) -> ArchiveEntry:
    report = Report(uuid4().hex, decision.packet.packet_id, decision.packet.body_digest,
                    canonical_json(asdict(decision)))
    receipt = ArchiveReceipt(uuid4().hex, report.report_id, report.packet_id,
                             report.packet_digest, report.snapshot_digest)
    entry = ArchiveEntry(report, receipt)
    store.commit_signed(entry)
    return entry
