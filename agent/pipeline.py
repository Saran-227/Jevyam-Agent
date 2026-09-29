"""Autonomous content generation pipeline for Jevyam Technologies.

Orchestrates Knowledge -> Strategist -> Duplicate Check -> Writer -> Image Brief -> Database (Post + Revision).
"""

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field
from google import genai

from agent.exceptions import (
    ContentGenerationError,
    DuplicateContentError,
)
from agent.image_generator import ImageBrief, generate_image_brief
from agent.knowledge import CompanyKnowledge, load_company_knowledge
from agent.prompts import render_regeneration_prompt
from agent.repetition import check_repetition
from agent.strategist import ContentIdea, format_previous_posts_summary, select_content_idea
from agent.writer import LinkedInPostContent, generate_linkedin_post
from database.models import Post, PostRevision, PostStatus
from database.repositories import RepositoryManager, get_repository_manager
from integrations.gemini import generate_structured_content, get_gemini_client

DEFAULT_POSTS_DIR = Path(__file__).resolve().parent.parent / "data" / "posts"


class LinkedInDraft(BaseModel):
    """Structured representation of a complete LinkedIn post package."""

    post_id: str = Field(..., description="Unique post identifier, e.g. JVY-20260929-001")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp")
    topic: str = Field(..., description="The core subject of the post")
    angle: str = Field(..., description="The unique viewpoint or technical argument")
    content_type: str = Field(..., description="Content category")
    target_audience: str = Field(..., description="Target reader persona")
    hook: str = Field(..., description="Attention-grabbing opening hook")
    caption: str = Field(..., description="Complete ready-to-publish LinkedIn post text")
    hashtags: List[str] = Field(..., description="5-8 formatted hashtags")
    call_to_action: str = Field(..., description="Closing engagement question or prompt")
    visual_concept: str = Field(..., description="Core concept for the accompanying visual")
    image_brief: ImageBrief = Field(..., description="Structured image generation brief")
    revision: int = Field(default=1, description="Revision number of this draft")
    status: str = Field(default="DRAFT", description="Workflow approval status")


def generate_post_id(
    date_str: Optional[str] = None,
    posts_dir: Optional[Path] = None,
    repo_manager: Optional[RepositoryManager] = None,
) -> str:
    """Generate a unique sequential post ID for the given date (JVY-YYYYMMDD-XXX)."""
    target_date = date_str or datetime.now().strftime("%Y%m%d")
    highest_seq = 0

    # 1. Check database sequence if repository manager provided
    if repo_manager:
        highest_seq = max(highest_seq, repo_manager.posts.get_next_sequence_for_date(target_date) - 1)

    # 2. Check local posts directory (if exists)
    directory = posts_dir or DEFAULT_POSTS_DIR
    if directory.exists():
        pattern = re.compile(rf"^JVY-{target_date}-(\d{{3}})\.json$")
        for file_path in directory.glob(f"JVY-{target_date}-*.json"):
            match = pattern.match(file_path.name)
            if match:
                seq = int(match.group(1))
                if seq > highest_seq:
                    highest_seq = seq

    new_seq = highest_seq + 1
    return f"JVY-{target_date}-{new_seq:03d}"


def load_previous_drafts(posts_dir: Optional[Path] = None) -> List[LinkedInDraft]:
    """Load previously saved drafts from local JSON storage (fallback/export utility)."""
    directory = posts_dir or DEFAULT_POSTS_DIR
    if not directory.exists():
        return []

    drafts: List[LinkedInDraft] = []
    for file_path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            drafts.append(LinkedInDraft.model_validate(data))
        except Exception:
            continue

    drafts.sort(key=lambda d: d.generated_at, reverse=True)
    return drafts


def save_draft(draft: LinkedInDraft, posts_dir: Optional[Path] = None) -> Path:
    """Save completed draft to local JSON storage."""
    directory = posts_dir or DEFAULT_POSTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / f"{draft.post_id}.json"
    file_path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
    return file_path


def run_content_pipeline(
    client: Optional[genai.Client] = None,
    company_dir: Optional[Path] = None,
    posts_dir: Optional[Path] = None,
    prompts_dir: Optional[Path] = None,
    current_date: Optional[str] = None,
    recent_activity: Optional[str] = None,
    max_retries: int = 3,
    model: Optional[str] = None,
    repo_manager: Optional[RepositoryManager] = None,
    use_in_memory: Optional[bool] = None,
    save_local_copy: bool = True,
) -> LinkedInDraft:
    """Execute the end-to-end LinkedIn content generation pipeline.

    1. Load company knowledge and brand guidelines.
    2. Load previous post history from Database (and local fallback).
    3. Generate and validate content idea with duplicate detection (up to max_retries).
    4. Write complete LinkedIn post (hook, caption, hashtags, CTA).
    5. Generate structured companion image brief.
    6. Persist Post master record and initial PostRevision to Supabase / Repository.
    7. Optionally save local JSON export.

    Returns:
        Complete validated LinkedInDraft.

    Raises:
        DuplicateContentError: If no non-repetitive idea is found within max_retries.
        ContentGenerationError: If generation fails unexpectedly.
    """
    ai_client = client or get_gemini_client()
    company_knowledge = load_company_knowledge(company_dir)
    repos = repo_manager or get_repository_manager(use_in_memory=use_in_memory)

    # Load previous posts from database as primary source of truth
    db_posts = repos.posts.get_previous_posts(limit=50)

    # Also load local drafts if available and combine (avoiding duplicates)
    local_drafts = load_previous_drafts(posts_dir)
    existing_pids = {p.post_id for p in db_posts}
    combined_previous: List[Any] = list(db_posts)
    for ld in local_drafts:
        if ld.post_id not in existing_pids:
            combined_previous.append(ld)

    # 1. Content Strategist with Duplicate / Repetition Control
    selected_idea: Optional[ContentIdea] = None
    last_repetition_reason: Optional[str] = None
    attempt_history: List[str] = []

    for attempt in range(1, max_retries + 1):
        all_previous_summary = format_previous_posts_summary(combined_previous)
        if attempt_history:
            all_previous_summary += (
                f"\nRejected Candidate Ideas This Run (DO NOT REUSE):\n"
                + "\n".join(f"- {att}" for att in attempt_history)
            )

        candidate_idea = select_content_idea(
            client=ai_client,
            company_knowledge=company_knowledge,
            previous_posts=all_previous_summary,
            current_date=current_date,
            recent_activity=recent_activity,
            model=model,
            prompts_dir=prompts_dir,
        )

        is_dup, reason = check_repetition(
            candidate_topic=candidate_idea.topic,
            previous_posts=combined_previous,
        )

        if not is_dup:
            selected_idea = candidate_idea
            break

        last_repetition_reason = reason
        attempt_history.append(f"Topic: {candidate_idea.topic} (Reason: {reason})")

    if not selected_idea:
        raise DuplicateContentError(
            f"Failed to generate a non-repetitive topic after {max_retries} attempts. "
            f"Last check flagged: {last_repetition_reason}"
        )

    # 2. LinkedIn Post Writer
    try:
        post_content: LinkedInPostContent = generate_linkedin_post(
            client=ai_client,
            company_knowledge=company_knowledge,
            idea=selected_idea,
            previous_posts=combined_previous,
            model=model,
            prompts_dir=prompts_dir,
        )
    except Exception as e:
        raise ContentGenerationError(f"LinkedIn writer failed: {e}") from e

    # 3. Image Brief Generator
    try:
        image_brief: ImageBrief = generate_image_brief(
            client=ai_client,
            topic=selected_idea.topic,
            angle=selected_idea.angle,
            hook=post_content.hook,
            caption=post_content.caption,
            brand_voice=company_knowledge.brand_voice,
            model=model,
            prompts_dir=prompts_dir,
        )
    except Exception as e:
        raise ContentGenerationError(f"Image brief generation failed: {e}") from e

    # 4. Generate post_id
    date_formatted = current_date.replace("-", "") if current_date else None
    post_id = generate_post_id(
        date_str=date_formatted,
        posts_dir=posts_dir,
        repo_manager=repos,
    )

    # Lookup company
    company = repos.companies.get_by_slug("jevyam")
    company_id = company.id if company else None

    # 5. Persist to Database: Master Post (status=DRAFT, revision=1)
    post_entity = Post(
        post_id=post_id,
        company_id=company_id,
        status=PostStatus.DRAFT,
        current_revision=1,
        content_type=selected_idea.content_type,
        topic=selected_idea.topic,
        angle=selected_idea.angle,
        target_audience=selected_idea.target_audience,
        hook=post_content.hook,
        caption=post_content.caption,
        hashtags=post_content.hashtags,
        call_to_action=post_content.call_to_action,
        visual_concept=image_brief.visual_concept,
        image_brief=image_brief,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    saved_post = repos.posts.create(post_entity)

    # 6. Persist to Database: Initial PostRevision (revision_number=1)
    revision_entity = PostRevision(
        post_id=post_id,
        revision_number=1,
        topic=selected_idea.topic,
        angle=selected_idea.angle,
        content_type=selected_idea.content_type,
        target_audience=selected_idea.target_audience,
        hook=post_content.hook,
        caption=post_content.caption,
        hashtags=post_content.hashtags,
        call_to_action=post_content.call_to_action,
        visual_concept=image_brief.visual_concept,
        image_brief=image_brief,
        created_at=datetime.now(),
    )
    repos.revisions.create(revision_entity)

    # 7. Construct output draft
    draft = LinkedInDraft(
        post_id=saved_post.post_id,
        generated_at=str(saved_post.created_at or datetime.now().isoformat()),
        topic=saved_post.topic,
        angle=saved_post.angle,
        content_type=saved_post.content_type,
        target_audience=saved_post.target_audience,
        hook=saved_post.hook,
        caption=saved_post.caption,
        hashtags=saved_post.hashtags,
        call_to_action=saved_post.call_to_action,
        visual_concept=saved_post.visual_concept,
        image_brief=image_brief,
        revision=saved_post.current_revision,
        status=saved_post.status.value,
    )

    if save_local_copy:
        save_draft(draft, posts_dir)

    return draft


def regenerate_draft(
    rejected_draft: Union[LinkedInDraft, Post, str],
    rejection_reason: Optional[str] = None,
    client: Optional[genai.Client] = None,
    company_dir: Optional[Path] = None,
    posts_dir: Optional[Path] = None,
    prompts_dir: Optional[Path] = None,
    model: Optional[str] = None,
    repo_manager: Optional[RepositoryManager] = None,
    use_in_memory: Optional[bool] = None,
    save_local_copy: bool = True,
) -> LinkedInDraft:
    """Regenerate a draft by intentionally pivoting topic, angle, hook, or structure.

    1. Load existing post and latest revision from database.
    2. Prompt Gemini for a pivoted strategy.
    3. Generate new LinkedIn post and companion image brief.
    4. Persist new row in post_revisions (revision_number = current_revision + 1).
    5. Update post in posts table (increment current_revision, status = PENDING_APPROVAL).
    6. Return updated LinkedInDraft.

    Returns:
        New LinkedInDraft reflecting the updated revision.
    """
    ai_client = client or get_gemini_client()
    company_knowledge = load_company_knowledge(company_dir)
    repos = repo_manager or get_repository_manager(use_in_memory=use_in_memory)

    # Extract target post_id and current draft info
    if isinstance(rejected_draft, str):
        post_id = rejected_draft
        existing_post = repos.posts.get_by_post_id(post_id)
        if not existing_post:
            raise ValueError(f"Post with post_id '{post_id}' not found in repository.")
        rejected_topic = existing_post.topic
        rejected_angle = existing_post.angle
        rejected_content_type = existing_post.content_type
        rejected_hook = existing_post.hook
        rejected_caption = existing_post.caption
        current_rev_num = existing_post.current_revision
    else:
        post_id = rejected_draft.post_id
        rejected_topic = rejected_draft.topic
        rejected_angle = rejected_draft.angle
        rejected_content_type = rejected_draft.content_type
        rejected_hook = rejected_draft.hook
        rejected_caption = rejected_draft.caption
        current_rev_num = getattr(rejected_draft, "revision", getattr(rejected_draft, "current_revision", 1))

        existing_post = repos.posts.get_by_post_id(post_id)
        if not existing_post:
            # Seed in repository if coming from external test
            post_entity = Post(
                post_id=post_id,
                status=PostStatus.DRAFT,
                current_revision=current_rev_num,
                content_type=rejected_content_type,
                topic=rejected_topic,
                angle=rejected_angle,
                target_audience=rejected_draft.target_audience,
                hook=rejected_hook,
                caption=rejected_caption,
                hashtags=rejected_draft.hashtags,
                call_to_action=rejected_draft.call_to_action,
                visual_concept=rejected_draft.visual_concept,
                image_brief=rejected_draft.image_brief,
            )
            existing_post = repos.posts.create(post_entity)
            repos.revisions.create(
                PostRevision(
                    post_id=post_id,
                    revision_number=current_rev_num,
                    topic=rejected_topic,
                    angle=rejected_angle,
                    content_type=rejected_content_type,
                    target_audience=rejected_draft.target_audience,
                    hook=rejected_hook,
                    caption=rejected_caption,
                    hashtags=rejected_draft.hashtags,
                    call_to_action=rejected_draft.call_to_action,
                    visual_concept=rejected_draft.visual_concept,
                    image_brief=rejected_draft.image_brief,
                )
            )

    # Next revision number
    latest_rev = repos.revisions.get_latest_revision(post_id)
    next_rev_num = (latest_rev.revision_number + 1) if latest_rev else (current_rev_num + 1)

    # Load history
    db_posts = repos.posts.get_previous_posts(limit=50)
    previous_summary = format_previous_posts_summary(db_posts)

    # Generate new strategic direction addressing feedback
    prompt = render_regeneration_prompt(
        company_context=company_knowledge.full_context,
        brand_voice=company_knowledge.brand_voice,
        rejected_topic=rejected_topic,
        rejected_angle=rejected_angle,
        rejected_content_type=rejected_content_type,
        rejected_hook=rejected_hook,
        rejected_caption=rejected_caption,
        rejection_reason=rejection_reason,
        previous_posts=previous_summary,
        prompts_dir=prompts_dir,
    )

    new_idea = generate_structured_content(
        client=ai_client,
        prompt=prompt,
        schema=ContentIdea,
        model=model,
        system_instruction="You are a senior tech strategist pivoting content strategy to fix a rejected post.",
    )

    # Write new post based on pivoted strategy
    post_content = generate_linkedin_post(
        client=ai_client,
        company_knowledge=company_knowledge,
        idea=new_idea,
        previous_posts=db_posts,
        model=model,
        prompts_dir=prompts_dir,
    )

    # Generate new visual brief matching new post
    image_brief = generate_image_brief(
        client=ai_client,
        topic=new_idea.topic,
        angle=new_idea.angle,
        hook=post_content.hook,
        caption=post_content.caption,
        brand_voice=company_knowledge.brand_voice,
        model=model,
        prompts_dir=prompts_dir,
    )

    # Persist NEW revision snapshot to post_revisions
    new_rev = PostRevision(
        post_id=post_id,
        revision_number=next_rev_num,
        topic=new_idea.topic,
        angle=new_idea.angle,
        content_type=new_idea.content_type,
        target_audience=new_idea.target_audience,
        hook=post_content.hook,
        caption=post_content.caption,
        hashtags=post_content.hashtags,
        call_to_action=post_content.call_to_action,
        visual_concept=image_brief.visual_concept,
        image_brief=image_brief,
        rejection_reason=rejection_reason,
        created_at=datetime.now(),
    )
    repos.revisions.create(new_rev)

    # Update Post in posts table
    existing_post.current_revision = next_rev_num
    existing_post.status = PostStatus.PENDING_APPROVAL
    existing_post.topic = new_idea.topic
    existing_post.angle = new_idea.angle
    existing_post.content_type = new_idea.content_type
    existing_post.target_audience = new_idea.target_audience
    existing_post.hook = post_content.hook
    existing_post.caption = post_content.caption
    existing_post.hashtags = post_content.hashtags
    existing_post.call_to_action = post_content.call_to_action
    existing_post.visual_concept = image_brief.visual_concept
    existing_post.image_brief = image_brief
    existing_post.updated_at = datetime.now()

    updated_post = repos.posts.update(existing_post)

    # Build return draft
    regenerated = LinkedInDraft(
        post_id=updated_post.post_id,
        generated_at=str(updated_post.updated_at or datetime.now().isoformat()),
        topic=updated_post.topic,
        angle=updated_post.angle,
        content_type=updated_post.content_type,
        target_audience=updated_post.target_audience,
        hook=updated_post.hook,
        caption=updated_post.caption,
        hashtags=updated_post.hashtags,
        call_to_action=updated_post.call_to_action,
        visual_concept=updated_post.visual_concept,
        image_brief=image_brief,
        revision=updated_post.current_revision,
        status=updated_post.status.value,
    )

    if save_local_copy:
        save_draft(regenerated, posts_dir)

    return regenerated
