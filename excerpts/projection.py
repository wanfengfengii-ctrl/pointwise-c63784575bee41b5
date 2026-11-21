from dataclasses import dataclass

from excerpts.policy import PublicationPermission
from revisions.model import Revision, SourceOrigin


@dataclass(frozen=True)
class PublicWord:
    word_id: str
    ordinal: int
    value: str
    origin: SourceOrigin


@dataclass(frozen=True)
class Excerpt:
    excerpt_id: str
    revision_id: str
    permission_id: str
    words: tuple[PublicWord, ...]


def project_excerpt(
    excerpt_id: str,
    revision: Revision,
    permission: PublicationPermission,
    bounds: tuple[int, int],
) -> Excerpt:
    start, end = bounds
    return Excerpt(excerpt_id, revision.revision_id, permission.permission_id, tuple(
        PublicWord(word.word_id, word.ordinal, word.value, word.origin)
        for word in revision.words[start:end + 1]
    ))
