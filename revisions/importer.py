from collections.abc import Sequence

from revisions.model import Revision, SourceSegment, require_identifier
from revisions.origins import validate_segment_order
from revisions.store import RevisionStore
from revisions.tokenize import index_words


def import_revision(
    store: RevisionStore,
    manuscript_id: str,
    revision_id: str,
    segments: Sequence[SourceSegment],
) -> Revision:
    require_identifier(manuscript_id)
    require_identifier(revision_id)
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise ValueError('a revision must supply a sequence of segments')
    segments = tuple(segments)
    validate_segment_order(segments)
    copied = []
    for segment in segments:
        if not isinstance(segment.words, (tuple, list)):
            raise ValueError('a segment must supply a sequence of word values')
        copied.append(SourceSegment(segment.segment_id, segment.order, tuple(segment.words)))
    frozen_segments = tuple(copied)
    revision = Revision(manuscript_id, revision_id, frozen_segments, index_words(revision_id, frozen_segments))
    store.insert(revision)
    return revision
