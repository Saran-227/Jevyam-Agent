"""Publication repository layer for audit tracking of LinkedIn dispatches."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4
from supabase import Client

from database.exceptions import SupabaseDatabaseError
from database.models import Publication, PublicationStatus
from database.repositories.base import BasePublicationRepository


class InMemoryPublicationRepository(BasePublicationRepository):
    """In-memory publication repository for testing and offline development."""

    def __init__(self):
        self._publications: Dict[str, Publication] = {}

    def create(self, publication: Publication) -> Publication:
        pub_id = publication.id or str(uuid4())
        created = publication.model_copy(deep=True)
        created.id = pub_id
        if not created.created_at:
            created.created_at = datetime.now()
        self._publications[pub_id] = created
        return created.model_copy(deep=True)

    def get_by_post_id(self, post_id: str) -> List[Publication]:
        matching = [
            p.model_copy(deep=True)
            for p in self._publications.values()
            if p.post_id == post_id
        ]
        return sorted(matching, key=lambda p: str(p.created_at or ""), reverse=True)

    def get_latest_by_post_id(self, post_id: str) -> Optional[Publication]:
        records = self.get_by_post_id(post_id)
        return records[0] if records else None

    def update_status(
        self,
        publication_id: str,
        status: PublicationStatus,
        external_post_id: Optional[str] = None,
        error_message: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> Publication:
        pub = self._publications.get(publication_id)
        if not pub:
            raise ValueError(f"Publication with ID '{publication_id}' not found.")

        pub.status = status
        if external_post_id:
            pub.external_post_id = external_post_id
        if error_message:
            pub.error_message = error_message
        if published_at:
            pub.published_at = published_at
        elif status == PublicationStatus.PUBLISHED and not pub.published_at:
            pub.published_at = datetime.now()

        self._publications[publication_id] = pub.model_copy(deep=True)
        return pub.model_copy(deep=True)


class SupabasePublicationRepository(BasePublicationRepository):
    """Supabase PostgreSQL publication repository."""

    def __init__(self, client: Client):
        self.client = client

    def create(self, publication: Publication) -> Publication:
        payload = publication.model_dump(mode="json", exclude_none=True)
        try:
            response = self.client.table("publications").insert(payload).execute()
            if response.data and len(response.data) > 0:
                return Publication.model_validate(response.data[0])
            raise SupabaseDatabaseError("Failed to persist publication record: empty response")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to create publication: {e}") from e

    def get_by_post_id(self, post_id: str) -> List[Publication]:
        try:
            response = (
                self.client.table("publications")
                .select("*")
                .eq("post_id", post_id)
                .order("created_at", desc=True)
                .execute()
            )
            if response.data:
                return [Publication.model_validate(item) for item in response.data]
            return []
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch publications for post '{post_id}': {e}") from e

    def get_latest_by_post_id(self, post_id: str) -> Optional[Publication]:
        try:
            response = (
                self.client.table("publications")
                .select("*")
                .eq("post_id", post_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Publication.model_validate(response.data[0])
            return None
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch latest publication for post '{post_id}': {e}") from e

    def update_status(
        self,
        publication_id: str,
        status: PublicationStatus,
        external_post_id: Optional[str] = None,
        error_message: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> Publication:
        payload: Dict[str, Any] = {"status": status.value}
        if external_post_id:
            payload["external_post_id"] = external_post_id
        if error_message:
            payload["error_message"] = error_message
        if published_at:
            payload["published_at"] = published_at.isoformat()
        elif status == PublicationStatus.PUBLISHED:
            payload["published_at"] = datetime.now().isoformat()

        try:
            response = (
                self.client.table("publications")
                .update(payload)
                .eq("id", publication_id)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Publication.model_validate(response.data[0])
            raise ValueError(f"Publication with ID '{publication_id}' was not updated.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to update publication status: {e}") from e
