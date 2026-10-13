"""Tests for Gemini integration wrapper and error handling."""

import os
from unittest.mock import MagicMock, patch
import pytest
from pydantic import BaseModel
from google.genai.errors import APIError

from agent.exceptions import (
    GeminiAPIError,
    GeminiAuthError,
    GeminiNetworkError,
    GeminiRateLimitError,
    GeminiUnavailableError,
    InvalidGeminiResponseError,
    MissingGeminiApiKeyError,
)
from integrations.gemini import (
    MAX_RETRIES,
    _calculate_backoff,
    _extract_retry_after,
    _is_transient_error,
    generate_structured_content,
    generate_text,
    get_gemini_client,
)
from config.settings import settings


class SampleSchema(BaseModel):
    title: str
    score: int


def test_default_gemini_model_is_gemini_3_8_flash():
    """Verify that the default configured Gemini model is gemini-3.8-flash."""
    assert settings.GEMINI_MODEL == "gemini-3.8-flash"


def test_generate_structured_content_uses_default_gemini_model():
    """Verify generate_structured_content invokes client with the default gemini-3.8-flash model."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"title": "Test Title", "score": 42}'
    mock_client.models.generate_content.return_value = mock_resp

    generate_structured_content(
        client=mock_client,
        prompt="Test Prompt",
        schema=SampleSchema,
    )

    mock_client.models.generate_content.assert_called_once()
    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs.get("model") == "gemini-3.8-flash"


def test_generate_structured_content_respects_custom_model_override():
    """Verify that an explicit model argument overrides the default model."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"title": "Custom Model", "score": 99}'
    mock_client.models.generate_content.return_value = mock_resp

    generate_structured_content(
        client=mock_client,
        prompt="Test Prompt",
        schema=SampleSchema,
        model="custom-gemini-model",
    )

    _, kwargs = mock_client.models.generate_content.call_args
    assert kwargs.get("model") == "custom-gemini-model"


def test_missing_api_key_raises_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(MissingGeminiApiKeyError) as exc_info:
        get_gemini_client(api_key="")
    assert "GEMINI_API_KEY is missing or empty" in str(exc_info.value)


def test_invalid_json_raises_invalid_response_error():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "This is not valid JSON at all"
    mock_client.models.generate_content.return_value = mock_resp

    with pytest.raises(InvalidGeminiResponseError) as exc_info:
        generate_structured_content(
            client=mock_client,
            prompt="Test",
            schema=SampleSchema,
        )
    assert "Failed to validate" in str(exc_info.value) or "Failed to parse" in str(exc_info.value)


def test_schema_mismatch_raises_invalid_response_error():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"title": "Valid title", "score": "not_an_int"}'
    mock_client.models.generate_content.return_value = mock_resp

    with pytest.raises(InvalidGeminiResponseError):
        generate_structured_content(
            client=mock_client,
            prompt="Test",
            schema=SampleSchema,
        )


def test_api_error_wrapped():
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = APIError(
        code=403,
        response_json={"error": {"message": "API key expired or quota exceeded"}},
    )

    with pytest.raises(GeminiAPIError) as exc_info:
        generate_structured_content(
            client=mock_client,
            prompt="Test",
            schema=SampleSchema,
        )
    assert "Gemini API error" in str(exc_info.value)


def test_gemini_auth_error_not_retried():
    """Verify permanent 401/403 authentication error raises GeminiAuthError without retries."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = APIError(
        code=401,
        response_json={"error": {"code": 401, "message": "API_KEY_INVALID", "status": "UNAUTHENTICATED"}},
    )

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiAuthError) as exc_info:
            generate_structured_content(
                client=mock_client,
                prompt="Test",
                schema=SampleSchema,
            )
        assert mock_client.models.generate_content.call_count == 1
        mock_sleep.assert_not_called()
        assert "authentication/permission error" in str(exc_info.value)


def test_gemini_503_transient_retry_success():
    """Verify transient 503 error retries and succeeds if subsequent attempt succeeds."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "The model is overloaded. Please try again later.", "status": "UNAVAILABLE"}},
    )
    mock_resp = MagicMock()
    mock_resp.text = '{"title": "Success After Retry", "score": 90}'
    mock_client.models.generate_content.side_effect = [mock_503, mock_resp]

    with patch("time.sleep") as mock_sleep:
        result = generate_structured_content(
            client=mock_client,
            prompt="Test",
            schema=SampleSchema,
        )
        assert result.title == "Success After Retry"
        assert result.score == 90
        assert mock_client.models.generate_content.call_count == 2
        mock_sleep.assert_called_once()
        # Verify sleep duration is bounded and positive
        sleep_dur = mock_sleep.call_args[0][0]
        assert 1.5 <= sleep_dur <= 5.0


def test_gemini_503_exhausted_retries_raises_unavailable_error():
    """Verify repeated 503 error exhausts retries and raises GeminiUnavailableError."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "Service Unavailable", "status": "UNAVAILABLE"}},
    )
    mock_client.models.generate_content.side_effect = mock_503

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiUnavailableError) as exc_info:
            generate_structured_content(
                client=mock_client,
                prompt="Test",
                schema=SampleSchema,
                fallback_model="",
            )
        assert mock_client.models.generate_content.call_count == MAX_RETRIES
        assert mock_sleep.call_count == MAX_RETRIES - 1
        assert "service temporarily unavailable" in str(exc_info.value)


def test_gemini_429_rate_limit_error_exhausted():
    """Verify 429 quota exhaustion raises GeminiRateLimitError after retries."""
    mock_client = MagicMock()
    mock_429 = APIError(
        code=429,
        response_json={"error": {"code": 429, "message": "RESOURCE_EXHAUSTED", "status": "RESOURCE_EXHAUSTED"}},
    )
    mock_client.models.generate_content.side_effect = mock_429

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiRateLimitError) as exc_info:
            generate_structured_content(
                client=mock_client,
                prompt="Test",
                schema=SampleSchema,
                fallback_model="",
            )
        assert mock_client.models.generate_content.call_count == MAX_RETRIES
        assert "rate limit or quota exceeded" in str(exc_info.value)


def test_gemini_retry_after_respected():
    """Verify Retry-After response header is respected for backoff duration."""
    mock_resp = MagicMock()
    mock_resp.headers = {"retry-after": "6.5"}
    err = APIError(
        code=429,
        response_json={"error": {"code": 429, "message": "Rate limit"}},
        response=mock_resp,
    )
    assert _extract_retry_after(err) == 6.5
    backoff = _calculate_backoff(attempt=1, e=err)
    assert backoff == 6.5


def test_gemini_network_timeout_retry():
    """Verify transient network timeout retries and raises GeminiNetworkError when exhausted."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = TimeoutError("Connection to Gemini timed out")

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiNetworkError) as exc_info:
            generate_structured_content(
                client=mock_client,
                prompt="Test",
                schema=SampleSchema,
                fallback_model="",
            )
        assert mock_client.models.generate_content.call_count == MAX_RETRIES
        assert "network error" in str(exc_info.value).lower()


def test_primary_model_failure_with_successful_fallback():
    """Verify primary model 503 transient exhaustion falls back to fallback model and succeeds."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}},
    )
    mock_resp = MagicMock()
    mock_resp.text = '{"title": "Fallback Success", "score": 88}'
    # Primary model fails MAX_RETRIES (3) times with 503, then fallback succeeds on 1st attempt
    mock_client.models.generate_content.side_effect = [mock_503, mock_503, mock_503, mock_resp]

    with patch("time.sleep") as mock_sleep:
        res = generate_structured_content(
            client=mock_client,
            prompt="Test",
            schema=SampleSchema,
            model="gemini-3.8-flash",
            fallback_model="gemini-3.1-flash-lite",
        )
        assert res.title == "Fallback Success"
        assert res.score == 88
        assert mock_client.models.generate_content.call_count == MAX_RETRIES + 1
        calls = mock_client.models.generate_content.call_args_list
        for i in range(MAX_RETRIES):
            assert calls[i].kwargs.get("model") == "gemini-3.8-flash"
        assert calls[MAX_RETRIES].kwargs.get("model") == "gemini-3.1-flash-lite"
        assert mock_sleep.call_count == MAX_RETRIES - 1


def test_primary_model_failure_without_fallback():
    """Verify primary model 503 error exhausts retries and raises GeminiUnavailableError when no fallback configured."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "Service Unavailable", "status": "UNAVAILABLE"}},
    )
    mock_client.models.generate_content.side_effect = mock_503

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiUnavailableError) as exc_info:
            generate_structured_content(
                client=mock_client,
                prompt="Test",
                schema=SampleSchema,
                fallback_model="",
            )
        assert mock_client.models.generate_content.call_count == MAX_RETRIES
        assert mock_sleep.call_count == MAX_RETRIES - 1
        assert "service temporarily unavailable" in str(exc_info.value)


def test_total_failure_primary_and_fallback_exhausted():
    """Verify both primary and fallback models fail 503, exhausting all retries and raising GeminiUnavailableError."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "Overloaded", "status": "UNAVAILABLE"}},
    )
    mock_client.models.generate_content.side_effect = mock_503

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiUnavailableError) as exc_info:
            generate_structured_content(
                client=mock_client,
                prompt="Test",
                schema=SampleSchema,
                model="gemini-3.8-flash",
                fallback_model="gemini-3.1-flash-lite",
            )
        assert mock_client.models.generate_content.call_count == MAX_RETRIES * 2
        assert mock_sleep.call_count == (MAX_RETRIES - 1) * 2
        assert "service temporarily unavailable" in str(exc_info.value)


def test_generate_text_primary_failure_with_successful_fallback():
    """Verify generate_text fails over to fallback model on transient 503 failures."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}},
    )
    mock_resp = MagicMock()
    mock_resp.text = "Fallback Text Output"
    mock_client.models.generate_content.side_effect = [mock_503, mock_503, mock_503, mock_resp]

    with patch("time.sleep") as mock_sleep:
        res = generate_text(
            client=mock_client,
            prompt="Prompt",
            model="gemini-3.8-flash",
            fallback_model="gemini-3.1-flash-lite",
        )
        assert res == "Fallback Text Output"
        assert mock_client.models.generate_content.call_count == MAX_RETRIES + 1
        calls = mock_client.models.generate_content.call_args_list
        assert calls[-1].kwargs.get("model") == "gemini-3.1-flash-lite"


def test_generate_text_total_failure():
    """Verify generate_text raises GeminiUnavailableError when all models exhaust retries."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}},
    )
    mock_client.models.generate_content.side_effect = mock_503

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(GeminiUnavailableError):
            generate_text(
                client=mock_client,
                prompt="Prompt",
                model="gemini-3.8-flash",
                fallback_model="gemini-3.1-flash-lite",
            )
        assert mock_client.models.generate_content.call_count == MAX_RETRIES * 2


def test_failed_generation_does_not_create_duplicate_posts_or_send_telegram_approval(tmp_path):
    """Verify that when Gemini generation fails, no duplicate posts are persisted and no Telegram approval is sent."""
    from database.repositories import RepositoryManager
    from database.repositories.companies import InMemoryCompanyRepository
    from database.repositories.posts import InMemoryPostRepository
    from database.repositories.revisions import InMemoryRevisionRepository
    from database.repositories.approvals import InMemoryApprovalRepository
    from database.repositories.publications import InMemoryPublicationRepository
    from api.services.approval_service import ApprovalService
    from api.services.telegram_service import TelegramService
    from integrations.telegram.mock import MockTelegramProvider
    from agent.orchestrator import DailyOrchestrator
    from agent.exceptions import DailyOrchestrationError

    repos = RepositoryManager(
        companies=InMemoryCompanyRepository(),
        posts=InMemoryPostRepository(),
        revisions=InMemoryRevisionRepository(),
        approvals=InMemoryApprovalRepository(),
        publications=InMemoryPublicationRepository(),
    )
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}},
    )
    mock_tg_provider = MockTelegramProvider()
    approval_svc = ApprovalService(repo_manager=repos, gemini_client=mock_client)
    tg_svc = TelegramService(approval_service=approval_svc, provider=mock_tg_provider)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_client,
        approval_service=approval_svc,
        telegram_service=tg_svc,
        use_in_memory_db=True,
        posts_dir=tmp_path,
    )

    with patch("time.sleep"):
        with pytest.raises(DailyOrchestrationError):
            orchestrator.run(mode="mock", date_str="20261013")

    # 1. No post persisted in database
    assert len(repos.posts.get_previous_posts()) == 0
    # 2. No approval request created
    assert len(repos.approvals._approvals) == 0
    # 3. No Telegram approval notification dispatched
    assert len(mock_tg_provider.sent_messages) == 0
    # 4. No local JSON file created in posts_dir
    assert list(tmp_path.glob("*.json")) == []


def test_generate_text_transient_retry_and_success():
    """Verify generate_text also benefits from transient retries and mappings."""
    mock_client = MagicMock()
    mock_503 = APIError(
        code=503,
        response_json={"error": {"code": 503, "message": "High demand", "status": "UNAVAILABLE"}},
    )
    mock_resp = MagicMock()
    mock_resp.text = "Generated text content"
    mock_client.models.generate_content.side_effect = [mock_503, mock_resp]

    with patch("time.sleep") as mock_sleep:
        text = generate_text(client=mock_client, prompt="Prompt")
        assert text == "Generated text content"
        assert mock_client.models.generate_content.call_count == 2


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_GEMINI_TESTS", "0") != "1",
    reason="Live Gemini API test skipped unless RUN_LIVE_GEMINI_TESTS=1 is set.",
)
def test_live_gemini_api():
    """Live integration test: only executed when a valid GEMINI_API_KEY is available."""
    client = get_gemini_client()
    result = generate_structured_content(
        client=client,
        prompt="Output a title 'Test Live' and integer score 100",
        schema=SampleSchema,
    )
    assert isinstance(result, SampleSchema)
    assert result.score == 100


def test_generate_gemini_image_multimodal_success():
    """Verify generate_gemini_image extracts image bytes from multimodal response."""
    from integrations.gemini import generate_gemini_image

    mock_client = MagicMock()
    mock_part = MagicMock()
    mock_part.inline_data = MagicMock(data=b"\x89PNGFakeImageBytes", mime_type="image/png")
    mock_cand = MagicMock()
    mock_cand.content.parts = [mock_part]
    mock_resp = MagicMock()
    mock_resp.candidates = [mock_cand]
    mock_client.models.generate_content.return_value = mock_resp

    image_bytes, mime = generate_gemini_image(mock_client, "Test prompt")
    assert image_bytes == b"\x89PNGFakeImageBytes"
    assert mime == "image/png"


def test_generate_gemini_image_fallback_to_generate_images():
    """Verify fallback to models.generate_images if multimodal has no image parts."""
    from integrations.gemini import generate_gemini_image

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = MagicMock(candidates=[])

    mock_img = MagicMock()
    mock_img.image = MagicMock(image_bytes=b"JpegBytes", mime_type="image/png")
    mock_client.models.generate_images.return_value = MagicMock(generated_images=[mock_img])

    image_bytes, mime = generate_gemini_image(mock_client, "Test prompt")
    assert image_bytes == b"JpegBytes"
    assert mime == "image/png"




