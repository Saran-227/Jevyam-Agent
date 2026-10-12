"""Storage service layer for persistent post asset management in Supabase Storage."""

from abc import ABC, abstractmethod
import logging
from typing import Dict, Optional, Tuple
from uuid import uuid4
from supabase import Client

from agent.exceptions import ImageStorageError
from config.settings import settings
from database.supabase_client import get_supabase_client

logger = logging.getLogger("jevyam.storage")


class BaseStorageService(ABC):
    """Abstract interface for image storage providers."""

    @abstractmethod
    def upload_image(
        self,
        post_id: str,
        revision: int,
        image_bytes: bytes,
        mime_type: str = "image/png",
    ) -> str:
        """Upload image bytes to persistent storage and return the public access URL."""
        pass


class SupabaseStorageService(BaseStorageService):
    """Persistent asset storage backed by Supabase Storage."""

    def __init__(
        self,
        client: Optional[Client] = None,
        bucket_name: Optional[str] = None,
    ):
        self._client = client
        self.bucket_name = bucket_name or getattr(settings, "SUPABASE_IMAGE_BUCKET", "post-images")

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = get_supabase_client()
        return self._client

    def upload_image(
        self,
        post_id: str,
        revision: int,
        image_bytes: bytes,
        mime_type: str = "image/png",
    ) -> str:
        """Upload generated image bytes to Supabase Storage bucket and return public URL.

        Args:
            post_id: Business post ID (e.g. JVY-20261013-001).
            revision: Revision number.
            image_bytes: Raw binary image payload.
            mime_type: MIME type of image (default 'image/png').

        Returns:
            Permanent public URL to the uploaded visual.

        Raises:
            ImageStorageError: If upload fails.
        """
        if not image_bytes:
            raise ImageStorageError("Cannot upload empty image bytes to storage.")

        unique_id = uuid4().hex[:8]
        extension = "jpg" if "jpeg" in mime_type.lower() else "png"
        storage_path = f"{post_id}/rev_{revision}_{unique_id}.{extension}"

        try:
            bucket = self.client.storage.from_(self.bucket_name)
            # Perform upsert upload
            bucket.upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": mime_type, "upsert": "true"},
            )
            public_url = bucket.get_public_url(storage_path)
            if not public_url:
                raise ImageStorageError(f"Supabase returned an empty public URL for path '{storage_path}'.")

            logger.info(f"Successfully uploaded post visual to Supabase Storage bucket '{self.bucket_name}' path: {storage_path}")
            return public_url

        except Exception as e:
            if isinstance(e, ImageStorageError):
                raise
            # Safe error logging: never expose secret keys or signed URL tokens
            safe_msg = f"Failed to upload visual for post '{post_id}' to Supabase Storage: {str(e)}"
            logger.error(f"[ERROR] {safe_msg}")
            raise ImageStorageError(safe_msg) from e


class MockStorageService(BaseStorageService):
    """In-memory mock storage service for testing and dry-run execution."""

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        base_url: str = "https://mock-storage.supabase.co",
    ):
        self.bucket_name = bucket_name or getattr(settings, "SUPABASE_IMAGE_BUCKET", "post-images")
        self.base_url = base_url.rstrip("/")
        self.stored_files: Dict[str, Tuple[bytes, str]] = {}

    def upload_image(
        self,
        post_id: str,
        revision: int,
        image_bytes: bytes,
        mime_type: str = "image/png",
    ) -> str:
        if not image_bytes:
            raise ImageStorageError("Cannot upload empty image bytes to storage.")

        extension = "jpg" if "jpeg" in mime_type.lower() else "png"
        storage_path = f"{post_id}/rev_{revision}.{extension}"
        self.stored_files[storage_path] = (image_bytes, mime_type)
        return f"{self.base_url}/storage/v1/object/public/{self.bucket_name}/{storage_path}"
