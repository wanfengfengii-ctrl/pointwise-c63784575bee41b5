from collections.abc import Sequence

from revisions.model import SourceSegment, WordOccurrence, make_word_id
from revisions.origins import make_source_origin


def index_words(revision_id: str, segments: Sequence[SourceSegment]) -> tuple[WordOccurrence, ...]:
    indexed = []
    for segment in segments:
        if not isinstance(segment.words, (tuple, list)):
            raise ValueError('a segment must supply a sequence of word values')
        for word_index, value in enumerate(segment.words):
            if not isinstance(value, str) or not value:
                raise ValueError('a word value must be a nonempty string')
            value.encode('utf-8')
            ordinal = len(indexed)
            indexed.append(WordOccurrence(
                make_word_id(revision_id, ordinal), ordinal, value,
                make_source_origin(segment, word_index),
            ))
    return tuple(indexed)
