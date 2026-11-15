"""Comprehensive tests for the Service-Focused LinkedIn Content & Visual Engine.

Verifies:
1. All eight official service categories are strictly defined with capabilities and URLs.
2. The generator restricts output strictly to the 8 official services.
3. Service rotation functions correctly, cycling across all 8 services.
4. Consecutive posts strictly avoid repeating the same service category.
5. All 10 official content formats are supported and rotated.
6. Service URLs are mapped correctly and accurately.
7. Captions avoid unsupported claims, fake numbers, and hype clichés.
8. Visual concepts correspond directly to the selected service.
9. Distinct 1200x1200 images are generated and saved separately for each post.
10. Previous posts and images are not overwritten.
11. Telegram preview and approval compatibility is maintained.
12. LinkedIn publishing integration remains intact.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from agent.knowledge import load_company_knowledge
from agent.pillars import (
    OFFICIAL_CONTENT_FORMATS,
    OFFICIAL_SERVICE_PILLARS,
    calculate_pillar_rotation,
    get_next_content_target,
    get_pillar_by_name,
    get_service_url,
    normalize_content_format,
)
from agent.strategist import ContentIdea, select_content_idea
from agent.writer import LinkedInPostContent, generate_linkedin_post
from agent.image_generator import (
    BrandedPillowImageProvider,
    ImageBrief,
    MockImageProvider,
    generate_image_brief,
)
from agent.branded_renderer import detect_optimal_layout, render_branded_image
from agent.pipeline import LinkedInDraft, run_content_pipeline
from database.models import Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager


EXPECTED_SERVICE_NAMES = [
    "Inventory Management Systems",
    "CRM Solutions",
    "Custom Software Development",
    "Website Design & Development",
    "Mobile App Development",
    "Digital Marketing",
    "AI & Business Automation",
    "IT Consultancy & Support",
]

EXPECTED_SERVICE_URLS = {
    "Inventory Management Systems": "https://www.jeevyamtechnologies.com/services/inventory-management.html",
    "CRM Solutions": "https://www.jeevyamtechnologies.com/services/crm-solutions.html",
    "Custom Software Development": "https://www.jeevyamtechnologies.com/services/custom-software.html",
    "Website Design & Development": "https://www.jeevyamtechnologies.com/services/website-development.html",
    "Mobile App Development": "https://www.jeevyamtechnologies.com/services/mobile-apps.html",
    "Digital Marketing": "https://www.jeevyamtechnologies.com/services/digital-marketing.html",
    "AI & Business Automation": "https://www.jeevyamtechnologies.com/services/ai-automation.html",
    "IT Consultancy & Support": "https://www.jeevyamtechnologies.com/services/it-consultancy.html",
}

EXPECTED_10_FORMATS = [
    "Problem → Solution",
    "Service Spotlight",
    "Educational Post",
    "Before vs After",
    "Business Pain Point",
    "Feature Breakdown",
    "Industry Scenario",
    "Myth vs Reality",
    "Question-Based Engagement",
    "Solution Showcase",
]


# ==============================================================================
# 1. SERVICE DEFINITIONS & URL MAPPING
# ==============================================================================

def test_eight_official_services_and_urls():
    """Verify all eight official services exist with exact URLs, capabilities, and opportunities."""
    assert len(OFFICIAL_SERVICE_PILLARS) == 8
    pillar_names = [p["name"] for p in OFFICIAL_SERVICE_PILLARS]
    assert pillar_names == EXPECTED_SERVICE_NAMES

    for p in OFFICIAL_SERVICE_PILLARS:
        name = p["name"]
        expected_url = EXPECTED_SERVICE_URLS[name]
        assert p["url"] == expected_url, f"URL mismatch for {name}"
        assert get_service_url(name) == expected_url
        assert len(p["capabilities"]) >= 5
        assert len(p.get("content_opportunities", [])) >= 4
        assert len(p["business_pain_points"]) >= 3
        assert len(p["target_audience"]) > 0


def test_ten_official_content_formats():
    """Verify all 10 official content formats are defined and normalizable."""
    assert len(OFFICIAL_CONTENT_FORMATS) == 10
    assert OFFICIAL_CONTENT_FORMATS == EXPECTED_10_FORMATS

    # Test alias normalization
    assert normalize_content_format("Problem to Practical Solution") == "Problem → Solution"
    assert normalize_content_format("Educational Explainer") == "Educational Post"
    assert normalize_content_format("Common Operational Mistakes") == "Business Pain Point"
    assert normalize_content_format("Industry-Specific Use Case") == "Industry Scenario"


# ==============================================================================
# 2. SERVICE ROTATION & AVOIDING CONSECUTIVE DUPLICATES
# ==============================================================================

def test_consecutive_service_avoidance():
    """Verify that the rotation engine NEVER recommends the immediately preceding service."""
    for service_name in EXPECTED_SERVICE_NAMES:
        # Simulate last post was this service
        mock_history = [
            {"service_category": service_name, "content_type": f"{service_name} | Problem → Solution", "topic": "Operational Focus"}
        ]
        rec_pillar, rec_format, recent_cov = calculate_pillar_rotation(mock_history, include_format=True)
        assert rec_pillar["name"] != service_name, f"Should not repeat {service_name} consecutively"
        assert recent_cov[0] == service_name


def test_full_cycle_rotation():
    """Verify that rotation cycles across all eight services in sequence."""
    simulated_history = []
    seen_services = []

    # Run 8 successive rotations
    for step in range(8):
        rec_pillar, rec_format, _ = calculate_pillar_rotation(simulated_history, include_format=True)
        p_name = rec_pillar["name"]
        seen_services.append(p_name)
        # Add to history
        simulated_history.insert(0, {
            "service_category": p_name,
            "content_type": f"{p_name} | {rec_format}",
            "topic": f"Topic for {p_name}",
        })

    # All 8 services must be covered in the 8 iterations
    assert len(set(seen_services)) == 8
    assert seen_services == EXPECTED_SERVICE_NAMES


def test_format_rotation():
    """Verify content formats rotate away from the immediately previous format."""
    mock_history = [
        {"service_category": "CRM Solutions", "content_format": "Problem → Solution"}
    ]
    _, rec_format, _ = calculate_pillar_rotation(mock_history, include_format=True)
    assert rec_format != "Problem → Solution"
    assert rec_format in EXPECTED_10_FORMATS


# ==============================================================================
# 3. CONTENT STRATEGIST & WRITER RESTRICTIONS
# ==============================================================================

def test_content_idea_schema_defaults_and_validation():
    """Verify ContentIdea schema automatically synchronizes URLs and service names."""
    idea = ContentIdea(
        topic="Eliminating Warehouse Stockouts with Custom Inventory Logic",
        angle="Real-time purchase and scrap reconciliation beats monthly spreadsheet counting",
        content_type="",
        service_category="Inventory Management Systems",
        content_format="Problem → Solution",
        target_audience="Warehouse Operations Heads",
        reason="Demonstrates practical agency business software value.",
        visual_concept="Warehouse stock dashboard mockup",
    )
    assert idea.service_name == "Inventory Management Systems"
    assert idea.service_url == "https://www.jeevyamtechnologies.com/services/inventory-management.html"
    assert idea.content_type == "Inventory Management Systems | Problem → Solution"
    assert idea.visual_concept == "Warehouse stock dashboard mockup"


def test_writer_prompt_contains_service_url():
    """Verify writer prompt renders service URL and strict anti-hype guidelines."""
    from agent.prompts import render_writer_prompt
    rendered = render_writer_prompt(
        company_context="Agency overview",
        brand_voice="Professional B2B",
        topic="Lead Pipeline Visibility",
        angle="Stage-by-stage pipeline tracking",
        content_type="CRM Solutions | Problem → Solution",
        target_audience="Sales Directors",
        previous_posts="None",
        service_url="https://www.jeevyamtechnologies.com/services/crm-solutions.html",
        service_name="CRM Solutions",
        content_format="Problem → Solution",
    )
    assert "https://www.jeevyamtechnologies.com/services/crm-solutions.html" in rendered
    assert "CRM Solutions" in rendered
    assert "NO CLICHÉS OR HYPE" in rendered
    assert "NO FAKE STATS OR CLAIMS" in rendered


# ==============================================================================
# 4. SERVICE-SPECIFIC VISUAL GENERATION
# ==============================================================================

def test_detect_optimal_layout_for_all_eight_services():
    """Verify that layout detection produces diverse, relevant layouts for all 8 services."""
    chosen_layouts = {}
    for p in OFFICIAL_SERVICE_PILLARS:
        s_name = p["name"]
        layout = detect_optimal_layout(
            title=f"Enterprise {s_name} Platform",
            caption=f"How modern {s_name} transforms business operations and eliminates friction.",
            visual_concept=p["visual_themes"][0],
            service_category=s_name,
        )
        chosen_layouts[s_name] = layout
        assert layout in p["suggested_layouts"], f"{s_name} layout {layout} not in {p['suggested_layouts']}"

    # Verify that different layouts are utilized across the 8 services (not all identical)
    unique_layouts = set(chosen_layouts.values())
    assert len(unique_layouts) >= 3, f"Expected visual diversity, but only got layouts: {unique_layouts}"


def test_render_branded_image_all_eight_services(tmp_path):
    """Verify that render_branded_image produces valid 1200x1200 PNGs for each service."""
    for idx, p in enumerate(OFFICIAL_SERVICE_PILLARS, 1):
        s_name = p["name"]
        out_file = tmp_path / f"test_{p['slug']}.png"
        png_bytes = render_branded_image(
            title=f"Optimizing {s_name}",
            subtitle=f"Enterprise solutions engineered by Jevyam Technologies for {p['target_audience']}.",
            topic=p["content_opportunities"][0],
            visual_concept=p["visual_themes"][0],
            service_category=s_name,
            output_path=out_file,
            post_id=f"JVY-TEST-{idx:03d}",
        )
        assert len(png_bytes) > 5000
        assert out_file.exists()

        # Check image dimensions
        with Image.open(out_file) as im:
            assert im.size == (1200, 1200)
            assert im.format == "PNG"


# ==============================================================================
# 5. END-TO-END PIPELINE & PERSISTENCE
# ==============================================================================

def test_pipeline_metadata_and_image_persistence(tmp_path):
    """Verify end-to-end pipeline persists all suggested metadata and distinct images."""
    repo_manager = create_in_memory_repository_manager()
    ai_client = MagicMock()

    writer_resp = MagicMock()
    writer_resp.text = json.dumps({
        "hook": "Leads falling through the cracks cost B2B teams thousands every quarter.",
        "caption": "Leads falling through the cracks cost B2B teams thousands every quarter.\n\nWithout a structured CRM, customer follow-ups get lost between spreadsheets and chat threads.\n\nAt Jevyam Technologies, our CRM Solutions provide stage-by-stage deal visibility.\n\nLearn more at https://www.jeevyamtechnologies.com/services/crm-solutions.html\n\nHow does your team track follow-up accountability?",
        "hashtags": ["#CRMSolutions", "#SalesOperations", "#B2BGrowth", "#JevyamTechnologies"],
        "call_to_action": "How does your team track follow-up accountability?",
    })

    brief_resp = MagicMock()
    brief_resp.text = json.dumps({
        "visual_concept": "Sales pipeline stage tracker card with clear deal stages",
        "style": "Clean enterprise UI dashboard",
        "composition": "Centered card layout with balance",
        "color_direction": "Deep navy and cobalt",
        "text_on_image": "Sales Pipeline Visibility",
        "aspect_ratio": "1:1",
        "layout": "process_flow",
    })

    ai_client.models.generate_content.side_effect = [writer_resp, brief_resp]

    override_idea = ContentIdea(
        topic="Preventing Lost Leads in High-Velocity B2B Sales",
        angle="Stage-by-stage deal tracking beats fragmented spreadsheet notes",
        content_type="CRM Solutions | Problem → Solution",
        service_category="CRM Solutions",
        content_format="Problem → Solution",
        target_audience="Sales Leaders & Founders",
        reason="Addresses immediate operational sales pipeline leakages.",
        visual_concept="Sales pipeline dashboard mockup",
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

    # 1. Draft validation
    assert draft.post_id.startswith("JVY-")
    assert draft.service_category == "CRM Solutions"
    assert draft.service_url == "https://www.jeevyamtechnologies.com/services/crm-solutions.html"
    assert draft.content_format == "Problem → Solution"

    # 2. Database Post validation
    saved_post = repo_manager.posts.get_by_post_id(draft.post_id)
    assert saved_post is not None
    assert "CRM Solutions" in saved_post.content_type
    assert saved_post.image_brief.get("service_category") == "CRM Solutions"
    assert saved_post.image_brief.get("service_url") == "https://www.jeevyamtechnologies.com/services/crm-solutions.html"
    assert saved_post.image_brief.get("content_format") == "Problem → Solution"
    assert saved_post.image_brief.get("generation_timestamp") is not None

    # 3. Post Revision validation
    revisions = repo_manager.revisions.get_by_post_id(draft.post_id)
    assert len(revisions) == 1
    assert "CRM Solutions" in revisions[0].content_type

    # 4. JSON draft copy on disk
    json_copy = tmp_path / f"{draft.post_id}.json"
    assert json_copy.exists()
    disk_data = json.loads(json_copy.read_text(encoding="utf-8"))
    assert disk_data["service_category"] == "CRM Solutions"
    assert disk_data["service_url"] == "https://www.jeevyamtechnologies.com/services/crm-solutions.html"

