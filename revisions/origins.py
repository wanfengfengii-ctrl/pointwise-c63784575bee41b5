from collections.abc import Sequence

from revisions.model import SourceOrigin, SourceSegment, require_identifier


def validate_segment_order(segments: Sequence[SourceSegment]) -> None:
    previous = -1
    used = set()
    for segment in segments:
        if not isinstance(segment, SourceSegment):
            raise ValueError('a revision must contain source segments')
        require_identifier(segment.segment_id)
        if segment.segment_id in used:
            raise ValueError('duplicate source segment identifier')
        if type(segment.order) is not int or segment.order <= previous:
            raise ValueError('source segment orders must strictly increase from zero or higher')
        used.add(segment.segment_id)
        previous = segment.order


def make_source_origin(segment: SourceSegment, word_index: int) -> SourceOrigin:
    return SourceOrigin(segment.segment_id, segment.order, word_index)
