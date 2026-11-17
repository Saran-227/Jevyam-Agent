"""Test suite for Admin Telegram Role and Role-Based Notification Routing.

Covers all 12 mandatory requirements:
1. Admin receives generated post previews.
2. Admin receives operational notifications.
3. Founder receives approval cards with buttons.
4. Admin preview has no approval buttons.
5. Founder can approve.
6. Founder can reject and regenerate.
7. Admin cannot approve or reject.
8. Unauthorized users cannot execute admin commands.
9. Admin can execute /status.
10. Admin can execute /run.
11. Existing founder authorization tests continue passing.
12. Existing GitHub Actions and Cloudflare callback workflows continue working.
"""

from unittest.mock import MagicMock, patch
import pytest

from agent.orchestrator import DailyOrchestrator
from api.services.approval_service import ApprovalService
from api.services.publishing_service import PublishingService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import (
    ApprovalStatus,
    Post,
    PostRevision,
    PostStatus,
    PublicationStatus,
)
from database.repositories import get_repository_manager
from integrations.telegram.mock import MockTelegramProvider
import scripts.process_telegram_callback as callback_script

FOUNDER_ID = "8164283098"
ADMIN_ID = "1293148688"
UNAUTH_ID = "999888777"
TARGET_ORG_URN = "urn:li:organization:108376955"
TARGET_ORG_ID = "108376955"


@pytest.fixture
def test_repo_manager():
    """Create isolated in-memory repository manager."""
    return get_repository_manager(use_in_memory=True)


@pytest.fixture
def mock_telegram_provider():
    """Create mock Telegram provider initialized with founder and admin."""
    return MockTelegramProvider(
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
        webhook_secret="test_secret_123",
    )


@pytest.fixture
def sample_pending_post(test_repo_manager):
    """Seed repository with an active draft post awaiting founder approval."""
    post = Post(
        post_id="JVY-TEST-ADMIN-ROLE",
        topic="Role-Based Operational Monitoring in Event-Driven Systems",
        angle="Separation of concerns between Approvers and Administrators",
        content_type="software engineering",
        target_audience="CTOs and Tech Leads",
        hook="Why administrative monitoring should never bypass business approval gates.",
        caption="Separating operational visibility from publishing authority ensures strict governance in enterprise AI systems.",
        hashtags=["#CloudArchitecture", "#Governance", "#FinOps"],
        call_to_action="Follow Jevyam Technologies for enterprise engineering insights.",
        visual_concept="A dual-path diagram showing admin alerts vs founder approval gates.",
        image_brief={"title": "Role-Based Agent Architecture", "layout": "hero_metric", "metrics": "100% Audit"},
        image_url="https://kqtqehqipczuiomxxxvc.supabase.co/storage/v1/object/public/post-images/test_admin.png",
        current_revision=1,
        status=PostStatus.PENDING_APPROVAL,
    )
    test_repo_manager.posts.create(post)

    rev = PostRevision(
        post_id=post.post_id,
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
        image_brief=post.image_brief,
        image_url=post.image_url,
    )
    test_repo_manager.revisions.create(rev)

    app = test_repo_manager.approvals.create_approval_request(
        post_id=post.post_id,
        revision_number=1,
    )
    return post, rev, app


# -----------------------------------------------------------------------------
# Requirements 1, 3, 4: Founder gets buttons, Admin gets preview with NO buttons
# -----------------------------------------------------------------------------
def test_dual_delivery_founder_buttons_admin_no_buttons(
    test_repo_manager, sample_pending_post, mock_telegram_provider
):
    """Verify that when post approval is sent, Founder receives buttons and Admin receives preview with NO buttons."""
    post, rev, app = sample_pending_post

    app_service = ApprovalService(repo_manager=test_repo_manager)
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    res = tel_service.send_post_approval_notification(post_id=post.post_id)
    assert res.success is True

    # 1. Founder message check
    founder_msgs = [m for m in mock_telegram_provider.sent_messages if m["chat_id"] == FOUNDER_ID]
    assert len(founder_msgs) >= 1
    founder_card = founder_msgs[0]
    assert founder_card["type"] == "approval_interactive"
    assert founder_card["buttons"] is not None
    assert len(founder_card["buttons"]) == 2
    assert any("YES" in b["text"] for b in founder_card["buttons"])
    assert any("NO" in b["text"] for b in founder_card["buttons"])

    # 2. Admin message check (Req 1 & Req 4: Preview copy, NO buttons)
    admin_msgs = [m for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
    assert len(admin_msgs) >= 1
    admin_preview = admin_msgs[0]
    assert admin_preview["type"] == "admin_preview"
    assert admin_preview["buttons"] is None  # STRICTLY NO ACTIONABLE BUTTONS
    assert "Admin Copy" in admin_preview["text"] or "Admin Informational Copy" in admin_preview["text"]


# -----------------------------------------------------------------------------
# Requirement 2: Admin receives operational notifications
# -----------------------------------------------------------------------------
def test_admin_receives_operational_notifications(
    test_repo_manager, mock_telegram_provider
):
    """Verify admin receives operational alerts (start, skip, complete, alerts)."""
    tel_service = TelegramService(
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    # Test direct admin notification
    tel_service.send_admin_notification("🚀 Daily Post Generation Started")
    tel_service.send_admin_notification("✅ Daily Run Completed")

    admin_texts = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
    assert any("Daily Post Generation Started" in t for t in admin_texts)
    assert any("Daily Run Completed" in t for t in admin_texts)


# -----------------------------------------------------------------------------
# Requirement 5: Founder can approve
# -----------------------------------------------------------------------------
def test_founder_can_approve(test_repo_manager, sample_pending_post, mock_telegram_provider):
    """Verify Founder can successfully approve post and trigger LinkedIn publication."""
    post, rev, app = sample_pending_post

    mock_publisher = MagicMock()
    mock_publisher.publish.return_value = MagicMock(
        post_urn="urn:li:share:admin_role_1",
        post_url="https://www.linkedin.com/feed/update/urn:li:share:admin_role_1",
        is_success=True,
        image_urn="urn:li:image:1",
    )
    mock_publisher.client = MagicMock(organization_urn=TARGET_ORG_URN, organization_id=TARGET_ORG_ID)

    pub_service = PublishingService(
        repo_manager=test_repo_manager,
        publisher=mock_publisher,
        mock_mode=False,
    )
    app_service = ApprovalService(
        repo_manager=test_repo_manager,
        publishing_service=pub_service,
    )
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    callback_payload = {
        "callback_query": {
            "id": "cb_founder_yes_test",
            "from": {"id": int(FOUNDER_ID)},
            "message": {"chat": {"id": int(FOUNDER_ID)}},
            "data": f"approve:{app.approval_token}",
        }
    }

    res = tel_service.handle_webhook_callback(
        payload_dict=callback_payload,
        secret_token_header="test_secret_123",
        is_polling=False,
    )

    assert res["status"] == "approved"
    assert res["published"] is True

    # Authoritative status in database updated
    updated_post = test_repo_manager.posts.get_by_post_id(post.post_id)
    assert updated_post.status == PostStatus.PUBLISHED

    # Admin received publication notice as well
    admin_texts = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
    assert any("LinkedIn Publishing Notice" in t or "approved" in t for t in admin_texts)


# -----------------------------------------------------------------------------
# Requirement 6: Founder can reject and regenerate
# -----------------------------------------------------------------------------
def test_founder_can_reject_and_regenerate(test_repo_manager, sample_pending_post, mock_telegram_provider):
    """Verify Founder can reject and trigger new revision generation."""
    post, rev, app = sample_pending_post

    def mock_regenerate(rejected_draft, **kwargs):
        post_record = test_repo_manager.posts.get_by_post_id(post.post_id)
        post_record.current_revision = 2
        test_repo_manager.posts.update(post_record)
        return MagicMock(post_id=post.post_id, revision=2)

    with patch("api.services.approval_service.regenerate_draft", side_effect=mock_regenerate):
        app_service = ApprovalService(repo_manager=test_repo_manager)
        tel_service = TelegramService(
            approval_service=app_service,
            provider=mock_telegram_provider,
            founder_chat_id=FOUNDER_ID,
            admin_chat_id=ADMIN_ID,
        )

        callback_payload = {
            "callback_query": {
                "id": "cb_founder_no_test",
                "from": {"id": int(FOUNDER_ID)},
                "message": {"chat": {"id": int(FOUNDER_ID)}},
                "data": f"reject:{app.approval_token}",
            }
        }

        res = tel_service.handle_webhook_callback(
            payload_dict=callback_payload,
            secret_token_header="test_secret_123",
            is_polling=False,
        )

        assert res["status"] in ("accepted", "regenerated") or res.get("code") == "REGENERATION_SCHEDULED"

        # Verify old token rejected
        consumed_app = test_repo_manager.approvals.get_by_token(app.approval_token)
        assert consumed_app.status == ApprovalStatus.REJECTED

        # Admin notified of rejection & new revision
        admin_texts = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
        assert any("Post Rejection Notice" in t for t in admin_texts)


# -----------------------------------------------------------------------------
# Requirement 7: Admin CANNOT approve or reject
# -----------------------------------------------------------------------------
def test_admin_cannot_approve_or_reject(test_repo_manager, sample_pending_post, mock_telegram_provider):
    """Verify that if Admin attempts to execute approval/rejection callback, it is strictly rejected."""
    post, rev, app = sample_pending_post

    mock_publisher = MagicMock()
    pub_service = PublishingService(repo_manager=test_repo_manager, publisher=mock_publisher)
    app_service = ApprovalService(repo_manager=test_repo_manager, publishing_service=pub_service)

    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    # 1. Admin attempts YES approval
    admin_approve_payload = {
        "callback_query": {
            "id": "cb_admin_yes",
            "from": {"id": int(ADMIN_ID)},
            "message": {"chat": {"id": int(ADMIN_ID)}},
            "data": f"approve:{app.approval_token}",
        }
    }

    res_approve = tel_service.handle_webhook_callback(
        payload_dict=admin_approve_payload,
        secret_token_header="test_secret_123",
        is_polling=False,
    )
    assert res_approve["status"] == "unauthorized"
    # Token must remain PENDING
    assert test_repo_manager.approvals.get_by_token(app.approval_token).status == ApprovalStatus.PENDING
    mock_publisher.publish.assert_not_called()

    # Verify access-denied message explains admin role limitation
    admin_msgs = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
    assert any("As Admin, you cannot approve" in m for m in admin_msgs)

    # 2. Admin attempts NO rejection
    admin_reject_payload = {
        "callback_query": {
            "id": "cb_admin_no",
            "from": {"id": int(ADMIN_ID)},
            "message": {"chat": {"id": int(ADMIN_ID)}},
            "data": f"reject:{app.approval_token}",
        }
    }

    res_reject = tel_service.handle_webhook_callback(
        payload_dict=admin_reject_payload,
        secret_token_header="test_secret_123",
        is_polling=False,
    )
    assert res_reject["status"] == "unauthorized"
    assert test_repo_manager.approvals.get_by_token(app.approval_token).status == ApprovalStatus.PENDING


# -----------------------------------------------------------------------------
# Requirement 8: Unauthorized users cannot execute admin commands
# -----------------------------------------------------------------------------
def test_unauthorized_user_cannot_execute_admin_commands(mock_telegram_provider):
    """Verify unauthorized user is rejected when attempting /status, /run, /help."""
    tel_service = TelegramService(
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    for cmd in ("/status", "/run", "/help"):
        unauth_payload = {
            "message": {
                "chat": {"id": int(UNAUTH_ID)},
                "from": {"id": int(UNAUTH_ID)},
                "text": cmd,
            }
        }
        res = tel_service.handle_webhook_callback(
            payload_dict=unauth_payload,
            secret_token_header="test_secret_123",
            is_polling=False,
        )
        assert res["status"] == "unauthorized"
        assert res["code"] == "ADMIN_ONLY"

    unauth_msgs = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == UNAUTH_ID]
    assert all("Access Denied" in m for m in unauth_msgs)


# -----------------------------------------------------------------------------
# Requirement 9: Admin can execute /status
# -----------------------------------------------------------------------------
def test_admin_can_execute_status(test_repo_manager, sample_pending_post, mock_telegram_provider):
    """Verify Admin can execute /status and receive system operational report."""
    post, rev, app = sample_pending_post

    app_service = ApprovalService(repo_manager=test_repo_manager)
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    admin_payload = {
        "message": {
            "chat": {"id": int(ADMIN_ID)},
            "from": {"id": int(ADMIN_ID)},
            "text": "/status",
        }
    }

    res = tel_service.handle_webhook_callback(
        payload_dict=admin_payload,
        secret_token_header="test_secret_123",
        is_polling=False,
    )

    assert res["status"] == "info"
    assert res["code"] == "STATUS_REPORTED"
    assert "report" in res

    admin_msgs = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
    assert any("System Status" in m and post.post_id in m for m in admin_msgs)


# -----------------------------------------------------------------------------
# Requirement 10: Admin can execute /run
# -----------------------------------------------------------------------------
def test_admin_can_execute_run(test_repo_manager, mock_telegram_provider):
    """Verify Admin can execute /run to trigger daily post generation."""
    app_service = ApprovalService(repo_manager=test_repo_manager)
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    mock_run_result = MagicMock(
        post_id="JVY-TEST-RUN-CMD",
        revision_number=1,
        topic="Manual Execution Test",
        status="PENDING_APPROVAL",
    )

    with patch("agent.orchestrator.DailyOrchestrator.run", return_value=mock_run_result):
        admin_payload = {
            "message": {
                "chat": {"id": int(ADMIN_ID)},
                "from": {"id": int(ADMIN_ID)},
                "text": "/run",
            }
        }

        res = tel_service.handle_webhook_callback(
            payload_dict=admin_payload,
            secret_token_header="test_secret_123",
            is_polling=False,
        )

        assert res["status"] == "accepted"
        assert res["code"] == "MANUAL_RUN_COMPLETED"
        assert res["post_id"] == "JVY-TEST-RUN-CMD"

        admin_msgs = [m["text"] for m in mock_telegram_provider.sent_messages if m["chat_id"] == ADMIN_ID]
        assert any("Manual Run Triggered" in m for m in admin_msgs)
        assert any("Manual Run Completed" in m for m in admin_msgs)


# -----------------------------------------------------------------------------
# Requirement 11: Existing founder authorization tests continue passing
# -----------------------------------------------------------------------------
def test_founder_authorization_intact(mock_telegram_provider):
    """Verify existing founder authorization checks remain unchanged."""
    tel_service = TelegramService(
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
        admin_chat_id=ADMIN_ID,
    )

    assert tel_service.is_authorized_founder(chat_id=FOUNDER_ID, sender_id=FOUNDER_ID) is True
    assert tel_service.is_authorized_founder(chat_id=FOUNDER_ID, sender_id=None) is True
    assert tel_service.is_authorized_founder(chat_id=None, sender_id=FOUNDER_ID) is True

    # Admin is NOT an authorized founder
    assert tel_service.is_authorized_founder(chat_id=ADMIN_ID, sender_id=ADMIN_ID) is False
    assert tel_service.is_authorized_founder(chat_id=ADMIN_ID, sender_id=None) is False

    # Admin IS an authorized admin
    assert tel_service.is_authorized_admin(chat_id=ADMIN_ID, sender_id=ADMIN_ID) is True
    assert tel_service.is_authorized_admin(chat_id=FOUNDER_ID, sender_id=FOUNDER_ID) is False


# -----------------------------------------------------------------------------
# Requirement 12: Existing CLI callback script rejects Admin from approving
# -----------------------------------------------------------------------------
def test_cli_callback_script_rejects_admin_approval():
    """Verify scripts/process_telegram_callback.py strictly rejects admin attempts."""
    test_args = [
        "process_telegram_callback.py",
        "--action", "approve",
        "--token", "dummy_token_12345",
        "--chat-id", ADMIN_ID,
        "--user-id", ADMIN_ID,
    ]
    with patch("sys.argv", test_args):
        with patch.object(settings, "TELEGRAM_FOUNDER_CHAT_ID", FOUNDER_ID):
            with patch.object(settings, "TELEGRAM_ADMIN_CHAT_ID", ADMIN_ID):
                exit_code = callback_script.main()
                assert exit_code == 1
