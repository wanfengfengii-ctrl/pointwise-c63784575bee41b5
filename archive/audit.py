import re

from archive.records import ArchiveEntry

_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_DELEGATION_FIELDS = {'parent_packet_id', 'parent_body_digest', 'delegation_id', 'delegation_digest'}


def _verify_delegation(details: dict, report) -> None:
    delegation = details.get('delegation')
    if delegation is None:
        return
    if not isinstance(delegation, dict) or set(delegation) != _DELEGATION_FIELDS:
        raise ValueError('stored snapshot has a malformed delegation binding')
    for field in ('parent_packet_id', 'delegation_id'):
        if not isinstance(delegation[field], str) or not delegation[field].strip():
            raise ValueError('stored snapshot does not name its parent packet and delegation')
    for field in ('parent_body_digest', 'delegation_digest'):
        if not isinstance(delegation[field], str) or _DIGEST.fullmatch(delegation[field]) is None:
            raise ValueError('stored snapshot has an invalid delegation digest')
    if delegation['parent_packet_id'] == report.packet_id:
        raise ValueError('a delegated report cannot name itself as its parent packet')


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
    _verify_delegation(details, report)
