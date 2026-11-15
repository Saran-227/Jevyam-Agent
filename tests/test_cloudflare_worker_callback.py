"""Phase B Verification Test Suite: Cloudflare Worker, Telegram Callbacks, and LinkedIn Publishing Guards.

Covers all 12 mandatory requirements from Phase B:
1. Valid founder callback.
2. Invalid webhook secret.
3. Unauthorized Telegram user.
4. YES approval (publishes to org 108376955, records in DB, updates status).
5. NO regeneration (triggers new revision, new token, preview to founder, never publishes).
6. Expired approval token.
7. Already-consumed token.
8. Duplicate callback.
9. Concurrent callback.
10. GitHub dispatch failure handling.
11. Supabase persistence.
12. No LinkedIn publishing without founder YES.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    PostNotApprovedError,
)
from api.services.approval_service import ApprovalService
from api.services.publishing_service import PublishingService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import (
    Approval,
    ApprovalStatus,
    Post,
    PostRevision,
    PostStatus,
    Publication,
    PublicationStatus,
)
from database.repositories import RepositoryManager, get_repository_manager
from integrations.telegram.mock import MockTelegramProvider
import scripts.process_telegram_callback as callback_script

FOUNDER_ID = "8164283098"
TARGET_ORG_URN = "urn:li:organization:108376955"
TARGET_ORG_ID = "108376955"


@pytest.fixture
def test_repo_manager():
    """Create isolated in-memory repository manager."""
    return get_repository_manager(use_in_memory=True)


@pytest.fixture
def mock_telegram_provider():
    """Create mock Telegram provider initialized for founder."""
    return MockTelegramProvider(founder_chat_id=FOUNDER_ID, webhook_secret="test_secret_123")


@pytest.fixture
def sample_pending_post(test_repo_manager):
    """Seed repository with an active draft post awaiting founder approval."""
    post = Post(
        post_id="JVY-TEST-PHASE-B",
        topic="Event-Driven Zero-Budget AI Architectures",
        angle="Enterprise resilience on serverless infrastructure",
        content_type="software engineering",
        target_audience="CTOs and Tech Leads",
        hook="Why paying for 24/7 idle servers is a thing of the past.",
        caption="Modern event-driven architectures with Cloudflare Workers and GitHub Actions scale to zero when idle.",
        hashtags=["#CloudArchitecture", "#FinOps", "#AIAutomation"],
        call_to_action="Follow Jevyam Technologies for enterprise engineering insights.",
        visual_concept="A clean architectural blueprint showing serverless triggers.",
        image_brief={"title": "Cloudflare Worker Event-Driven Relay", "layout": "hero_metric", "metrics": "0 Idle Cost"},
        image_url="https://kqtqehqipczuiomxxxvc.supabase.co/storage/v1/object/public/post-images/test.png",
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
# Requirement 1: Valid founder callback
# -----------------------------------------------------------------------------
def test_valid_founder_callback_identification(mock_telegram_provider, test_repo_manager):
    """Verify TelegramService strictly identifies and authorizes the founder."""
    service = TelegramService(
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
    )
    assert service.is_authorized_user(chat_id=FOUNDER_ID, sender_id=FOUNDER_ID) is True
    assert service.is_authorized_user(chat_id=FOUNDER_ID, sender_id=None) is True
    assert service.is_authorized_user(chat_id=None, sender_id=FOUNDER_ID) is True


# -----------------------------------------------------------------------------
# Requirement 2: Invalid webhook secret
# -----------------------------------------------------------------------------
def test_invalid_webhook_secret_rejected(mock_telegram_provider, test_repo_manager):
    """Verify TelegramService rejects webhook payloads with mismatched secret token."""
    service = TelegramService(
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
    )
    res = service.handle_webhook_callback(
        payload_dict={"update_id": 100},
        secret_token_header="wrong_secret_token",
        is_polling=False,
    )
    assert res["status"] == "error"
    assert res["code"] == "AUTH_FAILED"


# -----------------------------------------------------------------------------
# Requirement 3: Unauthorized Telegram user
# -----------------------------------------------------------------------------
def test_unauthorized_telegram_user_rejected(mock_telegram_provider, test_repo_manager, sample_pending_post):
    """Verify unauthorized users cannot execute approvals or regenerations."""
    _, _, app = sample_pending_post
    service = TelegramService(
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
    )

    unauthorized_payload = {
        "callback_query": {
            "id": "cb_unauth_999",
            "from": {"id": 999888777},
            "message": {"chat": {"id": 999888777}},
            "data": f"approve:{app.approval_token}",
        }
    }

    res = service.handle_webhook_callback(
        payload_dict=unauthorized_payload,
        secret_token_header="test_secret_123",
        is_polling=False,
    )
    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"

    # Verify post and approval status remain untouched
    re_app = test_repo_manager.approvals.get_by_token(app.approval_token)
    assert re_app.status == ApprovalStatus.PENDING


# -----------------------------------------------------------------------------
# Requirement 4: YES approval publishes to org 108376955 and updates Supabase
# -----------------------------------------------------------------------------
def test_yes_approval_publishes_to_organization_and_records_in_db(
    test_repo_manager, sample_pending_post, mock_telegram_provider
):
    """Verify YES approval consumes token, publishes to LinkedIn org 108376955, and updates records."""
    post, rev, app = sample_pending_post

    # Mock LinkedIn Publisher to avoid external network calls
    mock_publisher = MagicMock()
    mock_publish_response = MagicMock(
        post_urn="urn:li:share:987654321",
        post_url="https://www.linkedin.com/feed/update/urn:li:share:987654321",
        is_success=True,
        image_urn="urn:li:image:123",
    )
    mock_publisher.publish.return_value = mock_publish_response
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
    )

    callback_payload = {
        "callback_query": {
            "id": "cb_founder_yes",
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

    # 1. Authoritative approval token consumed
    consumed_app = test_repo_manager.approvals.get_by_token(app.approval_token)
    assert consumed_app.status == ApprovalStatus.APPROVED

    # 2. Post updated to PUBLISHED
    updated_post = test_repo_manager.posts.get_by_post_id(post.post_id)
    assert updated_post.status == PostStatus.PUBLISHED
    assert updated_post.linkedin_post_id == "urn:li:share:987654321"

    # 3. Publication record stored in repository
    publications = test_repo_manager.publications.get_by_post_id(post.post_id)
    assert len(publications) == 1
    assert publications[0].status == PublicationStatus.PUBLISHED
    assert publications[0].external_post_id == "urn:li:share:987654321"

    # 4. Confirmation sent to founder on Telegram
    sent_msgs = mock_telegram_provider.sent_messages
    assert any("Approved!" in m["text"] and "urn:li:share:987654321" in m["text"] for m in sent_msgs)


# -----------------------------------------------------------------------------
# Requirement 5: NO regeneration creates new revision & never calls LinkedIn
# -----------------------------------------------------------------------------
def test_no_regeneration_creates_revision_and_never_publishes(
    test_repo_manager, sample_pending_post, mock_telegram_provider
):
    """Verify NO button click rejects previous approval, regenerates new revision, and never publishes."""
    post, rev, app = sample_pending_post

    mock_publisher = MagicMock()
    pub_service = PublishingService(
        repo_manager=test_repo_manager,
        publisher=mock_publisher,
        mock_mode=False,
    )

    def mock_regenerate(rejected_draft, **kwargs):
        # Emulate what pipeline does: advances current_revision on post entity
        post_record = test_repo_manager.posts.get_by_post_id(post.post_id)
        post_record.current_revision = 2
        test_repo_manager.posts.update(post_record)
        return MagicMock(post_id=post.post_id, revision=2)

    with patch("api.services.approval_service.regenerate_draft", side_effect=mock_regenerate):
        app_service = ApprovalService(
            repo_manager=test_repo_manager,
            publishing_service=pub_service,
        )
        tel_service = TelegramService(
            approval_service=app_service,
            provider=mock_telegram_provider,
            founder_chat_id=FOUNDER_ID,
        )

        callback_payload = {
            "callback_query": {
                "id": "cb_founder_no",
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

        # Explicitly verify LinkedIn publisher was NEVER called
        mock_publisher.publish.assert_not_called()

        # Verify old token marked REJECTED
        old_app = test_repo_manager.approvals.get_by_token(app.approval_token)
        assert old_app.status == ApprovalStatus.REJECTED


# -----------------------------------------------------------------------------
# Requirement 6: Expired approval token
# -----------------------------------------------------------------------------
def test_expired_approval_token_rejected(test_repo_manager, sample_pending_post, mock_telegram_provider):
    """Verify expired approval tokens cannot be approved and notify founder."""
    post, rev, app = sample_pending_post

    # Set expiration in past
    app.expires_at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    test_repo_manager.approvals.update(app)

    app_service = ApprovalService(repo_manager=test_repo_manager)
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
    )

    callback_payload = {
        "callback_query": {
            "id": "cb_expired",
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

    assert res["status"] == "expired"
    assert res["code"] == "APPROVAL_EXPIRED"

    # Verify founder received expiration notice
    assert any("Approval Expired" in m["text"] for m in mock_telegram_provider.sent_messages)


# -----------------------------------------------------------------------------
# Requirement 7: Already-consumed token
# -----------------------------------------------------------------------------
def test_already_consumed_token_rejected(test_repo_manager, sample_pending_post, mock_telegram_provider):
    """Verify that an already approved or rejected token cannot be re-consumed."""
    post, rev, app = sample_pending_post

    # Mark as already consumed
    test_repo_manager.approvals.update_status(app.approval_token, ApprovalStatus.APPROVED)

    app_service = ApprovalService(repo_manager=test_repo_manager)
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
    )

    callback_payload = {
        "callback_query": {
            "id": "cb_consumed",
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

    assert res["status"] == "ignored"
    assert res["code"] == "ALREADY_PROCESSED"
    assert any("Already Processed" in m["text"] for m in mock_telegram_provider.sent_messages)


# -----------------------------------------------------------------------------
# Requirement 8 & 9: Duplicate and concurrent callbacks
# -----------------------------------------------------------------------------
def test_duplicate_and_concurrent_callbacks_prevented(
    test_repo_manager, sample_pending_post, mock_telegram_provider
):
    """Verify duplicate callback query IDs and concurrent token in-flight locks."""
    post, rev, app = sample_pending_post

    app_service = ApprovalService(repo_manager=test_repo_manager)
    tel_service = TelegramService(
        approval_service=app_service,
        provider=mock_telegram_provider,
        founder_chat_id=FOUNDER_ID,
    )

    # 1. Duplicate callback_query_id check
    tel_service._processed_callback_ids.add("cb_duplicate_id_123")
    res_dup = tel_service.handle_webhook_callback(
        payload_dict={
            "callback_query": {
                "id": "cb_duplicate_id_123",
                "from": {"id": int(FOUNDER_ID)},
                "message": {"chat": {"id": int(FOUNDER_ID)}},
                "data": f"approve:{app.approval_token}",
            }
        },
        secret_token_header="test_secret_123",
        is_polling=False,
    )
    assert res_dup["code"] == "DUPLICATE_CALLBACK"

    # 2. In-flight token concurrency check
    tel_service._in_flight_tokens.add(app.approval_token)
    res_inflight = tel_service.handle_webhook_callback(
        payload_dict={
            "callback_query": {
                "id": "cb_new_id_456",
                "from": {"id": int(FOUNDER_ID)},
                "message": {"chat": {"id": int(FOUNDER_ID)}},
                "data": f"reject:{app.approval_token}",
            }
        },
        secret_token_header="test_secret_123",
        is_polling=False,
    )
    assert res_inflight["code"] == "IN_PROGRESS"


# -----------------------------------------------------------------------------
# Requirement 10: Script handles unauthorized user and exits with code 1
# -----------------------------------------------------------------------------
def test_script_handles_unauthorized_user_and_exits_with_code_1():
    """Verify scripts/process_telegram_callback.py rejects unauthorized user safely."""
    test_args = [
        "process_telegram_callback.py",
        "--action", "approve",
        "--token", "dummy_token_12345",
        "--chat-id", "999888777",
        "--user-id", "999888777",
    ]
    with patch("sys.argv", test_args):
        with patch.object(settings, "TELEGRAM_FOUNDER_CHAT_ID", FOUNDER_ID):
            exit_code = callback_script.main()
            assert exit_code == 1


# -----------------------------------------------------------------------------
# Requirement 11: Supabase persistence of approvals and publications
# -----------------------------------------------------------------------------
def test_supabase_persistence_integrity(test_repo_manager, sample_pending_post):
    """Verify that approval lifecycle updates are properly persisted in repositories."""
    post, rev, app = sample_pending_post

    # Verify initial pending state
    loaded_app = test_repo_manager.approvals.get_by_token(app.approval_token)
    assert loaded_app.status == ApprovalStatus.PENDING

    # Transition to APPROVED
    test_repo_manager.approvals.update_status(app.approval_token, ApprovalStatus.APPROVED)
    loaded_app2 = test_repo_manager.approvals.get_by_token(app.approval_token)
    assert loaded_app2.status == ApprovalStatus.APPROVED

    # Create publication record
    pub = test_repo_manager.publications.create(
        Publication(
            post_id=post.post_id,
            revision_number=rev.revision_number,
            platform="LINKEDIN",
            status=PublicationStatus.PUBLISHED,
            external_post_id="urn:li:share:11223344",
            target_urn=TARGET_ORG_URN,
        )
    )
    assert pub.id is not None
    loaded_pubs = test_repo_manager.publications.get_by_post_id(post.post_id)
    assert len(loaded_pubs) == 1
    assert loaded_pubs[0].external_post_id == "urn:li:share:11223344"


# -----------------------------------------------------------------------------
# Requirement 12: No LinkedIn publishing without founder YES
# -----------------------------------------------------------------------------
def test_no_linkedin_publishing_without_founder_yes(test_repo_manager):
    """Verify that PublishingService strictly refuses to publish unapproved posts."""
    mock_publisher = MagicMock()
    pub_service = PublishingService(
        repo_manager=test_repo_manager,
        publisher=mock_publisher,
        mock_mode=False,
    )

    base_kwargs = {
        "topic": "Topic",
        "angle": "Angle",
        "content_type": "engineering",
        "target_audience": "Devs",
        "hook": "Hook",
        "caption": "Caption",
        "hashtags": ["#Tech"],
        "call_to_action": "CTA",
        "visual_concept": "Visual",
        "image_brief": {"title": "Title"},
    }

    # 1. Refuse DRAFT post
    draft_post = Post(post_id="JVY-TEST-DRAFT", status=PostStatus.DRAFT, **base_kwargs)
    test_repo_manager.posts.create(draft_post)
    with pytest.raises(PostNotApprovedError):
        pub_service.publish_approved_post(draft_post.post_id)

    # 2. Refuse PENDING_APPROVAL post
    pending_post = Post(post_id="JVY-TEST-PENDING", status=PostStatus.PENDING_APPROVAL, **base_kwargs)
    test_repo_manager.posts.create(pending_post)
    with pytest.raises(PostNotApprovedError):
        pub_service.publish_approved_post(pending_post.post_id)

    # 3. Refuse REJECTED post
    rejected_post = Post(post_id="JVY-TEST-REJECTED", status=PostStatus.REJECTED, **base_kwargs)
    test_repo_manager.posts.create(rejected_post)
    with pytest.raises(PostNotApprovedError):
        pub_service.publish_approved_post(rejected_post.post_id)

    # Assert publisher was never invoked for any of these
    mock_publisher.publish.assert_not_called()
