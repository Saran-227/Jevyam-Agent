"""FastAPI router for LinkedIn OAuth 2.0 authorization-code flow and status."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from api.dependencies import get_linkedin_oauth_client
from config.settings import settings
from integrations.linkedin.exceptions import (
    LinkedInNetworkError,
    LinkedInOAuthError,
    LinkedInOAuthStateError,
    MissingLinkedInCredentialsError,
)
from integrations.linkedin.oauth import LinkedInOAuthClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/linkedin", tags=["LinkedIn OAuth"])


@router.get(
    "/authorize",
    summary="Initiate LinkedIn OAuth 2.0 authorization flow",
    description="Generates a cryptographically secure CSRF state token and redirects founder to LinkedIn OAuth consent screen.",
)
@router.get(
    "/login",
    summary="Alias to initiate LinkedIn OAuth 2.0 authorization",
    include_in_schema=False,
)
async def authorize_linkedin_endpoint(
    request: Request,
    json_response: bool = Query(
        False,
        alias="json",
        description="Return JSON authorization URL instead of 307 redirect",
    ),
    scope: Optional[str] = Query(
        None,
        description="Override OAuth scope (defaults to 'w_organization_social')",
    ),
    oauth_client: LinkedInOAuthClient = Depends(get_linkedin_oauth_client),
):
    """Initiates 3-legged LinkedIn OAuth authorization code flow.

    Generates CSRF state and returns redirect to LinkedIn consent screen.
    """
    try:
        auth_url, state = oauth_client.get_authorization_url(scope=scope)

        wants_json = json_response or "application/json" in request.headers.get("accept", "")
        if wants_json:
            return {
                "status": "pending_authorization",
                "authorization_url": auth_url,
                "state": state,
                "scope": scope or oauth_client.scope,
            }

        return RedirectResponse(
            url=auth_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )
    except MissingLinkedInCredentialsError as e:
        logger.error(f"Cannot initiate LinkedIn authorization: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except LinkedInOAuthError as e:
        logger.error(f"LinkedIn OAuth configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get(
    "/callback",
    summary="LinkedIn OAuth 2.0 redirect callback endpoint",
    description="Validates single-use CSRF state and exchanges authorization code for access token. Never exposes secrets or tokens.",
)
async def linkedin_callback_endpoint(
    code: Optional[str] = Query(None, description="LinkedIn OAuth authorization code"),
    state: Optional[str] = Query(None, description="Cryptographic CSRF state token"),
    error: Optional[str] = Query(None, description="OAuth error code if authorization was denied"),
    error_description: Optional[str] = Query(
        None, description="Human-readable OAuth error message"
    ),
    oauth_client: LinkedInOAuthClient = Depends(get_linkedin_oauth_client),
):
    """Handles the redirect from LinkedIn after user grants or denies authorization.

    1. Checks for provider error responses.
    2. Validates and consumes single-use CSRF state token.
    3. Exchanges authorization code for an OAuth access token.
    4. Persists the token securely and safely reports success without token leakage.
    5. Note: Does NOT publish any post or trigger dispatches.
    """
    # 1. Check for provider error
    if error:
        logger.warning(f"LinkedIn OAuth authorization failed: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LinkedIn authorization denied: {error_description or error}",
        )

    # 2. Check for missing params
    if not code or not str(code).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'code' parameter in LinkedIn callback.",
        )

    if not state or not str(state).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'state' parameter in LinkedIn callback.",
        )

    # 3. Validate and consume single-use state
    is_valid_state = oauth_client.state_store.validate_and_consume_state(state.strip())
    if not is_valid_state:
        logger.warning("Rejected LinkedIn OAuth callback with invalid, expired, or replayed state token.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already used OAuth state parameter. Please restart authorization.",
        )

    # 4. Exchange code for access token
    try:
        result = oauth_client.exchange_code_for_token(code=code.strip())
        logger.info("Successfully completed LinkedIn OAuth 2.0 authorization exchange.")

        # Safe response: never return raw access_token or authorization code!
        return {
            "status": "success",
            "message": "LinkedIn OAuth 2.0 authorization successful. Jevyam AI Marketing Agent is authorized to publish to your Company Page.",
            "scope": result.get("scope"),
            "expires_in": result.get("expires_in"),
            "expires_at": result.get("expires_at"),
            "auto_publishing_enabled": settings.AUTO_PUBLISH_ON_APPROVAL,
        }

    except MissingLinkedInCredentialsError as e:
        logger.error(f"LinkedIn credentials missing during code exchange: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except LinkedInOAuthError as e:
        logger.error(f"LinkedIn token exchange error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except LinkedInNetworkError as e:
        logger.error(f"Network error during LinkedIn token exchange: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )


@router.get(
    "/status",
    summary="Check LinkedIn OAuth authentication and token expiration status",
    description="Inspects active token source, validity, expiry, and reauthorization needs without leaking credentials.",
)
async def linkedin_status_endpoint(
    oauth_client: LinkedInOAuthClient = Depends(get_linkedin_oauth_client),
):
    """Provides non-sensitive diagnostic status of LinkedIn integration."""
    token_store = oauth_client.token_store
    has_oauth_token = token_store.has_token()
    is_oauth_expired = token_store.is_expired() if has_oauth_token else True

    static_token = (settings.LINKEDIN_ACCESS_TOKEN or "").strip()
    has_static_fallback = bool(static_token and not static_token.startswith("your_"))

    active_source = "none"
    is_authenticated = False
    expires_at_iso = None
    scope = None

    if has_oauth_token and not is_oauth_expired:
        active_source = "oauth_token_store"
        is_authenticated = True
        data = token_store.get_token_data() or {}
        exp_timestamp = data.get("expires_at")
        if exp_timestamp:
            expires_at_iso = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc).isoformat()
        scope = data.get("scope")
    elif has_static_fallback:
        active_source = "static_env_fallback"
        is_authenticated = True
    elif has_oauth_token and is_oauth_expired:
        active_source = "oauth_expired"

    needs_reauth = not is_authenticated

    return {
        "is_authenticated": is_authenticated,
        "token_source": active_source,
        "has_oauth_token": has_oauth_token,
        "is_oauth_expired": is_oauth_expired if has_oauth_token else None,
        "needs_reauthorization": needs_reauth,
        "expires_at": expires_at_iso,
        "scope": scope,
        "api_version": settings.LINKEDIN_API_VERSION,
        "organization_id_configured": bool(
            settings.LINKEDIN_ORGANIZATION_ID and not settings.LINKEDIN_ORGANIZATION_ID.startswith("your_")
        ),
        "reauthorization_url": "/auth/linkedin/authorize" if needs_reauth else None,
    }
