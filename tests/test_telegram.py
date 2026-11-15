"""Comprehensive unit tests for Telegram integration provider, approval message formatting, and webhook callbacks."""

from datetime import datetime, timedelta
import json
import logging
import os
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from agent.image_generator import ImageBrief
from agent.orchestrator import DailyOrchestrator
from api.dependencies import get_approval_service, get_telegram_service
from api.main import app
from api.services.approval_service import ApprovalService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import Approval, ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from integrations.telegram.client import TelegramApiProvider, mask_sensitive_url
from integrations.telegram.mock import MockTelegramProvider
from integrations.telegram.models import (
    TelegramApprovalMessagePayload,
    TelegramMessageResponse,
    TelegramWebhookEvent,
)


@pytest.fixture(autouse=True)
def configure_test_founder_chat_id(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_FOUNDER_CHAT_ID", "123456")


@pytest.fixture
def mock_repo_manager():
    return create_in_memory_repository_manager()


@pytest.fixture
def sample_draft_post(mock_repo_manager):
    brief = ImageBrief(
        visual_concept="Architecture flowchart",
        style="Slate 2D",
        composition="Center",
        color_direction="Charcoal",
        text_on_image="Automation",
    )
    post = Post(
        post_id="JVY-20261006-001",
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="software engineering",
        topic="Event-Driven Automation Architecture",
        angle="Webhooks over cron",
        target_audience="Tech Leads",
        hook="Cron jobs fail silently.",
        caption="Cron jobs fail silently. Use idempotent webhooks.\n\nHow do you handle retries?",
        hashtags=["#DevOps", "#Cloud"],
        call_to_action="How do you handle retries?",
        visual_concept="Architecture flowchart",
        image_brief=brief,
        image_url="https://cdn.jevyam.com/visuals/jvy-001.png",
    )
    mock_repo_manager.posts.create(post)
    mock_repo_manager.revisions.create(
        PostRevision(
            post_id="JVY-20261006-001",
            revision_number=1,
            topic=post.topic,
            angle=post.angle,
            content_type=post.content_type,
            target_audience=post.target_audience,
            hook=post.hook,
            caption=post.caption,
            hashtags=post.hashtags,
            call_to_action=post.call_to_action,
            visual_concept=post.visual_concept,
            image_brief=brief,
            image_url=post.image_url,
        )
    )
    return post


# ==============================================================================
# 1. Telegram provider initialization
# ==============================================================================
def test_telegram_provider_initialization():
    provider = TelegramApiProvider(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        founder_chat_id="987654321",
        webhook_secret="my_sec_token",
        base_url="https://api.telegram.org",
    )
    assert provider.bot_token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    assert provider.founder_chat_id == "987654321"
    assert provider.webhook_secret == "my_sec_token"
    assert provider.base_url == "https://api.telegram.org"


# ==============================================================================
# 2. Missing token configuration
# ==============================================================================
def test_missing_token_configuration():
    # Empty token
    provider = TelegramApiProvider(
        bot_token="",
        founder_chat_id="987654321",
    )
    is_valid, errors = provider.validate_configuration()
    assert is_valid is False
    assert any("TELEGRAM_BOT_TOKEN" in e for e in errors)

    # Placeholder token
    placeholder_provider = TelegramApiProvider(
        bot_token="your_telegram_bot_token_here",
        founder_chat_id="987654321",
    )
    is_valid, errors = placeholder_provider.validate_configuration()
    assert is_valid is False
    assert any("placeholder" in e for e in errors)


# ==============================================================================
# 3. Missing founder Chat ID
# ==============================================================================
def test_missing_founder_chat_id():
    # Empty chat ID
    provider = TelegramApiProvider(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        founder_chat_id="",
    )
    is_valid, errors = provider.validate_configuration()
    assert is_valid is False
    assert any("TELEGRAM_FOUNDER_CHAT_ID" in e for e in errors)

    # Sending with no chat ID fails cleanly
    res = provider.send_text_message(chat_id="", text="Hello")
    assert res.success is False
    assert "missing" in res.error.lower()


# ==============================================================================
# 4. Mock Telegram send
# ==============================================================================
def test_mock_telegram_send():
    mock_provider = MockTelegramProvider(founder_chat_id="123456789")
    res = mock_provider.send_text_message(
        chat_id="123456789",
        text="Hello Founder!",
    )
    assert res.success is True
    assert res.provider == "mock"
    assert res.message_id.startswith("mock_tg_msg_")
    assert len(mock_provider.sent_messages) == 1
    assert mock_provider.sent_messages[0]["text"] == "Hello Founder!"


# ==============================================================================
# 5. Approval message formatting
# ==============================================================================
def test_approval_message_formatting():
    provider = TelegramApiProvider(bot_token="token_123", founder_chat_id="123456")
    payload = TelegramApprovalMessagePayload(
        post_id="JVY-20261006-001",
        revision_number=1,
        hook="Cron jobs fail silently.",
        caption="Full LinkedIn caption here.",
        hashtags=["#DevOps", "#Architecture"],
        visual_concept="Flowchart blueprint",
        approval_token="appr_sec_tok_12345",
        approval_url="http://127.0.0.1:8000/approve/appr_sec_tok_12345",
        image_url="https://cdn.jevyam.com/visuals/jvy-001.png",
    )
    text = provider.format_approval_text(payload)

    assert "Jevyam Technologies — LinkedIn Post Approval" in text
    assert "Revision:</b> #1" in text
    assert "JVY-20261006-001" in text
    assert "Full LinkedIn caption here." in text
    assert "#DevOps" in text
    assert "Flowchart blueprint" in text
    assert "Please approve this post:" in text
    # Crucial security requirement: unguessable raw token must NOT be in the visible message text
    assert "appr_sec_tok_12345" not in text


# ==============================================================================
# 6. YES inline button & 7. NO inline button
# ==============================================================================
def test_yes_and_no_inline_buttons():
    mock_provider = MockTelegramProvider(founder_chat_id="123456789")
    payload = TelegramApprovalMessagePayload(
        post_id="JVY-20261006-001",
        revision_number=1,
        hook="Cron jobs fail silently.",
        caption="Full LinkedIn caption here.",
        hashtags=["#DevOps"],
        approval_token="appr_very_long_secret_token_abc123xyz789",
        approval_url="http://127.0.0.1:8000/approve/appr_very_long_secret_token_abc123xyz789",
    )
    res = mock_provider.send_approval_message(payload)
    assert res.success is True

    record = mock_provider.sent_messages[0]
    buttons = record["buttons"]
    assert len(buttons) == 2

    # 6. YES Button
    yes_btn = buttons[0]
    assert yes_btn["text"] == "✅ YES, PUBLISH"
    assert yes_btn["callback_data"] == f"approve:{payload.approval_token}"
    # Verify Telegram 64-byte limit constraint
    assert len(yes_btn["callback_data"].encode("utf-8")) <= 64

    # 7. NO Button
    no_btn = buttons[1]
    assert no_btn["text"] == "❌ NO, REGENERATE"
    assert no_btn["callback_data"] == f"reject:{payload.approval_token}"
    assert len(no_btn["callback_data"].encode("utf-8")) <= 64


# ==============================================================================
# 8. Callback parsing
# ==============================================================================
def test_callback_parsing():
    provider = TelegramApiProvider(bot_token="token_123")
    update_payload = {
        "update_id": 99991,
        "callback_query": {
            "id": "query_id_777",
            "from": {"id": 123456, "first_name": "Saranjeet"},
            "message": {
                "message_id": 101,
                "chat": {"id": 123456, "type": "private"},
                "date": 1727618000,
                "text": "Post text",
            },
            "data": "approve:appr_abc123",
        },
    }
    event = provider.parse_webhook_event(update_payload)
    assert event is not None
    assert event.event_type == "callback_query"
    assert event.callback_query_id == "query_id_777"
    assert event.callback_data == "approve:appr_abc123"
    assert event.chat_id == "123456"
    assert event.sender_id == "123456"
    assert event.message_id == "101"


# ==============================================================================
# 9. Invalid callback
# ==============================================================================
def test_invalid_callback():
    mock_provider = MockTelegramProvider()
    service = TelegramService(provider=mock_provider)

    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99992,
        "callback_query": {
            "id": "query_inv_1",
            "from": {"id": 123456},
            "message": {"message_id": 102, "chat": {"id": 123456}},
            "data": "corrupted_payload_no_token",
        },
    }
    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["code"] == "INVALID_CALLBACK"


# ==============================================================================
# 10. Unknown approval
# ==============================================================================
def test_unknown_approval(mock_repo_manager):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)

    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99993,
        "callback_query": {
            "id": "query_unknown",
            "from": {"id": 123456},
            "message": {"message_id": 103, "chat": {"id": 123456}},
            "data": "approve:appr_nonexistent_token_12345",
        },
    }
    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["code"] == "TOKEN_NOT_FOUND"


# ==============================================================================
# 11. Expired approval
# ==============================================================================
def test_expired_approval(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    # Force expiration into past
    appr = mock_repo_manager.approvals.get_by_token(token)
    appr.expires_at = datetime.now() - timedelta(days=2)
    mock_repo_manager.approvals.update(appr)

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99994,
        "callback_query": {
            "id": "query_exp",
            "from": {"id": 123456},
            "message": {"message_id": 104, "chat": {"id": 123456}},
            "data": f"approve:{token}",
        },
    }
    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "expired"
    assert data["code"] == "APPROVAL_EXPIRED"


# ==============================================================================
# 12. Duplicate callback
# ==============================================================================
def test_duplicate_callback(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99995,
        "callback_query": {
            "id": "query_duplicate_1",
            "from": {"id": 123456},
            "message": {"message_id": 105, "chat": {"id": 123456}},
            "data": f"approve:{token}",
        },
    }

    # First call: successfully approved
    resp1 = client.post("/telegram/webhook", json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "approved"

    # Second call with same callback_query.id: caught as duplicate
    resp2 = client.post("/telegram/webhook", json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ignored"
    assert resp2.json()["code"] == "DUPLICATE_CALLBACK"


# ==============================================================================
# 13. YES → approval → LinkedIn publication
# ==============================================================================
def test_yes_approval_linkedin_publication(mock_repo_manager, sample_draft_post):
    mock_pub = MagicMock()
    mock_pub.publish_approved_post.return_value = {
        "external_post_id": "urn:li:share:987654321",
        "post_url": "https://www.linkedin.com/feed/update/urn:li:share:987654321",
    }

    approval_service = ApprovalService(repo_manager=mock_repo_manager, publishing_service=mock_pub)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99996,
        "callback_query": {
            "id": "query_yes_publish",
            "from": {"id": 123456},
            "message": {"message_id": 106, "chat": {"id": 123456}},
            "data": f"approve:{token}",
        },
    }

    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["post_id"] == "JVY-20261006-001"

    # Verify post state in DB
    updated_post = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert updated_post.status == PostStatus.APPROVED

    # Verify confirmation text was sent to founder chat on Telegram
    assert len(mock_provider.sent_messages) == 1
    assert "approved" in mock_provider.sent_messages[0]["text"].lower()


# ==============================================================================
# 14. NO → regeneration → new approval & 15. New revision → new Telegram approval
# ==============================================================================
def test_no_regeneration_and_new_approval(mock_repo_manager, sample_draft_post):
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Pivoted Topic: Kafka Architecture",
            "angle": "Consumer lag monitoring",
            "content_type": "technology insight",
            "target_audience": "Architects",
            "reason": "Founder rejected previous draft",
        })),
        MagicMock(text=json.dumps({
            "hook": "Kafka lag is silent downtime.",
            "caption": "Kafka lag is silent downtime.\n\nSet up proactive alerts.\n\nHow do you monitor lag?",
            "hashtags": ["#Kafka", "#Streaming"],
            "call_to_action": "How do you monitor lag?",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Kafka stream diagram",
            "style": "Vector",
            "composition": "Centered",
            "color_direction": "Charcoal and orange",
            "text_on_image": "Stream Reliability",
            "aspect_ratio": "1:1",
        })),
    ]

    approval_service = ApprovalService(repo_manager=mock_repo_manager, gemini_client=mock_gemini)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99997,
        "callback_query": {
            "id": "query_no_regen",
            "from": {"id": 123456},
            "message": {"message_id": 107, "chat": {"id": 123456}},
            "data": f"reject:{token}",
        },
    }

    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("accepted", "regenerated")

    # 14. Old approval marked REJECTED
    old_approval = mock_repo_manager.approvals.get_by_token(token)
    assert old_approval.status == ApprovalStatus.REJECTED

    # Post revision incremented to 2
    post = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert post.current_revision == 2

    # 15. Verify NEW approval notification with inline buttons was dispatched to Telegram founder chat
    assert len(mock_provider.sent_messages) == 1
    new_msg = mock_provider.sent_messages[0]
    assert new_msg["type"] == "approval_interactive"
    assert new_msg["payload"]["revision_number"] == 2


# ==============================================================================
# 16. Telegram API error
# ==============================================================================
def test_telegram_api_error():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.content = b'{"ok": false, "description": "Bad Request: chat not found", "error_code": 400}'
    mock_resp.json.return_value = {"ok": False, "description": "Bad Request: chat not found", "error_code": 400}
    mock_client.post.return_value = mock_resp


    provider = TelegramApiProvider(
        bot_token="token_123",
        founder_chat_id="invalid_chat_id",
        http_client=mock_client,
    )

    result = provider.send_text_message(chat_id="invalid_chat_id", text="Test")
    assert result.success is False
    assert "chat not found" in result.error


# ==============================================================================
# 17. Telegram timeout
# ==============================================================================
def test_telegram_timeout():
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out after 15s")

    provider = TelegramApiProvider(
        bot_token="token_123",
        founder_chat_id="123456",
        http_client=mock_client,
    )

    result = provider.send_text_message(chat_id="123456", text="Test timeout")
    assert result.success is False
    assert "timed out" in result.error.lower()


# ==============================================================================
# 18. Secret values never appearing in logs
# ==============================================================================
def test_secret_values_never_appearing_in_logs(caplog):
    secret_token = "secret_bot_token_789456123"
    secret_webhook = "my_super_secret_webhook_pass"

    url = f"https://api.telegram.org/bot{secret_token}/sendMessage"
    masked = mask_sensitive_url(url)
    assert secret_token not in masked
    assert "<MASKED_TELEGRAM_TOKEN>" in masked

    provider = TelegramApiProvider(
        bot_token=secret_token,
        founder_chat_id="123456",
        webhook_secret=secret_webhook,
    )

    with caplog.at_level(logging.INFO):
        # Attempt send to invalid URL with mock client to trigger logging
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = RuntimeError(f"Connection failed to {url}")
        provider._http_client = mock_client
        provider.send_text_message(chat_id="123456", text="Hello")

    # Verify secret_token is not in captured logs
    assert secret_token not in caplog.text


# ==============================================================================
# 19. Telegram Webhook Secret Header Verification
# ==============================================================================
def test_telegram_webhook_secret_verification():
    mock_provider = MockTelegramProvider(webhook_secret="configured_secret_token_abc")
    service = TelegramService(provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {"update_id": 100}

    # 1. Missing secret header -> HTTP 403
    bad_resp1 = client.post("/telegram/webhook", json=payload)
    assert bad_resp1.status_code == 403
    assert bad_resp1.json()["code"] == "AUTH_FAILED"

    # 2. Wrong secret header -> HTTP 403
    bad_resp2 = client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
    )
    assert bad_resp2.status_code == 403

    # 3. Matching secret header -> HTTP 200
    good_resp = client.post(
        "/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "configured_secret_token_abc"},
    )
    assert good_resp.status_code == 200


# ==============================================================================
# 20. End-to-end Orchestration with Telegram
# ==============================================================================
def test_daily_run_mock_telegram_end_to_end(tmp_path):
    repos = create_in_memory_repository_manager()
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Event-Driven Automation Architecture",
            "angle": "Webhooks over cron",
            "content_type": "software engineering",
            "target_audience": "Tech Leads",
            "reason": "Clear architectural insights.",
        })),
        MagicMock(text=json.dumps({
            "hook": "Cron jobs fail silently.",
            "caption": "Cron jobs fail silently. When scaling automation, idempotency is paramount.",
            "hashtags": ["#DevOps", "#Cloud"],
            "call_to_action": "How do you handle retries?",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Clean blueprint",
            "style": "Dark mode modern blueprint",
            "composition": "Horizontal message queue pipeline",
            "color_direction": "Slate blue",
            "text_on_image": "Idempotent Architectures",
            "aspect_ratio": "1:1",
        })),
    ]

    mock_tg = MockTelegramProvider()
    approval_svc = ApprovalService(repo_manager=repos, gemini_client=mock_gemini)
    tg_svc = TelegramService(approval_service=approval_svc, provider=mock_tg)

    with patch.object(settings, "APPROVAL_PROVIDER", "telegram"):
        orchestrator = DailyOrchestrator(
            repo_manager=repos,
            gemini_client=mock_gemini,
            approval_service=approval_svc,
            telegram_service=tg_svc,
            use_in_memory_db=True,
            posts_dir=tmp_path,
        )

        res = orchestrator.run(mode="mock", date_str="2026-10-06")

        assert res.success is True
        assert res.mode == "mock"
        assert res.post_id == "JVY-20261006-001"
        assert res.telegram_message_id is not None
        assert res.telegram_message_id.startswith("mock_tg_msg_")
        assert len(mock_tg.sent_messages) == 1
        assert mock_tg.sent_messages[0]["type"] == "approval_interactive"


def test_telegram_webhook_gemini_failure_and_recovery(mock_repo_manager, sample_draft_post):
    """21. Test that transient Gemini failure in Telegram callback returns processing error without consuming token, allowing subsequent retry."""
    from agent.exceptions import GeminiUnavailableError

    mock_gemini = MagicMock()
    approval_service = ApprovalService(repo_manager=mock_repo_manager, gemini_client=mock_gemini)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99998,
        "callback_query": {
            "id": "query_fail_then_retry",
            "from": {"id": 123456},
            "message": {"message_id": 108, "chat": {"id": 123456}},
            "data": f"reject:{token}",
        },
    }

    # 1. Simulate failure during regeneration
    mock_gemini.models.generate_content.side_effect = GeminiUnavailableError("Gemini 503 unavailable")

    resp1 = client.post("/telegram/webhook", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] in ("accepted", "error")

    # Founder received a polite failure notification on Telegram
    assert len(mock_provider.sent_messages) == 1
    assert "delayed" in mock_provider.sent_messages[0]["text"].lower()

    # Token is STILL PENDING
    tok = mock_repo_manager.approvals.get_by_token(token)
    assert tok.status == ApprovalStatus.PENDING
    # Post is STILL PENDING_APPROVAL
    p = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert p.status == PostStatus.PENDING_APPROVAL
    assert p.current_revision == 1

    # 2. Simulate Gemini recovering on subsequent callback attempt
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Recovered Topic",
            "angle": "Recovered Angle",
            "content_type": "technology insight",
            "target_audience": "CTOs",
            "reason": "Recovered after failure",
        })),
        MagicMock(text=json.dumps({
            "hook": "Recovered hook",
            "caption": "Recovered caption",
            "hashtags": ["#Tech"],
            "call_to_action": "Recovered CTA",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Recovered visual",
            "style": "Vector",
            "composition": "Center",
            "color_direction": "Charcoal",
            "text_on_image": "Recovered",
            "aspect_ratio": "1:1",
        })),
    ]

    resp2 = client.post("/telegram/webhook", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] in ("accepted", "regenerated")

    # Token is now consumed as REJECTED
    tok_after = mock_repo_manager.approvals.get_by_token(token)
    assert tok_after.status == ApprovalStatus.REJECTED
    assert p.current_revision == 1  # prior instance
    p_updated = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert p_updated.current_revision == 2


def test_telegram_webhook_yes_in_dry_run_never_calls_linkedin(mock_repo_manager, sample_draft_post):
    """22. Test that clicking YES via Telegram in dry_run / test mode records successful publication without calling external LinkedIn API."""
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 99999,
        "callback_query": {
            "id": "query_yes_dry_run",
            "from": {"id": 123456},
            "message": {"message_id": 109, "chat": {"id": 123456}},
            "data": f"approve:{token}",
        },
    }

    with patch.object(settings, "DRY_RUN", True), patch.object(settings, "LINKEDIN_MOCK_PUBLISHING", True):
        with patch("integrations.linkedin.client.LinkedInClient.publish_text_post") as mock_real_call:
            mock_real_call.side_effect = RuntimeError("External LinkedIn publish must NEVER be called!")

            resp = client.post("/telegram/webhook", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "approved"
            assert data["published"] is True
            mock_real_call.assert_not_called()

            # Verify post state in DB
            post = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
            assert post.status == PostStatus.PUBLISHED
            assert post.linkedin_post_id.startswith("urn:li:share:mock_")

            # Verify confirmation text was sent to founder chat on Telegram
            assert len(mock_provider.sent_messages) == 1
            sent_text = mock_provider.sent_messages[0]["text"]
            assert "approved" in sent_text.lower()


# ==============================================================================
# 23. Fast webhook acknowledgment with BackgroundTasks
# ==============================================================================
def test_telegram_webhook_fast_acknowledgment_with_background_tasks(mock_repo_manager, sample_draft_post):
    """Verify that clicking NO returns prompt HTTP 200 accepted while background task creates revision 2 and sends notification."""
    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Fast Background Topic",
            "angle": "Async decoupling",
            "content_type": "technology insight",
            "target_audience": "Engineers",
            "reason": "Decoupled webhook processing",
        })),
        MagicMock(text=json.dumps({
            "hook": "Fast webhooks prevent timeouts.",
            "caption": "Fast webhooks prevent timeouts.\n\nOffload heavy AI tasks.",
            "hashtags": ["#Architecture"],
            "call_to_action": "How do you handle webhook timeouts?",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Background worker queue diagram",
            "style": "Vector",
            "composition": "Centered",
            "color_direction": "Charcoal and blue",
            "text_on_image": "Async Decoupling",
            "aspect_ratio": "1:1",
        })),
    ]

    approval_service = ApprovalService(repo_manager=mock_repo_manager, gemini_client=mock_gemini)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 100001,
        "callback_query": {
            "id": "query_fast_ack",
            "from": {"id": 123456},
            "message": {"message_id": 110, "chat": {"id": 123456}},
            "data": f"reject:{token}",
        },
    }

    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["code"] == "REGENERATION_SCHEDULED"

    # Background task executed and created revision 2
    post = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert post.current_revision == 2

    # New approval message sent to Telegram
    assert len(mock_provider.sent_messages) == 1
    assert "#2" in mock_provider.sent_messages[0]["text"]
    assert "jvy-20261006-001" in mock_provider.sent_messages[0]["text"].lower()


# ==============================================================================
# 24. ClientDisconnect gracefully handled
# ==============================================================================
def test_telegram_webhook_client_disconnect_gracefully_handled():
    """Verify that ClientDisconnect during request.body() returns HTTP 400 without unhandled traceback."""
    from starlette.requests import ClientDisconnect

    client = TestClient(app)

    with patch("fastapi.Request.body", side_effect=ClientDisconnect()):
        resp = client.post("/telegram/webhook", content=b"{}")
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == "aborted"
        assert "disconnected" in data["message"].lower()


# ==============================================================================
# 25. Duplicate callback while in-progress is ignored
# ==============================================================================
def test_telegram_webhook_duplicate_callback_while_in_progress_ignored(mock_repo_manager, sample_draft_post):
    """Verify that duplicate callback queries while post is in REGENERATING state or token in flight are cleanly ignored."""
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    # Mark post status in database as REGENERATING (simulating active in-progress regeneration)
    mock_repo_manager.posts.update_status("JVY-20261006-001", PostStatus.REJECTED)
    mock_repo_manager.posts.update_status("JVY-20261006-001", PostStatus.REGENERATING)

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 100002,
        "callback_query": {
            "id": "query_duplicate_in_progress",
            "from": {"id": 123456},
            "message": {"message_id": 111, "chat": {"id": 123456}},
            "data": f"reject:{token}",
        },
    }

    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"
    assert data["code"] == "IN_PROGRESS"


# ==============================================================================
# 26. Gemini 503 rollback sends polite Telegram failure notice
# ==============================================================================
def test_telegram_webhook_gemini_503_sends_polite_failure_notice(mock_repo_manager, sample_draft_post):
    """Verify that when Gemini fails in background task, post and token remain retryable and founder receives a notice on Telegram."""
    from agent.exceptions import GeminiUnavailableError

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = GeminiUnavailableError("Gemini 503 unavailable")

    approval_service = ApprovalService(repo_manager=mock_repo_manager, gemini_client=mock_gemini)
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 100003,
        "callback_query": {
            "id": "query_503_failure",
            "from": {"id": 123456},
            "message": {"message_id": 112, "chat": {"id": 123456}},
            "data": f"reject:{token}",
        },
    }

    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200

    # Token and post are STILL retryable
    appr_after = mock_repo_manager.approvals.get_by_token(token)
    assert appr_after.status == ApprovalStatus.PENDING

    post_after = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert post_after.status == PostStatus.PENDING_APPROVAL
    assert post_after.current_revision == 1

    # Failure notice was sent to Telegram founder chat
    assert len(mock_provider.sent_messages) == 1
    sent_text = mock_provider.sent_messages[0]["text"]
    assert "delayed" in sent_text.lower()
    assert "pending" in sent_text.lower()
    assert "retry" in sent_text.lower()
    # Ensure no internal error strings or secrets leaked
    assert "503" not in sent_text or "unavailable" in sent_text
    assert "token" not in sent_text.lower()


# ==============================================================================
# 27. Telegram photo approval: single message (<=1024 chars) vs linked messages (>1024 chars)
# ==============================================================================
def test_telegram_photo_approval_delivery_single_and_linked():
    """Verify that photo approval sends single sendPhoto if <= 1024 chars, and linked sendPhoto + sendMessage if > 1024 chars."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"ok": true, "result": {"message_id": 555}}'
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 555}}
    mock_http.post.return_value = mock_resp

    provider = TelegramApiProvider(
        bot_token="test_bot_token",
        founder_chat_id="12345678",
        http_client=mock_http,
    )

    # 1. Short caption <= 1024 chars: single sendPhoto call
    short_payload = TelegramApprovalMessagePayload(
        post_id="JVY-20261013-001",
        revision_number=1,
        hook="Short hook",
        caption="Short caption.",
        hashtags=["#Tech"],
        visual_concept="Minimalist architecture diagram",
        approval_token="token_short",
        approval_url="http://localhost:8000/approve/token_short",
        image_url="https://mock-storage.supabase.co/post-images/img.png",
        chat_id="12345678",
    )

    res1 = provider.send_approval_message(short_payload)
    assert res1.success is True
    # Verify sendPhoto was called with reply_markup
    assert mock_http.post.call_count == 1
    args, kwargs = mock_http.post.call_args
    assert "sendPhoto" in args[0]
    assert kwargs["json"]["photo"] == "https://mock-storage.supabase.co/post-images/img.png"
    assert "reply_markup" in kwargs["json"]

    mock_http.post.reset_mock()

    # 2. Long caption > 1024 chars: linked messages (sendPhoto preview + sendMessage with buttons)
    long_caption = "Enterprise automation systems must guarantee idempotency across all webhook boundaries. " * 20
    long_payload = TelegramApprovalMessagePayload(
        post_id="JVY-20261013-002",
        revision_number=1,
        hook="Long hook",
        caption=long_caption,
        hashtags=["#Tech", "#Architecture", "#Enterprise"],
        visual_concept="Comprehensive pipeline graph",
        approval_token="token_long",
        approval_url="http://localhost:8000/approve/token_long",
        image_url="https://mock-storage.supabase.co/post-images/img2.png",
        chat_id="12345678",
    )

    res2 = provider.send_approval_message(long_payload)
    assert res2.success is True
    # Two HTTP calls: sendPhoto then sendMessage
    assert mock_http.post.call_count == 2
    first_call_url = mock_http.post.call_args_list[0][0][0]
    second_call_url = mock_http.post.call_args_list[1][0][0]
    assert "sendPhoto" in first_call_url
    assert "sendMessage" in second_call_url
    # Second message contains the inline keyboard buttons
    assert "reply_markup" in mock_http.post.call_args_list[1][1]["json"]


# ==============================================================================
# 28. Image generation failure during NO regeneration triggers rollback and notice
# ==============================================================================
def test_telegram_image_generation_failure_rolls_back_and_notifies(mock_repo_manager, sample_draft_post):
    """Verify that when image generation fails during NO regeneration, post rolls back to PENDING_APPROVAL and notice is sent."""
    from agent.exceptions import ImageGenerationError
    from agent.image_generator import MockImageProvider

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Retryable Topic",
            "angle": "Angle",
            "content_type": "tech",
            "target_audience": "Tech Leads",
            "reason": "Good topic",
        })),
        MagicMock(text=json.dumps({
            "hook": "Hook",
            "caption": "New caption text.",
            "hashtags": ["#Tech"],
            "call_to_action": "CTA",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Concept",
            "style": "Style",
            "composition": "Comp",
            "color_direction": "Col",
            "text_on_image": "None",
            "aspect_ratio": "1:1",
        })),
    ]

    failing_img_provider = MockImageProvider(should_fail=True)
    approval_service = ApprovalService(
        repo_manager=mock_repo_manager,
        gemini_client=mock_gemini,
        image_provider=failing_img_provider,
    )
    create_res = approval_service.create_approval_request("JVY-20261006-001")
    token = create_res.approval_token

    mock_provider = MockTelegramProvider()
    service = TelegramService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_telegram_service] = lambda: service
    client = TestClient(app)

    payload = {
        "update_id": 100004,
        "callback_query": {
            "id": "query_img_fail",
            "from": {"id": 123456},
            "message": {"message_id": 113, "chat": {"id": 123456}},
            "data": f"reject:{token}",
        },
    }

    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200

    # Verify rollback: post is still PENDING_APPROVAL, rev is still 1, token is still PENDING
    post_after = mock_repo_manager.posts.get_by_post_id("JVY-20261006-001")
    assert post_after.status == PostStatus.PENDING_APPROVAL
    assert post_after.current_revision == 1

    appr_after = mock_repo_manager.approvals.get_by_token(token)
    assert appr_after.status == ApprovalStatus.PENDING

    # Telegram failure notice was sent to founder
    assert len(mock_provider.sent_messages) == 1
    sent_text = mock_provider.sent_messages[0]["text"]
    assert "delayed" in sent_text.lower()





