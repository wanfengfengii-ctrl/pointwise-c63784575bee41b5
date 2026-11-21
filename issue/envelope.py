import hashlib
import hmac
import json
from dataclasses import asdict

from issue.packet import (
    EvidencePayload, ExcerptIdentity, Packet, PacketWord, PublishedExcerpt,
    ordered_arcs, public_matches,
)


class EnvelopeMismatch(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _digest(body: str) -> str:
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def packet_digest(packet: Packet) -> str:
    return _digest(canonical_json(asdict(packet)))


def _declaration(packet: Packet) -> dict:
    return {'packet_id': packet.packet_id, 'old': asdict(packet.old.identity), 'new': asdict(packet.new.identity)}


def seal_packet(packet: Packet) -> str:
    body = canonical_json(asdict(packet))
    return canonical_json({'version': 1, 'declaration': _declaration(packet), 'body': body, 'sha256': _digest(body)})


def _fields(value: object, *keys: str) -> None:
    if type(value) is not dict or value.keys() != set(keys):
        raise EnvelopeMismatch('unexpected packet fields')


def _text(value: object, *, identifier: bool = True) -> None:
    if not isinstance(value, str) or not (value.strip() if identifier else value):
        raise EnvelopeMismatch('expected nonempty packet text')
    value.encode('utf-8')


def _read_excerpt(data: dict) -> PublishedExcerpt:
    _fields(data, 'identity', 'words')
    identity = data['identity']
    _fields(identity, 'manuscript_id', 'revision_id', 'excerpt_id', 'permission_id')
    for value in identity.values():
        _text(value)
    raw_words = data['words']
    if type(raw_words) is not list or not raw_words:
        raise EnvelopeMismatch('expected a nonempty excerpt')
    words = []
    for word in raw_words:
        _fields(word, 'word_id', 'ordinal', 'value', 'segment_id', 'segment_order', 'word_index')
        _text(word['word_id'])
        _text(word['value'], identifier=False)
        _text(word['segment_id'])
        if any(type(word[key]) is not int or word[key] < 0 for key in ('ordinal', 'segment_order', 'word_index')):
            raise EnvelopeMismatch('invalid public word position')
        parsed = PacketWord(**word)
        if parsed.word_id != f'{identity["revision_id"]}:{parsed.ordinal}':
            raise EnvelopeMismatch('public word identifier does not name this revision and position')
        if words:
            prior = words[-1]
            if parsed.ordinal != prior.ordinal + 1:
                raise EnvelopeMismatch('excerpt positions are not contiguous')
            if parsed.segment_order == prior.segment_order:
                if parsed.segment_id != prior.segment_id or parsed.word_index != prior.word_index + 1:
                    raise EnvelopeMismatch('invalid within-segment provenance')
            elif parsed.segment_order < prior.segment_order or parsed.word_index != 0 or parsed.segment_id == prior.segment_id:
                raise EnvelopeMismatch('invalid segment transition')
        words.append(parsed)
    return PublishedExcerpt(ExcerptIdentity(**identity), tuple(words))


def _integer_rows(rows: object, width: int) -> tuple:
    if type(rows) is not list:
        raise EnvelopeMismatch('invalid evidence rows')
    if any(type(row) is not list or len(row) != width or
           any(type(value) is not int or value < 0 for value in row) for row in rows):
        raise EnvelopeMismatch('invalid evidence coordinate or cost')
    return tuple(tuple(row) for row in rows)


def _read_evidence(data: dict, old: PublishedExcerpt, new: PublishedExcerpt) -> EvidencePayload:
    _fields(data, 'nodes', 'edges')
    nodes = _integer_rows(data['nodes'], 2)
    if nodes != public_matches(old, new):
        raise EnvelopeMismatch('evidence nodes do not identify the public matches')
    edges = _integer_rows(data['edges'], 3)
    positions = ((-1, -1),) + nodes + ((len(old.words), len(new.words)),)
    for edge, expected in zip(edges, ordered_arcs(positions), strict=True):
        if edge[:2] != expected:
            raise EnvelopeMismatch('invalid evidence edge order or endpoints')
    return EvidencePayload(nodes, edges)


def _read_packet(data: dict) -> Packet:
    _fields(data, 'packet_id', 'old', 'new', 'evidence')
    _text(data['packet_id'])
    old, new = _read_excerpt(data['old']), _read_excerpt(data['new'])
    if old.identity.manuscript_id != new.identity.manuscript_id:
        raise EnvelopeMismatch('packet sides name different manuscripts')
    if old.identity.revision_id == new.identity.revision_id or old.identity.excerpt_id == new.identity.excerpt_id:
        raise EnvelopeMismatch('packet requires two distinct revisions and excerpts')
    return Packet(data['packet_id'], old, new, _read_evidence(data['evidence'], old, new))


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise EnvelopeMismatch('duplicate JSON object key')
    return result


def open_envelope(envelope: str) -> Packet:
    try:
        if not isinstance(envelope, str):
            raise EnvelopeMismatch('envelope must be JSON text')
        outer = json.loads(envelope, object_pairs_hook=_unique_json_object)
        _fields(outer, 'version', 'declaration', 'body', 'sha256')
        if type(outer['version']) is not int or outer['version'] != 1:
            raise EnvelopeMismatch('unsupported envelope version')
        body, digest = outer['body'], outer['sha256']
        if not isinstance(body, str) or not isinstance(digest, str) or not digest.isascii():
            raise EnvelopeMismatch('missing packet body or digest')
        if not hmac.compare_digest(_digest(body), digest):
            raise EnvelopeMismatch('packet body digest does not match')
        packet = _read_packet(json.loads(body))
        if body != canonical_json(asdict(packet)):
            raise EnvelopeMismatch('packet body is not in canonical form')
        if outer['declaration'] != _declaration(packet):
            raise EnvelopeMismatch('packet declaration does not match its body')
        return packet
    except EnvelopeMismatch:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise EnvelopeMismatch('malformed packet envelope') from exc
