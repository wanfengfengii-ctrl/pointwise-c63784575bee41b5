import sqlite3
from dataclasses import dataclass
from uuid import uuid4

from issue.envelope import EnvelopeMismatch, open_envelope, packet_digest
from issue.packet import Packet


@dataclass(frozen=True)
class PacketReceipt:
    receipt_id: str
    packet_id: str
    body_digest: str


@dataclass(frozen=True)
class ReceivedPacket:
    packet: Packet
    envelope: str
    receipt: PacketReceipt


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

    def accept(self, envelope: str) -> PacketReceipt:
        packet = open_envelope(envelope)
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
