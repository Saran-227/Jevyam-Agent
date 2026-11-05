"""Content strategist module for Jevyam Technologies.

Analyzes company knowledge, brand voice, and post history to propose
a diverse, high-value content idea for LinkedIn promoting one of the eight
official service categories.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field, model_validator
from google import genai

from agent.knowledge import CompanyKnowledge
from agent.pillars import (
    calculate_pillar_rotation,
    get_pillar_by_name,
    get_service_url,
    normalize_content_format,
)
from agent.prompts import render_strategist_prompt
from integrations.gemini import generate_structured_content


class ContentIdea(BaseModel):
    """Structured representation of a selected LinkedIn content strategy."""

    topic: str = Field(..., description="The core subject or theme of the post")
    angle: str = Field(
        ...,
        description="The unique viewpoint, technical contrast, or argument being made",
    )
    content_type: str = Field(
        ...,
        description="The combined service category and format (e.g. 'Inventory Management Systems | Problem → Solution')",
    )
    service_category: Optional[str] = Field(
        default="Custom Software Development",
        description="One of the 8 official service categories",
    )
    service_name: Optional[str] = Field(
        default=None,
        description="Official name of the selected service category",
    )
    service_pillar: Optional[str] = Field(
        default=None,
        description="Legacy alias for service_category",
    )
    service_url: Optional[str] = Field(
        default=None,
        description="Official webpage URL for this service",
    )
    content_format: Optional[str] = Field(
        default="Problem → Solution",
        description="One of the 10 official content formats",
    )
    target_audience: str = Field(
        ...,
        description="Target audience persona (e.g. Operations Heads, Sales Directors, Founders, CTOs)",
    )
    reason: str = Field(
        ...,
        description="Strategic justification for why this topic is relevant, non-repetitive, and timely",
    )
    visual_concept: Optional[str] = Field(
        default=None,
        description="High-level visual concept directly representing this service and topic",
    )

    @model_validator(mode="after")
    def sync_service_fields(self) -> "ContentIdea":
        """Synchronize service category, pillar alias, and URL."""
        cat = self.service_category or self.service_pillar or "Custom Software Development"
        matched = get_pillar_by_name(cat)
        if matched:
            canonical_name = matched["name"]
            self.service_category = canonical_name
            self.service_name = canonical_name
            self.service_pillar = canonical_name
            if not self.service_url:
                self.service_url = matched.get("url", get_service_url(canonical_name))
        else:
            self.service_name = self.service_name or cat
            self.service_pillar = self.service_pillar or cat
            if not self.service_url:
                self.service_url = get_service_url(cat)

        self.content_format = normalize_content_format(self.content_format)
        if " | " not in self.content_type:
            self.content_type = f"{self.service_category} | {self.content_format}"
        return self


def format_previous_posts_summary(previous_posts: Union[List[Any], str]) -> str:
    """Format previous posts into a concise summary for prompt injection."""
    if isinstance(previous_posts, str):
        return previous_posts

    if not previous_posts:
        return "No previous posts recorded."

    summaries = []
    for idx, post in enumerate(previous_posts, 1):
        if isinstance(post, dict):
            pid = post.get("post_id", f"Post-{idx}")
            topic = post.get("topic", "N/A")
            angle = post.get("angle", "N/A")
            hook = post.get("hook", "N/A")
            ctype = post.get("content_type", "N/A")
            summaries.append(f"- [{pid}] Service/Format: {ctype} | Topic: {topic} | Angle: {angle}")
        elif hasattr(post, "topic"):
            pid = getattr(post, "post_id", idx)
            ctype = getattr(post, "content_type", "N/A")
            summaries.append(
                f"- [{pid}] Service/Format: {ctype} | Topic: {post.topic} | Angle: {getattr(post, 'angle', 'N/A')}"
            )
        else:
            summaries.append(f"- {post}")

    return "\n".join(summaries)


def select_content_idea(
    client: genai.Client,
    company_knowledge: CompanyKnowledge,
    previous_posts: Union[List[Any], str],
    current_date: Optional[str] = None,
    recent_activity: Optional[str] = None,
    model: Optional[str] = None,
    prompts_dir: Optional[Path] = None,
) -> ContentIdea:
    """Ask Gemini to select a diverse, non-repetitive content idea promoting one official service.

    Args:
        client: Active Gemini API client.
        company_knowledge: Loaded authoritative company knowledge.
        previous_posts: List or text summary of previous post drafts.
        current_date: ISO date or formatted date string (defaults to today).
        recent_activity: Optional recent company activity note.
        model: Optional Gemini model override.
        prompts_dir: Optional path to prompts directory.

    Returns:
        Validated ContentIdea Pydantic model.
    """
    date_str = current_date or datetime.now().strftime("%Y-%m-%d")
    previous_summary = format_previous_posts_summary(previous_posts)

    activity_context = recent_activity or ""
    if isinstance(previous_posts, list) and previous_posts:
        rec_pillar, rec_format, recent_cov = calculate_pillar_rotation(previous_posts, include_format=True)
        rotation_hint = (
            f"[Service Rotation Engine Priority]:\n"
            f"- Recommended Next Service Category: '{rec_pillar['name']}' (Service {rec_pillar['id']})\n"
            f"- Official Service URL: {rec_pillar['url']}\n"
            f"- Recommended Content Format: '{rec_format}'\n"
            f"- Core Focus: {rec_pillar['core_focus']}\n"
            f"- Target Audience: {rec_pillar['target_audience']}\n"
            f"- Recently Promoted Services: {', '.join(recent_cov[:4])}\n"
            f"STRICT RULE: Do NOT repeat the immediately preceding service ({recent_cov[0] if recent_cov else 'None'}). "
            f"Select exactly ONE service category and ensure balanced rotation across all 8 official services."
        )
        activity_context = f"{activity_context}\n{rotation_hint}".strip()

    prompt = render_strategist_prompt(
        company_context=company_knowledge.full_context,
        brand_voice=company_knowledge.brand_voice,
        previous_posts=previous_summary,
        current_date=date_str,
        recent_activity=activity_context,
        prompts_dir=prompts_dir,
    )

    idea = generate_structured_content(
        client=client,
        prompt=prompt,
        schema=ContentIdea,
        model=model,
        system_instruction=(
            "You are the Lead B2B Content Strategist for Jevyam Technologies. "
            "Your sole mission is to market Jevyam's actual agency services to business clients. "
            "You never produce generic tech trivia, AI gossip, or motivational fluff."
        ),
    )
    return idea
