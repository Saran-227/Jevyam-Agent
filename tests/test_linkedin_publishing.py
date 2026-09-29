"""Unit tests for LinkedIn publishing client, publisher, service, and approval integration."""

from datetime import datetime
import json
import logging
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import httpx
import pytest

from agent.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInDuplicatePostError,
    LinkedInError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInRateLimitError,
    LinkedInValidationError,
    MissingLinkedInCredentialsError,
    PostNotApprovedError,
    PostNotFoundError,
)
from agent.image_generator import ImageBrief
from api.dependencies import get_approval_service, get_publishing_service
from api.main import app
from api.services.approval_service import ApprovalService
from api.services.publishing_service import PublishingService
from database.models import (
    Approval,
    ApprovalStatus,
    LinkedInTarget,
    Post,
    PostRevision,
    PostStatus,
    Publication,
    PublicationStatus,
)
from database.repositories import create_in_memory_repository_manager
from integrations.linkedin.client import LinkedInClient, LinkedInPublishResponse
from integrations.linkedin.publisher import LinkedInPublisher


@pytest.fixture
def mock_repo_manager():
    return create_in_memory_repository_manager()


@pytest.fixture
def sample_approved_post(mock_repo_manager):
    brief = ImageBrief(
        visual_concept="Architecture diagram",
        style="2D isometric",
        composition="Center",
        color_direction="Charcoal and Cyan",
        text_on_image="Reliable Automation",
    )
    post_id = "JVY-20260929-001"
    post = Post(
        post_id=post_id,
        status=PostStatus.APPROVED,
        current_revision=1,
        content_type="software engineering",
        topic="Event-Driven Automation Architecture",
        angle="Webhooks over cron",
        target_audience="Tech Leads",
        hook="Cron jobs fail silently.",
        caption="Cron jobs fail silently. Use idempotent webhooks.\n\nHow do you handle retries?",
        hashtags=["#DevOps", "#CloudArchitecture"],
        call_to_action="How do you handle retries?",
        visual_concept="Architecture diagram",
        image_brief=brief,
        image_url="https://cdn.jevyam.com/visuals/jvy-001.png",
        linkedin_target=LinkedInTarget.COMPANY_PAGE,
    )
    mock_repo_manager.posts.create(post)
    mock_repo_manager.revisions.create(
        PostRevision(
            post_id=post_id,
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
    # Seed approved approval record
    appr = mock_repo_manager.approvals.create_approval_request(post_id=post_id, revision_number=1)
    mock_repo_manager.approvals.update_status(appr.approval_token, ApprovalStatus.APPROVED)
    return post


# ==============================================================================
# 1. Successful publication
# ==============================================================================
def test_successful_publication(mock_repo_manager, sample_approved_post):
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.headers = {"x-restli-id": "urn:li:share:987654321"}
    mock_resp.content = b'{"id": "urn:li:share:987654321"}'
    mock_resp.json.return_value = {"id": "urn:li:share:987654321"}
    mock_http.post.return_value = mock_resp

    client = LinkedInClient(
        access_token="valid_oauth_token",
        organization_id="12345678",
        http_client=mock_http,
    )
    publisher = LinkedInPublisher(client=client)
    publishing_service = PublishingService(repo_manager=mock_repo_manager, publisher=publisher)

    result = publishing_service.publish_approved_post("JVY-20260929-001")

    assert result["status"] == "published"
    assert result["is_duplicate"] is False
    assert result["external_post_id"] == "urn:li:share:987654321"
    assert "linkedin.com" in result["post_url"]

    # Verify post master record updated in database
    updated_post = mock_repo_manager.posts.get_by_post_id("JVY-20260929-001")
    assert updated_post.status == PostStatus.PUBLISHED
    assert updated_post.linkedin_post_id == "urn:li:share:987654321"
    assert updated_post.published_at is not None

    # Verify publication audit record
    pub_records = mock_repo_manager.publications.get_by_post_id("JVY-20260929-001")
    assert len(pub_records) == 1
    assert pub_records[0].status == PublicationStatus.PUBLISHED
    assert pub_records[0].external_post_id == "urn:li:share:987654321"
    assert pub_records[0].target_urn == "urn:li:organization:12345678"


# ==============================================================================
# 2. Failed LinkedIn API request
# ==============================================================================
def test_failed_linkedin_api_request(mock_repo_manager, sample_approved_post):
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.content = b'{"message": "Internal server error"}'
    mock_resp.json.return_value = {"message": "Internal server error"}
    mock_http.post.return_value = mock_resp

    client = LinkedInClient(
        access_token="valid_token",
        organization_id="12345678",
        http_client=mock_http,
    )
    publisher = LinkedInPublisher(client=client)
    publishing_service = PublishingService(repo_manager=mock_repo_manager, publisher=publisher)

    with pytest.raises(LinkedInAPIError) as exc_info:
        publishing_service.publish_approved_post("JVY-20260929-001")
    assert "500" in str(exc_info.value)

    # Post should transition to FAILED status
    updated_post = mock_repo_manager.posts.get_by_post_id("JVY-20260929-001")
    assert updated_post.status == PostStatus.FAILED

    # Audit record should be marked FAILED
    pub_records = mock_repo_manager.publications.get_by_post_id("JVY-20260929-001")
    assert len(pub_records) == 1
    assert pub_records[0].status == PublicationStatus.FAILED
    assert "Internal server error" in pub_records[0].error_message


# ==============================================================================
# 3. Missing credentials
# ==============================================================================
def test_missing_credentials(mock_repo_manager, sample_approved_post):
    # Empty token
    client1 = LinkedInClient(access_token="", organization_id="12345678")
    with pytest.raises(MissingLinkedInCredentialsError) as exc_info:
        client1.validate_credentials()
    assert "LINKEDIN_ACCESS_TOKEN is missing" in str(exc_info.value)

    # Placeholder token
    client2 = LinkedInClient(access_token="your_token_here", organization_id="12345678")
    with pytest.raises(MissingLinkedInCredentialsError) as exc_info:
        client2.validate_credentials()
    assert "placeholder" in str(exc_info.value)

    # Missing organization ID
    client3 = LinkedInClient(access_token="valid_token", organization_id="")
    with pytest.raises(MissingLinkedInCredentialsError) as exc_info:
        client3.validate_credentials()
    assert "LINKEDIN_ORGANIZATION_ID is missing" in str(exc_info.value)


# ==============================================================================
# 4. Invalid approval state
# ==============================================================================
def test_invalid_approval_state(mock_repo_manager, sample_approved_post):
    # Change status back to PENDING_APPROVAL
    sample_approved_post.status = PostStatus.PENDING_APPROVAL
    mock_repo_manager.posts.update(sample_approved_post)

    publishing_service = PublishingService(repo_manager=mock_repo_manager)

    with pytest.raises(PostNotApprovedError) as exc_info:
        publishing_service.publish_approved_post("JVY-20260929-001")
    assert "PENDING_APPROVAL" in str(exc_info.value)
    assert "Only posts in APPROVED status" in str(exc_info.value)


# ==============================================================================
# 5. Rejected post is not published
# ==============================================================================
def test_rejected_post_is_not_published(mock_repo_manager, sample_approved_post):
    sample_approved_post.status = PostStatus.REJECTED
    mock_repo_manager.posts.update(sample_approved_post)

    publishing_service = PublishingService(repo_manager=mock_repo_manager)

    with pytest.raises(PostNotApprovedError) as exc_info:
        publishing_service.publish_approved_post("JVY-20260929-001")
    assert "REJECTED" in str(exc_info.value)


# ==============================================================================
# 6. Regenerated unapproved revision is not published
# ==============================================================================
def test_regenerated_unapproved_revision_not_published(mock_repo_manager, sample_approved_post):
    # Increment post to revision 2 with status PENDING_APPROVAL
    sample_approved_post.current_revision = 2
    sample_approved_post.status = PostStatus.PENDING_APPROVAL
    mock_repo_manager.posts.update(sample_approved_post)

    publishing_service = PublishingService(repo_manager=mock_repo_manager)

    with pytest.raises(PostNotApprovedError) as exc_info:
        publishing_service.publish_approved_post("JVY-20260929-001")
    assert "PENDING_APPROVAL" in str(exc_info.value)


# ==============================================================================
# 7. Already-published post is not published again (Idempotency)
# ==============================================================================
def test_already_published_post_idempotency(mock_repo_manager, sample_approved_post):
    sample_approved_post.status = PostStatus.PUBLISHED
    sample_approved_post.linkedin_post_id = "urn:li:share:EXISTING_12345"
    sample_approved_post.published_at = datetime.now()
    mock_repo_manager.posts.update(sample_approved_post)

    mock_client = MagicMock()
    publisher = LinkedInPublisher(client=mock_client)
    publishing_service = PublishingService(repo_manager=mock_repo_manager, publisher=publisher)

    result = publishing_service.publish_approved_post("JVY-20260929-001")

    # Should return existing result without making any network call
    assert result["is_duplicate"] is True
    assert result["external_post_id"] == "urn:li:share:EXISTING_12345"
    mock_client.publish_text_post.assert_not_called()


# ==============================================================================
# 8. Publishing result is persisted
# ==============================================================================
def test_publishing_result_is_persisted(mock_repo_manager, sample_approved_post):
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.headers = {"x-restli-id": "urn:li:share:AUDIT_TEST_777"}
    mock_resp.content = b'{"id": "urn:li:share:AUDIT_TEST_777"}'
    mock_resp.json.return_value = {"id": "urn:li:share:AUDIT_TEST_777"}
    mock_http.post.return_value = mock_resp

    client = LinkedInClient(
        access_token="valid_token",
        organization_id="12345678",
        http_client=mock_http,
    )
    publisher = LinkedInPublisher(client=client)
    publishing_service = PublishingService(repo_manager=mock_repo_manager, publisher=publisher)

    publishing_service.publish_approved_post("JVY-20260929-001")

    # Verify audit table persistence
    publications = mock_repo_manager.publications.get_by_post_id("JVY-20260929-001")
    assert len(publications) == 1
    assert publications[0].external_post_id == "urn:li:share:AUDIT_TEST_777"
    assert publications[0].platform == "LINKEDIN"
    assert publications[0].status == PublicationStatus.PUBLISHED


# ==============================================================================
# 9. API token is never written to logs
# ==============================================================================
def test_api_token_never_written_to_logs(caplog):
    secret_token = "SECRET_LINKEDIN_OAUTH_TOKEN_XYZ_98765"
    mock_http = MagicMock(spec=httpx.Client)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.content = b'{"message": "Invalid token"}'
    mock_resp.json.return_value = {"message": "Invalid token"}
    mock_http.post.return_value = mock_resp

    client = LinkedInClient(
        access_token=secret_token,
        organization_id="12345678",
        http_client=mock_http,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LinkedInAuthError):
            client.publish_text_post("Test post")

    # Check captured logs
    for record in caplog.records:
        assert secret_token not in record.message
        assert secret_token not in str(record.args)


# ==============================================================================
# 10. LinkedIn API errors are converted into appropriate exceptions
# ==============================================================================
def test_linkedin_api_errors_converted():
    mock_http = MagicMock(spec=httpx.Client)

    def set_mock_status(status_code: int, msg: str):
        resp = MagicMock()
        resp.status_code = status_code
        resp.content = json.dumps({"message": msg}).encode()
        resp.json.return_value = {"message": msg}
        mock_http.post.return_value = resp

    client = LinkedInClient(
        access_token="valid_token",
        organization_id="12345678",
        http_client=mock_http,
    )

    # 401 -> LinkedInAuthError
    set_mock_status(401, "Token expired")
    with pytest.raises(LinkedInAuthError):
        client.publish_text_post("Post content")

    # 403 -> LinkedInPermissionError
    set_mock_status(403, "Not an organization admin")
    with pytest.raises(LinkedInPermissionError):
        client.publish_text_post("Post content")

    # 400 / 422 -> LinkedInValidationError
    set_mock_status(400, "Text exceeds 3000 chars")
    with pytest.raises(LinkedInValidationError):
        client.publish_text_post("Post content")

    # 429 -> LinkedInRateLimitError
    set_mock_status(429, "Too many requests")
    with pytest.raises(LinkedInRateLimitError):
        client.publish_text_post("Post content")

    # 503 -> LinkedInAPIError
    set_mock_status(503, "Service unavailable")
    with pytest.raises(LinkedInAPIError):
        client.publish_text_post("Post content")

    # Timeout -> LinkedInNetworkError
    mock_http.post.side_effect = httpx.TimeoutException("Connection timed out")
    with pytest.raises(LinkedInNetworkError):
        client.publish_text_post("Post content")


# ==============================================================================
# 11. Full approval flow triggers publishing
# ==============================================================================
def test_approval_flow_triggers_publishing(mock_repo_manager):
    # Setup pending draft
    brief = ImageBrief(
        visual_concept="V", style="S", composition="C", color_direction="CD", text_on_image="T"
    )
    post_id = "JVY-20260929-002"
    post = Post(
        post_id=post_id,
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="ed",
        topic="Architecture",
        angle="Angle",
        target_audience="Engineers",
        hook="Hook",
        caption="Caption text",
        hashtags=["#Tech"],
        call_to_action="CTA",
        visual_concept="V",
        image_brief=brief,
    )
    mock_repo_manager.posts.create(post)
    mock_repo_manager.revisions.create(
        PostRevision(
            post_id=post_id,
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
        )
    )

    mock_client = MagicMock()
    mock_client.organization_urn = "urn:li:organization:12345678"
    mock_client.publish_text_post.return_value = LinkedInPublishResponse(
        success=True,
        post_urn="urn:li:share:AUTO_PUB_001",
        post_url="https://www.linkedin.com/feed/update/urn:li:share:AUTO_PUB_001",
        target_urn="urn:li:organization:12345678",
    )
    publisher = LinkedInPublisher(client=mock_client)
    pub_service = PublishingService(repo_manager=mock_repo_manager, publisher=publisher)

    approval_service = ApprovalService(
        repo_manager=mock_repo_manager,
        publishing_service=pub_service,
    )

    create_res = approval_service.create_approval_request(post_id)
    token = create_res.approval_token

    # Approving should trigger LinkedIn publishing automatically!
    action_res = approval_service.approve_post(token=token, auto_publish=True)

    assert action_res.status == "approved"
    assert action_res.published is True
    assert action_res.external_post_id == "urn:li:share:AUTO_PUB_001"

    # Verify post in database is PUBLISHED
    saved_post = mock_repo_manager.posts.get_by_post_id(post_id)
    assert saved_post.status == PostStatus.PUBLISHED
    assert saved_post.linkedin_post_id == "urn:li:share:AUTO_PUB_001"


# ==============================================================================
# 12. Publishing API endpoint (/posts/{post_id}/publish)
# ==============================================================================
def test_publishing_api_endpoints(mock_repo_manager, sample_approved_post):
    mock_client = MagicMock()
    mock_client.organization_urn = "urn:li:organization:12345678"
    mock_client.publish_text_post.return_value = LinkedInPublishResponse(
        success=True,
        post_urn="urn:li:share:API_PUB_999",
        post_url="https://www.linkedin.com/feed/update/urn:li:share:API_PUB_999",
        target_urn="urn:li:organization:12345678",
    )
    publisher = LinkedInPublisher(client=mock_client)
    pub_service = PublishingService(repo_manager=mock_repo_manager, publisher=publisher)

    app.dependency_overrides[get_publishing_service] = lambda: pub_service
    client = TestClient(app)

    # 1. Publish approved post
    resp = client.post("/posts/JVY-20260929-001/publish")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "published"
    assert data["external_post_id"] == "urn:li:share:API_PUB_999"

    # 2. Query publications audit history
    audit_resp = client.get("/posts/JVY-20260929-001/publications")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["count"] == 1
    assert audit_data["publications"][0]["external_post_id"] == "urn:li:share:API_PUB_999"
