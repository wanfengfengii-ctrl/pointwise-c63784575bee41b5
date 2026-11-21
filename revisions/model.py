from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSegment:
    segment_id: str
    order: int
    words: tuple[str, ...]


@dataclass(frozen=True)
class SourceOrigin:
    segment_id: str
    segment_order: int
    word_index: int


@dataclass(frozen=True)
class WordOccurrence:
    word_id: str
    ordinal: int
    value: str
    origin: SourceOrigin


@dataclass(frozen=True)
class Revision:
    manuscript_id: str
    revision_id: str
    segments: tuple[SourceSegment, ...]
    words: tuple[WordOccurrence, ...]


def require_identifier(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('an identifier must be a nonblank string')
    value.encode('utf-8')


def make_word_id(revision_id: str, ordinal: int) -> str:
    return f'{revision_id}:{ordinal}'
