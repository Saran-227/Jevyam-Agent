"""Tests for Jevyam Technologies Premium Graphic Design System 2.0."""

from io import BytesIO
from PIL import Image
import pytest

from agent.design_system import (
    DESIGN_DIRECTIONS,
    LANDSCAPE_SIZE,
    PORTRAIT_SIZE,
    SQUARE_SIZE,
    render_design_v2,
    resolve_service_photo,
    validate_design_quality,
)


@pytest.mark.parametrize("direction", DESIGN_DIRECTIONS)
def test_all_8_design_directions_square_and_pass_validation(direction: str):
    png_bytes, report = render_design_v2(
        direction=direction,
        headline="Build Reliable Systems Around Your Business",
        subheadline="Practical custom software and digital solutions for growing teams.",
        key_points=["Centralized workflows", "Real-time visibility", "Ongoing support"],
        service_category="Custom Software Development",
        format_type="square",
    )
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert report.passed is True
    assert report.dimensions == SQUARE_SIZE
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == SQUARE_SIZE


@pytest.mark.parametrize("direction", ["split_editorial", "multi_panel_agency", "editorial_collage"])
def test_portrait_format_1080x1350(direction: str):
    png_bytes, report = render_design_v2(
        direction=direction,
        headline="Modernize Your Corporate Digital Presence",
        subheadline="Fast, mobile-ready websites engineered for qualified inquiries.",
        key_points=["Clean UX", "Technical SEO"],
        service_category="Website Design & Development",
        format_type="portrait",
    )
    assert report.passed is True
    assert report.dimensions == PORTRAIT_SIZE
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == PORTRAIT_SIZE


def test_landscape_format_1200x628():
    png_bytes, report = render_design_v2(
        direction="landscape_banner",
        headline="Turn Paid Clicks Into Real Business Inquiries",
        subheadline="Align search campaigns with fast landing pages.",
        service_category="Digital Marketing",
        format_type="landscape",
    )
    assert report.passed is True
    assert report.dimensions == LANDSCAPE_SIZE
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == LANDSCAPE_SIZE


def test_design_quality_rejects_unsupported_statistics():
    report = validate_design_quality(
        direction="business_metrics",
        headline="340% Increase in Revenue Guaranteed",
        subheadline="10+ years of experience delivering 500+ projects.",
        size=SQUARE_SIZE,
        human_photo_used=True,
        verified_metrics=None,
    )
    assert report.passed is False
    assert any("unsupported statistics" in i.lower() for i in report.issues)


def test_distinct_photos_per_service():
    p1 = resolve_service_photo("Website Design & Development")
    p2 = resolve_service_photo("CRM Solutions")
    p3 = resolve_service_photo("Inventory Management Systems")
    p4 = resolve_service_photo("Mobile App Development")
    assert len({p1.name, p2.name, p3.name, p4.name}) == 4
