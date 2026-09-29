"""Visual image brief and generation module for Jevyam Technologies.

Generates structured image briefs aligned with LinkedIn posts and provides
a pluggable provider architecture for future image generation backends.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from google import genai

from agent.prompts import render_image_brief_prompt
from integrations.gemini import generate_structured_content


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
    """Abstract interface for image generation providers (e.g. Imagen, DALL-E, local SD)."""

    @abstractmethod
    def generate_image(self, brief: ImageBrief, output_path: Optional[Path] = None) -> Optional[str]:
        """Generate an image from an ImageBrief and return image path or URL."""
        pass


class PlaceholderImageProvider(BaseImageProvider):
    """Phase 1 placeholder provider that logs the brief without external image API calls."""

    def generate_image(self, brief: ImageBrief, output_path: Optional[Path] = None) -> Optional[str]:
        # In Phase 1, image generation API is optional.
        # This will be replaced by an actual provider in later phases.
        return None


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
