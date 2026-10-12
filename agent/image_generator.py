"""Visual image brief and generation module for Jevyam Technologies.

Generates structured image briefs aligned with LinkedIn posts and provides
image generation using Google GenAI SDK (Nano Banana / gemini-3.1-flash-image)
backed by persistent Supabase Storage.
"""

from abc import ABC, abstractmethod
import logging
from pathlib import Path
import shutil
import tempfile
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from google import genai

from agent.exceptions import ImageGenerationError
from agent.prompts import render_image_brief_prompt
from database.storage import BaseStorageService
from config.settings import settings
from integrations.gemini import generate_gemini_image, generate_structured_content

logger = logging.getLogger("jevyam.image_generator")


class ImageBrief(BaseModel):
    """Structured design specification for post imagery."""

    visual_concept: str = Field(
        ...,
        description="Detailed description of what is depicted in the graphic",
    )
    style: str = Field(
        ...,
        description="Specific design aesthetic (e.g. Minimalist tech vector, clean 2D system blueprint)",
    )
    composition: str = Field(
        ...,
        description="Visual framing, layout focal point, and balance of negative space",
    )
    color_direction: str = Field(
        ...,
        description="Palette direction (e.g. neutral slate, deep navy, subtle technical blue accents)",
    )
    text_on_image: str = Field(
        ...,
        description="Concise 3-6 word anchor phrase or headline rendered on graphic, or 'None'",
    )
    aspect_ratio: str = Field(
        default="1:1",
        description="Aspect ratio for LinkedIn feed, default 1:1",
    )


class BaseImageProvider(ABC):
    """Abstract interface for image generation providers."""

    @abstractmethod
    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
    ) -> Optional[str]:
        """Generate an image from an ImageBrief and return persistent image URL or path."""
        pass


class PlaceholderImageProvider(BaseImageProvider):
    """Placeholder provider that returns None without external image API calls."""

    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
    ) -> Optional[str]:
        return None


def expand_image_prompt(brief: ImageBrief) -> str:
    """Expand ImageBrief into a polished, professional LinkedIn visual prompt for Jevyam Technologies."""
    prompt_parts = [
        "Create a professional, high-resolution, modern enterprise technology graphic for a LinkedIn company feed.",
        f"Core Subject & Visual Concept: {brief.visual_concept}.",
        f"Design Aesthetic: {brief.style}.",
        f"Composition & Framing: {brief.composition}.",
        f"Color Direction: {brief.color_direction}.",
    ]
    if brief.text_on_image and brief.text_on_image.strip().lower() not in ("none", "null", ""):
        prompt_parts.append(f"Visual Text Accent: '{brief.text_on_image.strip()}'.")

    prompt_parts.extend([
        "Visual Requirements & Negative Constraints:",
        "- Elegant, modern enterprise B2B tech aesthetic (suitable for Jevyam Technologies: cloud automation, multi-agent systems, idempotent backend workflows).",
        "- Prefer clean 4:5 or 1:1 framing with balanced negative space.",
        "- Absolutely NO distorted or unreadable text, NO spelling errors, NO fake company logos, NO watermarks added by us, and NO clutter.",
        "- High-clarity digital illustration or architectural blueprint with crisp vector-like fidelity.",
    ])
    return "\n".join(prompt_parts)


class GeminiImageProvider(BaseImageProvider):
    """Official Google GenAI SDK Gemini image generation provider (Nano Banana / gemini-3.1-flash-image)."""

    def __init__(
        self,
        client: Optional[genai.Client] = None,
        storage_service: Optional[BaseStorageService] = None,
        model: Optional[str] = None,
    ):
        self._client = client
        self.storage_service = storage_service
        self.model = model or getattr(settings, "GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            from integrations.gemini import get_gemini_client
            self._client = get_gemini_client()
        return self._client

    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
    ) -> Optional[str]:
        """Generate an image from ImageBrief, save to a temporary file during processing, and upload to storage.

        Args:
            brief: Validated ImageBrief instance.
            post_id: Unique business post ID (e.g. JVY-20261013-001).
            revision: Revision number.
            output_path: Optional local destination path.

        Returns:
            Permanent public URL to the uploaded visual.

        Raises:
            ImageGenerationError: If generation or storage fails.
        """
        prompt = expand_image_prompt(brief)
        logger.info(f"Generating visual with model '{self.model}' for post '{post_id}' (rev #{revision})...")

        try:
            image_bytes, mime_type = generate_gemini_image(
                client=self.client,
                prompt=prompt,
                model=self.model,
                aspect_ratio=brief.aspect_ratio or "1:1",
            )
        except Exception as e:
            logger.error(f"[ERROR] Gemini image generation failed: {e}")
            raise ImageGenerationError(f"Gemini image generation failed: {e}") from e

        # Save to local temporary file only during processing
        temp_fd, temp_path_str = tempfile.mkstemp(suffix=".png")
        temp_path = Path(temp_path_str)
        try:
            with open(temp_fd, "wb") as f:
                f.write(image_bytes)

            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(temp_path, output_path)

            if self.storage_service is not None:
                storage_url = self.storage_service.upload_image(
                    post_id=post_id or "TEMP",
                    revision=revision,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                )
                return storage_url

            return str(output_path or temp_path)

        except Exception as e:
            if isinstance(e, ImageGenerationError):
                raise
            logger.error(f"[ERROR] Failed processing or storing generated image: {e}")
            raise ImageGenerationError(f"Failed to process and store generated image: {e}") from e

        finally:
            # Guarantees local temporary file cleanup
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass


class MockImageProvider(BaseImageProvider):
    """Deterministic mock image provider for tests and dry-run execution."""

    def __init__(
        self,
        base_url: str = "https://mock-storage.supabase.co/storage/v1/object/public/post-images",
        should_fail: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.should_fail = should_fail
        self.generated_images: List[Dict[str, Any]] = []

    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
    ) -> Optional[str]:
        if self.should_fail:
            raise ImageGenerationError("Simulated mock image generation failure.")

        pid = post_id or "JVY-MOCK"
        url = f"{self.base_url}/{pid}/rev_{revision}.png"
        self.generated_images.append({
            "post_id": pid,
            "revision": revision,
            "brief": brief,
            "url": url,
        })
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
        return url


def generate_image_brief(
    client: genai.Client,
    topic: str,
    angle: str,
    hook: str,
    caption: str,
    brand_voice: str,
    model: Optional[str] = None,
    prompts_dir: Optional[Path] = None,
) -> ImageBrief:
    """Generate a structured image brief for a LinkedIn post using Gemini.

    Args:
        client: Active Gemini client.
        topic: Topic of the post.
        angle: Angle of the post.
        hook: Opening hook.
        caption: Full post caption.
        brand_voice: Brand voice guidelines.
        model: Optional model override.
        prompts_dir: Optional custom prompts directory.

    Returns:
        Validated ImageBrief instance.
    """
    prompt = render_image_brief_prompt(
        topic=topic,
        angle=angle,
        hook=hook,
        caption=caption,
        brand_voice=brand_voice,
        prompts_dir=prompts_dir,
    )

    return generate_structured_content(
        client=client,
        prompt=prompt,
        schema=ImageBrief,
        model=model,
        system_instruction="You are a professional B2B design director for an enterprise tech company. You produce crisp, professional visual briefs.",
    )
