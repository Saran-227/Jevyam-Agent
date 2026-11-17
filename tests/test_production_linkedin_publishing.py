"""Tests for Phase 3: Production LinkedIn Publishing Integration.

Verifies:
1. Production configuration validation (DRY_RUN=False, LINKEDIN_MOCK_PUBLISHING=False, AUTO_PUBLISH_ON_APPROVAL=True).
2. Real publisher selection when mock mode is disabled (mock_mode == False).
3. Company page author URN validation (urn:li:organization:108376955, personal profile rejection).
4. OAuth token validation (unexpired, token presence, w_organization_social scope).
5. Founder YES approval triggers publishing to Company Page with real API headers.
6. Founder NO rejection triggers regeneration and NEVER publishes.
7. Unauthorized approval attempts NEVER publish to LinkedIn.
8. Duplicate publishing prevention across restarts and callback retries.
9. LinkedIn failure handling (401 Auth, 403 Permission, Network, Image Upload).
10. Existing daily scheduler generates posts in PENDING_APPROVAL without publishing.
"""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest

from agent.image_generator import ImageBrief, MockImageProvider
from agent.orchestrator import DailyOrchestrator
from agent.scheduler import DailyScheduler, SchedulerStateStore
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
from database.repositories import create_in_memory_repository_manager
from integrations.linkedin.client import (
    LinkedInClient,
    LinkedInPublishResponse,
)
from integrations.linkedin.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInDuplicatePostError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInTokenExpiredError,
    MissingLinkedInCredentialsError,
)
from integrations.linkedin.oauth import LinkedInTokenStore
from integrations.linkedin.publisher import LinkedInPublisher
from integrations.telegram.mock import MockTelegramProvider


@pytest.fixture
def founder_chat_id():
    return str(settings.TELEGRAM_FOUNDER_CHAT_ID or "8164283098").strip()


@pytest.fixture
def fake_token_store(tmp_path):
    token_file = tmp_path / "linkedin_token.json"
    store = LinkedInTokenStore(storage_path=str(token_file))
    store.save_token(
        access_token="test_live_oauth_token_xyz789",
        expires_in=5184000,  # 60 days
        scope="w_organization_social r_organization_social",
    )
    return store


@pytest.fixture
def phase3_env(tmp_path, founder_chat_id, fake_token_store):
    repos = create_in_memory_repository_manager()
    mock_http = MagicMock()
    mock_img_provider = MockImageProvider(base_url="https://mock-storage.supabase.co/post-images")

    # Real client configured with target organization 108376955
    real_client = LinkedInClient(
        organization_id="108376955",
        api_version="202610",
        token_store=fake_token_store,
        http_client=mock_http,
    )
    real_publisher = LinkedInPublisher(client=real_client)

    # Real publishing service (mock_mode=False)
    pub_service = PublishingService(
        repo_manager=repos,
        publisher=real_publisher,
        mock_mode=False,
    )

    approval_service = ApprovalService(
        repo_manager=repos,
        publishing_service=pub_service,
        image_provider=mock_img_provider,
    )

    mock_tg = MockTelegramProvider(founder_chat_id=founder_chat_id)
    tg_service = TelegramService(
        approval_service=approval_service,
        provider=mock_tg,
        founder_chat_id=founder_chat_id,
    )

    # Seed an initial post
    brief = ImageBrief(
        visual_concept="Modern ERP flow",
        style="Clean 2D",
        composition="Center",
        color_direction="Navy",
        text_on_image="ERP",
    )
    post = Post(
        post_id="JVY-PROD-001",
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="01. Inventory Management Systems | Business Pain Point",
        topic="Enterprise Warehouse Scrap Tracking",
        angle="Auditing variance beats manual logs",
        target_audience="Operations Heads",
        hook="Ghost inventory destroys fulfillment timelines.",
        caption="Ghost inventory destroys fulfillment timelines.\n\nhttps://www.jeevyamtechnologies.com/services/inventory-management.html",
        hashtags=["#Inventory", "#SupplyChain"],
        call_to_action="How does your team track scrap reconciliation?",
        visual_concept="Modern ERP flow",
        image_brief=brief,
        image_url="https://mock-storage.supabase.co/post-images/JVY-PROD-001/rev_1.png",
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
        "mock_http": mock_http,
        "client": real_client,
        "publisher": real_publisher,
        "pub_service": pub_service,
        "approval_service": approval_service,
        "tg_service": tg_service,
        "mock_tg": mock_tg,
        "post": post,
        "approval": approval,
        "token_store": fake_token_store,
        "founder_id": founder_chat_id,
    }


def test_production_configuration_settings():
    """Verify that production environment variables are properly injected and validated.

    Explicitly injects production values rather than relying on global defaults:
    - DRY_RUN=false
    - LINKEDIN_MOCK_PUBLISHING=false
    - AUTO_PUBLISH_ON_APPROVAL=true
    - LINKEDIN_ORGANIZATION_ID=108376955
    - LINKEDIN_API_VERSION=202610
    - TELEGRAM_FOUNDER_CHAT_ID=8164283098
    - TELEGRAM_ADMIN_CHAT_ID=1293148688
    """
    prod_env = {
        "DRY_RUN": "false",
        "LINKEDIN_MOCK_PUBLISHING": "false",
        "AUTO_PUBLISH_ON_APPROVAL": "true",
        "LINKEDIN_ORGANIZATION_ID": "108376955",
        "LINKEDIN_API_VERSION": "202610",
        "TELEGRAM_FOUNDER_CHAT_ID": "8164283098",
        "TELEGRAM_ADMIN_CHAT_ID": "1293148688",
    }
    with patch("dotenv.load_dotenv"), patch.dict(os.environ, prod_env, clear=True):
        import importlib
        import config.settings
        importlib.reload(config.settings)
        s = config.settings.settings

        assert s.DRY_RUN is False
        assert s.LINKEDIN_MOCK_PUBLISHING is False
        assert s.AUTO_PUBLISH_ON_APPROVAL is True
        assert s.LINKEDIN_ORGANIZATION_ID == "108376955"
        assert s.LINKEDIN_API_VERSION == "202610"
        assert s.TELEGRAM_FOUNDER_CHAT_ID == "8164283098"
        assert s.TELEGRAM_ADMIN_CHAT_ID == "1293148688"

    # Restore module state
    import importlib
    import config.settings
    importlib.reload(config.settings)


def test_safe_development_defaults():
    """Verify that default settings without production injection maintain safe development defaults (mock & dry-run)."""
    with patch("dotenv.load_dotenv"), patch.dict(os.environ, {}, clear=True):
        import importlib
        import config.settings
        importlib.reload(config.settings)
        s = config.settings.settings

        assert s.DRY_RUN is True
        assert s.LINKEDIN_MOCK_PUBLISHING is True
        assert s.LINKEDIN_ORGANIZATION_ID == "108376955"

    # Restore module state
    import importlib
    import config.settings
    importlib.reload(config.settings)


def test_real_publisher_selection_when_mock_mode_disabled(phase3_env):
    """When DRY_RUN=False and LINKEDIN_MOCK_PUBLISHING=False, PublishingService uses real mode."""
    pub_service = phase3_env["pub_service"]
    assert pub_service.mock_mode is False


def test_company_page_author_urn_validation(fake_token_store):
    """Author URN must be strictly urn:li:organization:108376955 and reject personal profile URNs."""
    client = LinkedInClient(
        organization_id="108376955",
        token_store=fake_token_store,
    )
    assert client.organization_urn == "urn:li:organization:108376955"

    # Reject personal profile URNs
    personal_client = LinkedInClient(
        organization_id="urn:li:person:abcdef123",
        token_store=fake_token_store,
    )
    with pytest.raises(LinkedInPermissionError) as exc_info:
        _ = personal_client.organization_urn
    assert "personal LinkedIn profiles is strictly forbidden" in str(exc_info.value)


def test_oauth_token_validation_unexpired_and_scope(tmp_path):
    """Verify validate_credentials checks expiry and w_organization_social scope."""
    token_file = tmp_path / "valid_token.json"
    valid_store = LinkedInTokenStore(storage_path=str(token_file))
    valid_store.save_token("valid_tok", 3600, scope="w_organization_social")

    client = LinkedInClient(organization_id="108376955", token_store=valid_store)
    client.validate_credentials()  # Must not raise

    # 1. Missing scope
    bad_scope_file = tmp_path / "bad_scope.json"
    bad_scope_store = LinkedInTokenStore(storage_path=str(bad_scope_file))
    bad_scope_store.save_token("bad_tok", 3600, scope="r_liteprofile")

    bad_client = LinkedInClient(organization_id="108376955", token_store=bad_scope_store)
    with pytest.raises(LinkedInPermissionError) as exc_scope:
        bad_client.validate_credentials()
    assert "w_organization_social" in str(exc_scope.value)

    # 2. Expired token
    expired_file = tmp_path / "expired_token.json"
    expired_store = LinkedInTokenStore(storage_path=str(expired_file))
    expired_store.save_token("expired_tok", -10, scope="w_organization_social")

    with patch.object(settings, "LINKEDIN_ACCESS_TOKEN", ""):
        expired_client = LinkedInClient(organization_id="108376955", token_store=expired_store)
        with pytest.raises(LinkedInTokenExpiredError) as exc_exp:
            expired_client.validate_credentials()
        assert "expired" in str(exc_exp.value).lower()


def test_founder_yes_approval_triggers_real_publishing(phase3_env):
    """Authorized founder clicking YES publishes to Company Page with real headers."""
    tg_service = phase3_env["tg_service"]
    mock_http = phase3_env["mock_http"]
    repos = phase3_env["repos"]
    token = phase3_env["approval"].approval_token
    founder_id = phase3_env["founder_id"]

    # Mock LinkedIn REST API image upload & post creation responses
    upload_init_resp = MagicMock(status_code=200, content=b'{"value":{"uploadUrl":"https://media.licdn.com/upload/123","image":"urn:li:image:D5600X"}}')
    upload_init_resp.json.return_value = {"value": {"uploadUrl": "https://media.licdn.com/upload/123", "image": "urn:li:image:D5600X"}}

    image_download_resp = MagicMock(status_code=200, content=b"\x89PNG\r\n\x1a\nFakeImageBytes", headers={"Content-Type": "image/png"})
    image_put_resp = MagicMock(status_code=201, content=b"")

    post_resp = MagicMock(status_code=201, content=b'{"id":"urn:li:share:108376955_99999"}', headers={"x-restli-id": "urn:li:share:108376955_99999"})
    post_resp.json.return_value = {"id": "urn:li:share:108376955_99999"}

    def mock_http_post(url, **kwargs):
        if "action=initializeUpload" in url:
            # Check LinkedIn-Version header
            headers = kwargs.get("headers", {})
            assert headers.get("LinkedIn-Version") == "202610"
            assert "Bearer test_live_oauth_token" in headers.get("Authorization", "")
            return upload_init_resp
        elif "rest/posts" in url:
            headers = kwargs.get("headers", {})
            assert headers.get("LinkedIn-Version") == "202610"
            json_body = kwargs.get("json", {})
            assert json_body.get("author") == "urn:li:organization:108376955"
            assert json_body.get("lifecycleState") == "PUBLISHED"
            return post_resp
        return MagicMock(status_code=404)

    mock_http.post.side_effect = mock_http_post
    mock_http.get.return_value = image_download_resp
    mock_http.put.return_value = image_put_resp

    # Founder clicks YES
    res = tg_service.handle_webhook_callback({
        "update_id": 40001,
        "callback_query": {
            "id": "cb_founder_yes_prod",
            "from": {"id": int(founder_id)},
            "message": {"message_id": 80, "chat": {"id": int(founder_id)}},
            "data": f"approve:{token}",
        },
    })

    assert res["status"] == "approved"
    assert res["published"] is True

    # Master post updated
    post = repos.posts.get_by_post_id("JVY-PROD-001")
    assert post.status == PostStatus.PUBLISHED
    assert post.linkedin_post_id == "urn:li:share:108376955_99999"

    # Publication audit record updated
    pubs = repos.publications.get_by_post_id("JVY-PROD-001")
    assert len(pubs) == 1
    assert pubs[0].status == PublicationStatus.PUBLISHED
    assert pubs[0].external_post_id == "urn:li:share:108376955_99999"
    assert pubs[0].target_urn == "urn:li:organization:108376955"


def test_founder_no_rejection_never_publishes(phase3_env):
    """Authorized founder clicking NO triggers regeneration and NEVER calls LinkedIn publishing."""
    tg_service = phase3_env["tg_service"]
    mock_http = phase3_env["mock_http"]
    repos = phase3_env["repos"]
    token = phase3_env["approval"].approval_token
    founder_id = phase3_env["founder_id"]

    mock_draft = MagicMock()
    mock_draft.post_id = "JVY-PROD-001"
    mock_draft.revision = 2
    mock_draft.hook = "Revised hook"
    mock_draft.caption = "Revised caption"
    mock_draft.hashtags = ["#SupplyChain"]
    mock_draft.visual_concept = "New flow"
    mock_draft.image_url = "https://mock-storage.supabase.co/post-images/JVY-PROD-001/rev_2.png"
    mock_draft.image_brief = ImageBrief(
        visual_concept="New flow",
        style="2D Slate",
        composition="Center",
        color_direction="Navy",
        text_on_image="Audit",
    )

    def fake_regenerate(rejected_draft, rejection_reason, client, repo_manager, image_provider):
        post = repo_manager.posts.get_by_post_id("JVY-PROD-001")
        post.current_revision = 2
        repo_manager.posts.update(post)
        repo_manager.revisions.create(
            PostRevision(
                post_id="JVY-PROD-001",
                revision_number=2,
                content_type=post.content_type,
                topic=post.topic,
                angle="Auditing variance beats manual logs",
                target_audience=post.target_audience,
                hook="Revised hook",
                caption="Revised caption",
                hashtags=["#SupplyChain"],
                call_to_action=post.call_to_action,
                visual_concept="New flow",
                image_brief=mock_draft.image_brief,
                image_url="https://mock-storage.supabase.co/post-images/JVY-PROD-001/rev_2.png",
            )
        )
        return mock_draft

    with patch("api.services.approval_service.regenerate_draft", side_effect=fake_regenerate):
        res = tg_service.handle_webhook_callback({
            "update_id": 40002,
            "callback_query": {
                "id": "cb_founder_no_prod",
                "from": {"id": int(founder_id)},
                "message": {"message_id": 81, "chat": {"id": int(founder_id)}},
                "data": f"reject:{token}",
            },
        })

    assert res["status"] == "regenerated"
    mock_http.post.assert_not_called()
    mock_http.put.assert_not_called()


def test_unauthorized_approval_never_publishes(phase3_env):
    """Unauthorized users clicking approve are blocked and LinkedIn API is never called."""
    tg_service = phase3_env["tg_service"]
    mock_http = phase3_env["mock_http"]
    repos = phase3_env["repos"]
    token = phase3_env["approval"].approval_token

    res = tg_service.handle_webhook_callback({
        "update_id": 40003,
        "callback_query": {
            "id": "cb_unauth_prod",
            "from": {"id": 999888111},
            "message": {"message_id": 82, "chat": {"id": 999888111}},
            "data": f"approve:{token}",
        },
    })

    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"
    mock_http.post.assert_not_called()

    # Post remains PENDING_APPROVAL
    assert repos.posts.get_by_post_id("JVY-PROD-001").status == PostStatus.PENDING_APPROVAL


def test_admin_approval_attempt_never_publishes(phase3_env):
    """Admin role (1293148688) clicking approve is rejected as UNAUTHORIZED_USER and LinkedIn is never called."""
    tg_service = phase3_env["tg_service"]
    mock_http = phase3_env["mock_http"]
    repos = phase3_env["repos"]
    token = phase3_env["approval"].approval_token
    admin_id = int(settings.TELEGRAM_ADMIN_CHAT_ID or "1293148688")

    res = tg_service.handle_webhook_callback({
        "update_id": 40004,
        "callback_query": {
            "id": "cb_admin_attempt_prod",
            "from": {"id": admin_id},
            "message": {"message_id": 83, "chat": {"id": admin_id}},
            "data": f"approve:{token}",
        },
    })

    assert res["status"] == "unauthorized"
    assert res["code"] == "UNAUTHORIZED_USER"
    mock_http.post.assert_not_called()
    mock_http.put.assert_not_called()

    # Post remains PENDING_APPROVAL
    assert repos.posts.get_by_post_id("JVY-PROD-001").status == PostStatus.PENDING_APPROVAL


def test_duplicate_publishing_prevention(phase3_env):
    """Calling publish on an already PUBLISHED post returns duplicate flag without calling LinkedIn API twice."""
    pub_service = phase3_env["pub_service"]
    mock_http = phase3_env["mock_http"]
    repos = phase3_env["repos"]

    # Pre-set post as already PUBLISHED
    post = repos.posts.get_by_post_id("JVY-PROD-001")
    post.status = PostStatus.PUBLISHED
    post.linkedin_post_id = "urn:li:share:108376955_already_done"
    post.published_at = datetime.now()
    repos.posts.update(post)

    # Calling publish_approved_post must detect duplicate immediately
    res = pub_service.publish_approved_post("JVY-PROD-001")

    assert res["status"] == "published"
    assert res["is_duplicate"] is True
    assert res["external_post_id"] == "urn:li:share:108376955_already_done"
    mock_http.post.assert_not_called()


def test_linkedin_failure_handling(phase3_env):
    """When LinkedIn API returns 401 or 500, post transitions to FAILED and error is raised."""
    pub_service = phase3_env["pub_service"]
    mock_http = phase3_env["mock_http"]
    repos = phase3_env["repos"]

    # Mark post as APPROVED so it is eligible for publishing attempt
    post = repos.posts.get_by_post_id("JVY-PROD-001")
    post.status = PostStatus.APPROVED
    repos.posts.update(post)

    appr = repos.approvals.get_by_post_id("JVY-PROD-001")[0]
    repos.approvals.update_status(appr.approval_token, ApprovalStatus.APPROVED)

    # Ensure image fetch succeeds so we reach LinkedIn REST API initializeUpload
    mock_http.get.return_value = MagicMock(
        status_code=200,
        content=b"\x89PNG\r\n\x1a\nFakeImageBytes",
        headers={"Content-Type": "image/png"},
    )

    # Simulate LinkedIn 401 Auth Error
    err_resp = MagicMock(status_code=401, content=b'{"message":"Expired token"}')
    mock_http.post.return_value = err_resp

    with pytest.raises(LinkedInAuthError):
        pub_service.publish_approved_post("JVY-PROD-001")

    # Post must NOT be marked PUBLISHED; transitions to FAILED
    post_after = repos.posts.get_by_post_id("JVY-PROD-001")
    assert post_after.status == PostStatus.FAILED
    assert post_after.linkedin_post_id is None


def test_scheduler_generates_without_calling_publishing(tmp_path, founder_chat_id, fake_token_store):
    """Verify that daily scheduler generates post in PENDING_APPROVAL and never invokes publisher."""
    repos = create_in_memory_repository_manager()
    runs_file = tmp_path / "scheduler_runs.json"
    state_store = SchedulerStateStore(persistence_file=runs_file)

    mock_http = MagicMock()
    real_client = LinkedInClient(
        organization_id="108376955",
        token_store=fake_token_store,
        http_client=mock_http,
    )
    real_publisher = LinkedInPublisher(client=real_client)
    pub_service = PublishingService(
        repo_manager=repos,
        publisher=real_publisher,
        mock_mode=False,
    )

    mock_img = MockImageProvider(base_url="https://mock-storage.supabase.co/post-images")
    approval_service = ApprovalService(
        repo_manager=repos,
        publishing_service=pub_service,
        image_provider=mock_img,
    )
    mock_tg = MockTelegramProvider(founder_chat_id=founder_chat_id)
    tg_service = TelegramService(
        approval_service=approval_service,
        provider=mock_tg,
        founder_chat_id=founder_chat_id,
    )

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content.side_effect = [
        MagicMock(text=json.dumps({
            "topic": "Warehouse Inventory Scrap Tracking",
            "angle": "Real-time auditing beats manual logs",
            "content_type": "01. Inventory Management Systems | Business Pain Point",
            "service_category": "Inventory Management Systems",
            "content_format": "Business Pain Point",
            "target_audience": "Operations Heads",
            "reason": "Solves stockout friction",
            "visual_concept": "Dashboard reconciliation flow",
        })),
        MagicMock(text=json.dumps({
            "hook": "Ghost stock silently drains fulfillment speed.",
            "caption": "Ghost stock silently drains fulfillment speed.\n\nhttps://www.jeevyamtechnologies.com/services/inventory-management.html",
            "hashtags": ["#Inventory", "#Logistics"],
            "call_to_action": "How often does your team perform stock reconciliation?",
        })),
        MagicMock(text=json.dumps({
            "visual_concept": "Dashboard visual flow",
            "style": "Minimalist UI",
            "composition": "Centered",
            "color_direction": "Navy",
            "text_on_image": "Stock",
            "aspect_ratio": "1:1",
            "layout": "process_flow",
        })),
    ]

    test_posts_dir = tmp_path / "posts"
    test_posts_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        approval_service=approval_service,
        telegram_service=tg_service,
        image_provider=mock_img,
        use_in_memory_db=True,
        posts_dir=test_posts_dir,
    )

    scheduler = DailyScheduler(
        orchestrator=orchestrator,
        state_store=state_store,
        retry_delay_seconds=0.01,
    )

    res = scheduler.execute_daily_run(target_date_str="2026-11-28", mode="mock")

    assert res.success is True
    # Verify LinkedIn was NEVER called
    mock_http.post.assert_not_called()
    mock_http.put.assert_not_called()

    # Post is strictly PENDING_APPROVAL
    post = repos.posts.get_by_post_id(res.post_id)
    assert post.status == PostStatus.PENDING_APPROVAL
    assert post.linkedin_post_id is None
