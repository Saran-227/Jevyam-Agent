"""Prompt template loader and renderer."""

from pathlib import Path
from typing import Optional

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt_template(filename: str, prompts_dir: Optional[Path] = None) -> str:
    """Load a markdown prompt template from the prompts directory."""
    directory = prompts_dir or PROMPTS_DIR
    template_path = directory / filename
    if not template_path.exists():
        raise FileNotFoundError(
            f"Prompt template '{filename}' not found at: {template_path.resolve()}"
        )
    return template_path.read_text(encoding="utf-8")


def render_strategist_prompt(
    company_context: str,
    brand_voice: str,
    previous_posts: str,
    current_date: str,
    recent_activity: Optional[str] = None,
    prompts_dir: Optional[Path] = None,
) -> str:
    """Render the strategist prompt with injected variables."""
    template = load_prompt_template("strategist.md", prompts_dir)
    recent_activity_text = (
        f"Recent Company Activity / Focus:\n{recent_activity}"
        if recent_activity
        else "No recent unusual company activities noted. Rely on standard offerings."
    )
    return template.format(
        company_context=company_context,
        brand_voice=brand_voice,
        previous_posts=previous_posts or "No previous posts recorded yet.",
        current_date=current_date,
        recent_activity=recent_activity_text,
    )


def render_writer_prompt(
    company_context: str,
    brand_voice: str,
    topic: str,
    angle: str,
    content_type: str,
    target_audience: str,
    previous_posts: str,
    prompts_dir: Optional[Path] = None,
) -> str:
    """Render the writer prompt with injected variables."""
    template = load_prompt_template("writer.md", prompts_dir)
    return template.format(
        company_context=company_context,
        brand_voice=brand_voice,
        topic=topic,
        angle=angle,
        content_type=content_type,
        target_audience=target_audience,
        previous_posts=previous_posts or "No previous posts recorded yet.",
    )


def render_regeneration_prompt(
    company_context: str,
    brand_voice: str,
    rejected_topic: str,
    rejected_angle: str,
    rejected_content_type: str,
    rejected_hook: str,
    rejected_caption: str,
    rejection_reason: Optional[str] = None,
    previous_posts: Optional[str] = None,
    prompts_dir: Optional[Path] = None,
) -> str:
    """Render the regeneration prompt with injected feedback."""
    template = load_prompt_template("regeneration.md", prompts_dir)
    feedback_text = (
        rejection_reason.strip()
        if rejection_reason and rejection_reason.strip()
        else "No specific rejection reason provided. Formulate a fundamentally different topic/angle/approach."
    )
    return template.format(
        company_context=company_context,
        brand_voice=brand_voice,
        rejected_topic=rejected_topic,
        rejected_angle=rejected_angle,
        rejected_content_type=rejected_content_type,
        rejected_hook=rejected_hook,
        rejected_caption=rejected_caption,
        rejection_reason=feedback_text,
        previous_posts=previous_posts or "No previous posts recorded yet.",
    )


def render_image_brief_prompt(
    topic: str,
    angle: str,
    hook: str,
    caption: str,
    brand_voice: str,
    prompts_dir: Optional[Path] = None,
) -> str:
    """Render the image brief prompt with injected variables."""
    template = load_prompt_template("image_brief.md", prompts_dir)
    return template.format(
        topic=topic,
        angle=angle,
        hook=hook,
        caption=caption,
        brand_voice=brand_voice,
    )

