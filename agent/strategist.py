"""Content strategist module for Jevyam Technologies.

Analyzes company knowledge, brand voice, and post history to propose
a diverse, high-value content idea for LinkedIn.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field
from google import genai

from agent.knowledge import CompanyKnowledge
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
        description="The category (e.g. educational, technology insight, AI, automation, software engineering, industry insight, company/project, product/service, problem/solution, behind the scenes, founder/company culture)",
    )
    target_audience: str = Field(
        ...,
        description="Target audience persona (e.g. CTOs, Engineering Leaders, Operations Directors)",
    )
    reason: str = Field(
        ...,
        description="Strategic justification for why this topic is relevant and timely",
    )


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
            summaries.append(f"- [{pid}] Topic: {topic} | Angle: {angle} | Hook: {hook}")
        elif hasattr(post, "topic"):
            summaries.append(
                f"- [{getattr(post, 'post_id', idx)}] Topic: {post.topic} | Angle: {getattr(post, 'angle', 'N/A')} | Hook: {getattr(post, 'hook', 'N/A')}"
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
    """Ask Gemini to select a diverse, non-repetitive content idea.

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

    prompt = render_strategist_prompt(
        company_context=company_knowledge.full_context,
        brand_voice=company_knowledge.brand_voice,
        previous_posts=previous_summary,
        current_date=date_str,
        recent_activity=recent_activity,
        prompts_dir=prompts_dir,
    )

    return generate_structured_content(
        client=client,
        prompt=prompt,
        schema=ContentIdea,
        model=model,
        system_instruction="You are an expert B2B tech content strategist for Jevyam Technologies. You strictly adhere to company facts.",
    )
