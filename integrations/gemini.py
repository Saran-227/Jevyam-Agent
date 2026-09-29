"""Gemini integration using Google GenAI SDK."""

from typing import Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types
from google.genai.errors import APIError

from agent.exceptions import (
    GeminiAPIError,
    InvalidGeminiResponseError,
    MissingGeminiApiKeyError,
)
from config.settings import settings

T = TypeVar("T", bound=BaseModel)


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """Initialize and return a Gemini API client.

    Raises:
        MissingGeminiApiKeyError: If no API key is provided or found in settings.
    """
    key = api_key or settings.GEMINI_API_KEY
    if not key or not key.strip():
        raise MissingGeminiApiKeyError(
            "GEMINI_API_KEY is missing or empty. Please configure it in your .env file."
        )
    return genai.Client(api_key=key.strip())


def generate_structured_content(
    client: genai.Client,
    prompt: str,
    schema: Type[T],
    model: Optional[str] = None,
    system_instruction: Optional[str] = None,
) -> T:
    """Generate structured output validated against a Pydantic model.

    Args:
        client: Active Google GenAI client.
        prompt: User prompt content.
        schema: Pydantic model class for expected output.
        model: Gemini model identifier (defaults to settings.GEMINI_MODEL).
        system_instruction: Optional system instruction string.

    Returns:
        Instance of schema populated with model output.

    Raises:
        GeminiAPIError: If the remote API call fails.
        InvalidGeminiResponseError: If response cannot be parsed or validated.
    """
    chosen_model = model or settings.GEMINI_MODEL
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system_instruction,
    )

    try:
        response = client.models.generate_content(
            model=chosen_model,
            contents=prompt,
            config=config,
        )
    except APIError as e:
        raise GeminiAPIError(f"Gemini API error during generation: {e}") from e
    except Exception as e:
        raise GeminiAPIError(f"Unexpected error communicating with Gemini: {e}") from e

    if not response or not response.text:
        raise InvalidGeminiResponseError("Gemini returned an empty response.")

    try:
        return schema.model_validate_json(response.text)
    except ValidationError as e:
        raise InvalidGeminiResponseError(
            f"Failed to validate Gemini response against schema {schema.__name__}: {e}"
        ) from e
    except Exception as e:
        raise InvalidGeminiResponseError(
            f"Failed to parse Gemini JSON response: {e}"
        ) from e


def generate_text(
    client: genai.Client,
    prompt: str,
    model: Optional[str] = None,
    system_instruction: Optional[str] = None,
) -> str:
    """Generate raw text content from Gemini.

    Raises:
        GeminiAPIError: If the API call fails.
        InvalidGeminiResponseError: If response text is empty.
    """
    chosen_model = model or settings.GEMINI_MODEL
    config = (
        types.GenerateContentConfig(system_instruction=system_instruction)
        if system_instruction
        else None
    )

    try:
        response = client.models.generate_content(
            model=chosen_model,
            contents=prompt,
            config=config,
        )
    except APIError as e:
        raise GeminiAPIError(f"Gemini API error: {e}") from e
    except Exception as e:
        raise GeminiAPIError(f"Unexpected error communicating with Gemini: {e}") from e

    if not response or not response.text:
        raise InvalidGeminiResponseError("Gemini returned an empty response.")

    return response.text
