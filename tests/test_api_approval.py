"""Comprehensive tests for FastAPI founder approval system (Phase 3)."""

from datetime import datetime, timedelta
import json
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from agent.image_generator import ImageBrief
from api.dependencies import get_approval_service
from api.main import app
from api.services.approval_service import ApprovalService
from database.models import ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager


@pytest.fixture
def mock_repo_manager():
    """Create isolated in-memory repository manager for each test."""
    return create_in_memory_repository_manager()


@pytest.fixture
def sample_brief():
    return ImageBrief(
        visual_concept="Clean pipeline diagram with data verification shields",
        style="Minimalist dark mode isometric vector",
        composition="Center aligned with ample negative space",
        color_direction="Charcoal and cyan",
        text_on_image="Zero-Trust Architecture",
        aspect_ratio="1:1",
    )


@pytest.fixture
def seeded_post(mock_repo_manager, sample_brief):
    """Seed a sample post and revision 1 into the repository."""
    post_id = "JVY-20260929-001"
    post = Post(
        post_id=post_id,
        status=PostStatus.DRAFT,
        current_revision=1,
        content_type="technology insight",
        topic="Evaluating Zero-Trust Vectors",
        angle="Why access control must happen at embedding time",
        target_audience="CTOs and Security Architects",
        hook="Vector search without access control is a security vulnerability.",
        caption="Vector search without access control is a security vulnerability.\n\nEnforcing strict isolation prevents cross-tenant data leakage in enterprise RAG.\n\nHow do you handle vector security?",
        hashtags=["#CyberSecurity", "#AI", "#EnterpriseTech", "#CloudArchitecture", "#SoftwareEngineering"],
        call_to_action="How do you handle vector security?",
        visual_concept="Clean pipeline diagram with data verification shields",
        image_brief=sample_brief,
        image_url=None,
    )
    mock_repo_manager.posts.create(post)

    rev = PostRevision(
        post_id=post_id,
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
        image_brief=sample_brief,
        image_url=None,
    )
    mock_repo_manager.revisions.create(rev)
    return post


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini client configured for draft regeneration."""
    client = MagicMock()
    new_idea_json = json.dumps({
        "topic": "Pivoted Topic: Data Governance in RAG",
        "angle": "Role-based access control inside vector embeddings",
        "content_type": "technology insight",
        "target_audience": "Security and Engineering Leaders",
        "reason": "Addresses feedback requesting deeper enterprise security focus.",
    })
    new_writer_json = json.dumps({
        "hook": "Vector search without access control is a security breach waiting to happen.",
        "caption": "Vector search without access control is a security breach waiting to happen.\n\nImplementing tenant isolation and ACLs at ingestion prevents unauthorized data leakage.\n\nHow does your team enforce document security in RAG?",
        "hashtags": ["#CyberSecurity", "#AI", "#EnterpriseTech", "#SoftwareEngineering", "#CloudSecurity"],
        "call_to_action": "How does your team enforce document security in RAG?",
    })
    new_brief_json = json.dumps({
        "visual_concept": "Shield and permission matrix overlay on vector database",
        "style": "Clean isometric diagram",
        "composition": "Centered security gatekeeper concept",
        "color_direction": "Charcoal and shield blue",
        "text_on_image": "Securing Enterprise Vectors",
        "aspect_ratio": "1:1",
    })

    resp1 = MagicMock()
    resp1.text = new_idea_json
    resp2 = MagicMock()
    resp2.text = new_writer_json
    resp3 = MagicMock()
    resp3.text = new_brief_json
    client.models.generate_content.side_effect = [resp1, resp2, resp3]
    return client


@pytest.fixture
def client_and_service(mock_repo_manager, mock_gemini_client):
    """TestClient wired with in-memory repository and mocked Gemini."""
    service = ApprovalService(
        repo_manager=mock_repo_manager,
        gemini_client=mock_gemini_client,
    )

    app.dependency_overrides[get_approval_service] = lambda: service
    test_client = TestClient(app)
    yield test_client, service, mock_repo_manager
    app.dependency_overrides.clear()


# ==============================================================================
# TEST CASES
# ==============================================================================

def test_health_endpoint(client_and_service):
    """1. Test GET /health endpoint."""
    test_client, _, _ = client_and_service
    resp = test_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "jevyam-approval-api"


def test_invalid_approval_token(client_and_service):
    """2. Test invalid / nonexistent approval token returns 404."""
    test_client, _, _ = client_and_service
    invalid_token = "appr_nonexistent_fake_token"

    # GET HTML page
    resp_get = test_client.get(f"/approve/{invalid_token}")
    assert resp_get.status_code == 404
    assert "Approval Link Not Found" in resp_get.text

    # POST YES
    resp_yes = test_client.post(f"/approve/{invalid_token}/yes")
    assert resp_yes.status_code == 404

    # POST NO
    resp_no = test_client.post(f"/approve/{invalid_token}/no")
    assert resp_no.status_code == 404


def test_expired_approval_token(client_and_service, seeded_post):
    """3. Test expired approval token returns 410."""
    test_client, service, repo_manager = client_and_service

    # Create approval expired 2 hours ago
    past_time = datetime.now() - timedelta(hours=2)
    approval = repo_manager.approvals.create_approval_request(
        post_id=seeded_post.post_id,
        revision_number=1,
        expires_at=past_time,
    )
    # Ensure post status is PENDING_APPROVAL
    repo_manager.posts.update_status(seeded_post.post_id, PostStatus.PENDING_APPROVAL)

    token = approval.approval_token

    # GET
    resp_get = test_client.get(f"/approve/{token}")
    assert resp_get.status_code == 410
    assert "Approval Link Expired" in resp_get.text

    # POST YES
    resp_yes = test_client.post(f"/approve/{token}/yes")
    assert resp_yes.status_code == 410
    assert "expired" in resp_yes.json()["detail"].lower()


def test_valid_approval_page_rendering(client_and_service, seeded_post):
    """4. Test valid approval page loads with content, hook, hashtags, and buttons."""
    test_client, service, _ = client_and_service
    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)

    resp = test_client.get(f"/approve/{appr_resp.approval_token}")
    assert resp.status_code == 200
    assert "Jevyam Technologies" in resp.text
    assert "Evaluating Zero-Trust Vectors" in resp.text
    assert "Vector search without access control" in resp.text
    assert "YES — PUBLISH" in resp.text
    assert "NO — REGENERATE" in resp.text
    assert "Revision #1" in resp.text


def test_yes_approval_lifecycle(client_and_service, seeded_post):
    """5. Test YES approval transitions post to APPROVED and consumes token."""
    test_client, service, repo_manager = client_and_service
    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)

    # Initial state
    post_before = repo_manager.posts.get_by_post_id(seeded_post.post_id)
    assert post_before.status == PostStatus.PENDING_APPROVAL

    # Submit YES
    resp = test_client.post(f"/approve/{appr_resp.approval_token}/yes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["post_id"] == seeded_post.post_id
    assert data["revision"] == 1

    # Verify repository state
    post_after = repo_manager.posts.get_by_post_id(seeded_post.post_id)
    assert post_after.status == PostStatus.APPROVED
    assert post_after.approved_at is not None

    approval_record = repo_manager.approvals.get_by_token(appr_resp.approval_token)
    assert approval_record.status == ApprovalStatus.APPROVED
    assert approval_record.approved_at is not None


def test_double_yes_request_idempotency(client_and_service, seeded_post):
    """6. Test double YES request safely rejects duplicate action without error."""
    test_client, service, _ = client_and_service
    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)

    # First YES: success
    resp1 = test_client.post(f"/approve/{appr_resp.approval_token}/yes")
    assert resp1.status_code == 200

    # Second YES: rejected with 410
    resp2 = test_client.post(f"/approve/{appr_resp.approval_token}/yes")
    assert resp2.status_code == 410
    assert "no longer active" in resp2.json()["detail"].lower()


def test_no_regeneration_flow(client_and_service, seeded_post):
    """7, 9, 10, 11, 12, 13. Test complete NO regeneration flow."""
    test_client, service, repo_manager = client_and_service
    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)

    old_token = appr_resp.approval_token

    # Submit NO with rejection reason
    rejection_payload = {"reason": "Make it more technical and focused on enterprise security."}
    resp = test_client.post(f"/approve/{old_token}/no", json=rejection_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "regenerated"
    assert data["post_id"] == seeded_post.post_id
    assert data["revision"] == 2
    assert "approval_url" in data
    new_approval_url = data["approval_url"]
    assert new_approval_url.startswith("http") or new_approval_url.startswith("/")

    # Verify Revision Number Increment (Requirement 9)
    post_updated = repo_manager.posts.get_by_post_id(seeded_post.post_id)
    assert post_updated.current_revision == 2
    assert post_updated.status == PostStatus.PENDING_APPROVAL

    # Verify Previous Revision Preserved (Requirement 10)
    all_revisions = repo_manager.revisions.get_by_post_id(seeded_post.post_id)
    assert len(all_revisions) == 2
    assert all_revisions[0].revision_number == 1
    assert all_revisions[0].topic == "Evaluating Zero-Trust Vectors"
    assert all_revisions[1].revision_number == 2
    assert all_revisions[1].topic == "Pivoted Topic: Data Governance in RAG"

    # Verify Rejection Reason Persisted (Requirement 13)
    assert all_revisions[1].rejection_reason == rejection_payload["reason"]

    # Verify Old Token Invalidated (Requirement 12)
    old_approval_record = repo_manager.approvals.get_by_token(old_token)
    assert old_approval_record.status == ApprovalStatus.REJECTED

    # Verify New Approval Token Generated (Requirement 11)
    new_token = new_approval_url.split("/approve/")[-1]
    assert new_token != old_token
    assert new_token.startswith("appr_")

    new_approval_record = repo_manager.approvals.get_by_token(new_token)
    assert new_approval_record is not None
    assert new_approval_record.revision_number == 2
    assert new_approval_record.status == ApprovalStatus.PENDING


def test_double_no_request_idempotency(client_and_service, seeded_post):
    """8. Test clicking NO twice does not trigger duplicate regenerations."""
    test_client, service, repo_manager = client_and_service
    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)
    old_token = appr_resp.approval_token

    # First NO
    resp1 = test_client.post(f"/approve/{old_token}/no", json={"reason": "First reject"})
    assert resp1.status_code == 200

    # Second NO on old consumed token
    resp2 = test_client.post(f"/approve/{old_token}/no", json={"reason": "Second reject"})
    assert resp2.status_code == 410
    assert "no longer active" in resp2.json()["detail"].lower()

    # Verify revisions did not duplicate
    revisions = repo_manager.revisions.get_by_post_id(seeded_post.post_id)
    assert len(revisions) == 2  # Only revision 1 and revision 2


def test_invalid_state_transition_rejection(client_and_service, seeded_post):
    """14. Test attempting approval when post is already PUBLISHED fails."""
    test_client, service, repo_manager = client_and_service
    # Mark post as PUBLISHED
    seeded_post.status = PostStatus.PUBLISHED
    repo_manager.posts.update(seeded_post)

    with pytest.raises(Exception):
        service.create_approval_request(seeded_post.post_id)


def test_missing_post_error(client_and_service):
    """15. Test approval creation fails cleanly when post does not exist."""
    _, service, _ = client_and_service
    with pytest.raises(Exception) as exc_info:
        service.create_approval_request("JVY-NONEXISTENT-999")
    assert "does not exist" in str(exc_info.value)


def test_image_url_present_rendering(client_and_service, seeded_post):
    """17. Test that image_url renders an <img> tag when available."""
    test_client, service, repo_manager = client_and_service
    seeded_post.image_url = "https://images.unsplash.com/photo-example.jpg"
    repo_manager.posts.update(seeded_post)

    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)
    resp = test_client.get(f"/approve/{appr_resp.approval_token}")
    assert resp.status_code == 200
    assert '<img src="https://images.unsplash.com/photo-example.jpg"' in resp.text


def test_image_url_absent_rendering(client_and_service, seeded_post):
    """18. Test that page renders clean placeholder without crash when image_url is None."""
    test_client, service, repo_manager = client_and_service
    seeded_post.image_url = None
    repo_manager.posts.update(seeded_post)

    appr_resp = service.create_approval_request(seeded_post.post_id, revision_number=1)
    resp = test_client.get(f"/approve/{appr_resp.approval_token}")
    assert resp.status_code == 200
    assert "Visual Brief" in resp.text
    assert "<img" not in resp.text


def test_dev_endpoint_create_approval(client_and_service, seeded_post):
    """19. Test development endpoint POST /api/posts/{post_id}/approval."""
    test_client, _, repo_manager = client_and_service
    resp = test_client.post(f"/api/posts/{seeded_post.post_id}/approval")
    assert resp.status_code == 200
    data = resp.json()
    assert data["post_id"] == seeded_post.post_id
    assert data["revision_number"] == 1
    assert data["approval_token"].startswith("appr_")
    assert "/approve/" in data["approval_url"]
