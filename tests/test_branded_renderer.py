"""Unit and regression tests for zero-cost Pillow-based diverse branded image generator.

Covers:
- All 12 distinct layout renders and dimensions (1200 x 1200)
- PNG header signature and valid image structure
- Long-text wrapping and truncation safety
- Missing / sparse input fields handling
- Semantic layout detection and scoring
- Layout rotation across revisions (preventing consecutive identical layouts)
- BrandedPillowImageProvider storage upload and diagnostics
- End-to-end integration with initial draft generation and regeneration
"""

from io import BytesIO
import json
from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image
import pytest

from agent.branded_renderer import (
    ALL_LAYOUTS,
    render_branded_image,
    render_dark_cyber_tech_layout,
    render_minimalist_editorial_layout,
    render_split_screen_comparison_layout,
    render_data_visualization_layout,
    render_isometric_infrastructure_layout,
    render_timeline_roadmap_layout,
    render_process_flow_layout,
    render_magazine_cover_layout,
    render_geometric_abstract_layout,
    render_quote_insight_layout,
    render_layered_cards_layout,
    render_product_announcement_layout,
    extract_content_summary,
    detect_optimal_layout,
    wrap_text_to_lines,
    get_font,
)
from agent.image_generator import (
    BaseImageProvider,
    BrandedPillowImageProvider,
    ImageBrief,
    resolve_image_provider,
)
from agent.exceptions import ImageGenerationError, ImageStorageError
from agent.pipeline import (
    LinkedInDraft,
    regenerate_draft,
    run_content_pipeline,
)
from database.storage import MockStorageService
from database.models import Post, PostRevision, PostStatus
from config.settings import settings


# ==============================================================================
# 1. ALL 12 LAYOUTS, DIMENSIONS & PNG VALIDITY
# ==============================================================================

@pytest.mark.parametrize("layout_name", ALL_LAYOUTS)
def test_all_12_layouts_produce_valid_1200x1200_png(layout_name: str, tmp_path: Path):
    """Verify each of the 12 layouts generates a valid 1200x1200 PNG with correct headers."""
    out_file = tmp_path / f"test_{layout_name}.png"
    png_bytes = render_branded_image(
        title="Mission-Critical Enterprise Systems",
        caption="Building resilient multi-agent backends with verified state persistence.",
        visual_concept="Advanced high-availability architecture",
        key_points=["Idempotency", "Observability", "Consensus"],
        stats=[("99.99%", "Uptime"), ("10x", "Velocity"), ("0%", "Loss")],
        layout=layout_name,
        output_path=out_file,
    )

    # 1. Byte validity
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    # 2. PIL Image parsing and exact dimension check
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == (1200, 1200)
        assert img.format == "PNG"


def test_individual_layout_functions():
    """Verify direct calls to layout renderer functions return 1200x1200 images."""
    renderers = [
        lambda: render_dark_cyber_tech_layout("Cyber Core", "Sub", ["P1", "P2"]),
        lambda: render_minimalist_editorial_layout("Editorial Essay", "Sub", ["P1", "P2"]),
        lambda: render_split_screen_comparison_layout("Comparison", "Sub", ["P1", "P2"]),
        lambda: render_data_visualization_layout("Stats", "Sub", [("99%", "Val")]),
        lambda: render_isometric_infrastructure_layout("Infrastructure", "Sub", ["P1", "P2"]),
        lambda: render_timeline_roadmap_layout("Roadmap", "Sub", ["S1", "S2"]),
        lambda: render_process_flow_layout("Process", "Sub", ["S1", "S2"]),
        lambda: render_magazine_cover_layout("Magazine Review", "Sub", ["F1", "F2"]),
        lambda: render_geometric_abstract_layout("Abstract", "Sub", ["P1", "P2"]),
        lambda: render_quote_insight_layout("Insight Quote", "Sub", ["P1"]),
        lambda: render_layered_cards_layout("Layered Cards", "Sub", ["F1", "F2"]),
        lambda: render_product_announcement_layout("Product Launch", "Sub", ["F1", "F2"]),
    ]

    for idx, fn in enumerate(renderers):
        img = fn()
        assert img.size == (1200, 1200), f"Renderer #{idx + 1} size was {img.size}"


# ==============================================================================
# 2. SEMANTIC LAYOUT DETECTION & REVISION DIVERSITY
# ==============================================================================

def test_semantic_layout_detection():
    """Verify layout detection chooses appropriate layouts based on keywords."""
    assert detect_optimal_layout("Legacy Batch vs Event Mesh", "Comparing old cron vs modern AI") == "split_screen_comparison"
    assert detect_optimal_layout("Throughput Benchmark", "Achieved 99.9% uptime metric") == "data_visualization"
    assert detect_optimal_layout("Ingestion Pipeline", "Four-stage workflow process") == "process_flow"
    assert detect_optimal_layout("2026 Technology Roadmap", "Four milestone phases evolution") == "timeline_roadmap"
    assert detect_optimal_layout("Cloud Backend Architecture", "Kubernetes distributed cluster database") == "isometric_infrastructure"
    assert detect_optimal_layout("Zero-Trust Security Mesh", "Cyber authentication and neural token audit") == "dark_cyber_tech"
    assert detect_optimal_layout("Announcing Agent v2.0", "Official release launch of new platform feature") == "product_announcement"
    assert detect_optimal_layout("Industry Special Report", "Executive magazine review on AI trends") == "magazine_cover"
    assert detect_optimal_layout("Simplicity is Reliability", "A core philosophy quote on engineering wisdom") == "quote_insight"


def test_layout_rotation_across_revisions():
    """Verify consecutive revisions avoid using the same layout."""
    topic = "Cloud Backend Architecture with Distributed Queues"
    caption = "How we design resilient enterprise systems."

    # Rev 1 selects top semantic candidate
    layout_rev1 = detect_optimal_layout(topic, caption, revision=1)

    # Rev 2 with previous_layouts avoids rev 1
    layout_rev2 = detect_optimal_layout(
        topic, caption,
        previous_layouts=[layout_rev1],
        revision=2,
    )
    assert layout_rev2 != layout_rev1, f"Rev 2 ({layout_rev2}) must differ from Rev 1 ({layout_rev1})"

    # Rev 3 avoids both Rev 1 and Rev 2
    layout_rev3 = detect_optimal_layout(
        topic, caption,
        previous_layouts=[layout_rev1, layout_rev2],
        revision=3,
    )
    assert layout_rev3 not in (layout_rev1, layout_rev2), f"Rev 3 ({layout_rev3}) must differ from previous"


# ==============================================================================
# 3. TEXT WRAPPING & LONG-TEXT RESILIENCE
# ==============================================================================

def test_extreme_long_text_does_not_crash():
    """Verify the renderer gracefully handles arbitrarily long titles and captions."""
    very_long_title = "Transforming Modern Enterprise Infrastructure Through Highly Resilient Autonomous Multi-Agent Workflows And Scalable Distributed Architecture Across Global Cloud Networks"
    very_long_caption = (
        "In today's fast-moving enterprise landscape, traditional batch workflows often fall short "
        "when dealing with distributed microservices, network partitions, and unpredictable rate limits. "
        * 10
    )
    very_long_points = [
        "First massive bullet point that goes on and on describing in extreme detail how the system operates under load " * 3,
        "Second massive bullet point with intricate architectural explanations regarding idempotent event loops " * 3,
        "Third massive bullet point detailing compliance, security frameworks, automated retries, and failure containment " * 3,
    ]

    png_bytes = render_branded_image(
        title=very_long_title,
        caption=very_long_caption,
        key_points=very_long_points,
        layout="auto",
    )

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == (1200, 1200)


def test_wrap_text_to_lines_bounds():
    """Verify wrap_text_to_lines obeys max_lines and length limits."""
    font = get_font(28, bold=False)
    long_str = "This is a comprehensive test string intended to wrap over multiple lines gracefully without word breaking."
    lines = wrap_text_to_lines(long_str, font, max_width=300, max_lines=3)
    assert len(lines) <= 3
    assert len(lines) > 0


# ==============================================================================
# 4. MISSING & SPARSE FIELDS HANDLING
# ==============================================================================

def test_missing_and_none_fields():
    """Verify rendering succeeds with completely missing or None inputs."""
    png_bytes = render_branded_image(
        title=None,
        subtitle=None,
        caption=None,
        visual_concept=None,
        key_points=None,
        stats=None,
    )
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(png_bytes)) as img:
        assert img.size == (1200, 1200)


def test_extract_content_summary_fallbacks():
    """Verify extract_content_summary provides professional fallbacks."""
    h1, sub1 = extract_content_summary()
    assert h1 == "Enterprise AI & Scalable Automation"
    assert "Custom AI solutions" in sub1

    h2, sub2 = extract_content_summary(title="**Scalable Cloud** Architecture")
    assert h2 == "Scalable Cloud Architecture"

    h3, sub3 = extract_content_summary(title="   ", topic="Multi-Agent Systems")
    assert h3 == "Multi-Agent Systems"


# ==============================================================================
# 5. FIXTURES & BRANDED PILLOW IMAGE PROVIDER TESTS
# ==============================================================================

@pytest.fixture
def mock_gemini_client():
    client = MagicMock()
    idea_json = json.dumps({
        "topic": "Zero-Trust Security for Vector Databases",
        "angle": "Why tenant isolation must be enforced at embedding time, not retrieval time",
        "content_type": "technology insight",
        "target_audience": "CISOs and Lead Architects",
        "reason": "Addresses high-priority security concerns for enterprise AI deployments.",
    })
    writer_json = json.dumps({
        "hook": "Vector embeddings without tenant access control are a data breach in waiting.",
        "caption": "Vector embeddings without tenant access control are a data breach in waiting.\n\nEnforcing strict isolation prevents cross-tenant data leakage in enterprise RAG.\n\nAt Jevyam Technologies, we build secure data bridges.\n\nHow do you isolate sensitive documents in your vector index?",
        "hashtags": ["#CyberSecurity", "#AI", "#EnterpriseTech", "#CloudArchitecture", "#DataSecurity"],
        "call_to_action": "How do you isolate sensitive documents in your vector index?",
    })
    brief_json = json.dumps({
        "visual_concept": "Cryptographic shield encasing vector clusters with role badges",
        "style": "Minimalist isometric blueprint",
        "composition": "Centered focal shield with isolated data layers",
        "color_direction": "Deep slate with cobalt security barriers",
        "text_on_image": "Zero-Trust Vectors",
        "aspect_ratio": "1:1",
    })

    resp1 = MagicMock(text=idea_json)
    resp2 = MagicMock(text=writer_json)
    resp3 = MagicMock(text=brief_json)
    client.models.generate_content.side_effect = [
        resp1, resp2, resp3,
        resp1, resp2, resp3,
        resp1, resp2, resp3,
    ]
    return client


@pytest.fixture
def in_memory_repo_manager():
    from database.repositories import create_in_memory_repository_manager
    return create_in_memory_repository_manager()


def test_branded_pillow_image_provider_with_mock_storage(tmp_path: Path):
    """Verify BrandedPillowImageProvider renders and uploads to MockStorageService."""
    storage = MockStorageService(base_url="https://supabase.local")
    provider = BrandedPillowImageProvider(storage_service=storage)

    brief = ImageBrief(
        visual_concept="Isometric technical architecture diagram",
        style="Modern vector blueprint",
        composition="Center balanced",
        color_direction="Navy and cyan",
        text_on_image="Autonomous Automation",
        aspect_ratio="1:1",
    )

    out_file = tmp_path / "local_output.png"
    url = provider.generate_image(
        brief=brief,
        post_id="JVY-BRANDED-001",
        revision=1,
        output_path=out_file,
        topic="Cloud Automation",
        caption="Modern cloud automation eliminates manual toil.",
    )

    assert url == "https://supabase.local/storage/v1/object/public/post-images/JVY-BRANDED-001/rev_1.png"
    assert out_file.exists()
    assert out_file.stat().st_size > 0
    assert brief.layout in ALL_LAYOUTS

    # Diagnostic check
    diag = provider.last_diagnostic
    assert diag is not None
    assert diag.provider_name == "BrandedPillowImageProvider"
    assert diag.generation_succeeded is True
    assert diag.storage_succeeded is True
    assert "JVY-BRANDED-001" in diag.image_url


def test_branded_pillow_image_provider_storage_failure():
    """Verify BrandedPillowImageProvider raises ImageStorageError when storage fails."""
    mock_storage = MagicMock()
    mock_storage.upload_image.side_effect = RuntimeError("Supabase S3 timeout 504")

    provider = BrandedPillowImageProvider(storage_service=mock_storage)
    brief = ImageBrief(
        visual_concept="Concept",
        style="Vector",
        composition="Center",
        color_direction="Navy",
        text_on_image="Test Storage Fail",
        aspect_ratio="1:1",
    )

    with pytest.raises(ImageStorageError) as exc_info:
        provider.generate_image(
            brief=brief,
            post_id="JVY-ERR-002",
            revision=1,
        )

    assert "Failed to upload visual to storage" in str(exc_info.value)
    diag = provider.last_diagnostic
    assert diag is not None
    assert diag.generation_succeeded is True
    assert diag.storage_succeeded is False


def test_resolve_image_provider_branded(monkeypatch):
    """Verify resolve_image_provider correctly resolves branded and pillow providers."""
    p1 = resolve_image_provider(provider_type="branded")
    assert isinstance(p1, BrandedPillowImageProvider)

    p2 = resolve_image_provider(provider_type="pillow")
    assert isinstance(p2, BrandedPillowImageProvider)

    monkeypatch.setattr(settings, "IMAGE_PROVIDER", "branded")
    p3 = resolve_image_provider()
    assert isinstance(p3, BrandedPillowImageProvider)

    monkeypatch.setattr(settings, "IMAGE_PROVIDER", "unknown_custom_provider")
    p4 = resolve_image_provider()
    assert isinstance(p4, BrandedPillowImageProvider)


# ==============================================================================
# 6. PIPELINE INTEGRATION & REGENERATION DIVERSITY
# ==============================================================================

def test_pipeline_integration_with_branded_provider(mock_gemini_client, in_memory_repo_manager, tmp_path: Path):
    """Verify run_content_pipeline with BrandedPillowImageProvider generates, stores, and persists."""
    storage = MockStorageService(base_url="https://mock-storage.local/post-images")
    provider = BrandedPillowImageProvider(storage_service=storage)

    draft = run_content_pipeline(
        client=mock_gemini_client,
        posts_dir=tmp_path / "posts",
        current_date="2026-10-14",
        repo_manager=in_memory_repo_manager,
        use_in_memory=True,
        image_provider=provider,
        require_image=True,
    )

    assert isinstance(draft, LinkedInDraft)
    assert draft.image_url is not None
    assert draft.image_url.startswith("https://mock-storage.local/post-images/")
    assert draft.revision == 1

    # Verify repository records have image_url
    post = in_memory_repo_manager.posts.get_by_post_id(draft.post_id)
    assert post is not None
    assert post.image_url == draft.image_url

    rev = in_memory_repo_manager.revisions.get_latest_revision(draft.post_id)
    assert rev is not None
    assert rev.image_url == draft.image_url


def test_pipeline_regeneration_with_branded_provider(mock_gemini_client, in_memory_repo_manager, tmp_path: Path):
    """Verify regenerate_draft with BrandedPillowImageProvider creates rev 2 with distinct layout."""
    storage = MockStorageService(base_url="https://mock-storage.local/post-images")
    provider = BrandedPillowImageProvider(storage_service=storage)

    # Initial draft (Rev 1)
    draft_v1 = run_content_pipeline(
        client=mock_gemini_client,
        posts_dir=tmp_path / "posts",
        current_date="2026-10-14",
        repo_manager=in_memory_repo_manager,
        use_in_memory=True,
        image_provider=provider,
        require_image=True,
    )

    rev1 = in_memory_repo_manager.revisions.get_latest_revision(draft_v1.post_id)
    rev1_layout = getattr(draft_v1.image_brief, "layout", None) or rev1.image_brief.get("layout")

    # Regenerate draft with feedback (Rev 2)
    draft_v2 = regenerate_draft(
        client=mock_gemini_client,
        rejected_draft=draft_v1,
        rejection_reason="Pivot perspective to highlight comparative differences",
        repo_manager=in_memory_repo_manager,
        use_in_memory=True,
        image_provider=provider,
        require_image=True,
    )

    assert isinstance(draft_v2, LinkedInDraft)
    assert draft_v2.post_id == draft_v1.post_id
    assert draft_v2.revision == 2
    assert draft_v2.image_url is not None
    assert "rev_2.png" in draft_v2.image_url

    rev2 = in_memory_repo_manager.revisions.get_latest_revision(draft_v1.post_id)
    assert rev2 is not None
    assert rev2.revision_number == 2
    assert rev2.image_url == draft_v2.image_url

    rev2_layout = getattr(draft_v2.image_brief, "layout", None) or rev2.image_brief.get("layout")
    if rev1_layout and rev2_layout:
        assert rev2_layout != rev1_layout, f"Regeneration layout ({rev2_layout}) must differ from initial layout ({rev1_layout})"
