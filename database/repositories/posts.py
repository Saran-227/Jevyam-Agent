"""Post repository implementations."""

from datetime import datetime
import re
from typing import Any, Dict, List, Optional
from uuid import uuid4
from supabase import Client

from agent.exceptions import (
    PostNotFoundError,
    SupabaseDatabaseError,
)
from database.models import (
    Post,
    PostStatus,
    validate_status_transition,
)
from database.repositories.base import BasePostRepository


def serialize_post_for_db(post: Post) -> Dict[str, Any]:
    """Serialize Post Pydantic model into a clean dictionary suitable for Supabase."""
    data = post.model_dump(exclude_none=True)
    if isinstance(data.get("status"), PostStatus):
        data["status"] = data["status"].value
    if hasattr(post.status, "value"):
        data["status"] = post.status.value
    if hasattr(post.linkedin_target, "value"):
        data["linkedin_target"] = post.linkedin_target.value
    if hasattr(post.image_brief, "model_dump"):
        data["image_brief"] = post.image_brief.model_dump()
    return data


class InMemoryPostRepository(BasePostRepository):
    """In-memory post repository for offline testing and local development."""

    def __init__(self):
        self._posts: Dict[str, Post] = {}

    def create(self, post: Post) -> Post:
        if not post.id:
            post.id = str(uuid4())
        now = datetime.now()
        if not post.created_at:
            post.created_at = now
        post.updated_at = now
        self._posts[post.post_id] = post.model_copy(deep=True)
        return self._posts[post.post_id]

    def get_by_post_id(self, post_id: str) -> Optional[Post]:
        post = self._posts.get(post_id)
        return post.model_copy(deep=True) if post else None

    def update(self, post: Post) -> Post:
        if post.post_id not in self._posts:
            raise PostNotFoundError(f"Post with post_id '{post.post_id}' does not exist.")
        post.updated_at = datetime.now()
        self._posts[post.post_id] = post.model_copy(deep=True)
        return self._posts[post.post_id]

    def update_status(self, post_id: str, new_status: PostStatus) -> Post:
        post = self.get_by_post_id(post_id)
        if not post:
            raise PostNotFoundError(f"Post with post_id '{post_id}' does not exist.")

        # Validate lifecycle transition rules
        validate_status_transition(post.status, new_status)

        post.status = new_status
        now = datetime.now()
        post.updated_at = now
        if new_status == PostStatus.APPROVED:
            post.approved_at = now
        elif new_status == PostStatus.PUBLISHED:
            post.published_at = now

        return self.update(post)

    def get_previous_posts(self, limit: int = 50) -> List[Post]:
        posts_list = list(self._posts.values())
        # Sort by created_at descending
        posts_list.sort(
            key=lambda p: str(p.created_at) if p.created_at else "",
            reverse=True,
        )
        return [p.model_copy(deep=True) for p in posts_list[:limit]]

    def get_next_sequence_for_date(self, date_str: str) -> int:
        pattern = re.compile(rf"^JVY-{date_str}-(\d{{3}})$")
        highest = 0
        for pid in self._posts.keys():
            match = pattern.match(pid)
            if match:
                seq = int(match.group(1))
                if seq > highest:
                    highest = seq
        return highest + 1


class SupabasePostRepository(BasePostRepository):
    """Supabase PostgreSQL post repository."""

    def __init__(self, client: Client):
        self.client = client

    def create(self, post: Post) -> Post:
        try:
            payload = serialize_post_for_db(post)
            response = self.client.table("posts").insert(payload).execute()
            if response.data and len(response.data) > 0:
                return Post.model_validate(response.data[0])
            raise SupabaseDatabaseError("Post insert returned empty response.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to create post '{post.post_id}': {e}") from e

    def get_by_post_id(self, post_id: str) -> Optional[Post]:
        try:
            response = (
                self.client.table("posts")
                .select("*")
                .eq("post_id", post_id)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Post.model_validate(response.data[0])
            return None
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch post '{post_id}': {e}") from e

    def update(self, post: Post) -> Post:
        try:
            payload = serialize_post_for_db(post)
            # Remove primary id / post_id from update payload
            payload.pop("post_id", None)
            payload.pop("id", None)
            payload["updated_at"] = datetime.now().isoformat()

            response = (
                self.client.table("posts")
                .update(payload)
                .eq("post_id", post.post_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Post.model_validate(response.data[0])
            raise PostNotFoundError(f"Post with post_id '{post.post_id}' not found for update.")
        except PostNotFoundError:
            raise
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to update post '{post.post_id}': {e}") from e

    def update_status(self, post_id: str, new_status: PostStatus) -> Post:
        existing = self.get_by_post_id(post_id)
        if not existing:
            raise PostNotFoundError(f"Post with post_id '{post_id}' does not exist.")

        # Validate lifecycle transition rules
        validate_status_transition(existing.status, new_status)

        update_fields: Dict[str, Any] = {
            "status": new_status.value,
            "updated_at": datetime.now().isoformat(),
        }
        if new_status == PostStatus.APPROVED:
            update_fields["approved_at"] = datetime.now().isoformat()
        elif new_status == PostStatus.PUBLISHED:
            update_fields["published_at"] = datetime.now().isoformat()

        try:
            response = (
                self.client.table("posts")
                .update(update_fields)
                .eq("post_id", post_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Post.model_validate(response.data[0])
            raise PostNotFoundError(f"Post '{post_id}' was not updated.")
        except PostNotFoundError:
            raise
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to update status for post '{post_id}': {e}") from e

    def get_previous_posts(self, limit: int = 50) -> List[Post]:
        try:
            response = (
                self.client.table("posts")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            if response.data:
                return [Post.model_validate(row) for row in response.data]
            return []
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch previous posts: {e}") from e

    def get_next_sequence_for_date(self, date_str: str) -> int:
        try:
            prefix = f"JVY-{date_str}-"
            response = (
                self.client.table("posts")
                .select("post_id")
                .like("post_id", f"{prefix}%")
                .execute()
            )
            pattern = re.compile(rf"^JVY-{date_str}-(\d{{3}})$")
            highest = 0
            if response.data:
                for row in response.data:
                    match = pattern.match(row.get("post_id", ""))
                    if match:
                        seq = int(match.group(1))
                        if seq > highest:
                            highest = seq
            return highest + 1
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to calculate next sequence for date '{date_str}': {e}") from e
