from dataclasses import dataclass

from revisions.model import Revision, require_identifier


@dataclass(frozen=True)
class PublicationPermission:
    permission_id: str
    revision_id: str
    first_word_id: str
    last_word_id: str


def require_permitted_range(
    revision: Revision,
    permission: PublicationPermission,
    first_word_id: str,
    last_word_id: str,
) -> tuple[int, int]:
    if not isinstance(permission, PublicationPermission):
        raise ValueError('publication permission is required')
    require_identifier(permission.permission_id)
    if permission.revision_id != revision.revision_id:
        raise ValueError('permission belongs to a different revision')
    positions = {word.word_id: word.ordinal for word in revision.words}
    endpoints = (permission.first_word_id, first_word_id, last_word_id, permission.last_word_id)
    for endpoint in endpoints:
        require_identifier(endpoint)
    try:
        permitted_start, start, end, permitted_end = (positions[word_id] for word_id in endpoints)
    except KeyError as exc:
        raise ValueError('every endpoint must exist in the selected revision') from exc
    if not permitted_start <= start <= end <= permitted_end:
        raise ValueError('excerpt is reversed or exceeds its publication permission')
    return start, end
