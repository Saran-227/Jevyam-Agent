"""LinkedIn OAuth 2.0 Authorization-Code Flow and Token Management.

Implements secure OAuth 2.0 for LinkedIn Company Page publishing:
- Cryptographically secure single-use CSRF state tokens.
- 3-legged authorization URL generation with minimal required scope (w_organization_social).
- Authorization code exchange against LinkedIn's official token endpoint.
- Secure token persistence, expiry tracking, and expired token reauthorization checks.
- Zero secret leakage in logs, responses, or error traces.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse

import httpx

from config.settings import settings
from integrations.linkedin.exceptions import (
    LinkedInNetworkError,
    LinkedInOAuthError,
    LinkedInOAuthStateError,
    LinkedInTokenExpiredError,
    MissingLinkedInCredentialsError,
)

logger = logging.getLogger(__name__)


class OAuthStateStore:
    """Thread-safe, in-memory store for single-use OAuth state parameters."""

    def __init__(self, default_ttl_seconds: int = 600):
        self._default_ttl = default_ttl_seconds
        self._states: Dict[str, float] = {}
        self._lock = threading.Lock()

    def generate_state(self, ttl_seconds: Optional[int] = None) -> str:
        """Generate a cryptographically secure, single-use state string with an expiration timestamp."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        state = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            # Purge expired entries to prevent memory growth
            self._purge_expired_locked(now)
            self._states[state] = now + ttl
        return state

    def validate_and_consume_state(self, state: Optional[str]) -> bool:
        """Validate state token and immediately consume it to prevent replay attacks.

        Returns True if state was valid and unexpired; False otherwise.
        """
        if not state or not isinstance(state, str):
            return False

        now = time.time()
        with self._lock:
            expires_at = self._states.pop(state, None)
            if expires_at is None:
                return False
            return now <= expires_at

    def _purge_expired_locked(self, current_time: float) -> None:
        """Remove states whose TTL has passed."""
        expired = [s for s, exp in self._states.items() if exp < current_time]
        for s in expired:
            self._states.pop(s, None)

    def clear(self) -> None:
        """Clear all states (used primarily in tests)."""
        with self._lock:
            self._states.clear()


class LinkedInTokenStore:
    """Secure on-disk and in-memory store for LinkedIn OAuth access tokens.

    Tracks token expiration, ensures atomic writes, and guarantees that token values
    are never leaked into string representations or logs.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path or settings.LINKEDIN_TOKEN_FILE_PATH)
        self._cached_data: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        configured = self.has_token()
        expired = self.is_expired() if configured else None
        return f"<LinkedInTokenStore configured={configured} expired={expired}>"

    def save_token(
        self,
        access_token: str,
        expires_in: int,
        scope: str = "w_organization_social",
    ) -> Dict[str, Any]:
        """Atomically persist access token and metadata to disk."""
        if not access_token or not str(access_token).strip():
            raise LinkedInOAuthError("Cannot save empty access token.")

        now = time.time()
        expires_at = now + float(expires_in)
        token_data: Dict[str, Any] = {
            "access_token": str(access_token).strip(),
            "expires_in": int(expires_in),
            "expires_at": expires_at,
            "obtained_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
        }

        with self._lock:
            # Ensure parent directory exists
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write via temporary file
            temp_path = self.storage_path.with_suffix(".tmp")
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(token_data, f, indent=2)

                # Set restrictive file permissions on POSIX if available
                if hasattr(os, "chmod"):
                    try:
                        os.chmod(temp_path, 0o600)
                    except Exception:
                        pass

                temp_path.replace(self.storage_path)
            except Exception as e:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise LinkedInOAuthError(f"Failed to persist LinkedIn OAuth token: {e}") from e

            self._cached_data = token_data.copy()

        logger.info(
            f"Successfully stored LinkedIn OAuth access token (scope='{scope}', expires_in={expires_in}s)."
        )
        # Return safe copy without exposing raw token if not needed
        return {
            "expires_in": token_data["expires_in"],
            "expires_at": token_data["expires_at"],
            "scope": token_data["scope"],
            "obtained_at": token_data["obtained_at"],
        }

    def get_token_data(self) -> Optional[Dict[str, Any]]:
        """Retrieve stored token data from cache, environment secret, or disk."""
        with self._lock:
            if self._cached_data is not None:
                return self._cached_data.copy()

            # 1. Environment variable LINKEDIN_TOKEN_DATA (Full JSON payload)
            env_token_data = os.getenv("LINKEDIN_TOKEN_DATA")
            if env_token_data:
                try:
                    data = json.loads(env_token_data)
                    if isinstance(data, dict) and "access_token" in data:
                        self._cached_data = data
                        return data.copy()
                except Exception:
                    pass

            # 2. Local token file on disk if exists
            if self.storage_path.exists():
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and "access_token" in data:
                            self._cached_data = data
                            return data.copy()
                except Exception as e:
                    logger.error(f"Error reading LinkedIn token storage file: {e}")

            # 3. Static LINKEDIN_ACCESS_TOKEN from settings (GitHub Actions Secrets fallback)
            static_token = (getattr(settings, "LINKEDIN_ACCESS_TOKEN", None) or "").strip()
            if static_token and not static_token.startswith("your_"):
                synthetic = {
                    "access_token": static_token,
                    "expires_in": 5184000,
                    "expires_at": time.time() + 5184000,
                    "obtained_at": datetime.now(timezone.utc).isoformat(),
                    "scope": "w_organization_social",
                }
                self._cached_data = synthetic
                return synthetic.copy()

            return None

    def get_access_token(self, safety_margin_seconds: int = 60) -> Optional[str]:
        """Return the active access token if present and not expired."""
        data = self.get_token_data()
        if not data:
            return None

        expires_at = data.get("expires_at", 0)
        if time.time() + safety_margin_seconds >= expires_at:
            return None

        return data.get("access_token")

    def is_expired(self, safety_margin_seconds: int = 60) -> bool:
        """Return True if stored token is missing or within safety margin of expiration."""
        data = self.get_token_data()
        if not data:
            return True
        expires_at = data.get("expires_at", 0)
        return (time.time() + safety_margin_seconds) >= expires_at

    def has_token(self) -> bool:
        """Check whether any OAuth token has been saved."""
        data = self.get_token_data()
        return bool(data and data.get("access_token"))

    def needs_reauthorization(self) -> bool:
        """Return True if no valid, unexpired OAuth token is available."""
        return not self.has_token() or self.is_expired()

    def clear(self) -> None:
        """Clear cached and on-disk token data."""
        with self._lock:
            self._cached_data = None
            if self.storage_path.exists():
                try:
                    self.storage_path.unlink()
                except Exception:
                    pass


class LinkedInOAuthClient:
    """Handles LinkedIn OAuth 2.0 authorization requests and token exchanges."""

    AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
    TOKEN_ENDPOINT = "https://www.linkedin.com/oauth/v2/accessToken"
    DEFAULT_SCOPE = "w_organization_social"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        token_store: Optional[LinkedInTokenStore] = None,
        state_store: Optional[OAuthStateStore] = None,
        http_client: Optional[httpx.Client] = None,
        scope: Optional[str] = None,
    ):
        self.client_id = (client_id if client_id is not None else (settings.LINKEDIN_CLIENT_ID or "")).strip()
        self.client_secret = (client_secret if client_secret is not None else (settings.LINKEDIN_CLIENT_SECRET or "")).strip()
        self.redirect_uri = (redirect_uri if redirect_uri is not None else (settings.effective_linkedin_redirect_uri or "")).strip()
        self.token_store = token_store or _default_token_store
        self.state_store = state_store or _default_state_store
        self._http_client = http_client
        self.scope = scope or self.DEFAULT_SCOPE

    def validate_redirect_uri(self, uri: str) -> None:
        """Validate redirect URI format and HTTPS compliance in production environments."""
        if not uri or not isinstance(uri, str):
            raise LinkedInOAuthError("Redirect URI must not be empty.")

        parsed = urlparse(uri)
        if not parsed.scheme or not parsed.netloc:
            raise LinkedInOAuthError(f"Invalid redirect URI format: '{uri}'")

        is_production = settings.APP_ENV.lower() == "production"
        is_localhost = parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0")

        if is_production and not is_localhost and parsed.scheme.lower() != "https":
            raise LinkedInOAuthError(
                f"Production redirect URI must strictly use HTTPS (got '{uri}')."
            )

    def get_authorization_url(
        self,
        scope: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Generate a secure LinkedIn OAuth 2.0 authorization URL and single-use state token.

        Returns:
            Tuple of (authorization_url, state).
        """
        if not self.client_id or self.client_id.startswith("your_"):
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_CLIENT_ID is missing or contains a placeholder. Configure it in .env."
            )

        target_redirect_uri = (redirect_uri or self.redirect_uri).strip()
        self.validate_redirect_uri(target_redirect_uri)

        target_scope = scope or self.scope
        state = self.state_store.generate_state()

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": target_redirect_uri,
            "state": state,
            "scope": target_scope,
        }

        auth_url = f"{self.AUTHORIZATION_URL}?{urlencode(params)}"
        logger.info(
            f"Generated LinkedIn OAuth authorization URL (client_id={self.client_id[:4]}***, scope='{target_scope}')."
        )
        return auth_url, state

    def exchange_code_for_token(
        self,
        code: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchange an authorization code for an OAuth access token using LinkedIn's official token endpoint.

        Never logs client secrets, raw authorization codes, or response access tokens.
        """
        if not code or not str(code).strip():
            raise LinkedInOAuthError("Authorization code must not be empty.")

        if not self.client_id or self.client_id.startswith("your_"):
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_CLIENT_ID is missing or contains a placeholder. Configure it in .env."
            )

        if not self.client_secret or self.client_secret.startswith("your_"):
            raise MissingLinkedInCredentialsError(
                "LINKEDIN_CLIENT_SECRET is missing or contains a placeholder. Configure it in .env."
            )

        target_redirect_uri = (redirect_uri or self.redirect_uri).strip()
        self.validate_redirect_uri(target_redirect_uri)

        form_data = {
            "grant_type": "authorization_code",
            "code": str(code).strip(),
            "redirect_uri": target_redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        client = self._http_client or httpx.Client(timeout=30.0)
        should_close = not self._http_client

        try:
            logger.info("Exchanging LinkedIn authorization code for access token...")
            response = client.post(
                self.TOKEN_ENDPOINT,
                data=form_data,
                headers=headers,
            )

            if response.status_code == 200:
                payload = response.json()
                access_token = payload.get("access_token")
                expires_in = payload.get("expires_in")
                granted_scope = payload.get("scope", self.scope)

                if not access_token:
                    raise LinkedInOAuthError(
                        "LinkedIn token endpoint response did not contain 'access_token'."
                    )
                if expires_in is None:
                    # Fallback to standard 60-day token lifetime (5184000s) if missing
                    expires_in = 5184000

                # Persist token securely
                saved_info = self.token_store.save_token(
                    access_token=access_token,
                    expires_in=int(expires_in),
                    scope=granted_scope,
                )

                expires_at_dt = datetime.fromtimestamp(saved_info["expires_at"], tz=timezone.utc)
                return {
                    "success": True,
                    "scope": granted_scope,
                    "expires_in": int(expires_in),
                    "expires_at": expires_at_dt.isoformat(),
                    "message": "LinkedIn OAuth 2.0 authorization successful.",
                }

            # Handle OAuth Error Status Codes
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass

            err_code = error_data.get("error") or f"HTTP {response.status_code}"
            err_desc = error_data.get("error_description") or response.text[:200]
            safe_message = f"{err_code}: {err_desc}" if err_desc else str(err_code)

            logger.error(f"LinkedIn token exchange rejected: {safe_message}")
            raise LinkedInOAuthError(
                f"LinkedIn token exchange failed ({response.status_code}): {safe_message}"
            )

        except (LinkedInOAuthError, MissingLinkedInCredentialsError):
            raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error(f"Network error during LinkedIn token exchange: {e}")
            raise LinkedInNetworkError(f"Network error during LinkedIn token exchange: {str(e)}") from e
        except Exception as e:
            logger.error(f"Unexpected error during LinkedIn token exchange: {e}")
            raise LinkedInOAuthError(f"Unexpected error during LinkedIn token exchange: {str(e)}") from e
        finally:
            if should_close:
                client.close()


# Module-level singletons for standard runtime execution
_default_state_store = OAuthStateStore()
_default_token_store = LinkedInTokenStore()


def get_default_state_store() -> OAuthStateStore:
    """Return default application OAuthStateStore singleton."""
    return _default_state_store


def get_default_token_store() -> LinkedInTokenStore:
    """Return default application LinkedInTokenStore singleton."""
    return _default_token_store


def get_default_oauth_client() -> LinkedInOAuthClient:
    """Return default application LinkedInOAuthClient initialized from settings."""
    return LinkedInOAuthClient(
        token_store=_default_token_store,
        state_store=_default_state_store,
    )
