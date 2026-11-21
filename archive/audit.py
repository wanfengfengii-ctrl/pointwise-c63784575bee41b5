from archive.records import ArchiveEntry


def verify_archived_entry(entry: ArchiveEntry) -> None:
    report, receipt = entry.report, entry.receipt
    if (receipt.report_id, receipt.packet_id, receipt.packet_digest) != (report.report_id, report.packet_id, report.packet_digest):
        raise ValueError('archive receipt does not bind the stored report and packet')
    if receipt.report_digest != report.snapshot_digest:
        raise ValueError('stored report snapshot does not match its receipt')
    details = report.details
    provenance = details.get('packet') if isinstance(details, dict) else None
    if not isinstance(provenance, dict) or (provenance.get('packet_id'), provenance.get('body_digest')) != (report.packet_id, report.packet_digest):
        raise ValueError('stored snapshot does not bind the recorded packet')
