"""Validation and digesting for desk delegations delivered by trusted means."""
import hashlib
import re
from dataclasses import dataclass

from issue.envelope import canonical_json
from revisions.model import require_identifier

_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_SIDE_KEYS = {'revision_id', 'first_word_id', 'last_word_id'}
_DELEGATION_KEYS = {'delegation_id', 'parent_packet_id', 'parent_body_digest', 'old', 'new'}


@dataclass(frozen=True)
class DelegatedSide:
    revision_id: str
    first_word_id: str
    last_word_id: str
    first_ordinal: int
    last_ordinal: int


@dataclass(frozen=True)
class Delegation:
    delegation_id: str
    parent_packet_id: str
    parent_body_digest: str
    old: DelegatedSide
    new: DelegatedSide
    digest: str


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('a delegation identifier must be a nonblank string')
    value.encode('utf-8')
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError('a delegation digest must be 64 lowercase hexadecimal characters')
    return value


def _ordinal(word_id: str, revision_id: str) -> int:
    prefix = revision_id + ':'
    if not word_id.startswith(prefix):
        raise ValueError('a delegated word identifier must belong to its revision')
    digits = word_id[len(prefix):]
    if not digits.isascii() or not digits.isdigit() or (len(digits) > 1 and digits.startswith('0')):
        raise ValueError('a delegated word identifier must name a manuscript word position')
    return int(digits)


def _side(value: object) -> DelegatedSide:
    if type(value) is not dict or value.keys() != _SIDE_KEYS:
        raise ValueError('a delegated side must have exactly its three fields')
    revision_id = _text(value['revision_id'])
    first_word_id = _text(value['first_word_id'])
    last_word_id = _text(value['last_word_id'])
    first_ordinal = _ordinal(first_word_id, revision_id)
    last_ordinal = _ordinal(last_word_id, revision_id)
    if first_ordinal > last_ordinal:
        raise ValueError('a delegated range must follow the original word order')
    return DelegatedSide(revision_id, first_word_id, last_word_id, first_ordinal, last_ordinal)


def _normalized(delegation_id, parent_packet_id, parent_body_digest, old, new) -> dict:
    return {
        'delegation_id': delegation_id,
        'parent_packet_id': parent_packet_id,
        'parent_body_digest': parent_body_digest,
        'old': {'revision_id': old.revision_id, 'first_word_id': old.first_word_id,
                'last_word_id': old.last_word_id},
        'new': {'revision_id': new.revision_id, 'first_word_id': new.first_word_id,
                'last_word_id': new.last_word_id},
    }


def parse_delegation(value: object) -> Delegation:
    if type(value) is not dict or value.keys() != _DELEGATION_KEYS:
        raise ValueError('a delegation must have exactly its five fields')
    delegation_id = _text(value['delegation_id'])
    parent_packet_id = _text(value['parent_packet_id'])
    parent_body_digest = _digest(value['parent_body_digest'])
    old, new = _side(value['old']), _side(value['new'])
    if old.revision_id == new.revision_id:
        raise ValueError('a delegation must order two distinct revisions')
    normalized = _normalized(delegation_id, parent_packet_id, parent_body_digest, old, new)
    digest = hashlib.sha256(canonical_json(normalized).encode('utf-8')).hexdigest()
    return Delegation(delegation_id, parent_packet_id, parent_body_digest, old, new, digest)
