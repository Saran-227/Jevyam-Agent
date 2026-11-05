"""Unit tests for LinkedIn OAuth 2.0 authorization-code flow, token store, and FastAPI endpoints."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
import httpx
import pytest

from agent.exceptions import (
    LinkedInNetworkError,
    LinkedInOAuthError,
    LinkedInOAuthStateError,
    LinkedInTokenExpiredError,
    MissingLinkedInCredentialsError,
)
from api.dependencies import get_linkedin_oauth_client
from api.main import app
from config.settings import settings
from integrations.linkedin.client import LinkedInClient
from integrations.linkedin.oauth import (
    LinkedInOAuthClient,
    LinkedInTokenStore,
    OAuthStateStore,
)


@pytest.fixture
def temp_token_file(tmp_path):
    """Provide a temporary file path for LinkedIn token persistence."""
    return str(tmp_path / "linkedin_token.json")


@pytest.fixture
def mock_token_store(temp_token_file):
    """Instantiate a clean LinkedInTokenStore using temporary file path."""
    return LinkedInTokenStore(storage_path=temp_token_file)


@pytest.fixture
def mock_state_store():
    """Instantiate a clean OAuthStateStore."""
    return OAuthStateStore(default_ttl_seconds=600)


@pytest.fixture
def mock_oauth_client(mock_token_store, mock_state_store):
    """Create a configured LinkedInOAuthClient with clean stores and test credentials."""
    return LinkedInOAuthClient(
        client_id="test_client_id_12345",
        client_secret="test_secret_67890",
        redirect_uri="http://localhost:8000/auth/linkedin/callback",
        token_store=mock_token_store,
        state_store=mock_state_store,
    )


@pytest.fixture
def test_client(mock_oauth_client):
    """FastAPI TestClient with overridden OAuth client dependency."""
    app.dependency_overrides[get_linkedin_oauth_client] = lambda: mock_oauth_client
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_linkedin_oauth_client, None)


# ==============================================================================
# 1. State Generation, Validation, and CSRF / Replay Protection
# ==============================================================================


def test_state_generation_and_validation(mock_state_store):
    """Verify cryptographically secure state generation, successful validation, and single-use consumption."""
    state = mock_state_store.generate_state()
    assert isinstance(state, str)
    assert len(state) >= 32

    # First validation succeeds
    assert mock_state_store.validate_and_consume_state(state) is True

    # Replay protection: second validation of same state MUST fail
    assert mock_state_store.validate_and_consume_state(state) is False


def test_state_expiration(mock_state_store):
    """Verify state token expires after its TTL has elapsed."""
    short_lived_state = mock_state_store.generate_state(ttl_seconds=-1)
    assert mock_state_store.validate_and_consume_state(short_lived_state) is False


def test_invalid_state_rejection(mock_state_store):
    """Verify nonexistent or empty states are rejected."""
    assert mock_state_store.validate_and_consume_state(None) is False
    assert mock_state_store.validate_and_consume_state("") is False
    assert mock_state_store.validate_and_consume_state("forged_random_state") is False


# ==============================================================================
# 2. Authorization URL Generation
# ==============================================================================


def test_authorization_url_generation(mock_oauth_client):
    """Verify authorization URL structure, query parameters, and minimum scope."""
    auth_url, state = mock_oauth_client.get_authorization_url()
    assert auth_url.startswith("https://www.linkedin.com/oauth/v2/authorization")

    parsed = urlparse(auth_url)
    params = parse_qs(parsed.query)

    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["test_client_id_12345"]
    assert params["redirect_uri"] == ["http://localhost:8000/auth/linkedin/callback"]
    assert params["scope"] == ["w_organization_social"]
    assert params["state"] == [state]


def test_authorization_url_missing_client_id(mock_token_store, mock_state_store):
    """Verify error raised when client_id is missing or placeholder."""
    client = LinkedInOAuthClient(
        client_id="",
        client_secret="test_secret",
        redirect_uri="http://localhost:8000/auth/linkedin/callback",
        token_store=mock_token_store,
        state_store=mock_state_store,
    )
    with pytest.raises(MissingLinkedInCredentialsError):
        client.get_authorization_url()


def test_production_https_redirect_uri_enforcement(mock_token_store, mock_state_store):
    """Verify production environments strictly enforce HTTPS for non-localhost redirect URIs."""
    client = LinkedInOAuthClient(
        client_id="test_client",
        client_secret="test_secret",
        redirect_uri="http://marketing.jevyam.com/auth/linkedin/callback",
        token_store=mock_token_store,
        state_store=mock_state_store,
    )
    with patch.object(settings, "APP_ENV", "production"):
        with pytest.raises(LinkedInOAuthError) as exc_info:
            client.get_authorization_url()
        assert "HTTPS" in str(exc_info.value)


# ==============================================================================
# 3. Successful Authorization Code Exchange & Token Store
# ==============================================================================


def test_successful_code_exchange(mock_oauth_client):
    """Verify authorization code exchange against LinkedIn token endpoint."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "access_token": "AQ_live_oauth_token_abc123",
            "expires_in": 5184000,
            "scope": "w_organization_social",
        },
        request=httpx.Request("POST", mock_oauth_client.TOKEN_ENDPOINT),
    )

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.return_value = mock_response
    mock_oauth_client._http_client = mock_http

    result = mock_oauth_client.exchange_code_for_token(code="auth_code_xyz789")

    assert result["success"] is True
    assert result["scope"] == "w_organization_social"
    assert result["expires_in"] == 5184000
    assert "access_token" not in result  # Raw token must not be leaked in result dict

    # Verify token store updated
    assert mock_oauth_client.token_store.has_token() is True
    assert mock_oauth_client.token_store.is_expired() is False
    assert mock_oauth_client.token_store.get_access_token() == "AQ_live_oauth_token_abc123"

    # Verify form payload passed to LinkedIn
    mock_http.post.assert_called_once()
    call_args, call_kwargs = mock_http.post.call_args
    data = call_kwargs["data"]
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "auth_code_xyz789"
    assert data["client_id"] == "test_client_id_12345"
    assert data["client_secret"] == "test_secret_67890"


def test_token_store_persistence(temp_token_file):
    """Verify token store survives instantiation across new objects."""
    store1 = LinkedInTokenStore(storage_path=temp_token_file)
    store1.save_token("persisted_token_999", expires_in=3600, scope="w_organization_social")

    # Second instance reading from same path
    store2 = LinkedInTokenStore(storage_path=temp_token_file)
    assert store2.has_token() is True
    assert store2.get_access_token() == "persisted_token_999"
    assert store2.is_expired() is False


# ==============================================================================
# 4. Token Expiry & Reauthorization Handling
# ==============================================================================


def test_token_expiry_detection(mock_token_store):
    """Verify expired tokens are detected and return None for active token."""
    # Save token expired 10 seconds ago
    mock_token_store.save_token("expired_token", expires_in=-10)

    assert mock_token_store.has_token() is True
    assert mock_token_store.is_expired() is True
    assert mock_token_store.get_access_token() is None
    assert mock_token_store.needs_reauthorization() is True


def test_linkedin_client_token_expired_raises(mock_token_store):
    """Verify LinkedInClient raises LinkedInTokenExpiredError when OAuth token expired and no fallback."""
    mock_token_store.save_token("expired_token", expires_in=-10)

    client = LinkedInClient(
        organization_id="12345678",
        token_store=mock_token_store,
    )
    with patch.object(settings, "LINKEDIN_ACCESS_TOKEN", None):
        with pytest.raises(LinkedInTokenExpiredError) as exc_info:
            client.validate_credentials()
        assert "expired" in str(exc_info.value).lower()
        assert "/auth/linkedin/authorize" in str(exc_info.value)


def test_static_fallback_when_no_oauth_token(mock_token_store):
    """Verify backward compatibility: falls back to static LINKEDIN_ACCESS_TOKEN if no OAuth token."""
    client = LinkedInClient(
        organization_id="12345678",
        token_store=mock_token_store,
    )
    with patch.object(settings, "LINKEDIN_ACCESS_TOKEN", "static_env_fallback_token"):
        assert client.access_token == "static_env_fallback_token"
        client.validate_credentials()  # should not raise


# ==============================================================================
# 5. OAuth Error Responses & Network Failures
# ==============================================================================


def test_oauth_error_from_linkedin_endpoint(mock_oauth_client):
    """Verify LinkedIn token endpoint rejection raises LinkedInOAuthError without secret leakage."""
    mock_response = httpx.Response(
        status_code=400,
        json={
            "error": "invalid_grant",
            "error_description": "The authorization code has expired.",
        },
        request=httpx.Request("POST", mock_oauth_client.TOKEN_ENDPOINT),
    )
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.return_value = mock_response
    mock_oauth_client._http_client = mock_http

    with pytest.raises(LinkedInOAuthError) as exc_info:
        mock_oauth_client.exchange_code_for_token(code="expired_code")

    err = str(exc_info.value)
    assert "invalid_grant" in err
    assert "expired" in err
    # Confirm secrets never leak into exception message
    assert "test_secret" not in err


def test_oauth_network_failure(mock_oauth_client):
    """Verify connection timeout during token exchange raises LinkedInNetworkError."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.side_effect = httpx.ConnectTimeout("Connection timed out")
    mock_oauth_client._http_client = mock_http

    with pytest.raises(LinkedInNetworkError) as exc_info:
        mock_oauth_client.exchange_code_for_token(code="any_code")

    assert "timed out" in str(exc_info.value)


# ==============================================================================
# 6. FastAPI Endpoints: /auth/linkedin/authorize, /callback, /status
# ==============================================================================


def test_endpoint_authorize_redirect(test_client):
    """Verify /auth/linkedin/authorize issues HTTP 307 redirect to LinkedIn."""
    response = test_client.get("/auth/linkedin/authorize", follow_redirects=False)
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://www.linkedin.com/oauth/v2/authorization")
    assert "client_id=test_client_id_12345" in location
    assert "scope=w_organization_social" in location


def test_endpoint_authorize_json(test_client):
    """Verify /auth/linkedin/authorize with json=true returns structured payload."""
    response = test_client.get("/auth/linkedin/authorize?json=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_authorization"
    assert "authorization_url" in data
    assert "state" in data
    assert data["scope"] == "w_organization_social"


def test_endpoint_callback_success(test_client, mock_oauth_client):
    """Verify successful callback exchanges code and returns success without leaking secrets."""
    # 1. Generate valid state
    state = mock_oauth_client.state_store.generate_state()

    # 2. Mock token endpoint response
    mock_response = httpx.Response(
        status_code=200,
        json={
            "access_token": "AQ_successful_callback_token",
            "expires_in": 5184000,
            "scope": "w_organization_social",
        },
        request=httpx.Request("POST", mock_oauth_client.TOKEN_ENDPOINT),
    )
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.return_value = mock_response
    mock_oauth_client._http_client = mock_http

    # 3. Request callback
    response = test_client.get(f"/auth/linkedin/callback?code=valid_code_123&state={state}")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert "expires_at" in data
    assert data["scope"] == "w_organization_social"

    # Strict Security: Assert NO secret or token leakage in response
    assert "access_token" not in data
    assert "AQ_successful_callback_token" not in response.text
    assert "test_secret_67890" not in response.text

    # Verify token was saved
    assert mock_oauth_client.token_store.has_token() is True


def test_endpoint_callback_invalid_state(test_client):
    """Verify callback rejects invalid or forged state parameter with HTTP 400."""
    response = test_client.get("/auth/linkedin/callback?code=some_code&state=forged_state")
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_endpoint_callback_replayed_state(test_client, mock_oauth_client):
    """Verify callback rejects replayed state parameter with HTTP 400."""
    state = mock_oauth_client.state_store.generate_state()

    mock_response = httpx.Response(
        status_code=200,
        json={
            "access_token": "AQ_token",
            "expires_in": 3600,
            "scope": "w_organization_social",
        },
        request=httpx.Request("POST", mock_oauth_client.TOKEN_ENDPOINT),
    )
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.return_value = mock_response
    mock_oauth_client._http_client = mock_http

    # First call consumes state
    r1 = test_client.get(f"/auth/linkedin/callback?code=code1&state={state}")
    assert r1.status_code == 200

    # Second call with same state MUST be rejected
    r2 = test_client.get(f"/auth/linkedin/callback?code=code2&state={state}")
    assert r2.status_code == 400
    assert "state" in r2.json()["detail"].lower()


def test_endpoint_callback_user_denied(test_client):
    """Verify callback handles user cancellation or rejection from LinkedIn consent screen."""
    response = test_client.get(
        "/auth/linkedin/callback?error=user_cancelled_authorize&error_description=User%20cancelled"
    )
    assert response.status_code == 400
    assert "denied" in response.json()["detail"].lower()


def test_endpoint_status(test_client, mock_oauth_client):
    """Verify /auth/linkedin/status reports diagnostic health without exposing credentials."""
    # When not authenticated
    mock_oauth_client.token_store.clear()
    with patch.object(settings, "LINKEDIN_ACCESS_TOKEN", None):
        res = test_client.get("/auth/linkedin/status")
        assert res.status_code == 200
        data = res.json()
        assert data["is_authenticated"] is False
        assert data["needs_reauthorization"] is True
        assert data["reauthorization_url"] == "/auth/linkedin/authorize"

    # When authenticated
    mock_oauth_client.token_store.save_token("test_active_token", expires_in=7200)
    res = test_client.get("/auth/linkedin/status")
    assert res.status_code == 200
    data = res.json()
    assert data["is_authenticated"] is True
    assert data["needs_reauthorization"] is False
    assert data["token_source"] == "oauth_token_store"
    assert data["api_version"] == "202610"
    # Never leak token in status
    assert "test_active_token" not in res.text


# ==============================================================================
# 7. Strict Safety & Secret Leakage Verifications
# ==============================================================================


def test_no_secret_leakage_in_logs(mock_oauth_client, caplog):
    """Verify client secrets, access tokens, and authorization codes are never logged."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "access_token": "AQ_super_sensitive_token_123",
            "expires_in": 3600,
            "scope": "w_organization_social",
        },
        request=httpx.Request("POST", mock_oauth_client.TOKEN_ENDPOINT),
    )
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.return_value = mock_response
    mock_oauth_client._http_client = mock_http

    with caplog.at_level(logging.DEBUG):
        mock_oauth_client.get_authorization_url()
        mock_oauth_client.exchange_code_for_token(code="super_secret_auth_code_999")

    log_text = caplog.text
    assert "AQ_super_sensitive_token_123" not in log_text
    assert "super_secret_auth_code_999" not in log_text
    assert "test_secret_67890" not in log_text


def test_oauth_flow_does_not_trigger_publishing(test_client, mock_oauth_client):
    """Verify completing OAuth authorization NEVER triggers or schedules post publishing."""
    state = mock_oauth_client.state_store.generate_state()

    mock_response = httpx.Response(
        status_code=200,
        json={
            "access_token": "AQ_token",
            "expires_in": 3600,
            "scope": "w_organization_social",
        },
        request=httpx.Request("POST", mock_oauth_client.TOKEN_ENDPOINT),
    )
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.return_value = mock_response
    mock_oauth_client._http_client = mock_http

    with patch("integrations.linkedin.client.LinkedInClient.publish_text_post") as mock_pub:
        resp = test_client.get(f"/auth/linkedin/callback?code=code_abc&state={state}")
        assert resp.status_code == 200
        # Assert publishing is NEVER called as part of OAuth callback
        mock_pub.assert_not_called()

