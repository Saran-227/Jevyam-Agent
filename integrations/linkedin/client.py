"""Official LinkedIn REST API Client for Company Page publishing."""

import logging
import re
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

from config.settings import settings
from integrations.linkedin.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInRateLimitError,
    LinkedInValidationError,
    MissingLinkedInCredentialsError,
)

logger = logging.getLogger(__name__)


class LinkedInPublishResponse(BaseModel):
    """Normalized response from a LinkedIn publication dispatch."""

    success: bool = Field(..., description="Whether the post was published successfully")
    post_urn: str = Field(..., description="Unique LinkedIn post URN (e.g. urn:li:share:12345678)")
    post_url: Optional[str] = Field(None, description="Public permalink URL to the LinkedIn post")
    target_urn: str = Field(..., description="Target author URN (e.g. urn:li:organization:12345678)")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Raw response payload or headers")


class LinkedInClient:
    """Client for interacting with LinkedIn REST API to publish organizational updates."""

    POSTS_API_URL = "https://api.linkedin.com/rest/posts"

    def __init__(
        self,
        access_token: Optional[str] = None,
        organization_id: Optional[str] = None,
        api_version: str = "202401",
        http_client: Optional[httpx.Client] = None,
    ):
        self.access_token = (access_token or settings.LINKEDIN_ACCESS_TOKEN or "").strip()
        self.organization_id = (organization_id or settings.LINKEDIN_ORGANIZATION_ID or "").strip()
        self.api_version = api_version
        self._client = http_client

    @property
    def organization_urn(self) -> str:
        """Formatted LinkedIn Organization URN."""
        clean_id = self.organization_id
        if clean_id.startswith("urn:li:"):
            return clean_id
        return f"urn:li:organization:{clean_id}"

    def validate_credentials(self) -> None:
        """Verify that necessary credentials are provided and not placeholders.

        Raises:
            MissingLinkedInCredentialsError: If access token or organization ID is missing or placeholder.
        """
        if not self.access_token:
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_ACCESS_TOKEN is missing or empty. Please set it in your .env file."
            )
        if self.access_token.startswith("your_"):
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_ACCESS_TOKEN contains a placeholder value. Please configure a valid OAuth token."
            )

        if not self.organization_id:
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_ORGANIZATION_ID is missing or empty. Please set it in your .env file."
            )
        if self.organization_id.startswith("your_"):
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_ORGANIZATION_ID contains a placeholder value. Please configure your Company Page ID."
            )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": self.api_version,
        }

    def publish_text_post(
        self,
        text: str,
        image_url: Optional[str] = None,
    ) -> LinkedInPublishResponse:
        """Publish a text update to the LinkedIn Company Page.

        Args:
            text: Post commentary text.
            image_url: Optional accompanying image URL.

        Returns:
            LinkedInPublishResponse with post URN and link.

        Raises:
            MissingLinkedInCredentialsError: If credentials are not configured.
            LinkedInAuthError: If access token is expired or unauthorized (401).
            LinkedInPermissionError: If app lacks page admin permissions (403).
            LinkedInValidationError: If payload or text length is rejected (400/422).
            LinkedInRateLimitError: If API rate limits are exceeded (429).
            LinkedInNetworkError: If connection or timeout occurs.
            LinkedInAPIError: If LinkedIn returns internal server error (5xx).
        """
        self.validate_credentials()

        if not text or not str(text).strip():
            raise LinkedInValidationError("Cannot publish an empty post to LinkedIn.")

        cleaned_text = str(text).strip()
        author_urn = self.organization_urn

        # Prepare LinkedIn REST Posts API payload
        payload: Dict[str, Any] = {
            "author": author_urn,
            "commentary": cleaned_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        client = self._client or httpx.Client(timeout=30.0)
        try:
            # Safe log (NEVER log the access token or full auth header)
            logger.info(f"Publishing post to LinkedIn organization: {author_urn}")

            response = client.post(
                self.POSTS_API_URL,
                json=payload,
                headers=self._get_headers(),
            )

            # Handle error status codes with structured exceptions
            if response.status_code in (401,):
                err_body = self._safe_error_extract(response)
                raise LinkedInAuthError(
                    f"LinkedIn authentication failed (401 Unauthorized): {err_body}"
                )

            if response.status_code in (403,):
                err_body = self._safe_error_extract(response)
                raise LinkedInPermissionError(
                    f"LinkedIn permission denied (403 Forbidden). Ensure app has 'w_organization_social' scope and access to {author_urn}: {err_body}"
                )

            if response.status_code in (400, 422):
                err_body = self._safe_error_extract(response)
                raise LinkedInValidationError(
                    f"LinkedIn rejected post content ({response.status_code} Bad Request): {err_body}"
                )

            if response.status_code in (429,):
                err_body = self._safe_error_extract(response)
                raise LinkedInRateLimitError(
                    f"LinkedIn API rate limit exceeded (429 Too Many Requests): {err_body}"
                )

            if response.status_code >= 500:
                err_body = self._safe_error_extract(response)
                raise LinkedInAPIError(
                    f"LinkedIn remote server error ({response.status_code}): {err_body}"
                )

            if response.status_code not in (200, 201):
                err_body = self._safe_error_extract(response)
                raise LinkedInAPIError(
                    f"Unexpected LinkedIn API response status {response.status_code}: {err_body}"
                )

            # Extract Post URN
            post_urn = response.headers.get("x-restli-id")
            raw_json = {}
            if response.content:
                try:
                    raw_json = response.json()
                    if not post_urn and "id" in raw_json:
                        post_urn = raw_json["id"]
                except Exception:
                    pass

            if not post_urn:
                # If neither header nor JSON provides ID, generate fallback identifier from response
                post_urn = f"urn:li:share:generated_{response.status_code}"

            permalink = f"https://www.linkedin.com/feed/update/{post_urn}"

            return LinkedInPublishResponse(
                success=True,
                post_urn=post_urn,
                post_url=permalink,
                target_urn=author_urn,
                raw_response=raw_json or {"status": response.status_code},
            )

        except (LinkedInAuthError, LinkedInPermissionError, LinkedInValidationError, LinkedInRateLimitError, LinkedInAPIError):
            raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise LinkedInNetworkError(f"LinkedIn API network failure: {str(e)}") from e
        except Exception as e:
            raise LinkedInAPIError(f"Unexpected error publishing to LinkedIn: {str(e)}") from e
        finally:
            if not self._client:
                client.close()

    @staticmethod
    def _safe_error_extract(response: httpx.Response) -> str:
        """Safely extract error message without exposing tokens or sensitive headers."""
        try:
            data = response.json()
            if isinstance(data, dict):
                return data.get("message") or str(data)
        except Exception:
            pass
        return response.text[:200] if response.text else f"HTTP {response.status_code}"
