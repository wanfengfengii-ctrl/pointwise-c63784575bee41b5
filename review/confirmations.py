from dataclasses import dataclass

from issue.packet import Packet


@dataclass(frozen=True)
class Confirmation:
    old_word_id: str
    new_word_id: str


@dataclass(frozen=True)
class BoundConfirmation:
    confirmation: Confirmation
    pair: tuple[int, int]


def bind_confirmations(
    packet: Packet,
    confirmations: tuple[Confirmation, ...] | list[Confirmation],
) -> tuple[BoundConfirmation, ...]:
    if not isinstance(confirmations, (tuple, list)):
        raise ValueError('confirmations must be a sequence, which may be empty')
    old = {word.word_id: i for i, word in enumerate(packet.old.words)}
    new = {word.word_id: i for i, word in enumerate(packet.new.words)}
    by_pair = {}
    for confirmation in confirmations:
        if not isinstance(confirmation, Confirmation):
            raise ValueError('expected a confirmation with two public word identifiers')
        old_id, new_id = confirmation.old_word_id, confirmation.new_word_id
        if not isinstance(old_id, str) or not isinstance(new_id, str) or old_id not in old or new_id not in new:
            raise ValueError('confirmation does not refer to this packet’s public sides')
        by_pair[old[old_id], new[new_id]] = confirmation
    return tuple(BoundConfirmation(by_pair[pair], pair) for pair in sorted(by_pair))
