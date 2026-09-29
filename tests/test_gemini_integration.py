"""Tests for Gemini integration wrapper and error handling."""

import os
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel
from google.genai.errors import APIError

from agent.exceptions import (
    GeminiAPIError,
    InvalidGeminiResponseError,
    MissingGeminiApiKeyError,
)
from integrations.gemini import (
    generate_structured_content,
    get_gemini_client,
)


class SampleSchema(BaseModel):
    title: str
    score: int


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
