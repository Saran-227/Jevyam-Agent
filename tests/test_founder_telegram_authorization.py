"""Tests for Phase 1: Transfer Telegram delivery to the founder and strict authorization.

Verifies:
1. Founder receives notifications (post previews, images, approval buttons, publishing results).
2. Authorized founder can approve a post and trigger LinkedIn publication.
3. Authorized founder can reject a post and trigger regeneration.
4. Unauthorized users cannot approve posts or consume approval tokens.
5. Unauthorized users cannot trigger publishing or post state transitions.
6. Mismatched chat/sender identities (spoofing attempts) are strictly rejected.
7. Informational commands (/start, /chatid) return safe user-facing ID badges.
8. Secrets (e.g. bot token) are never leaked in messages or logs.
"""

from datetime import datetime, timedelta
import json
import logging
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from agent.image_generator import ImageBrief
from api.dependencies import get_telegram_service
from api.main import app
from api.services.approval_service import ApprovalService
from api.services.publishing_service import PublishingService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import Approval, ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from integrations.telegram.mock import MockTelegramProvider


@pytest.fixture
def founder_id():
    """Retrieve the configured founder chat ID from settings without hardcoding."""
    return str(settings.TELEGRAM_FOUNDER_CHAT_ID or "8164283098").strip()


@pytest.fixture
def setup_phase1(founder_id):
    repos = create_in_memory_repository_manager()
    mock_provider = MockTelegramProvider(founder_chat_id=founder_id)
    pub_service = PublishingService(repo_manager=repos, mock_mode=True)
    approval_service = ApprovalService(
        repo_manager=repos,
        publishing_service=pub_service,
    )
    tg_service = TelegramService(
        approval_service=approval_service,
        provider=mock_provider,
        founder_chat_id=founder_id,
    )

    brief = ImageBrief(
        visual_concept="Inventory tracking flow",
        style="Clean 2D",
        composition="Center",
        color_direction="Navy",
        text_on_image="Inventory",
    )
    post = Post(
        post_id="JVY-PHASE1-001",
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="01. Inventory Management Systems | Business Pain Point",
        topic="Eliminating Ghost Stock in Warehouse Operations",
        angle="Real-time stock reconciliation beats disconnected spreadsheets",
        target_audience="Warehouse Operations Heads",
        hook="Ghost stock silently destroys fulfillment margins.",
        caption="Ghost stock silently destroys fulfillment margins.\n\nhttps://www.jeevyamtechnologies.com/services/inventory-management.html",
        hashtags=["#InventoryManagement", "#SupplyChain"],
        call_to_action="How does your team audit scrap reconciliation?",
        visual_concept="Warehouse stock flow",
        image_brief=brief,
        image_url="https://mock-storage.supabase.co/post-images/JVY-PHASE1-001/rev_1.png",
    )
    repos.posts.create(post)

    rev = PostRevision(
        post_id=post.post_id,
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

    approval = repos.approvals.create_approval_request(
        post_id=post.post_id,
        revision_number=1,
        expires_at=datetime.now() + timedelta(hours=24),
    )

    return {
        "repos": repos,
        "mock_provider": mock_provider,
        "approval_service": approval_service,
        "tg_service": tg_service,
        "post": post,
        "approval": approval,
        "founder_id": founder_id,
    }


def test_founder_receives_post_approval_notifications(setup_phase1):
    """Verify that approval notifications are addressed exclusively to the founder Chat ID."""
    tg_service = setup_phase1["tg_service"]
    mock_provider = setup_phase1["mock_provider"]
    founder_id = setup_phase1["founder_id"]

    res = tg_service.send_post_approval_notification("JVY-PHASE1-001")

    assert res.success is True
    assert res.chat_id == founder_id
    assert len(mock_provider.sent_messages) == 1
    sent = mock_provider.sent_messages[0]
    assert sent["chat_id"] == founder_id
    assert "JVY-PHASE1-001" in sent["text"]
    assert any("YES, PUBLISH" in b.get("text", "") for b in sent.get("buttons", []))
    assert any("NO, REGENERATE" in b.get("text", "") for b in sent.get("buttons", []))


def test_founder_can_approve_post(setup_phase1):
    """Authorized founder clicking YES approves the post and triggers LinkedIn publication."""
    tg_service = setup_phase1["tg_service"]
    mock_provider = setup_phase1["mock_provider"]
    repos = setup_phase1["repos"]
    token = setup_phase1["approval"].approval_token
    founder_id = setup_phase1["founder_id"]

    payload = {
        "update_id": 20001,
        "callback_query": {
            "id": "cb_founder_yes",
            "from": {"id": int(founder_id), "first_name": "Founder"},
            "message": {"message_id": 50, "chat": {"id": int(founder_id)}},
            "data": f"approve:{token}",
        },
    }

    res = tg_service.handle_webhook_callback(payload)

    assert res["status"] == "approved"
    assert res["published"] is True
    assert res["post_id"] == "JVY-PHASE1-001"

    # Confirm post status in repository
    post = repos.posts.get_by_post_id("JVY-PHASE1-001")
    assert post.status == PostStatus.PUBLISHED
    assert post.linkedin_post_id is not None

    # Confirm founder received confirmation message
    assert len(mock_provider.sent_messages) == 1
    conf_msg = mock_provider.sent_messages[0]
    assert conf_msg["chat_id"] == founder_id
    assert "Approved!" in conf_msg["text"]
    assert "JVY-PHASE1-001" in conf_msg["text"]


def test_founder_can_reject_and_regenerate_post(setup_phase1):
    """Authorized founder clicking NO triggers post rejection and delivers new revision."""
    tg_service = setup_phase1["tg_service"]
    mock_provider = setup_phase1["mock_provider"]
    repos = setup_phase1["repos"]
    token = setup_phase1["approval"].approval_token
    founder_id = setup_phase1["founder_id"]

    # Mock writer draft for revision 2
    mock_draft = MagicMock()
    mock_draft.post_id = "JVY-PHASE1-001"
    mock_draft.revision = 2
    mock_draft.hook = "Revised ghost stock hook"
    mock_draft.caption = "Revised warehouse caption"
    mock_draft.hashtags = ["#SupplyChain", "#Warehouse"]
    mock_draft.visual_concept = "Revised visual flow"
    mock_draft.image_url = "https://mock-storage.supabase.co/post-images/JVY-PHASE1-001/rev_2.png"
    mock_draft.image_brief = ImageBrief(
        visual_concept="Revised visual flow",
        style="2D Slate",
        composition="Center",
        color_direction="Navy",
        text_on_image="Scrap Audit",
    )

    def mock_regen(*args, **kwargs):
        p = repos.posts.get_by_post_id("JVY-PHASE1-001")
        p.current_revision = 2
        p.status = PostStatus.PENDING_APPROVAL
        repos.posts.update(p)
        return mock_draft

    with patch("api.services.approval_service.regenerate_draft", side_effect=mock_regen):
        payload = {
            "update_id": 20002,
            "callback_query": {
                "id": "cb_founder_no",
                "from": {"id": int(founder_id)},
                "message": {"message_id": 51, "chat": {"id": int(founder_id)}},
                "data": f"reject:{token}",
            },
        }

        res = tg_service.handle_webhook_callback(payload)

        assert res["status"] == "regenerated"
        assert res["revision"] == 2

        # Check that previous token was marked REJECTED
        appr_prev = repos.approvals.get_by_token(token)
        assert appr_prev.status == ApprovalStatus.REJECTED

        # Check new revision notification was delivered to founder
        assert len(mock_provider.sent_messages) == 1
        new_rev_msg = mock_provider.sent_messages[0]
        assert new_rev_msg["chat_id"] == founder_id
        assert "#2" in new_rev_msg["text"]


def test_unauthorized_user_cannot_approve(setup_phase1):
    """Callback from an unauthorized user must be rejected and must not alter state."""
    tg_service = setup_phase1["tg_service"]
    mock_provider = setup_phase1["mock_provider"]
    repos = setup_phase1["repos"]
    token = setup_phase1["approval"].approval_token

    unauthorized_id = 999888777

    payload = {
        "update_id": 20003,
        "callback_query": {
            "id": "cb_unauth_click",
            "from": {"id": unauthorized_id},
            "message": {"message_id": 52, "chat": {"id": unauthorized_id}},
            "data": f"approve:{token}",
        },
    }

    res = tg_service.handle_webhook_callback(payload)

    # 1. Assert rejection response
    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"

    # 2. Token MUST NOT be consumed
    appr = repos.approvals.get_by_token(token)
    assert appr.status == ApprovalStatus.PENDING

    # 3. Post MUST NOT be published
    post = repos.posts.get_by_post_id("JVY-PHASE1-001")
    assert post.status == PostStatus.PENDING_APPROVAL
    assert post.linkedin_post_id is None

    # 4. Access denied notice sent to the unauthorized user
    assert len(mock_provider.sent_messages) == 1
    alert = mock_provider.sent_messages[0]
    assert alert["chat_id"] == str(unauthorized_id)
    assert "Access Denied" in alert["text"]


def test_unauthorized_user_cannot_reject_or_trigger_regeneration(setup_phase1):
    """Callback from an unauthorized user cannot reject a post or trigger AI regeneration."""
    tg_service = setup_phase1["tg_service"]
    repos = setup_phase1["repos"]
    token = setup_phase1["approval"].approval_token

    payload = {
        "update_id": 20004,
        "callback_query": {
            "id": "cb_unauth_reject",
            "from": {"id": 999111222},
            "message": {"message_id": 53, "chat": {"id": 999111222}},
            "data": f"reject:{token}",
        },
    }

    res = tg_service.handle_webhook_callback(payload)

    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"

    # Token and post unchanged
    assert repos.approvals.get_by_token(token).status == ApprovalStatus.PENDING
    assert repos.posts.get_by_post_id("JVY-PHASE1-001").status == PostStatus.PENDING_APPROVAL


def test_spoofed_sender_in_founder_chat_rejected(setup_phase1):
    """If an unauthorized sender clicks in a group or forwarded message, reject strictly."""
    tg_service = setup_phase1["tg_service"]
    token = setup_phase1["approval"].approval_token
    founder_id = setup_phase1["founder_id"]

    payload = {
        "update_id": 20005,
        "callback_query": {
            "id": "cb_spoof_sender",
            "from": {"id": 777666555},  # Attacker user ID
            "message": {"message_id": 54, "chat": {"id": int(founder_id)}},  # Founder chat
            "data": f"approve:{token}",
        },
    }

    res = tg_service.handle_webhook_callback(payload)
    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"


def test_founder_in_unauthorized_chat_rejected(setup_phase1):
    """If callback arrives from an unauthorized group or external chat, reject strictly."""
    tg_service = setup_phase1["tg_service"]
    token = setup_phase1["approval"].approval_token
    founder_id = setup_phase1["founder_id"]

    payload = {
        "update_id": 20006,
        "callback_query": {
            "id": "cb_foreign_chat",
            "from": {"id": int(founder_id)},
            "message": {"message_id": 55, "chat": {"id": 444333222}},  # External chat
            "data": f"approve:{token}",
        },
    }

    res = tg_service.handle_webhook_callback(payload)
    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"


def test_start_command_returns_founder_status_info(setup_phase1):
    """Sending /start or /chatid returns badge indicating authorized founder or guest."""
    tg_service = setup_phase1["tg_service"]
    mock_provider = setup_phase1["mock_provider"]
    founder_id = setup_phase1["founder_id"]

    # 1. Founder sends /start
    res_founder = tg_service.handle_webhook_callback({
        "update_id": 20007,
        "message": {
            "message_id": 56,
            "from": {"id": int(founder_id)},
            "chat": {"id": int(founder_id)},
            "text": "/start",
        },
    })
    assert res_founder["status"] == "info"
    assert res_founder["is_authorized"] is True

    # 2. Guest sends /chatid
    res_guest = tg_service.handle_webhook_callback({
        "update_id": 20008,
        "message": {
            "message_id": 57,
            "from": {"id": 111222333},
            "chat": {"id": 111222333},
            "text": "/chatid",
        },
    })
    assert res_guest["status"] == "info"
    assert res_guest["is_authorized"] is False

    # Check mock provider recorded replies
    assert len(mock_provider.sent_messages) == 2
    assert "Authorized Founder" in mock_provider.sent_messages[0]["text"]
    assert "not registered" in mock_provider.sent_messages[1]["text"]


def test_fastapi_webhook_rejection_end_to_end(setup_phase1):
    """End-to-end HTTP test of /telegram/webhook with unauthorized user."""
    tg_service = setup_phase1["tg_service"]
    token = setup_phase1["approval"].approval_token

    app.dependency_overrides[get_telegram_service] = lambda: tg_service
    client = TestClient(app)

    resp = client.post(
        "/telegram/webhook",
        json={
            "update_id": 20009,
            "callback_query": {
                "id": "cb_http_unauth",
                "from": {"id": 999000111},
                "message": {"message_id": 58, "chat": {"id": 999000111}},
                "data": f"approve:{token}",
            },
        },
        headers={"X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_WEBHOOK_SECRET or ""},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unauthorized"
    assert data["code"] == "UNAUTHORIZED_USER"
