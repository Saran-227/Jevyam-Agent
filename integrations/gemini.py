"""Gemini integration using Google GenAI SDK."""

from typing import Optional, Tuple, Type, TypeVar
import logging
import random
import time
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types
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
from config.settings import settings

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF = 2.0
MAX_BACKOFF = 30.0


def get_gemini_client(api_key: Optional[str] = None) -> genai.Client:
    """Initialize and return a Gemini API client.

    Raises:
        MissingGeminiApiKeyError: If no API key is provided or found in settings.
    """
    key = settings.GEMINI_API_KEY if api_key is None else api_key
    if not key or not key.strip():
        raise MissingGeminiApiKeyError(
            "GEMINI_API_KEY is missing or empty. Please configure it in your .env file."
        )
    return genai.Client(api_key=key.strip())


def _is_transient_error(e: Exception) -> bool:
    """Determine whether an error is transient and eligible for retry."""
    if isinstance(e, APIError):
        code = getattr(e, "code", None)
        status = getattr(e, "status", None)

        # Permanent errors should never be retried
        if code in (400, 401, 403, 404) or status in (
            "INVALID_ARGUMENT",
            "UNAUTHENTICATED",
            "PERMISSION_DENIED",
            "NOT_FOUND",
        ):
            return False

        # Transient HTTP status codes
        if code in (429, 502, 503, 504, 408):
            return True

        if status in ("UNAVAILABLE", "RESOURCE_EXHAUSTED"):
            return True

        err_str = str(e).upper()
        return any(
            kw in err_str
            for kw in (
                "503",
                "429",
                "502",
                "504",
                "UNAVAILABLE",
                "RESOURCE_EXHAUSTED",
                "HIGH DEMAND",
                "OVERLOADED",
            )
        )

    # Check for network/timeout errors
    err_type = type(e).__name__
    if isinstance(e, (TimeoutError, ConnectionError)) or any(
        kw in err_type for kw in ("Timeout", "Connect", "Network")
    ):
        return True

    return False


def _extract_retry_after(e: Exception) -> Optional[float]:
    """Extract Retry-After header delay in seconds if provided by the server."""
    if isinstance(e, APIError):
        response = getattr(e, "response", None)
        if response is not None:
            headers = getattr(response, "headers", None)
            if headers:
                retry_val = headers.get("retry-after") or headers.get("Retry-After")
                if retry_val:
                    try:
                        parsed = float(retry_val)
                        if parsed > 0:
                            return parsed
                    except (ValueError, TypeError):
                        pass
    return None


def _calculate_backoff(attempt: int, e: Exception) -> float:
    """Calculate bounded exponential backoff delay with jitter, respecting Retry-After when available."""
    retry_after = _extract_retry_after(e)
    if retry_after is not None and 0 < retry_after <= MAX_BACKOFF:
        return retry_after

    # Exponential backoff: BASE_BACKOFF * (2 ** (attempt - 1)) + jitter
    base = BASE_BACKOFF * (2 ** (attempt - 1))
    jitter = random.uniform(0.1, 1.0)
    return min(base + jitter, MAX_BACKOFF)


def _map_gemini_error(e: Exception) -> GeminiAPIError:
    """Map Google GenAI or network exception to appropriate specific domain exception."""
    if isinstance(
        e,
        (
            GeminiAuthError,
            GeminiRateLimitError,
            GeminiUnavailableError,
            GeminiNetworkError,
        ),
    ):
        return e

    if isinstance(e, APIError):
        code = getattr(e, "code", None)
        status = getattr(e, "status", None)
        msg_upper = str(e).upper()

        if (
            code in (401, 403)
            or status in ("UNAUTHENTICATED", "PERMISSION_DENIED")
            or "PERMISSION_DENIED" in msg_upper
            or "API KEY" in msg_upper
        ):
            return GeminiAuthError(
                f"Gemini API error: authentication/permission error ({code} {status}): {e}"
            )

        if (
            code == 429
            or status == "RESOURCE_EXHAUSTED"
            or "RESOURCE_EXHAUSTED" in msg_upper
            or "429" in msg_upper
        ):
            return GeminiRateLimitError(
                f"Gemini API error: rate limit or quota exceeded ({code} {status}): {e}"
            )

        if (
            code == 503
            or status == "UNAVAILABLE"
            or "UNAVAILABLE" in msg_upper
            or "503" in msg_upper
            or "HIGH DEMAND" in msg_upper
            or "OVERLOADED" in msg_upper
        ):
            return GeminiUnavailableError(
                f"Gemini API error: service temporarily unavailable ({code} {status}): {e}"
            )

        return GeminiAPIError(
            f"Gemini API error during generation ({code} {status}): {e}"
        )

    err_type = type(e).__name__
    if isinstance(e, (TimeoutError, ConnectionError)) or any(
        kw in err_type for kw in ("Timeout", "Connect", "Network")
    ):
        return GeminiNetworkError(
            f"Gemini API error: network error communicating with Gemini ({err_type}): {e}"
        )

    return GeminiAPIError(f"Gemini API error: unexpected error communicating with Gemini: {e}")


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

    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=chosen_model,
                contents=prompt,
                config=config,
            )
            break
        except Exception as e:
            if attempt < MAX_RETRIES and _is_transient_error(e):
                backoff = _calculate_backoff(attempt, e)
                logger.warning(
                    f"Gemini API transient issue on attempt {attempt}/{MAX_RETRIES} ({e}). "
                    f"Retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
            else:
                mapped_err = _map_gemini_error(e)
                raise mapped_err from e

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

    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=chosen_model,
                contents=prompt,
                config=config,
            )
            break
        except Exception as e:
            if attempt < MAX_RETRIES and _is_transient_error(e):
                backoff = _calculate_backoff(attempt, e)
                logger.warning(
                    f"Gemini API transient issue on attempt {attempt}/{MAX_RETRIES} ({e}). "
                    f"Retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
            else:
                mapped_err = _map_gemini_error(e)
                raise mapped_err from e

    if not response or not response.text:
        raise InvalidGeminiResponseError("Gemini returned an empty response.")

    return response.text


def generate_gemini_image(
    client: genai.Client,
    prompt: str,
    model: Optional[str] = None,
    aspect_ratio: str = "1:1",
) -> Tuple[bytes, str]:
    """Generate image bytes and mime type from Gemini image models (e.g. Nano Banana / gemini-3.1-flash-image).

    Args:
        client: Active Google GenAI client.
        prompt: Detailed visual prompt.
        model: Model name override (defaults to settings.GEMINI_IMAGE_MODEL).
        aspect_ratio: Aspect ratio ("1:1", "4:5", "3:4", "16:9", etc.).

    Returns:
        Tuple of (image_bytes, mime_type).

    Raises:
        GeminiAPIError: If generation fails or retries are exhausted.
        InvalidGeminiResponseError: If no image data is returned.
    """
    chosen_model = model or getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    valid_aspect_ratios = {"1:1", "4:5", "3:4", "16:9", "9:16", "4:3"}
    chosen_ratio = aspect_ratio if aspect_ratio in valid_aspect_ratios else "1:1"

    image_cfg = None
    if hasattr(types, "ImageConfig"):
        try:
            image_cfg = types.ImageConfig(aspect_ratio=chosen_ratio)
        except Exception:
            image_cfg = None

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=image_cfg,
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # 1. Primary path: multimodal generate_content (Gemini 3.1 Flash Image / Nano Banana)
            response = client.models.generate_content(
                model=chosen_model,
                contents=prompt,
                config=config,
            )

            if response and getattr(response, "candidates", None):
                for candidate in response.candidates:
                    if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
                        for part in candidate.content.parts:
                            inline_data = getattr(part, "inline_data", None)
                            if inline_data and getattr(inline_data, "data", None):
                                raw_data = inline_data.data
                                mime_type = getattr(inline_data, "mime_type", "image/png")
                                if not isinstance(mime_type, str):
                                    mime_type = "image/png"
                                if isinstance(raw_data, (bytes, bytearray)):
                                    return bytes(raw_data), mime_type
                                elif isinstance(raw_data, str):
                                    import base64
                                    return base64.b64decode(raw_data), mime_type

            # 2. Secondary path: generate_images fallback (if supported on Vertex or Imagen models)
            if hasattr(client.models, "generate_images"):
                try:
                    img_cfg = None
                    if hasattr(types, "GenerateImagesConfig"):
                        img_cfg = types.GenerateImagesConfig(
                            number_of_images=1,
                            aspect_ratio=chosen_ratio,
                            output_mime_type="image/png",
                        )
                    img_resp = client.models.generate_images(
                        model=chosen_model,
                        prompt=prompt,
                        config=img_cfg,
                    )
                    if img_resp and getattr(img_resp, "generated_images", None):
                        gen_img = img_resp.generated_images[0]
                        image_part = getattr(gen_img, "image", None)
                        img_bytes = getattr(image_part, "image_bytes", None) or getattr(gen_img, "image_bytes", None)
                        mime_type = getattr(image_part, "mime_type", "image/png") or "image/png"
                        if not isinstance(mime_type, str):
                            mime_type = "image/png"
                        if isinstance(img_bytes, (bytes, bytearray)):
                            return bytes(img_bytes), mime_type
                        elif isinstance(img_bytes, str):
                            import base64
                            return base64.b64decode(img_bytes), mime_type
                except Exception as img_err:
                    logger.debug(f"generate_images fallback skipped: {img_err}")

            raise InvalidGeminiResponseError(
                f"Gemini image response from model '{chosen_model}' did not contain valid image data."
            )

        except Exception as e:
            if isinstance(e, InvalidGeminiResponseError):
                raise
            if attempt < MAX_RETRIES and _is_transient_error(e):
                backoff = _calculate_backoff(attempt, e)
                logger.warning(
                    f"Gemini image API transient issue on attempt {attempt}/{MAX_RETRIES} ({e}). "
                    f"Retrying in {backoff:.1f}s..."
                )
                time.sleep(backoff)
            else:
                mapped_err = _map_gemini_error(e)
                raise mapped_err from e

    raise InvalidGeminiResponseError("Gemini image generation returned an empty response.")

