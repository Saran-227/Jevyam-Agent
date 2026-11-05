"""LinkedIn writer module for Jevyam Technologies.

Generates high-signal, human-sounding LinkedIn posts adhering strictly to
Jevyam agency service offerings, brand voice, and factual boundaries.
"""

from pathlib import Path
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from google import genai

from agent.knowledge import CompanyKnowledge
from agent.prompts import render_writer_prompt
from agent.strategist import ContentIdea, format_previous_posts_summary
from integrations.gemini import generate_structured_content


class LinkedInPostContent(BaseModel):
    """Structured representation of generated LinkedIn post text."""

    hook: str = Field(
        ...,
        description="The opening 1-2 lines designed to capture attention without clickbait",
    )
    caption: str = Field(
        ...,
        description="Complete, ready-to-publish LinkedIn post text including the hook, body paragraphs, and call to action",
    )
    hashtags: List[str] = Field(
        ...,
        description="4 to 6 relevant hashtags prefixed with # (e.g. ['#InventoryManagement', '#BusinessOperations'])",
    )
    call_to_action: str = Field(
        ...,
        description="Thoughtful concluding question or prompt inviting authentic peer engagement or service inquiry",
    )

    @field_validator("hashtags")
    @classmethod
    def format_hashtags(cls, tags: List[str]) -> List[str]:
        """Ensure hashtags have clean '#' prefix and no spaces."""
        cleaned = []
        for tag in tags:
            tag_str = tag.strip()
            if not tag_str.startswith("#"):
                tag_str = f"#{tag_str}"
            cleaned.append(tag_str)
        return cleaned


def generate_linkedin_post(
    client: genai.Client,
    company_knowledge: CompanyKnowledge,
    idea: ContentIdea,
    previous_posts: Union[List[Any], str],
    model: Optional[str] = None,
    prompts_dir: Optional[Path] = None,
) -> LinkedInPostContent:
    """Generate a LinkedIn post from strategic direction.

    Args:
        client: Active Gemini API client.
        company_knowledge: Loaded company knowledge and brand voice.
        idea: Selected content strategy/idea.
        previous_posts: Summary or list of previously published drafts.
        model: Optional model override.
        prompts_dir: Optional prompts directory.

    Returns:
        LinkedInPostContent with hook, caption, hashtags, and CTA.
    """
    previous_summary = format_previous_posts_summary(previous_posts)

    service_url = getattr(idea, "service_url", None)
    service_name = getattr(idea, "service_name", None) or getattr(idea, "service_category", None)
    content_format = getattr(idea, "content_format", None)

    prompt = render_writer_prompt(
        company_context=company_knowledge.full_context,
        brand_voice=company_knowledge.brand_voice,
        topic=idea.topic,
        angle=idea.angle,
        content_type=idea.content_type,
        target_audience=idea.target_audience,
        previous_posts=previous_summary,
        service_url=service_url,
        service_name=service_name,
        content_format=content_format,
        prompts_dir=prompts_dir,
    )

    return generate_structured_content(
        client=client,
        prompt=prompt,
        schema=LinkedInPostContent,
        model=model,
        system_instruction=(
            "You are the Senior B2B Marketing Writer for Jevyam Technologies. "
            "You write authoritative, human-sounding LinkedIn posts that market Jevyam's agency services. "
            "Never use fake statistics, fake case studies, or hype clichés. "
            "Never include image generation instructions or visual concepts inside the post caption."
        ),
    )
