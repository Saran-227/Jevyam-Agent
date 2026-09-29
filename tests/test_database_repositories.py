"""Unit tests for repository implementations, token generation, and configuration validation."""

from unittest.mock import MagicMock
import pytest

from agent.exceptions import (
    InvalidStatusTransitionError,
    MissingSupabaseCredentialsError,
    PostNotFoundError,
)
from agent.image_generator import ImageBrief
from database.models import (
    ApprovalStatus,
    Company,
    Post,
    PostRevision,
    PostStatus,
)
from database.repositories.approvals import (
    InMemoryApprovalRepository,
    SupabaseApprovalRepository,
)
from database.repositories.companies import (
    InMemoryCompanyRepository,
    SupabaseCompanyRepository,
)
from database.repositories.posts import (
    InMemoryPostRepository,
    SupabasePostRepository,
)
from database.repositories.revisions import (
    InMemoryRevisionRepository,
    SupabaseRevisionRepository,
)
from database.supabase_client import get_supabase_client
from database.tokens import generate_approval_token


def sample_brief() -> ImageBrief:
    return ImageBrief(
        visual_concept="Diagram",
        style="Vector",
        composition="Center",
        color_direction="Slate",
        text_on_image="Title",
    )


def test_supabase_config_missing_validation():
    """Verify error raised when URL or Key is missing."""
    with pytest.raises(MissingSupabaseCredentialsError) as exc_info:
        get_supabase_client(url="", key="")
    assert "SUPABASE_URL is missing" in str(exc_info.value)

    with pytest.raises(MissingSupabaseCredentialsError) as exc_info:
        get_supabase_client(url="https://example.supabase.co", key="")
    assert "SUPABASE_KEY is missing" in str(exc_info.value)


def test_supabase_config_placeholder_validation():
    """Verify error raised when URL or Key has a placeholder value."""
    with pytest.raises(MissingSupabaseCredentialsError) as exc_info:
        get_supabase_client(url="your_supabase_url_here", key="your_key")
    assert "placeholder" in str(exc_info.value)


def test_generate_approval_token_properties():
    """Verify token entropy, length, uniqueness, and prefix."""
    token = generate_approval_token()
    assert token.startswith("appr_")
    assert len(token) > 40

    # Test uniqueness across 1000 generated tokens
    tokens = {generate_approval_token() for _ in range(1000)}
    assert len(tokens) == 1000


def test_in_memory_company_repository():
    repo = InMemoryCompanyRepository()
    default_company = repo.get_by_slug("jevyam")
    assert default_company is not None
    assert default_company.name == "Jevyam Technologies"

    # Create new company
    custom = Company(name="Custom Corp", slug="custom")
    saved = repo.create(custom)
    assert saved.id is not None
    assert repo.get_by_slug("custom") is not None


def test_in_memory_post_repository_crud_and_status():
    repo = InMemoryPostRepository()
    post = Post(
        post_id="JVY-20260929-001",
        content_type="technology insight",
        topic="ETL Pipelines",
        angle="Angle",
        target_audience="CTOs",
        hook="Hook",
        caption="Caption",
        hashtags=["#AI"],
        call_to_action="CTA",
        visual_concept="VC",
        image_brief=sample_brief(),
    )

    created = repo.create(post)
    assert created.status == PostStatus.DRAFT
    assert created.post_id == "JVY-20260929-001"

    # Retrieve
    retrieved = repo.get_by_post_id("JVY-20260929-001")
    assert retrieved is not None
    assert retrieved.topic == "ETL Pipelines"

    # Valid status transition: DRAFT -> PENDING_APPROVAL
    updated = repo.update_status("JVY-20260929-001", PostStatus.PENDING_APPROVAL)
    assert updated.status == PostStatus.PENDING_APPROVAL

    # Invalid status transition: PENDING_APPROVAL -> DRAFT (illegal backward step)
    with pytest.raises(InvalidStatusTransitionError):
        repo.update_status("JVY-20260929-001", PostStatus.DRAFT)

    # Next sequence calculation
    next_seq = repo.get_next_sequence_for_date("20260929")
    assert next_seq == 2


def test_in_memory_revision_repository():
    repo = InMemoryRevisionRepository()
    post_id = "JVY-20260929-001"

    rev1 = PostRevision(
        post_id=post_id,
        revision_number=1,
        topic="Topic v1",
        angle="Angle v1",
        content_type="educational",
        target_audience="Engineers",
        hook="Hook v1",
        caption="Caption v1",
        hashtags=["#AI"],
        call_to_action="CTA v1",
        visual_concept="VC v1",
        image_brief=sample_brief(),
    )
    rev2 = PostRevision(
        post_id=post_id,
        revision_number=2,
        topic="Topic v2",
        angle="Angle v2",
        content_type="educational",
        target_audience="Engineers",
        hook="Hook v2",
        caption="Caption v2",
        hashtags=["#AI"],
        call_to_action="CTA v2",
        visual_concept="VC v2",
        image_brief=sample_brief(),
        rejection_reason="Revise hook",
    )

    repo.create(rev1)
    repo.create(rev2)

    all_revs = repo.get_by_post_id(post_id)
    assert len(all_revs) == 2
    assert all_revs[0].revision_number == 1
    assert all_revs[1].revision_number == 2

    latest = repo.get_latest_revision(post_id)
    assert latest is not None
    assert latest.revision_number == 2
    assert latest.rejection_reason == "Revise hook"


def test_in_memory_approval_repository():
    repo = InMemoryApprovalRepository()
    approval = repo.create_approval_request("JVY-20260929-001", revision_number=1)

    assert approval.status == ApprovalStatus.PENDING
    assert approval.approval_token.startswith("appr_")

    # Fetch by token
    fetched = repo.get_by_token(approval.approval_token)
    assert fetched is not None
    assert fetched.post_id == "JVY-20260929-001"

    # Update status to APPROVED
    approved = repo.update_status(approval.approval_token, ApprovalStatus.APPROVED)
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.approved_at is not None


def test_supabase_post_repository_mocked():
    """Verify SupabasePostRepository executes client queries appropriately."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    repo = SupabasePostRepository(client=mock_client)
    post = Post(
        post_id="JVY-20260929-001",
        content_type="tech",
        topic="Topic",
        angle="Angle",
        target_audience="CTOs",
        hook="Hook",
        caption="Caption",
        hashtags=["#AI"],
        call_to_action="CTA",
        visual_concept="VC",
        image_brief=sample_brief(),
    )

    mock_resp = MagicMock()
    mock_resp.data = [{
        "post_id": "JVY-20260929-001",
        "content_type": "tech",
        "topic": "Topic",
        "angle": "Angle",
        "target_audience": "CTOs",
        "hook": "Hook",
        "caption": "Caption",
        "hashtags": ["#AI"],
        "call_to_action": "CTA",
        "visual_concept": "VC",
        "image_brief": sample_brief().model_dump(),
        "status": "DRAFT",
        "current_revision": 1,
    }]
    mock_table.insert.return_value.execute.return_value = mock_resp

    saved = repo.create(post)
    assert saved.post_id == "JVY-20260929-001"
    mock_client.table.assert_called_with("posts")
