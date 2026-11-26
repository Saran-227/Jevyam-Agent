"""Tests for the upgraded B2B content quality validator and Canva-style creative system."""

from io import BytesIO
from pathlib import Path
from PIL import Image
import pytest

from agent.branded_renderer import render_branded_image
from agent.canva_templates import (
    CANVA_TEMPLATES,
    CAROUSEL_SIZE,
    SINGLE_SIZE,
    render_canva_template,
    render_carousel_slides,
    select_canva_template,
)
from agent.image_generator import BrandedPillowImageProvider, ImageBrief
from agent.quality_validator import validate_post_quality
from database.storage import MockStorageService


def test_quality_validator_passes_clean_b2b_post():
    res = validate_post_quality(
        topic="Why a slow business website loses qualified customer inquiries",
        hook="Your sales team might be losing leads before a prospect ever reads your offer.",
        caption=(
            "Your sales team might be losing leads before a prospect ever reads your offer.\n\n"
            "Many corporate websites accumulate heavy templates and unoptimized scripts over time. "
            "On mobile connections, a few extra seconds of delay causes buyers to leave and check the next search result.\n\n"
            "Cleaning up your front-end architecture and technical SEO helps ensure visitors actually stay long enough to inquire. "
            "At Jevyam Technologies, we build fast, custom corporate websites designed around real buyer journeys.\n\n"
            "When was the last time you tested your site speed on a mobile network?"
        ),
        hashtags=["#WebsiteDevelopment", "#TechnicalSEO", "#B2BMarketing", "#JevyamTechnologies"],
        call_to_action="When was the last time you tested your site speed on a mobile network?",
        service_category="Website Design & Development",
    )
    assert res.passed is True
    assert res.score == 100
    assert res.issues == []


@pytest.mark.parametrize(
    "bad_phrase",
    [
        "In today's fast-paced digital world, websites matter.",
        "At Jevyam Technologies, we believe in excellence.",
        "Unlock the power of your digital presence today.",
        "This will boost revenue by 340% for every client.",
    ],
)
def test_quality_validator_rejects_ai_cliches_and_fake_stats(bad_phrase: str):
    res = validate_post_quality(
        topic="Custom website vs template website",
        hook=bad_phrase,
        caption=f"{bad_phrase}\n\nHere is a short explanation of why custom builds perform better for growing B2B companies.",
        hashtags=["#WebDesign", "#B2B", "#JevyamTechnologies"],
        call_to_action="Which approach does your team prefer?",
        service_category="Website Design & Development",
    )
    assert res.passed is False
    assert len(res.issues) >= 1


def test_quality_validator_rejects_generic_topic():
    res = validate_post_quality(
        topic="The future of AI",
        hook="Technology is changing fast.",
        caption="AI is changing everything for businesses everywhere. Learn more about how software works in modern offices.",
        hashtags=["#AI", "#Tech", "#Business"],
        call_to_action="What do you think?",
        service_category="AI & Business Automation",
    )
    assert res.passed is False
    assert any("generic" in i.lower() for i in res.issues)


@pytest.mark.parametrize("template_id", CANVA_TEMPLATES)
def test_all_6_canva_templates_render_1200x1200_png(template_id: str):
    png_bytes = render_canva_template(
        template_id=template_id,
        headline="Stop Losing Inbound Leads in Spreadsheets",
        subheadline="Centralize inquiries, follow-ups, and quotations in one CRM.",
        key_points=["Capture leads automatically", "Assign owner & follow-up", "Track deal stages"],
        problem_points=["Leads lost in inboxes", "Missed follow-ups"],
        solution_points=["Centralized CRM pipeline", "Automated reminders"],
        architecture_nodes=["Web Inquiry Form", "CRM API", "Central Database", "Alert Engine"],
        service_category="CRM Solutions",
    )
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == SINGLE_SIZE


def test_carousel_slides_render_1080x1350_png():
    slides = render_carousel_slides(
        headline="When to Move Beyond Spreadsheets",
        subheadline="Practical signs your operations need custom software.",
        slides=[
            {"title": "Conflicting Versions", "body": "Multiple copies circulate across teams."},
            {"title": "Manual Double Entry", "body": "Staff re-type orders across systems daily."},
        ],
        service_category="Custom Software Development",
    )
    assert len(slides) == 4  # Cover + 2 insights + CTA
    for slide_bytes in slides:
        assert slide_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        with Image.open(BytesIO(slide_bytes)) as img:
            assert img.size == CAROUSEL_SIZE


def test_dynamic_template_selection_and_rotation():
    t1 = select_canva_template("Website Design & Development", "Custom Website vs Template Website")
    assert t1 == "problem_vs_solution"

    t2 = select_canva_template("CRM Solutions", "4 Steps to Automate Lead Follow-ups")
    assert t2 == "educational_infographic"

    t3 = select_canva_template("Custom Software Development", "API and Database Integration Architecture")
    assert t3 == "technical_architecture"

    # Rotation avoids repeating previous template
    t4 = select_canva_template("Website Design & Development", "Custom Website vs Template", previous_templates=["problem_vs_solution"])
    assert t4 != "problem_vs_solution"


def test_branded_provider_uses_canva_template_from_brief(tmp_path: Path):
    storage = MockStorageService()
    provider = BrandedPillowImageProvider(storage_service=storage)
    brief = ImageBrief(
        visual_concept="Clean two-column comparison for website speed",
        style="Canva Problem vs Solution",
        composition="Two-column layout",
        color_direction="Off-white and deep navy",
        text_on_image="Slow Website vs Custom Build",
        layout="problem_vs_solution",
        headline="Slow Website vs Custom Build",
        subheadline="Why page speed impacts commercial inquiries.",
        problem_points=["Heavy bloated templates", "Slow mobile rendering"],
        solution_points=["Lean custom front-end", "Technical SEO built in"],
    )
    url = provider.generate_image(
        brief=brief,
        post_id="JVY-TEST-001",
        revision=1,
        output_path=tmp_path / "out.png",
        topic="Slow Website vs Custom Build",
    )
    assert url.startswith("https://")
    assert (tmp_path / "out.png").exists()
    with Image.open(tmp_path / "out.png") as img:
        assert img.size == SINGLE_SIZE
