"""Unit tests for WhatsApp integration provider, approval message formatting, and webhook callbacks."""

from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from unittest.mock import MagicMock
import httpx
import pytest
from fastapi.testclient import TestClient

from agent.image_generator import ImageBrief
from api.dependencies import get_approval_service, get_whatsapp_service
from api.main import app
from api.services.approval_service import ApprovalService
from api.services.whatsapp_service import WhatsAppService
from config.settings import settings
from database.models import Approval, ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from integrations.whatsapp.meta_cloud import MetaWhatsAppCloudProvider
from integrations.whatsapp.mock import MockWhatsAppProvider
from integrations.whatsapp.models import (
    WhatsAppApprovalMessagePayload,
    WhatsAppMessageResponse,
)


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
        post_id="JVY-20260929-001",
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
            post_id="JVY-20260929-001",
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
# 1. Provider configuration validation
# ==============================================================================
def test_provider_configuration_validation():
    # Empty credentials
    invalid_provider = MetaWhatsAppCloudProvider(
        access_token="",
        phone_number_id="",
        founder_phone="",
    )
    is_valid, errors = invalid_provider.validate_configuration()
    assert is_valid is False
    assert len(errors) == 3

    # Placeholder credentials
    placeholder_provider = MetaWhatsAppCloudProvider(
        access_token="your_access_token_here",
        phone_number_id="your_phone_id",
        founder_phone="your_phone",
    )
    is_valid, errors = placeholder_provider.validate_configuration()
    assert is_valid is False
    assert any("placeholder" in err for err in errors)

    # Valid credentials
    valid_provider = MetaWhatsAppCloudProvider(
        access_token="EAABxyz123...",
        phone_number_id="10987654321",
        founder_phone="+919876543210",
    )
    is_valid, errors = valid_provider.validate_configuration()
    assert is_valid is True
    assert len(errors) == 0


# ==============================================================================
# 2. Text message construction
# ==============================================================================
def test_text_message_construction():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"messages": [{"id": "wamid.HBgL123"}]}'
    mock_resp.json.return_value = {"messages": [{"id": "wamid.HBgL123"}]}
    mock_client.post.return_value = mock_resp

    provider = MetaWhatsAppCloudProvider(
        access_token="token_abc",
        phone_number_id="phone_123",
        founder_phone="+919876543210",
        http_client=mock_client,
    )

    result = provider.send_text_message("+919876543210", "Hello Founder!")
    assert result.success is True
    assert result.message_id == "wamid.HBgL123"
    assert result.provider == "meta"

    # Verify HTTP POST arguments
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "https://graph.facebook.com/v21.0/phone_123/messages" == call_args[0][0]
    payload = call_args[1]["json"]
    assert payload["to"] == "+919876543210"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "Hello Founder!"
    assert call_args[1]["headers"]["Authorization"] == "Bearer token_abc"


# ==============================================================================
# 3. Image message construction
# ==============================================================================
def test_image_message_construction():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"messages": [{"id": "wamid.IMG999"}]}'
    mock_resp.json.return_value = {"messages": [{"id": "wamid.IMG999"}]}
    mock_client.post.return_value = mock_resp

    provider = MetaWhatsAppCloudProvider(
        access_token="token_abc",
        phone_number_id="phone_123",
        http_client=mock_client,
    )

    result = provider.send_image_message(
        recipient_phone="+919876543210",
        image_url="https://cdn.jevyam.com/visuals/test.png",
        caption="Companion infographic",
    )
    assert result.success is True
    assert result.message_id == "wamid.IMG999"

    call_args = mock_client.post.call_args
    payload = call_args[1]["json"]
    assert payload["type"] == "image"
    assert payload["image"]["link"] == "https://cdn.jevyam.com/visuals/test.png"
    assert payload["image"]["caption"] == "Companion infographic"


# ==============================================================================
# 4. Approval message construction
# ==============================================================================
def test_approval_message_construction():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"messages": [{"id": "wamid.APPR001"}]}'
    mock_resp.json.return_value = {"messages": [{"id": "wamid.APPR001"}]}
    mock_client.post.return_value = mock_resp

    provider = MetaWhatsAppCloudProvider(
        access_token="token_abc",
        phone_number_id="phone_123",
        founder_phone="+919876543210",
        http_client=mock_client,
    )

    payload = WhatsAppApprovalMessagePayload(
        post_id="JVY-20260929-001",
        revision_number=1,
        hook="Cron jobs fail silently.",
        caption="Full LinkedIn caption here.",
        hashtags=["#DevOps", "#Architecture"],
        approval_token="appr_sec_tok_12345",
        approval_url="http://127.0.0.1:8000/approve/appr_sec_tok_12345",
        image_url="https://cdn.jevyam.com/visuals/jvy-001.png",
        expires_at="2026-09-30T10:00:00",
    )

    result = provider.send_approval_message(payload)
    assert result.success is True

    call_args = mock_client.post.call_args
    req_json = call_args[1]["json"]
    assert req_json["type"] == "interactive"
    interactive = req_json["interactive"]
    assert interactive["type"] == "button"

    # Verify buttons
    buttons = interactive["action"]["buttons"]
    assert len(buttons) == 2
    assert buttons[0]["reply"]["id"] == "approve:appr_sec_tok_12345"
    assert buttons[0]["reply"]["title"] == "APPROVE / YES"
    assert buttons[1]["reply"]["id"] == "regenerate:appr_sec_tok_12345"
    assert buttons[1]["reply"]["title"] == "REGENERATE / NO"

    # Verify image header
    assert interactive["header"]["type"] == "image"
    assert interactive["header"]["image"]["link"] == "https://cdn.jevyam.com/visuals/jvy-001.png"

    # Verify body text
    body_text = interactive["body"]["text"]
    assert "JVY-20260929-001" in body_text
    assert "Cron jobs fail silently." in body_text
    assert "#DevOps" in body_text


# ==============================================================================
# 5. YES callback mapping
# ==============================================================================
def test_yes_callback_mapping(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20260929-001")
    token = create_res.approval_token

    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(approval_service=approval_service, provider=mock_provider)

    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    # Inbound Meta Cloud API button reply payload
    meta_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "biz_123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.CLICK_YES_001",
                                    "timestamp": "1727618000",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": f"approve:{token}",
                                            "title": "APPROVE / YES",
                                        },
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    resp = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["post_id"] == "JVY-20260929-001"

    # Verify database state
    updated_post = mock_repo_manager.posts.get_by_post_id("JVY-20260929-001")
    assert updated_post.status == PostStatus.APPROVED

    updated_approval = mock_repo_manager.approvals.get_by_token(token)
    assert updated_approval.status == ApprovalStatus.APPROVED

    # Verify confirmation text was sent to founder
    assert len(mock_provider.sent_messages) == 1
    assert "approved" in mock_provider.sent_messages[0]["text"].lower()


# ==============================================================================
# 6. NO callback mapping
# ==============================================================================
def test_no_callback_mapping(mock_repo_manager, sample_draft_post):
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
    create_res = approval_service.create_approval_request("JVY-20260929-001")
    token = create_res.approval_token

    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(approval_service=approval_service, provider=mock_provider)

    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    meta_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "biz_123",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.CLICK_NO_001",
                                    "timestamp": "1727618000",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": f"regenerate:{token}",
                                            "title": "REGENERATE / NO",
                                        },
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    resp = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "regenerated"
    assert data["revision"] == 2

    # Verify old approval was marked REJECTED
    old_approval = mock_repo_manager.approvals.get_by_token(token)
    assert old_approval.status == ApprovalStatus.REJECTED

    # Verify post current revision is 2
    post = mock_repo_manager.posts.get_by_post_id("JVY-20260929-001")
    assert post.current_revision == 2

    # Verify NEW approval request was dispatched to founder
    assert len(mock_provider.sent_messages) == 1
    new_msg = mock_provider.sent_messages[0]
    assert new_msg["type"] == "approval_interactive"
    assert new_msg["payload"]["revision_number"] == 2


# ==============================================================================
# 7. Invalid callback
# ==============================================================================
def test_invalid_callback():
    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(provider=mock_provider)

    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    # Missing token or invalid payload string
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.INV001",
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": "random_payload_without_colon"}
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    resp = client.post("/webhook/whatsapp", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["code"] == "INVALID_CALLBACK"


# ==============================================================================
# 8. Duplicate callback
# ==============================================================================
def test_duplicate_callback(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20260929-001")
    token = create_res.approval_token

    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(approval_service=approval_service, provider=mock_provider)

    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    meta_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.DUPLICATE_999",
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": f"approve:{token}"}
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    # First call: approved
    resp1 = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "approved"

    # Second call with exact same message_id: caught as duplicate
    resp2 = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ignored"
    assert resp2.json()["code"] == "DUPLICATE_CALLBACK"


# ==============================================================================
# 9. Expired approval
# ==============================================================================
def test_expired_approval(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20260929-001")
    token = create_res.approval_token

    # Force expiration into the past
    appr = mock_repo_manager.approvals.get_by_token(token)
    appr.expires_at = datetime.now() - timedelta(days=2)
    mock_repo_manager.approvals.update(appr)

    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    meta_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.EXP001",
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": f"approve:{token}"}
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    resp = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "expired"
    assert data["code"] == "APPROVAL_EXPIRED"


# ==============================================================================
# 10. Already-approved post
# ==============================================================================
def test_already_approved_post(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20260929-001")
    token = create_res.approval_token

    # Approve once directly
    approval_service.approve_post(token)

    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    meta_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.DIFF_ID_ALREADY_DONE",
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": f"approve:{token}"}
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    resp = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"
    assert data["code"] == "ALREADY_PROCESSED"


# ==============================================================================
# 11. Already-regenerated post
# ==============================================================================
def test_already_regenerated_post(mock_repo_manager, sample_draft_post):
    approval_service = ApprovalService(repo_manager=mock_repo_manager)
    create_res = approval_service.create_approval_request("JVY-20260929-001")
    token = create_res.approval_token

    # Mark as already rejected
    mock_repo_manager.approvals.update_status(token, ApprovalStatus.REJECTED)

    mock_provider = MockWhatsAppProvider()
    service = WhatsAppService(approval_service=approval_service, provider=mock_provider)
    app.dependency_overrides[get_whatsapp_service] = lambda: service
    client = TestClient(app)

    meta_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "+919876543210",
                                    "id": "wamid.REJECT_AGAIN",
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": f"regenerate:{token}"}
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    resp = client.post("/webhook/whatsapp", json=meta_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ignored"
    assert data["code"] == "ALREADY_PROCESSED"


# ==============================================================================
# 12. Provider API error
# ==============================================================================
def test_provider_api_error():
    mock_client = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.content = b'{"error": {"message": "Invalid OAuth access token", "code": 190}}'
    mock_resp.json.return_value = {"error": {"message": "Invalid OAuth access token", "code": 190}}
    mock_client.post.return_value = mock_resp

    provider = MetaWhatsAppCloudProvider(
        access_token="invalid_token",
        phone_number_id="phone_123",
        http_client=mock_client,
    )

    result = provider.send_text_message("+919876543210", "Test fail")
    assert result.success is False
    assert "190" in result.error
    assert "Invalid OAuth access token" in result.error


# ==============================================================================
# 13. Timeout/retry handling
# ==============================================================================
def test_timeout_retry_handling():
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out after 15s")

    provider = MetaWhatsAppCloudProvider(
        access_token="valid_token",
        phone_number_id="phone_123",
        http_client=mock_client,
    )

    result = provider.send_text_message("+919876543210", "Test timeout")
    assert result.success is False
    assert "Connection timed out" in result.error


# ==============================================================================
# 14. Malformed webhook payload
# ==============================================================================
def test_malformed_webhook_payload():
    client = TestClient(app)
    # Send non-JSON raw body
    resp = client.post(
        "/webhook/whatsapp",
        content=b"this is not a json payload at all!",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "Malformed JSON" in resp.json()["message"]


# ==============================================================================
# 15. Webhook authentication failure
# ==============================================================================
def test_webhook_authentication_failure():
    # 1. GET verification challenge failure
    client = TestClient(app)
    bad_get_resp = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token_here",
            "hub.challenge": "12345678",
        },
    )
    assert bad_get_resp.status_code == 403

    # 2. GET verification challenge success
    good_get_resp = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "987654321",
        },
    )
    assert good_get_resp.status_code == 200
    assert good_get_resp.text == "987654321"

    # 3. POST HMAC-SHA256 signature failure
    provider = MetaWhatsAppCloudProvider(app_secret="test_secret_key_123")
    service = WhatsAppService(provider=provider)
    app.dependency_overrides[get_whatsapp_service] = lambda: service

    raw_body = json.dumps({"test": "data"}).encode("utf-8")

    # Invalid signature header
    bad_post_resp = client.post(
        "/webhook/whatsapp",
        content=raw_body,
        headers={"X-Hub-Signature-256": "sha256=invalid_hex_digest"},
    )
    assert bad_post_resp.status_code == 403
    assert bad_post_resp.json()["code"] == "AUTH_FAILED"

    # Valid signature header
    valid_sig = hmac.new(
        b"test_secret_key_123",
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    good_post_resp = client.post(
        "/webhook/whatsapp",
        content=raw_body,
        headers={"X-Hub-Signature-256": f"sha256={valid_sig}"},
    )
    assert good_post_resp.status_code == 200


# ==============================================================================
# 16. Optional Live Sandbox Test (skipped by default)
# ==============================================================================
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_WHATSAPP_TESTS", "0") != "1",
    reason="Live WhatsApp Cloud API test skipped unless RUN_LIVE_WHATSAPP_TESTS=1 is set.",
)
def test_live_whatsapp_api():
    """Live WhatsApp Cloud API test: only executed when explicitly enabled."""
    provider = MetaWhatsAppCloudProvider(
        access_token=settings.WHATSAPP_ACCESS_TOKEN,
        phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
        founder_phone=settings.WHATSAPP_FOUNDER_PHONE,
    )
    is_valid, errors = provider.validate_configuration()
    assert is_valid, f"Configuration invalid: {errors}"

    res = provider.send_text_message(
        recipient_phone=settings.WHATSAPP_FOUNDER_PHONE,
        text="[Jevyam Agent Live Test] Phase 4 WhatsApp integration verified.",
    )
    assert res.success is True
    assert res.message_id is not None
