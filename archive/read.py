from archive.audit import verify_archived_entry
from archive.records import ArchiveEntry
from archive.transactions import ArchiveStore


def read_report(store: ArchiveStore, report_id: str) -> ArchiveEntry | None:
    entry = store.get_signed(report_id)
    if entry is not None:
        verify_archived_entry(entry)
    return entry
