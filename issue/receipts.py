import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from issue.delegation import Delegation, parse_delegation
from issue.envelope import EnvelopeMismatch, open_envelope, packet_digest
from issue.packet import DelegatedPacket, Packet


@dataclass(frozen=True)
class PacketReceipt:
    receipt_id: str
    packet_id: str
    body_digest: str


@dataclass(frozen=True)
class ReceivedPacket:
    packet: Packet | DelegatedPacket
    envelope: str
    receipt: PacketReceipt


def _bind_delegation(packet: DelegatedPacket, delegation: object) -> None:
    if delegation is None:
        raise EnvelopeMismatch('a delegated packet requires its desk delegation')
    try:
        grant: Delegation = parse_delegation(delegation)
    except ValueError as exc:
        raise EnvelopeMismatch('malformed desk delegation') from exc
    if (grant.delegation_id, grant.digest) != (packet.delegation_id, packet.delegation_digest):
        raise EnvelopeMismatch('the delegation identity does not match the delegated packet')
    if (grant.parent_packet_id, grant.parent_body_digest) != (packet.parent_packet_id, packet.parent_body_digest):
        raise EnvelopeMismatch('the delegation names a different parent packet or body')
    for side, authorized in ((packet.old, grant.old), (packet.new, grant.new)):
        if side.identity.revision_id != authorized.revision_id:
            raise EnvelopeMismatch('the delegation orders different revisions than the packet')
        first, last = side.words[0].ordinal, side.words[-1].ordinal
        if not authorized.first_ordinal <= first <= last <= authorized.last_ordinal:
            raise EnvelopeMismatch('the delegated slice lies outside the authorized range')


class ReceiptStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''CREATE TABLE IF NOT EXISTS received_packets (
            packet_id TEXT PRIMARY KEY NOT NULL,
            envelope TEXT NOT NULL,
            receipt_id TEXT UNIQUE NOT NULL,
            body_digest TEXT NOT NULL
        )''')

    def accept(self, envelope: str, *, delegation: object = None) -> PacketReceipt:
        packet = open_envelope(envelope)
        if isinstance(packet, DelegatedPacket):
            _bind_delegation(packet, delegation)
        elif delegation is not None:
            raise EnvelopeMismatch('a version 1 packet does not take a desk delegation')
        digest = packet_digest(packet)
        db = self.connection
        db.execute('BEGIN IMMEDIATE')
        with db:
            prior = self.get_received(packet.packet_id)
            if prior is not None:
                if packet != prior.packet:
                    raise EnvelopeMismatch('packet identifier already names a different body')
                receipt = prior.receipt
            else:
                receipt = PacketReceipt(uuid4().hex, packet.packet_id, digest)
                db.execute('INSERT INTO received_packets VALUES (?, ?, ?, ?)',
                           (receipt.packet_id, envelope, receipt.receipt_id, digest))
        return receipt

    def get_received(self, packet_id: str) -> ReceivedPacket | None:
        row = self.connection.execute('''SELECT envelope, receipt_id, body_digest
            FROM received_packets WHERE packet_id = ?''', (packet_id,)).fetchone()
        if row is None:
            return None
        envelope, receipt_id, digest = row
        packet = open_envelope(envelope)
        if packet.packet_id != packet_id or packet_digest(packet) != digest:
            raise EnvelopeMismatch('stored receipt disagrees with the packet')
        return ReceivedPacket(packet, envelope, PacketReceipt(receipt_id, packet_id, digest))
