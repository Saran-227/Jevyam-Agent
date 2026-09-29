"""Unit tests for Pydantic models, post ID generation, and local JSON storage."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from agent.image_generator import ImageBrief
from agent.pipeline import (
    LinkedInDraft,
    generate_post_id,
    load_previous_drafts,
    save_draft,
)
from agent.writer import LinkedInPostContent


def test_image_brief_validation():
    brief = ImageBrief(
        visual_concept="Isometric server topology connected to neural nodes",
        style="Minimalist dark mode technical vector",
        composition="Center focused, ample negative space",
        color_direction="Deep slate grey with subtle cyan accents",
        text_on_image="RAG Without the Chaos",
        aspect_ratio="1:1",
    )
    assert brief.aspect_ratio == "1:1"
    assert "Isometric" in brief.visual_concept


def test_linkedin_post_content_hashtag_formatting():
    post = LinkedInPostContent(
        hook="Most enterprise RAG pipelines fail in production.",
        caption="Most enterprise RAG pipelines fail in production...\n\nHere is how to solve it.",
        hashtags=["AI", "#Automation", "  #SoftwareEngineering  "],
        call_to_action="How does your team handle vector deduplication?",
    )
    assert post.hashtags == ["#AI", "#Automation", "#SoftwareEngineering"]


def test_linkedin_draft_model_validation():
    brief = ImageBrief(
        visual_concept="Concept",
        style="Style",
        composition="Comp",
        color_direction="Color",
        text_on_image="Text",
    )
    draft = LinkedInDraft(
        post_id="JVY-20260929-001",
        generated_at="2026-09-29T10:00:00",
        topic="Modern Vector Pipelines",
        angle="Solving embedding drift",
        content_type="technology insight",
        target_audience="CTOs and Data Engineers",
        hook="Stop embedding raw text without normalization.",
        caption="Stop embedding raw text without normalization.\n\nHere is why...",
        hashtags=["#AI", "#DataEngineering"],
        call_to_action="What is your pipeline?",
        visual_concept="Concept",
        image_brief=brief,
    )
    assert draft.status == "DRAFT"
    assert draft.revision == 1
    assert draft.post_id == "JVY-20260929-001"


def test_generate_post_id_sequence(tmp_path: Path):
    # First ID
    id_1 = generate_post_id(date_str="20260929", posts_dir=tmp_path)
    assert id_1 == "JVY-20260929-001"

    # Simulate saving first post
    (tmp_path / f"{id_1}.json").write_text("{}", encoding="utf-8")

    # Second ID
    id_2 = generate_post_id(date_str="20260929", posts_dir=tmp_path)
    assert id_2 == "JVY-20260929-002"

    (tmp_path / f"{id_2}.json").write_text("{}", encoding="utf-8")

    # Third ID
    id_3 = generate_post_id(date_str="20260929", posts_dir=tmp_path)
    assert id_3 == "JVY-20260929-003"


def test_save_and_load_drafts(tmp_path: Path):
    brief = ImageBrief(
        visual_concept="Concept",
        style="Style",
        composition="Comp",
        color_direction="Color",
        text_on_image="None",
    )
    draft1 = LinkedInDraft(
        post_id="JVY-20260929-001",
        generated_at="2026-09-29T10:00:00",
        topic="Topic 1",
        angle="Angle 1",
        content_type="educational",
        target_audience="Engineers",
        hook="Hook 1",
        caption="Caption 1",
        hashtags=["#AI"],
        call_to_action="CTA 1",
        visual_concept="Visual 1",
        image_brief=brief,
        revision=1,
    )
    draft2 = LinkedInDraft(
        post_id="JVY-20260929-002",
        generated_at="2026-09-29T11:00:00",
        topic="Topic 2",
        angle="Angle 2",
        content_type="technology insight",
        target_audience="CTOs",
        hook="Hook 2",
        caption="Caption 2",
        hashtags=["#Cloud"],
        call_to_action="CTA 2",
        visual_concept="Visual 2",
        image_brief=brief,
        revision=1,
    )

    path1 = save_draft(draft1, posts_dir=tmp_path)
    path2 = save_draft(draft2, posts_dir=tmp_path)

    assert path1.exists()
    assert path2.exists()

    loaded = load_previous_drafts(posts_dir=tmp_path)
    assert len(loaded) == 2
    # Newest first by generated_at
    assert loaded[0].post_id == "JVY-20260929-002"
    assert loaded[1].post_id == "JVY-20260929-001"
