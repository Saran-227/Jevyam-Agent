"""Targeted debug and regression tests for Telegram YES/NO inline approval callbacks.

Verifies:
1. YES button click approves post and triggers mocked publishing service.
2. NO button click rejects post and triggers draft regeneration.
3. Invalid approval token returns appropriate error and notifies user.
4. Expired approval token prevents approval and notifies user.
5. Duplicate button clicks are safely ignored (idempotency).
6. Database status transitions correctly throughout lifecycle.
7. answerCallbackQuery is called to stop the loading indicator.
8. Post JVY-TEST-DEBUG-001 approval token resolves and operates correctly.
"""

from datetime import datetime, timedelta
import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from agent.image_generator import ImageBrief
from api.dependencies import get_approval_service, get_telegram_service
from api.main import app
from api.services.approval_service import ApprovalService
from api.services.publishing_service import PublishingService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import Approval, ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from integrations.telegram.mock import MockTelegramProvider
from integrations.telegram.models import TelegramWebhookEvent


@pytest.fixture
def test_setup():
    repos = create_in_memory_repository_manager()
    mock_tg = MockTelegramProvider()
    pub_service = PublishingService(repo_manager=repos, mock_mode=True)
    approval_service = ApprovalService(
        repo_manager=repos,
        publishing_service=pub_service,
    )
    tg_service = TelegramService(
        approval_service=approval_service,
        provider=mock_tg,
    )

    # Seed initial post JVY-TEST-DEBUG-001
    brief = ImageBrief(
        visual_concept="Schematic diagram",
        style="Enterprise minimalist",
        composition="Left-to-right",
        color_direction="Navy and cyan",
        text_on_image="Align Systems",
    )
    post = Post(
        post_id="JVY-TEST-DEBUG-001",
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="03. Custom Software Development | Service Spotlight / Agency Introduction",
        topic='Company Introduction: "Your Business Needs More Than Just Software. It Needs the Right Technology Partner."',
        angle="Positioning Jevyam as an end-to-end solutions agency",
        target_audience="Founders and SME leaders",
        hook="Most operational bottlenecks aren't caused by a lack of software.",
        caption="Most operational bottlenecks aren't caused by a lack of software...",
        hashtags=["#SoftwareDevelopment", "#DigitalTransformation"],
        call_to_action="What is the single biggest operational bottleneck?",
        visual_concept="Schematic diagram",
        image_brief=brief,
        image_url="https://mock-storage.supabase.co/storage/v1/object/public/post-images/JVY-TEST-DEBUG-001/rev_1.png",
    )
    repos.posts.create(post)

    rev = PostRevision(
        post_id="JVY-TEST-DEBUG-001",
        revision_number=1,
        content_type=post.content_type,
        topic=post.topic,
        angle=post.angle,
        target_audience=post.target_audience,
        hook=post.hook,
        caption=post.caption,
        hashtags=post.hashtags,
        call_to_action=post.call_to_action,
        visual_concept=post.visual_concept,
        image_brief=brief,
        image_url=post.image_url,
    )
    repos.revisions.create(rev)

    # Create active approval token
    approval = repos.approvals.create_approval_request(
        post_id="JVY-TEST-DEBUG-001",
        revision_number=1,
        expires_at=datetime.now() + timedelta(hours=24),
    )

    return {
        "repos": repos,
        "mock_tg": mock_tg,
        "pub_service": pub_service,
        "approval_service": approval_service,
        "tg_service": tg_service,
        "post": post,
        "approval": approval,
    }


def test_telegram_yes_callback_flow(test_setup):
    """Clicking YES approves the post, answers callback, and publishes in mock mode."""
    tg_service = test_setup["tg_service"]
    mock_tg = test_setup["mock_tg"]
    repos = test_setup["repos"]
    token = test_setup["approval"].approval_token

    payload = {
        "update_id": 10001,
        "callback_query": {
            "id": "cb_query_yes_123",
            "from": {"id": 1293148688, "first_name": "Founder"},
            "message": {"message_id": 19, "chat": {"id": 1293148688}},
            "data": f"approve:{token}",
        },
    }

    response = tg_service.handle_webhook_callback(payload)

    # 1. Verification of webhook response
    assert response["status"] == "approved"
    assert response["post_id"] == "JVY-TEST-DEBUG-001"
    assert response["published"] is True

    # 2. answerCallbackQuery was invoked
    assert any(c["callback_query_id"] == "cb_query_yes_123" for c in mock_tg.answered_callbacks)

    # 3. Confirmation message sent back to Telegram
    assert len(mock_tg.sent_messages) >= 1
    last_msg = mock_tg.sent_messages[-1]
    assert "Approved!" in last_msg["text"]
    assert "JVY-TEST-DEBUG-001" in last_msg["text"]

    # 4. Database state updated
    post_in_db = repos.posts.get_by_post_id("JVY-TEST-DEBUG-001")
    assert post_in_db.status == PostStatus.PUBLISHED
    assert post_in_db.published_at is not None

    approval_in_db = repos.approvals.get_by_token(token)
    assert approval_in_db.status == ApprovalStatus.APPROVED


def test_telegram_duplicate_clicks_prevented(test_setup):
    """Subsequent clicks on the same approved token are safely rejected (idempotency)."""
    tg_service = test_setup["tg_service"]
    token = test_setup["approval"].approval_token

    payload_first = {
        "update_id": 10002,
        "callback_query": {
            "id": "cb_query_first",
            "from": {"id": 1293148688},
            "message": {"message_id": 19, "chat": {"id": 1293148688}},
            "data": f"approve:{token}",
        },
    }
    first_res = tg_service.handle_webhook_callback(payload_first)
    assert first_res["status"] == "approved"

    # Second click with same callback query ID
    second_res = tg_service.handle_webhook_callback(payload_first)
    assert second_res["status"] == "ignored"
    assert second_res["code"] == "DUPLICATE_CALLBACK"

    # Third click with new query ID on now-consumed token
    payload_third = {
        "update_id": 10003,
        "callback_query": {
            "id": "cb_query_new_id",
            "from": {"id": 1293148688},
            "message": {"message_id": 19, "chat": {"id": 1293148688}},
            "data": f"approve:{token}",
        },
    }
    third_res = tg_service.handle_webhook_callback(payload_third)
    assert third_res["status"] == "ignored"
    assert third_res["code"] == "ALREADY_PROCESSED"


def test_telegram_invalid_token_handling(test_setup):
    """Invalid or nonexistent approval token returns error and notifies founder."""
    tg_service = test_setup["tg_service"]
    mock_tg = test_setup["mock_tg"]

    payload = {
        "update_id": 10004,
        "callback_query": {
            "id": "cb_query_invalid",
            "from": {"id": 1293148688},
            "message": {"message_id": 19, "chat": {"id": 1293148688}},
            "data": "approve:appr_nonexistent_token_12345",
        },
    }

    res = tg_service.handle_webhook_callback(payload)
    assert res["status"] == "error"
    assert res["code"] == "TOKEN_NOT_FOUND"

    # Verify callback answered so Telegram loading spinner stops
    assert any(c["callback_query_id"] == "cb_query_invalid" for c in mock_tg.answered_callbacks)

    # Verify clear explanation message sent to founder
    assert any("Approval Not Found" in m["text"] for m in mock_tg.sent_messages)


def test_telegram_expired_token_handling(test_setup):
    """Expired token returns expired code and notifies founder."""
    tg_service = test_setup["tg_service"]
    mock_tg = test_setup["mock_tg"]
    repos = test_setup["repos"]

    # Create expired token
    expired_approval = repos.approvals.create_approval_request(
        post_id="JVY-TEST-DEBUG-001",
        revision_number=1,
        expires_at=datetime.now() - timedelta(minutes=5),
    )

    payload = {
        "update_id": 10005,
        "callback_query": {
            "id": "cb_query_expired",
            "from": {"id": 1293148688},
            "message": {"message_id": 19, "chat": {"id": 1293148688}},
            "data": f"approve:{expired_approval.approval_token}",
        },
    }

    res = tg_service.handle_webhook_callback(payload)
    assert res["status"] == "expired"
    assert res["code"] == "APPROVAL_EXPIRED"

    assert any(c["callback_query_id"] == "cb_query_expired" for c in mock_tg.answered_callbacks)
    assert any("Approval Expired" in m["text"] for m in mock_tg.sent_messages)


def test_telegram_no_reject_flow(test_setup):
    """Clicking NO transitions post and triggers regeneration."""
    tg_service = test_setup["tg_service"]
    mock_tg = test_setup["mock_tg"]
    repos = test_setup["repos"]
    token = test_setup["approval"].approval_token

    # Mock regenerate_draft to avoid live AI calls
    mock_new_draft = MagicMock()
    mock_new_draft.post_id = "JVY-TEST-DEBUG-001"
    mock_new_draft.revision = 2
    mock_new_draft.hook = "Updated hook"
    mock_new_draft.caption = "Updated caption"
    mock_new_draft.hashtags = ["#Tech"]
    mock_new_draft.visual_concept = "New concept"
    mock_new_draft.image_url = "https://mock-storage.supabase.co/img2.png"
    mock_new_draft.image_brief = ImageBrief(
        visual_concept="New concept",
        style="2D Slate",
        composition="Center",
        color_direction="Navy",
        text_on_image="Scale",
    )

    def mock_regen(*args, **kwargs):
        p = repos.posts.get_by_post_id("JVY-TEST-DEBUG-001")
        p.current_revision = 2
        p.status = PostStatus.PENDING_APPROVAL
        repos.posts.update(p)
        return mock_new_draft

    with patch("api.services.approval_service.regenerate_draft", side_effect=mock_regen):
        payload = {
            "update_id": 10006,
            "callback_query": {
                "id": "cb_query_no",
                "from": {"id": 1293148688},
                "message": {"message_id": 19, "chat": {"id": 1293148688}},
                "data": f"reject:{token}",
            },
        }

        res = tg_service.handle_webhook_callback(payload)
        assert res["status"] == "regenerated"
        assert res["post_id"] == "JVY-TEST-DEBUG-001"
        assert res["revision"] == 2

        # Verify callback was answered
        assert any(c["callback_query_id"] == "cb_query_no" for c in mock_tg.answered_callbacks)

        # Verify initial token was marked REJECTED
        old_approval = repos.approvals.get_by_token(token)
        assert old_approval.status == ApprovalStatus.REJECTED

        # Verify post is in PENDING_APPROVAL with revision 2
        post = repos.posts.get_by_post_id("JVY-TEST-DEBUG-001")
        assert post.current_revision == 2
        assert post.status == PostStatus.PENDING_APPROVAL


def test_telegram_webhook_http_endpoint(test_setup):
    """Test FastAPI /telegram/webhook endpoint end-to-end with TestClient."""
    tg_service = test_setup["tg_service"]
    token = test_setup["approval"].approval_token

    app.dependency_overrides[get_telegram_service] = lambda: tg_service

    client = TestClient(app)
    try:
        response = client.post(
            "/telegram/webhook",
            json={
                "update_id": 10007,
                "callback_query": {
                    "id": "cb_query_http",
                    "from": {"id": 1293148688},
                    "message": {"message_id": 19, "chat": {"id": 1293148688}},
                    "data": f"approve:{token}",
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_WEBHOOK_SECRET or ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["post_id"] == "JVY-TEST-DEBUG-001"
    finally:
        app.dependency_overrides.clear()
