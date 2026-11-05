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
import re
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from google import genai

from agent.exceptions import ImageGenerationError, ImageStorageError
from agent.prompts import render_image_brief_prompt
from database.storage import BaseStorageService
from config.settings import settings
import integrations.gemini as gemini_mod

logger = logging.getLogger("jevyam.image_generator")


def mask_secret_strings(text: Optional[str]) -> str:
    """Mask sensitive tokens, keys, and authorization secrets from diagnostic or error strings."""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"(AIza[0-9A-Za-z-_]{35})", r"[MASKED_API_KEY]", s)
    s = re.sub(r"(sb_publishable_[0-9A-Za-z-_]{20,})", r"[MASKED_SUPABASE_KEY]", s)
    s = re.sub(r"(token=)[0-9A-Za-z-_]+", r"\1[MASKED_TOKEN]", s)
    s = re.sub(r"(bot[0-9]+:)[0-9A-Za-z-_]+", r"\1[MASKED_BOT_TOKEN]", s)
    s = re.sub(r"([0-9]{8,11}:[A-Za-z0-9_-]{30,})", r"[MASKED_TELEGRAM_TOKEN]", s)
    return s


def is_valid_image_url(url: Optional[str]) -> bool:
    """Validate that an image URL is a non-empty HTTP/HTTPS string and not a literal placeholder."""
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if clean.lower() in ("none", "null", ""):
        return False
    return clean.startswith("http://") or clean.startswith("https://")


class ImageGenerationDiagnostic(BaseModel):
    """Safe diagnostic report for image generation and storage execution."""

    provider_name: str
    model: Optional[str] = None
    generation_succeeded: bool = False
    storage_succeeded: bool = False
    image_url: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: float = 0.0


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
    layout: Optional[str] = Field(
        default=None,
        description="Selected visual layout style (e.g. dark_cyber_tech, minimalist_editorial)",
    )


class BaseImageProvider(ABC):
    """Abstract interface for image generation providers."""

    def __init__(self) -> None:
        self.last_diagnostic: Optional[ImageGenerationDiagnostic] = None

    @abstractmethod
    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
        topic: Optional[str] = None,
        caption: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        layout: Optional[str] = None,
        **kwargs: Any,
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
        topic: Optional[str] = None,
        caption: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        layout: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        self.last_diagnostic = ImageGenerationDiagnostic(
            provider_name="PlaceholderImageProvider",
            generation_succeeded=False,
            storage_succeeded=False,
            error_message="Placeholder provider configured: no image generated.",
        )
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
        super().__init__()
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
        topic: Optional[str] = None,
        caption: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        layout: Optional[str] = None,
        **kwargs: Any,
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
            ImageGenerationError: If remote generation fails.
            ImageStorageError: If persistent upload fails.
        """
        start_time = time.perf_counter()
        prompt = expand_image_prompt(brief)
        logger.info(f"Generating visual with model '{self.model}' for post '{post_id}' (rev #{revision})...")

        temp_path: Optional[Path] = None
        try:
            image_bytes, mime_type = gemini_mod.generate_gemini_image(
                client=self.client,
                prompt=prompt,
                model=self.model,
                aspect_ratio=brief.aspect_ratio or "1:1",
            )
            gen_ok = True
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            safe_err = mask_secret_strings(str(e))
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="GeminiImageProvider",
                model=self.model,
                generation_succeeded=False,
                storage_succeeded=False,
                error_message=safe_err,
                duration_ms=elapsed_ms,
            )
            logger.error(f"[ERROR] Gemini image generation failed ({elapsed_ms:.1f}ms): {safe_err}")
            raise ImageGenerationError(f"Gemini image generation failed: {safe_err}") from e

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
                try:
                    storage_url = self.storage_service.upload_image(
                        post_id=post_id or "TEMP",
                        revision=revision,
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                    )
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    safe_err = mask_secret_strings(str(e))
                    self.last_diagnostic = ImageGenerationDiagnostic(
                        provider_name="GeminiImageProvider",
                        model=self.model,
                        generation_succeeded=True,
                        storage_succeeded=False,
                        error_message=safe_err,
                        duration_ms=elapsed_ms,
                    )
                    logger.error(f"[ERROR] Persistent storage upload failed: {safe_err}")
                    if isinstance(e, ImageStorageError):
                        raise
                    raise ImageStorageError(f"Failed to upload visual to storage: {safe_err}") from e

                elapsed_ms = (time.perf_counter() - start_time) * 1000
                self.last_diagnostic = ImageGenerationDiagnostic(
                    provider_name="GeminiImageProvider",
                    model=self.model,
                    generation_succeeded=True,
                    storage_succeeded=True,
                    image_url=mask_secret_strings(storage_url),
                    duration_ms=elapsed_ms,
                )
                logger.info(
                    f"Visual generation and storage completed successfully in {elapsed_ms:.1f}ms: "
                    f"provider=GeminiImageProvider, model={self.model}, url={mask_secret_strings(storage_url)}"
                )
                return storage_url

            result_path = str(output_path or temp_path)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="GeminiImageProvider",
                model=self.model,
                generation_succeeded=True,
                storage_succeeded=False,
                image_url=result_path,
                duration_ms=elapsed_ms,
            )
            return result_path

        except (ImageGenerationError, ImageStorageError):
            raise
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            safe_err = mask_secret_strings(str(e))
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="GeminiImageProvider",
                model=self.model,
                generation_succeeded=gen_ok,
                storage_succeeded=False,
                error_message=safe_err,
                duration_ms=elapsed_ms,
            )
            logger.error(f"[ERROR] Failed processing or storing generated image: {safe_err}")
            raise ImageGenerationError(f"Failed to process and store generated image: {safe_err}") from e

        finally:
            # Guarantees local temporary file cleanup
            try:
                if temp_path and temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass


class BrandedPillowImageProvider(BaseImageProvider):
    """Zero-cost Python/Pillow-based branded image generator for Jevyam Technologies.

    Generates 1200x1200 high-resolution graphics matching company visual guidelines
    (Dark navy / clean white, cyan/blue accents, Jevyam logo mark, clean typography),
    and uploads to Supabase Storage if configured.
    """

    def __init__(
        self,
        storage_service: Optional[BaseStorageService] = None,
        default_layout: Optional[str] = "auto",
    ):
        super().__init__()
        self.storage_service = storage_service
        self.default_layout = default_layout

    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
        topic: Optional[str] = None,
        caption: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        layout: Optional[str] = None,
        previous_layouts: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        """Generate a branded 1200x1200 graphic using Pillow, and upload to storage.

        Args:
            brief: Validated ImageBrief instance.
            post_id: Unique business post ID (e.g. JVY-20261013-001).
            revision: Revision number.
            output_path: Optional local destination path.
            topic: Post topic for headline extraction.
            caption: Post caption for subtitle/copy extraction.
            key_points: Optional bullet points for layout cards.
            layout: Optional layout override or 'auto'.
            previous_layouts: Optional list of previously used layouts to rotate away from.

        Returns:
            Permanent public URL to the uploaded visual, or local path if storage not configured.

        Raises:
            ImageGenerationError: If rendering fails.
            ImageStorageError: If persistent upload fails.
        """
        start_time = time.perf_counter()
        chosen_layout = layout or self.default_layout or "auto"
        prev_layouts = previous_layouts or kwargs.get("previous_layouts")

        from agent.branded_renderer import detect_optimal_layout, render_branded_image

        temp_path: Optional[Path] = None
        gen_ok = False
        try:
            # Extract headline candidate from brief text_on_image or topic
            title_cand = None
            if brief.text_on_image and brief.text_on_image.strip().lower() not in ("none", "null", ""):
                title_cand = brief.text_on_image.strip()
            elif topic:
                title_cand = topic

            service_cat = (
                getattr(brief, "service_category", None)
                or kwargs.get("service_category")
                or kwargs.get("service_pillar")
            )
            if not service_cat:
                from agent.pillars import get_pillar_by_name
                for cand in [brief.visual_concept, topic, caption]:
                    p = get_pillar_by_name(cand or "")
                    if p:
                        service_cat = p["name"]
                        break

            actual_layout = detect_optimal_layout(
                title=title_cand or "",
                caption=caption or "",
                visual_concept=brief.visual_concept,
                preferred_layout=chosen_layout,
                previous_layouts=prev_layouts,
                revision=revision,
                post_id=post_id,
                service_category=service_cat,
            )
            brief.layout = actual_layout

            logger.info(
                f"Generating branded visual (layout='{actual_layout}', service='{service_cat}') for post '{post_id}' (rev #{revision})..."
            )

            png_bytes = render_branded_image(
                title=title_cand,
                topic=topic,
                caption=caption,
                visual_concept=brief.visual_concept,
                service_category=service_cat,
                key_points=key_points,
                layout=actual_layout,
                previous_layouts=prev_layouts,
                revision=revision,
                post_id=post_id,
            )
            gen_ok = True
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            safe_err = mask_secret_strings(str(e))
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="BrandedPillowImageProvider",
                model="pillow-branded-v1",
                generation_succeeded=False,
                storage_succeeded=False,
                error_message=safe_err,
                duration_ms=elapsed_ms,
            )
            logger.error(f"[ERROR] Branded Pillow image generation failed ({elapsed_ms:.1f}ms): {safe_err}")
            raise ImageGenerationError(f"Branded image generation failed: {safe_err}") from e

        # Save to local temporary file during processing
        temp_fd, temp_path_str = tempfile.mkstemp(suffix=".png")
        temp_path = Path(temp_path_str)
        try:
            with open(temp_fd, "wb") as f:
                f.write(png_bytes)

            if post_id:
                try:
                    local_dest = Path("data/posts") / f"{post_id}.png"
                    local_dest.parent.mkdir(parents=True, exist_ok=True)
                    local_dest.write_bytes(png_bytes)
                except Exception:
                    pass

            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(temp_path, output_path)

            if self.storage_service is not None:
                try:
                    storage_url = self.storage_service.upload_image(
                        post_id=post_id or "TEMP",
                        revision=revision,
                        image_bytes=png_bytes,
                        mime_type="image/png",
                    )
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    safe_err = mask_secret_strings(str(e))
                    self.last_diagnostic = ImageGenerationDiagnostic(
                        provider_name="BrandedPillowImageProvider",
                        model="pillow-branded-v1",
                        generation_succeeded=True,
                        storage_succeeded=False,
                        error_message=safe_err,
                        duration_ms=elapsed_ms,
                    )
                    logger.error(f"[ERROR] Persistent storage upload failed: {safe_err}")
                    if isinstance(e, ImageStorageError):
                        raise
                    raise ImageStorageError(f"Failed to upload visual to storage: {safe_err}") from e

                elapsed_ms = (time.perf_counter() - start_time) * 1000
                self.last_diagnostic = ImageGenerationDiagnostic(
                    provider_name="BrandedPillowImageProvider",
                    model="pillow-branded-v1",
                    generation_succeeded=True,
                    storage_succeeded=True,
                    image_url=mask_secret_strings(storage_url),
                    duration_ms=elapsed_ms,
                )
                logger.info(
                    f"Visual generation and storage completed successfully in {elapsed_ms:.1f}ms: "
                    f"provider=BrandedPillowImageProvider, url={mask_secret_strings(storage_url)}"
                )
                return storage_url

            result_path = str(output_path or temp_path)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="BrandedPillowImageProvider",
                model="pillow-branded-v1",
                generation_succeeded=True,
                storage_succeeded=False,
                image_url=result_path,
                duration_ms=elapsed_ms,
            )
            return result_path

        except (ImageGenerationError, ImageStorageError):
            raise
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            safe_err = mask_secret_strings(str(e))
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="BrandedPillowImageProvider",
                model="pillow-branded-v1",
                generation_succeeded=gen_ok,
                storage_succeeded=False,
                error_message=safe_err,
                duration_ms=elapsed_ms,
            )
            logger.error(f"[ERROR] Failed processing or storing generated image: {safe_err}")
            raise ImageGenerationError(f"Failed to process and store generated image: {safe_err}") from e

        finally:
            # Guarantees local temporary file cleanup when uploaded or saved to output_path
            try:
                if temp_path and temp_path.exists() and (self.storage_service is not None or output_path is not None):
                    temp_path.unlink()
            except Exception:
                pass


BrandedImageProvider = BrandedPillowImageProvider


class MockImageProvider(BaseImageProvider):
    """Deterministic mock image provider for tests and dry-run execution."""

    def __init__(
        self,
        base_url: str = "https://mock-storage.supabase.co/storage/v1/object/public/post-images",
        should_fail: bool = False,
    ):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.should_fail = should_fail
        self.generated_images: List[Dict[str, Any]] = []

    def generate_image(
        self,
        brief: ImageBrief,
        post_id: Optional[str] = None,
        revision: int = 1,
        output_path: Optional[Path] = None,
        topic: Optional[str] = None,
        caption: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        layout: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        if self.should_fail:
            self.last_diagnostic = ImageGenerationDiagnostic(
                provider_name="MockImageProvider",
                generation_succeeded=False,
                storage_succeeded=False,
                error_message="Simulated mock image generation failure.",
            )
            raise ImageGenerationError("Simulated mock image generation failure.")

        pid = post_id or "JVY-MOCK"
        url = f"{self.base_url}/{pid}/rev_{revision}.png"
        self.generated_images.append({
            "post_id": pid,
            "revision": revision,
            "brief": brief,
            "url": url,
            "topic": topic,
            "caption": caption,
            "key_points": key_points,
            "layout": layout,
        })
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

        self.last_diagnostic = ImageGenerationDiagnostic(
            provider_name="MockImageProvider",
            generation_succeeded=True,
            storage_succeeded=True,
            image_url=url,
        )
        return url


def resolve_image_provider(
    provider_type: Optional[str] = None,
    client: Optional[genai.Client] = None,
    storage_service: Optional[BaseStorageService] = None,
    use_in_memory: Optional[bool] = None,
) -> BaseImageProvider:
    """Resolve and instantiate the configured image provider.

    Resolution precedence:
    1. If use_in_memory is True, returns MockImageProvider.
    2. Explicit provider_type argument.
    3. settings.IMAGE_PROVIDER from environment (defaults to 'branded').
    """
    if use_in_memory:
        return MockImageProvider()

    ptype = (provider_type or getattr(settings, "IMAGE_PROVIDER", "branded") or "branded").lower().strip()

    if ptype in ("mock", "test"):
        return MockImageProvider()
    elif ptype in ("placeholder", "none"):
        return PlaceholderImageProvider()
    elif ptype in ("branded", "pillow", "local", "zero-cost"):
        from database.storage import SupabaseStorageService
        storage = storage_service or SupabaseStorageService()
        return BrandedPillowImageProvider(storage_service=storage)
    elif ptype in ("gemini", "google"):
        from database.storage import SupabaseStorageService
        storage = storage_service or SupabaseStorageService()
        return GeminiImageProvider(client=client, storage_service=storage)
    else:
        logger.warning(f"Unrecognized IMAGE_PROVIDER '{ptype}', falling back to BrandedPillowImageProvider.")
        from database.storage import SupabaseStorageService
        return BrandedPillowImageProvider(storage_service=storage_service or SupabaseStorageService())


def generate_image_brief(
    client: genai.Client,
    topic: str,
    angle: str,
    hook: str,
    caption: str,
    brand_voice: str,
    service_category: Optional[str] = None,
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
        service_category: Optional official service category.
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
        service_category=service_category,
        prompts_dir=prompts_dir,
    )

    return gemini_mod.generate_structured_content(
        client=client,
        prompt=prompt,
        schema=ImageBrief,
        model=model,
        system_instruction="You are a professional B2B design director for an enterprise tech company. You produce crisp, professional visual briefs.",
    )
