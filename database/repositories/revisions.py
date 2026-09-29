"""Post revision repository implementations."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from supabase import Client

from agent.exceptions import SupabaseDatabaseError
from database.models import PostRevision
from database.repositories.base import BaseRevisionRepository


def serialize_revision_for_db(revision: PostRevision) -> Dict[str, Any]:
    """Serialize PostRevision Pydantic model for database persistence."""
    data = revision.model_dump(exclude_none=True)
    if hasattr(revision.image_brief, "model_dump"):
        data["image_brief"] = revision.image_brief.model_dump()
    return data


class InMemoryRevisionRepository(BaseRevisionRepository):
    """In-memory revision repository for offline testing and local development."""

    def __init__(self):
        self._revisions: List[PostRevision] = []

    def create(self, revision: PostRevision) -> PostRevision:
        if not revision.id:
            revision.id = str(uuid4())
        if not revision.created_at:
            revision.created_at = datetime.now()
        self._revisions.append(revision.model_copy(deep=True))
        return revision.model_copy(deep=True)

    def get_by_post_id(self, post_id: str) -> List[PostRevision]:
        matches = [r for r in self._revisions if r.post_id == post_id]
        matches.sort(key=lambda r: r.revision_number)
        return [r.model_copy(deep=True) for r in matches]

    def get_latest_revision(self, post_id: str) -> Optional[PostRevision]:
        revs = self.get_by_post_id(post_id)
        return revs[-1] if revs else None


class SupabaseRevisionRepository(BaseRevisionRepository):
    """Supabase PostgreSQL post revision repository."""

    def __init__(self, client: Client):
        self.client = client

    def create(self, revision: PostRevision) -> PostRevision:
        try:
            payload = serialize_revision_for_db(revision)
            response = self.client.table("post_revisions").insert(payload).execute()
            if response.data and len(response.data) > 0:
                return PostRevision.model_validate(response.data[0])
            raise SupabaseDatabaseError("Insert into post_revisions returned empty response.")
        except Exception as e:
            raise SupabaseDatabaseError(
                f"Failed to create revision {revision.revision_number} for post '{revision.post_id}': {e}"
            ) from e

    def get_by_post_id(self, post_id: str) -> List[PostRevision]:
        try:
            response = (
                self.client.table("post_revisions")
                .select("*")
                .eq("post_id", post_id)
                .order("revision_number", desc=False)
                .execute()
            )
            if response.data:
                return [PostRevision.model_validate(row) for row in response.data]
            return []
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch revisions for post '{post_id}': {e}") from e

    def get_latest_revision(self, post_id: str) -> Optional[PostRevision]:
        try:
            response = (
                self.client.table("post_revisions")
                .select("*")
                .eq("post_id", post_id)
                .order("revision_number", desc=True)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return PostRevision.model_validate(response.data[0])
            return None
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch latest revision for post '{post_id}': {e}") from e
