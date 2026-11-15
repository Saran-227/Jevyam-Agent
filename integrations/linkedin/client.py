"""Official LinkedIn REST API Client for Company Page publishing."""

import logging
import re
from typing import Any, Dict, Optional, Tuple
import httpx
from pydantic import BaseModel, Field

from config.settings import settings
from integrations.linkedin.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInRateLimitError,
    LinkedInTokenExpiredError,
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
    IMAGES_API_URL = "https://api.linkedin.com/rest/images"

    def __init__(
        self,
        access_token: Optional[str] = None,
        organization_id: Optional[str] = None,
        api_version: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        token_store: Optional[Any] = None,
    ):
        self._explicit_access_token = access_token
        self.organization_id = (
            organization_id
            if organization_id is not None
            else (settings.LINKEDIN_ORGANIZATION_ID or "")
        ).strip()
        self.api_version = api_version or getattr(settings, "LINKEDIN_API_VERSION", "202610") or "202610"
        self._client = http_client
        if token_store is not None:
            self.token_store = token_store
        else:
            try:
                from integrations.linkedin.oauth import get_default_token_store
                self.token_store = get_default_token_store()
            except Exception:
                self.token_store = None

    @property
    def access_token(self) -> str:
        """Resolve active LinkedIn access token.

        Resolution order:
        1. Explicitly supplied access_token (including explicit empty string).
        2. Stored unexpired OAuth token from token_store.
        3. Backward-compatible static LINKEDIN_ACCESS_TOKEN from settings.
        """
        if self._explicit_access_token is not None:
            return self._explicit_access_token.strip()

        if self.token_store and self.token_store.has_token():
            if not self.token_store.is_expired():
                oauth_tok = self.token_store.get_access_token()
                if oauth_tok:
                    return oauth_tok

        return (settings.LINKEDIN_ACCESS_TOKEN or "").strip()

    @access_token.setter
    def access_token(self, val: Optional[str]) -> None:
        self._explicit_access_token = val

    @property
    def organization_urn(self) -> str:
        """Formatted LinkedIn Organization URN.

        Strictly enforces company page destination (urn:li:organization:...).
        Rejects personal profile URNs (urn:li:person:...).
        """
        clean_id = str(self.organization_id or "").strip()
        if clean_id.startswith("urn:li:organization:"):
            return clean_id
        if clean_id.startswith("urn:li:person:"):
            raise LinkedInPermissionError(
                f"Invalid author URN '{clean_id}'. Publishing to personal LinkedIn profiles is strictly forbidden. "
                "Target must be a LinkedIn Company Page (urn:li:organization:...)."
            )
        if clean_id.startswith("urn:li:"):
            raise LinkedInPermissionError(
                f"Invalid author URN '{clean_id}'. Publishing target must be a LinkedIn Company Page (urn:li:organization:...)."
            )
        return f"urn:li:organization:{clean_id}"

    def validate_credentials(self) -> None:
        """Verify that necessary credentials are provided, unexpired, and not placeholders.

        Raises:
            LinkedInTokenExpiredError: If stored OAuth token has expired and no valid static fallback exists.
            LinkedInPermissionError: If OAuth token lacks required w_organization_social scope or invalid author.
            MissingLinkedInCredentialsError: If access token or organization ID is missing or placeholder.
        """
        # Validate author URN is strictly an organization URN
        _ = self.organization_urn

        # If an OAuth token exists, validate expiration and required scopes
        if not self._explicit_access_token and self.token_store and self.token_store.has_token():
            if self.token_store.is_expired():
                static_fallback = (settings.LINKEDIN_ACCESS_TOKEN or "").strip()
                if not static_fallback or static_fallback.startswith("your_"):
                    raise LinkedInTokenExpiredError(
                        "LinkedIn OAuth access token has expired. Reauthorization required via /auth/linkedin/authorize."
                    )
            token_data = self.token_store.get_token_data()
            if token_data and "scope" in token_data:
                scopes = token_data.get("scope", "")
                if "w_organization_social" not in scopes:
                    raise LinkedInPermissionError(
                        f"LinkedIn OAuth token lacks mandatory 'w_organization_social' scope (found scopes: '{scopes}'). "
                        "Reauthorization required with w_organization_social."
                    )

        token = self.access_token
        if not token:
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_ACCESS_TOKEN is missing or empty. Please authenticate via OAuth (/auth/linkedin/authorize) or set it in your .env file."
            )
        if token.startswith("your_"):
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

    def initialize_image_upload(
        self,
        client: Optional[httpx.Client] = None,
    ) -> Tuple[str, str]:
        """Initialize an image upload via LinkedIn REST Images API.

        Calls: POST https://api.linkedin.com/rest/images?action=initializeUpload

        Returns:
            Tuple of (upload_url, image_urn).
        """
        self.validate_credentials()
        author_urn = self.organization_urn
        url = f"{self.IMAGES_API_URL}?action=initializeUpload"
        payload = {
            "initializeUploadRequest": {
                "owner": author_urn,
            }
        }

        http = client or self._client or httpx.Client(timeout=30.0)
        should_close = not (client or self._client)
        try:
            logger.info(f"Initializing LinkedIn image upload for owner: {author_urn}")
            response = http.post(
                url,
                json=payload,
                headers=self._get_headers(),
            )
            self._handle_status_code(response, "initialize image upload")
            data = response.json() if response.content else {}
            value = data.get("value", {})
            upload_url = value.get("uploadUrl")
            image_urn = value.get("image")
            if not upload_url or not image_urn:
                raise LinkedInAPIError(f"LinkedIn image upload initialization missing uploadUrl or image URN: {data}")
            return upload_url, image_urn
        except (LinkedInAuthError, LinkedInPermissionError, LinkedInValidationError, LinkedInRateLimitError, LinkedInAPIError):
            raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise LinkedInNetworkError(f"LinkedIn API network failure during image upload init: {str(e)}") from e
        except Exception as e:
            raise LinkedInAPIError(f"Unexpected error initializing LinkedIn image upload: {str(e)}") from e
        finally:
            if should_close:
                http.close()

    def upload_image_binary(
        self,
        upload_url: str,
        image_bytes: bytes,
        mime_type: str = "image/png",
        client: Optional[httpx.Client] = None,
    ) -> None:
        """Upload raw image binary to the single-use LinkedIn uploadUrl via PUT."""
        if not image_bytes:
            raise LinkedInValidationError("Cannot upload empty image binary payload.")

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": mime_type,
        }
        http = client or self._client or httpx.Client(timeout=60.0)
        should_close = not (client or self._client)
        try:
            logger.info("Uploading binary image bytes to LinkedIn media upload endpoint...")
            response = http.put(
                upload_url,
                content=image_bytes,
                headers=headers,
            )
            if response.status_code not in (200, 201):
                err_body = self._safe_error_extract(response)
                raise LinkedInAPIError(
                    f"LinkedIn image binary upload failed with status {response.status_code}: {err_body}"
                )
        except (LinkedInAPIError, LinkedInValidationError):
            raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise LinkedInNetworkError(f"Network error uploading image bytes to LinkedIn: {str(e)}") from e
        except Exception as e:
            raise LinkedInAPIError(f"Unexpected error uploading image bytes to LinkedIn: {str(e)}") from e
        finally:
            if should_close:
                http.close()

    def publish_image_post(
        self,
        text: str,
        image_url: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        title: Optional[str] = None,
    ) -> LinkedInPublishResponse:
        """Publish a complete post with accompanying image asset to LinkedIn Company Page.

        Performs:
        1. Download / read image bytes.
        2. Initialize image upload (POST /rest/images?action=initializeUpload).
        3. Upload binary bytes (PUT uploadUrl).
        4. Create post referencing image URN (POST /rest/posts).
        """
        self.validate_credentials()
        if not text or not str(text).strip():
            raise LinkedInValidationError("Cannot publish an empty post to LinkedIn.")

        cleaned_text = str(text).strip()
        author_urn = self.organization_urn

        client = self._client or httpx.Client(timeout=60.0)
        should_close = not self._client

        try:
            # 1. Obtain image binary bytes
            bytes_to_upload = image_bytes
            mime_type = "image/png"
            if bytes_to_upload is None and image_url:
                try:
                    logger.info(f"Fetching stored post image for LinkedIn dispatch from: {image_url}")
                    img_resp = client.get(image_url, timeout=30.0)
                    if img_resp.status_code != 200:
                        raise LinkedInValidationError(
                            f"Failed to fetch image from URL '{image_url}' (HTTP {img_resp.status_code})."
                        )
                    bytes_to_upload = img_resp.content
                    content_type = img_resp.headers.get("Content-Type", "")
                    if "jpeg" in content_type.lower() or "jpg" in content_type.lower():
                        mime_type = "image/jpeg"
                except Exception as e:
                    if isinstance(e, LinkedInValidationError):
                        raise
                    raise LinkedInNetworkError(f"Failed to fetch post image from storage: {e}") from e

            if not bytes_to_upload:
                raise LinkedInValidationError("No valid image bytes or URL provided for image publication.")

            # 2. Initialize upload
            upload_url, image_urn = self.initialize_image_upload(client=client)

            # 3. Upload binary image
            self.upload_image_binary(upload_url, bytes_to_upload, mime_type=mime_type, client=client)

            # 4. Create post with media
            payload: Dict[str, Any] = {
                "author": author_urn,
                "commentary": cleaned_text,
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "content": {
                    "media": {
                        "id": image_urn,
                        "title": title or "Jevyam Technologies Visual",
                    }
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }

            logger.info(f"Publishing image post to LinkedIn organization {author_urn} with media {image_urn}...")
            response = client.post(
                self.POSTS_API_URL,
                json=payload,
                headers=self._get_headers(),
            )
            self._handle_status_code(response, "create image post")

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
                post_urn = f"urn:li:share:generated_{response.status_code}"

            permalink = f"https://www.linkedin.com/feed/update/{post_urn}"
            return LinkedInPublishResponse(
                success=True,
                post_urn=post_urn,
                post_url=permalink,
                target_urn=author_urn,
                raw_response=raw_json or {"status": response.status_code, "image_urn": image_urn},
            )

        except (LinkedInAuthError, LinkedInPermissionError, LinkedInValidationError, LinkedInRateLimitError, LinkedInAPIError):
            raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            raise LinkedInNetworkError(f"LinkedIn API network failure during image post publishing: {str(e)}") from e
        except Exception as e:
            raise LinkedInAPIError(f"Unexpected error publishing image post to LinkedIn: {str(e)}") from e
        finally:
            if should_close:
                client.close()

    def _handle_status_code(self, response: httpx.Response, action_description: str = "request") -> None:
        """Handle error HTTP response status codes with structured exceptions."""
        if response.status_code in (200, 201):
            return

        author_urn = self.organization_urn
        err_body = self._safe_error_extract(response)

        if response.status_code in (401,):
            raise LinkedInAuthError(
                f"LinkedIn authentication failed (401 Unauthorized) during {action_description}: {err_body}"
            )
        if response.status_code in (403,):
            raise LinkedInPermissionError(
                f"LinkedIn permission denied (403 Forbidden). Ensure app has 'w_organization_social' scope and access to {author_urn}: {err_body}"
            )
        if response.status_code in (400, 422):
            raise LinkedInValidationError(
                f"LinkedIn rejected post content ({response.status_code} Bad Request) during {action_description}: {err_body}"
            )
        if response.status_code in (429,):
            raise LinkedInRateLimitError(
                f"LinkedIn API rate limit exceeded (429 Too Many Requests) during {action_description}: {err_body}"
            )
        if response.status_code >= 500:
            raise LinkedInAPIError(
                f"LinkedIn remote server error ({response.status_code}) during {action_description}: {err_body}"
            )

        raise LinkedInAPIError(
            f"Unexpected LinkedIn API response status {response.status_code} during {action_description}: {err_body}"
        )

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
