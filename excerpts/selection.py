from excerpts.policy import PublicationPermission, require_permitted_range
from excerpts.projection import Excerpt, project_excerpt
from excerpts.store import ExcerptStore
from revisions.model import require_identifier
from revisions.store import RevisionStore


def select_excerpt(
    revisions: RevisionStore,
    excerpts: ExcerptStore,
    excerpt_id: str,
    revision_id: str,
    permission: PublicationPermission,
    first_word_id: str,
    last_word_id: str,
) -> Excerpt:
    require_identifier(excerpt_id)
    require_identifier(revision_id)
    revision = revisions.get(revision_id)
    if revision is None:
        raise ValueError('unknown revision')
    bounds = require_permitted_range(revision, permission, first_word_id, last_word_id)
    excerpt = project_excerpt(excerpt_id, revision, permission, bounds)
    excerpts.insert(excerpt, permission)
    return excerpt
