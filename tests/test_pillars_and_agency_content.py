"""Unit tests for the 8 official service pillars, agency positioning, and rotation system."""

from unittest.mock import MagicMock
import pytest

from agent.knowledge import load_company_knowledge
from agent.pillars import (
    OFFICIAL_CONTENT_FORMATS,
    OFFICIAL_SERVICE_PILLARS,
    calculate_pillar_rotation,
    format_pillars_context_for_prompt,
    get_pillar_by_name,
)
from agent.strategist import ContentIdea, select_content_idea
from database.models import Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager


def test_official_eight_service_pillars_defined():
    """Verify all eight official pillars are defined with required metadata."""
    assert len(OFFICIAL_SERVICE_PILLARS) == 8
    pillar_names = [p["name"] for p in OFFICIAL_SERVICE_PILLARS]

    expected_pillars = [
        "Inventory Management Systems",
        "CRM Solutions",
        "Custom Software Development",
        "Website Design & Development",
        "Mobile App Development",
        "Digital Marketing",
        "AI & Business Automation",
        "IT Consultancy & Support",
    ]
    for expected in expected_pillars:
        assert expected in pillar_names

    for pillar in OFFICIAL_SERVICE_PILLARS:
        assert "capabilities" in pillar and len(pillar["capabilities"]) >= 5
        assert "core_focus" in pillar
        assert "target_audience" in pillar


def test_official_content_formats_defined():
    """Verify official content formats are defined."""
    assert len(OFFICIAL_CONTENT_FORMATS) == 10
    assert "Problem → Solution" in OFFICIAL_CONTENT_FORMATS
    assert "Service Spotlight" in OFFICIAL_CONTENT_FORMATS
    assert "Educational Post" in OFFICIAL_CONTENT_FORMATS
    assert "Before vs After" in OFFICIAL_CONTENT_FORMATS
    assert "Business Pain Point" in OFFICIAL_CONTENT_FORMATS
    assert "Feature Breakdown" in OFFICIAL_CONTENT_FORMATS
    assert "Industry Scenario" in OFFICIAL_CONTENT_FORMATS
    assert "Myth vs Reality" in OFFICIAL_CONTENT_FORMATS
    assert "Question-Based Engagement" in OFFICIAL_CONTENT_FORMATS
    assert "Solution Showcase" in OFFICIAL_CONTENT_FORMATS


def test_get_pillar_by_name():
    """Verify matching pillar by name, slug, or substring."""
    p1 = get_pillar_by_name("Inventory Management Systems")
    assert p1 is not None and p1["id"] == "01"

    p2 = get_pillar_by_name("crm_solutions")
    assert p2 is not None and p2["id"] == "02"

    p3 = get_pillar_by_name("Mobile App")
    assert p3 is not None and p3["id"] == "05"


def test_pillar_rotation_logic():
    """Verify least-recently covered pillars are prioritized in rotation."""
    # Simulate past posts covering Inventory and CRM
    mock_posts = [
        {"content_type": "Inventory Management Systems | Problem to Practical Solution", "topic": "Warehouse Stockouts"},
        {"content_type": "Inventory Management Systems | Explainer", "topic": "Cycle Counting"},
        {"content_type": "CRM Solutions | Case Study", "topic": "Deal Pipelines"},
    ]

    rec_pillar, recent_cov = calculate_pillar_rotation(mock_posts)
    # Recommended pillar should NOT be Inventory Management Systems because it has count 2
    assert rec_pillar["name"] != "Inventory Management Systems"
    # Custom Software Development has count 0 and comes first among 0-count pillars
    assert rec_pillar["name"] == "Custom Software Development"
    assert "Inventory Management Systems" in recent_cov
    assert "CRM Solutions" in recent_cov


def test_company_knowledge_agency_positioning():
    """Verify company profile and brand voice strictly enforce agency positioning."""
    knowledge = load_company_knowledge()
    assert "technology and digital solutions agency" in knowledge.profile.lower()
    assert "https://www.jeevyamtechnologies.com/" in knowledge.profile
    assert "not exclusively an ai firm" in knowledge.profile.lower()

    # Check brand voice prohibitions
    assert "Pillar Alignment" in knowledge.brand_voice
    assert "No Fake Clients or Testimonials" in knowledge.brand_voice
    assert "No Generic AI News" in knowledge.brand_voice


def test_content_idea_schema_with_pillars():
    """Verify ContentIdea schema supports service_pillar and content_format with defaults."""
    idea = ContentIdea(
        topic="Eliminating Warehouse Stockouts with Custom Inventory Logic",
        angle="Real-time purchase and scrap reconciliation beats monthly spreadsheet counting",
        content_type="Inventory Management Systems | Problem to Practical Solution",
        service_pillar="Inventory Management Systems",
        content_format="Problem to Practical Solution",
        target_audience="Warehouse & Operations Directors",
        reason="Addresses immediate operational friction and highlights agency capabilities.",
    )
    assert idea.service_pillar == "Inventory Management Systems"
    assert idea.content_format == "Problem to Practical Solution"
    assert "Inventory Management" in idea.content_type


def test_pipeline_pillar_metadata_persistence(tmp_path):
    """Verify pipeline records service pillar and content format into Post and PostRevision."""
    from agent.image_generator import MockImageProvider
    from agent.pipeline import run_content_pipeline

    repo_manager = create_in_memory_repository_manager()
    ai_client = MagicMock()

    # Mock writer and image brief
    writer_resp = MagicMock()
    writer_resp.text = """{
        "hook": "Spreadsheet stock counts are obsolete by 9:05 AM.",
        "caption": "Spreadsheet stock counts are obsolete by 9:05 AM. Real-time reconciliation stops stockouts.\\n\\nAt Jevyam Technologies, we build custom inventory workflows tailored to operational reality.",
        "hashtags": ["#InventoryManagement", "#BusinessOperations", "#JevyamTech"],
        "call_to_action": "How does your warehouse handle raw material reconciliation?"
    }"""

    brief_resp = MagicMock()
    brief_resp.text = """{
        "visual_concept": "Clean warehouse workflow diagram",
        "style": "Minimalist editorial",
        "composition": "Centered card layout",
        "color_direction": "Deep navy and cobalt",
        "text_on_image": "Real-Time Stock Logic",
        "aspect_ratio": "1:1",
        "layout": "minimalist_editorial"
    }"""
    ai_client.models.generate_content.side_effect = [writer_resp, brief_resp]

    override_idea = ContentIdea(
        topic="Real-Time Warehouse Inventory Reconciliation",
        angle="Event-driven updates eliminate spreadsheet discrepancies",
        content_type="Inventory Management Systems | Problem to Practical Solution",
        service_pillar="Inventory Management Systems",
        content_format="Problem to Practical Solution",
        target_audience="Operations Heads",
        reason="Demonstrates operational business software value.",
    )

    mock_img_provider = MockImageProvider(base_url="https://mock-storage.supabase.co/post-images")

    draft = run_content_pipeline(
        client=ai_client,
        repo_manager=repo_manager,
        posts_dir=tmp_path,
        override_idea=override_idea,
        image_provider=mock_img_provider,
        use_in_memory=True,
    )

    assert draft.post_id.startswith("JVY-")
    saved_post = repo_manager.posts.get_by_post_id(draft.post_id)
    assert saved_post is not None
    assert "Inventory Management Systems" in saved_post.content_type
    assert "Problem to Practical Solution" in saved_post.content_type

    # Verify image_brief JSON has pillar metadata
    assert saved_post.image_brief.get("service_pillar") == "Inventory Management Systems"
    assert saved_post.image_brief.get("content_format") == "Problem to Practical Solution"
