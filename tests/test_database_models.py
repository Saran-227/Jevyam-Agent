"""Unit tests for database models, enums, and post status transitions."""

import pytest
from pydantic import ValidationError

from agent.exceptions import InvalidStatusTransitionError
from agent.image_generator import ImageBrief
from database.models import (
    Approval,
    ApprovalStatus,
    Company,
    LinkedInTarget,
    Post,
    PostRevision,
    PostStatus,
    validate_status_transition,
)


def sample_image_brief() -> ImageBrief:
    return ImageBrief(
        visual_concept="Minimalist architecture blueprint",
        style="Isometric dark vector",
        composition="Center aligned",
        color_direction="Slate and indigo",
        text_on_image="Architecture First",
        aspect_ratio="1:1",
    )


def test_company_model_validation():
    company = Company(name="Jevyam Technologies", slug="jevyam")
    assert company.name == "Jevyam Technologies"
    assert company.slug == "jevyam"


def test_post_model_defaults_and_validation():
    brief = sample_image_brief()
    post = Post(
        post_id="JVY-20260929-001",
        content_type="technology insight",
        topic="Modern Data Pipelines",
        angle="Solving ETL drift",
        target_audience="CTOs",
        hook="Data drift silently corrupts RAG.",
        caption="Data drift silently corrupts RAG. Here is how to fix it.",
        hashtags=["AI", "DataEngineering"],
        call_to_action="How do you handle drift?",
        visual_concept="Architecture flow",
        image_brief=brief,
    )
    assert post.status == PostStatus.DRAFT
    assert post.current_revision == 1
    assert post.linkedin_target == LinkedInTarget.COMPANY_PAGE
    assert post.hashtags == ["#AI", "#DataEngineering"]


def test_post_revision_model_validation():
    brief = sample_image_brief()
    rev = PostRevision(
        post_id="JVY-20260929-001",
        revision_number=2,
        content_type="technology insight",
        topic="Modern Data Pipelines v2",
        angle="Solving ETL drift with validation checks",
        target_audience="CTOs",
        hook="Data drift silently corrupts RAG.",
        caption="Data drift silently corrupts RAG.",
        hashtags=["#AI", "#Data"],
        call_to_action="Share your thoughts.",
        visual_concept="Updated architecture flow",
        image_brief=brief,
        rejection_reason="Make it more technical and focused on verification.",
    )
    assert rev.revision_number == 2
    assert rev.rejection_reason == "Make it more technical and focused on verification."
    assert rev.hashtags == ["#AI", "#Data"]


def test_approval_model_validation():
    approval = Approval(
        post_id="JVY-20260929-001",
        revision_number=1,
        approval_token="appr_secure_random_token_12345",
    )
    assert approval.status == ApprovalStatus.PENDING
    assert approval.approval_token == "appr_secure_random_token_12345"


def test_valid_status_transitions():
    # DRAFT -> PENDING_APPROVAL
    assert validate_status_transition(PostStatus.DRAFT, PostStatus.PENDING_APPROVAL) is True

    # PENDING_APPROVAL -> APPROVED
    assert validate_status_transition(PostStatus.PENDING_APPROVAL, PostStatus.APPROVED) is True

    # PENDING_APPROVAL -> REJECTED
    assert validate_status_transition(PostStatus.PENDING_APPROVAL, PostStatus.REJECTED) is True

    # REJECTED -> REGENERATING
    assert validate_status_transition(PostStatus.REJECTED, PostStatus.REGENERATING) is True

    # REGENERATING -> PENDING_APPROVAL
    assert validate_status_transition(PostStatus.REGENERATING, PostStatus.PENDING_APPROVAL) is True

    # APPROVED -> PUBLISHED
    assert validate_status_transition(PostStatus.APPROVED, PostStatus.PUBLISHED) is True

    # APPROVED -> FAILED
    assert validate_status_transition(PostStatus.APPROVED, PostStatus.FAILED) is True

    # FAILED -> APPROVED (retry publish)
    assert validate_status_transition(PostStatus.FAILED, PostStatus.APPROVED) is True

    # FAILED -> REGENERATING (regenerate on failure)
    assert validate_status_transition(PostStatus.FAILED, PostStatus.REGENERATING) is True


def test_invalid_status_transitions():
    # Direct jump from DRAFT to PUBLISHED is forbidden
    with pytest.raises(InvalidStatusTransitionError) as exc_info:
        validate_status_transition(PostStatus.DRAFT, PostStatus.PUBLISHED)
    assert "Cannot transition post status" in str(exc_info.value)

    # Direct jump from DRAFT to APPROVED is forbidden (must pass through review)
    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(PostStatus.DRAFT, PostStatus.APPROVED)

    # Terminal state PUBLISHED cannot transition
    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(PostStatus.PUBLISHED, PostStatus.DRAFT)

    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(PostStatus.PUBLISHED, PostStatus.REJECTED)
