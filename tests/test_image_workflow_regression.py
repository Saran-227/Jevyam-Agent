"""Regression tests for image generation workflow, provider selection, fail-closed enforcement, and approval safeguards."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agent.exceptions import (
    ImageGenerationError,
    ImageRequiredError,
    ImageStorageError,
    PostNotEligibleForApprovalError,
    DailyOrchestrationError,
)
from agent.image_generator import (
    BaseImageProvider,
    GeminiImageProvider,
    ImageBrief,
    ImageGenerationDiagnostic,
    MockImageProvider,
    PlaceholderImageProvider,
    is_valid_image_url,
    mask_secret_strings,
    resolve_image_provider,
)
from agent.orchestrator import DailyOrchestrator
from agent.pipeline import LinkedInDraft, regenerate_draft, run_content_pipeline
from api.services.approval_service import ApprovalService
from api.services.telegram_service import TelegramService
from api.services.whatsapp_service import WhatsAppService
from config.settings import settings
from database.models import Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from database.storage import BaseStorageService, MockStorageService
from integrations.telegram.client import TelegramApiProvider
from integrations.telegram.models import TelegramApprovalMessagePayload
from integrations.whatsapp.meta_cloud import MetaWhatsAppCloudProvider
from integrations.whatsapp.models import WhatsAppApprovalMessagePayload


@pytest.fixture
def sample_brief() -> ImageBrief:
    return ImageBrief(
        visual_concept="Idempotent event flow with dead-letter queue",
        style="Clean 2D vector technical blueprint",
        composition="Centered horizontal sequence",
        color_direction="Deep slate background with cyan and cobalt trace lines",
        text_on_image="Idempotent Architecture",
        aspect_ratio="1:1",
    )


@pytest.fixture
def mock_gemini_client():
    client = MagicMock()
    resp_idea = MagicMock()
    resp_idea.text = json.dumps({
        "topic": "Event-Driven Automation Architecture",
        "angle": "Why webhooks beat cron",
        "content_type": "software engineering",
        "target_audience": "Tech Leads",
        "reason": "Production reliability topic",
    })
    resp_writer = MagicMock()
    resp_writer.text = json.dumps({
        "hook": "Cron jobs fail silently in enterprise stacks.",
        "caption": "Cron jobs fail silently in enterprise stacks.\n\nUse idempotent webhooks instead.\n\nHow do you handle retries?",
        "hashtags": ["#DevOps", "#Cloud", "#Architecture", "#SoftwareEngineering", "#Automation"],
        "call_to_action": "How do you handle retries?",
    })
    resp_brief = MagicMock()
    resp_brief.text = json.dumps({
        "visual_concept": "Idempotent event flow",
        "style": "Minimalist vector",
        "composition": "Centered",
        "color_direction": "Slate and cyan",
        "text_on_image": "Reliable Queues",
        "aspect_ratio": "1:1",
    })
    client.models.generate_content.side_effect = [resp_idea, resp_writer, resp_brief]
    return client


# ==============================================================================
# 1. PROVIDER RESOLUTION TESTS
# ==============================================================================

def test_resolve_image_provider_in_memory():
    """Verify in-memory flag resolves to MockImageProvider."""
    provider = resolve_image_provider(use_in_memory=True)
    assert isinstance(provider, MockImageProvider)


def test_resolve_image_provider_explicit_types():
    """Verify explicit provider_type argument resolution."""
    assert isinstance(resolve_image_provider(provider_type="mock"), MockImageProvider)
    assert isinstance(resolve_image_provider(provider_type="placeholder"), PlaceholderImageProvider)
    assert isinstance(resolve_image_provider(provider_type="none"), PlaceholderImageProvider)

    gemini_p = resolve_image_provider(provider_type="gemini")
    assert isinstance(gemini_p, GeminiImageProvider)


def test_resolve_image_provider_from_settings(monkeypatch):
    """Verify provider resolution falls back to settings.IMAGE_PROVIDER."""
    monkeypatch.setattr(settings, "IMAGE_PROVIDER", "mock")
    assert isinstance(resolve_image_provider(), MockImageProvider)

    monkeypatch.setattr(settings, "IMAGE_PROVIDER", "gemini")
    assert isinstance(resolve_image_provider(), GeminiImageProvider)


# ==============================================================================
# 2. IMAGE URL VALIDATION & MASKING DIAGNOSTICS
# ==============================================================================

def test_is_valid_image_url():
    """Test URL validator identifies valid HTTP/HTTPS URLs and rejects invalid ones."""
    assert is_valid_image_url("https://example.com/image.png") is True
    assert is_valid_image_url("http://cdn.jevyam.com/visuals/rev_1.jpg") is True
    assert is_valid_image_url(None) is False
    assert is_valid_image_url("") is False
    assert is_valid_image_url("   ") is False
    assert is_valid_image_url("None") is False
    assert is_valid_image_url("null") is False
    assert is_valid_image_url("/local/path/only.png") is False


def test_mask_secret_strings():
    """Verify secrets and keys are scrubbed from diagnostic strings."""
    secret_key = "sb_publishable_1mnuznYMLbiHmWXq5ai3IQ_BFRIJxYJ"
    telegram_bot = "8860801976:AAFN5KL5tGX-XCGOgMzq_yijp0jgu7HXVbM"
    raw_str = f"Error with key {secret_key} and token {telegram_bot}"
    masked = mask_secret_strings(raw_str)
    assert secret_key not in masked
    assert telegram_bot not in masked
    assert "[MASKED_SUPABASE_KEY]" in masked
    assert "[MASKED_TELEGRAM_TOKEN]" in masked


# ==============================================================================
# 3. IMAGE URL PERSISTENCE ON POST AND POSTREVISION
# ==============================================================================

def test_pipeline_persists_image_url(mock_gemini_client, tmp_path: Path):
    """Verify run_content_pipeline persists image_url in both Post and PostRevision."""
    repo = create_in_memory_repository_manager()
    mock_provider = MockImageProvider(base_url="https://images.jevyam.com")

    draft = run_content_pipeline(
        client=mock_gemini_client,
        posts_dir=tmp_path,
        repo_manager=repo,
        current_date="2026-10-13",
        image_provider=mock_provider,
        require_image=True,
    )

    assert draft.image_url == "https://images.jevyam.com/JVY-20261013-001/rev_1.png"

    # Verify Post table record
    post = repo.posts.get_by_post_id(draft.post_id)
    assert post is not None
    assert post.image_url == "https://images.jevyam.com/JVY-20261013-001/rev_1.png"

    # Verify PostRevision table record
    revs = repo.revisions.get_by_post_id(draft.post_id)
    assert len(revs) == 1
    assert revs[0].image_url == "https://images.jevyam.com/JVY-20261013-001/rev_1.png"


def test_regenerate_draft_persists_new_revision_image_url(tmp_path: Path, sample_brief: ImageBrief):
    """Verify regenerate_draft persists image_url on revision 2."""
    repo = create_in_memory_repository_manager()
    mock_provider = MockImageProvider(base_url="https://images.jevyam.com")

    initial_post = Post(
        post_id="JVY-20261013-001",
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="tech",
        topic="Initial Topic",
        angle="Initial Angle",
        target_audience="CTOs",
        hook="Initial Hook",
        caption="Initial Caption",
        hashtags=["#Tech"],
        call_to_action="CTA",
        visual_concept="VC",
        image_brief=sample_brief,
        image_url="https://images.jevyam.com/JVY-20261013-001/rev_1.png",
    )
    repo.posts.create(initial_post)
    repo.revisions.create(PostRevision(
        post_id="JVY-20261013-001",
        revision_number=1,
        topic=initial_post.topic,
        angle=initial_post.angle,
        content_type=initial_post.content_type,
        target_audience=initial_post.target_audience,
        hook=initial_post.hook,
        caption=initial_post.caption,
        hashtags=initial_post.hashtags,
        call_to_action=initial_post.call_to_action,
        visual_concept=initial_post.visual_concept,
        image_brief=sample_brief,
        image_url=initial_post.image_url,
    ))

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Pivoted Topic",
            "angle": "Pivoted Angle",
            "content_type": "tech",
            "target_audience": "CTOs",
            "reason": "Revision reason",
        })),
        MagicMock(text=json.dumps({
            "hook": "Pivoted Hook",
            "caption": "Pivoted Caption",
            "hashtags": ["#Pivoted"],
            "call_to_action": "CTA2",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "VC2",
            "style": "Style2",
            "composition": "Comp2",
            "color_direction": "Col2",
            "text_on_image": "Text2",
            "aspect_ratio": "1:1",
        })),
    ]

    new_draft = regenerate_draft(
        rejected_draft=initial_post.post_id,
        rejection_reason="Needs more technical depth",
        client=mock_gemini,
        posts_dir=tmp_path,
        repo_manager=repo,
        image_provider=mock_provider,
        require_image=True,
    )

    assert new_draft.revision == 2
    assert new_draft.image_url == "https://images.jevyam.com/JVY-20261013-001/rev_2.png"

    revs = repo.revisions.get_by_post_id(initial_post.post_id)
    rev2 = next(r for r in revs if r.revision_number == 2)
    assert rev2 is not None
    assert rev2.image_url == "https://images.jevyam.com/JVY-20261013-001/rev_2.png"


# ==============================================================================
# 4. FAIL-CLOSED PIPELINE & STORAGE FAILURE HANDLING
# ==============================================================================

def test_pipeline_fails_closed_when_image_missing(mock_gemini_client, tmp_path: Path):
    """Verify run_content_pipeline raises ImageRequiredError and persists nothing when image is None."""
    repo = create_in_memory_repository_manager()
    placeholder_provider = PlaceholderImageProvider()

    with pytest.raises(ImageRequiredError) as exc_info:
        run_content_pipeline(
            client=mock_gemini_client,
            posts_dir=tmp_path,
            repo_manager=repo,
            current_date="2026-10-13",
            image_provider=placeholder_provider,
            require_image=True,
        )

    assert "requires a valid companion image URL" in str(exc_info.value)
    # Ensure nothing was persisted in repository
    assert len(repo.posts.get_previous_posts()) == 0


def test_pipeline_fails_closed_on_storage_failure(mock_gemini_client, tmp_path: Path):
    """Verify storage upload failure raises ImageRequiredError and prevents post creation."""
    repo = create_in_memory_repository_manager()

    failing_storage = MagicMock()
    failing_storage.upload_image.side_effect = ImageStorageError("Supabase bucket RLS policy violation")

    mock_client = MagicMock()
    part = MagicMock()
    part.inline_data.data = b"fake_png_data"
    part.inline_data.mime_type = "image/png"
    cand = MagicMock()
    cand.content.parts = [part]
    resp = MagicMock()
    resp.candidates = [cand]
    mock_client.models.generate_content.return_value = resp

    provider = GeminiImageProvider(
        client=mock_client,
        storage_service=failing_storage,
    )

    with pytest.raises(ImageRequiredError) as exc_info:
        run_content_pipeline(
            client=mock_gemini_client,
            posts_dir=tmp_path,
            repo_manager=repo,
            current_date="2026-10-13",
            image_provider=provider,
            require_image=True,
        )

    assert "Supabase bucket RLS policy violation" in str(exc_info.value)
    assert len(repo.posts.get_previous_posts()) == 0


# ==============================================================================
# 5. PREVENTION OF TEXT-ONLY TELEGRAM APPROVALS (FAIL-CLOSED)
# ==============================================================================

def test_telegram_service_rejects_text_only_approval(monkeypatch, sample_brief: ImageBrief):
    """Verify TelegramService.send_post_approval_notification raises PostNotEligibleForApprovalError when image_url is missing."""
    monkeypatch.setattr(settings, "REQUIRE_POST_IMAGE", True)

    repo = create_in_memory_repository_manager()
    post = Post(
        post_id="JVY-20261013-002",
        status=PostStatus.DRAFT,
        current_revision=1,
        content_type="tech",
        topic="No Image Topic",
        angle="Angle",
        target_audience="CTOs",
        hook="Hook",
        caption="Caption",
        hashtags=["#Tech"],
        call_to_action="CTA",
        visual_concept="VC",
        image_brief=sample_brief,
        image_url=None,  # Root cause reproduced!
    )
    repo.posts.create(post)

    approval_service = ApprovalService(repo_manager=repo)
    mock_provider = MagicMock()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)

    with pytest.raises(PostNotEligibleForApprovalError) as exc_info:
        service.send_post_approval_notification("JVY-20261013-002")

    assert "does not have a valid companion image URL" in str(exc_info.value)
    assert "Text-only Telegram approval is prohibited" in str(exc_info.value)
    # Ensure provider send_approval_message was NEVER called
    mock_provider.send_approval_message.assert_not_called()


def test_telegram_api_provider_refuses_message_without_image(monkeypatch):
    """Verify TelegramApiProvider.send_approval_message returns failure response when image_url is None and REQUIRE_POST_IMAGE is True."""
    monkeypatch.setattr(settings, "REQUIRE_POST_IMAGE", True)

    mock_http = MagicMock()
    provider = TelegramApiProvider(
        bot_token="123456:AAFakeToken1234567890abcdefgh",
        founder_chat_id="12345678",
        http_client=mock_http,
    )

    payload = TelegramApprovalMessagePayload(
        post_id="JVY-20261013-002",
        revision_number=1,
        hook="Hook text",
        caption="Caption text",
        hashtags=["#Tech"],
        visual_concept="VC",
        approval_token="appr_token_123",
        approval_url="http://localhost:8000/approve/appr_token_123",
        image_url=None,  # Missing image
        chat_id="12345678",
    )

    res = provider.send_approval_message(payload)
    assert res.success is False
    assert "Refusing to send text-only Telegram approval message" in res.error
    # Verify no HTTP request was made to Telegram API
    mock_http.post.assert_not_called()


def test_whatsapp_service_rejects_text_only_approval(monkeypatch, sample_brief: ImageBrief):
    """Verify WhatsAppService.send_post_approval_notification raises PostNotEligibleForApprovalError when image_url is missing."""
    monkeypatch.setattr(settings, "REQUIRE_POST_IMAGE", True)

    repo = create_in_memory_repository_manager()
    post = Post(
        post_id="JVY-20261013-002",
        status=PostStatus.DRAFT,
        current_revision=1,
        content_type="tech",
        topic="No Image Topic",
        angle="Angle",
        target_audience="CTOs",
        hook="Hook",
        caption="Caption",
        hashtags=["#Tech"],
        call_to_action="CTA",
        visual_concept="VC",
        image_brief=sample_brief,
        image_url=None,
    )
    repo.posts.create(post)

    approval_service = ApprovalService(repo_manager=repo)
    mock_provider = MagicMock()
    wa_service = WhatsAppService(approval_service=approval_service, provider=mock_provider)

    with pytest.raises(PostNotEligibleForApprovalError) as exc_info:
        wa_service.send_post_approval_notification("JVY-20261013-002")

    assert "Text-only WhatsApp approval is prohibited" in str(exc_info.value)
    mock_provider.send_approval_message.assert_not_called()


# ==============================================================================
# 6. ORCHESTRATOR SAFEGUARD AGAINST MISSING COMPANION IMAGES
# ==============================================================================

def test_orchestrator_fails_closed_if_draft_has_no_image(monkeypatch):
    """Verify DailyOrchestrator raises DailyOrchestrationError if draft has no companion image."""
    monkeypatch.setattr(settings, "REQUIRE_POST_IMAGE", True)

    repo = create_in_memory_repository_manager()
    orchestrator = DailyOrchestrator(
        repo_manager=repo,
        gemini_client=MagicMock(),
        image_provider=PlaceholderImageProvider(),  # produces image_url=None
        use_in_memory_db=True,
    )

    # When PlaceholderImageProvider produces None, run_content_pipeline raises ImageRequiredError, wrapped in DailyOrchestrationError
    with pytest.raises(DailyOrchestrationError):
        orchestrator.run(mode="mock", force=True, date_str="2026-10-13")
