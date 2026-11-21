import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Report:
    report_id: str
    packet_id: str
    packet_digest: str
    snapshot: str

    @property
    def details(self) -> dict:
        return json.loads(self.snapshot)

    @property
    def snapshot_digest(self) -> str:
        return hashlib.sha256(self.snapshot.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ArchiveReceipt:
    receipt_id: str
    report_id: str
    packet_id: str
    packet_digest: str
    report_digest: str


@dataclass(frozen=True)
class ArchiveEntry:
    report: Report
    receipt: ArchiveReceipt
