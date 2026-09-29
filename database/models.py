"""Pydantic data models and enums for Supabase database layer."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, field_validator



class PostStatus(str, Enum):
    """Lifecycle status states for LinkedIn posts."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    REGENERATING = "REGENERATING"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ApprovalStatus(str, Enum):
    """Workflow states for post approval requests."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class LinkedInTarget(str, Enum):
    """Destination target for publication."""

    FOUNDER = "FOUNDER"
    COMPANY_PAGE = "COMPANY_PAGE"


# Allowed state transition matrix for post lifecycle
VALID_POST_TRANSITIONS: Dict[PostStatus, Set[PostStatus]] = {
    PostStatus.DRAFT: {PostStatus.PENDING_APPROVAL},
    PostStatus.PENDING_APPROVAL: {PostStatus.APPROVED, PostStatus.REJECTED},
    PostStatus.REJECTED: {PostStatus.REGENERATING},
    PostStatus.REGENERATING: {PostStatus.PENDING_APPROVAL},
    PostStatus.APPROVED: {PostStatus.PUBLISHED, PostStatus.FAILED},
    PostStatus.PUBLISHED: set(),  # Final terminal state
    PostStatus.FAILED: {PostStatus.APPROVED, PostStatus.REGENERATING},  # Can retry publish or regenerate
}


def validate_status_transition(current: Union[str, PostStatus], target: Union[str, PostStatus]) -> bool:
    """Validate that transition from current status to target status is permitted.

    Args:
        current: Current PostStatus.
        target: Target PostStatus to transition into.

    Returns:
        True if valid.

    Raises:
        InvalidStatusTransitionError: If the transition is not allowed by policy.
    """
    curr_enum = PostStatus(current)
    target_enum = PostStatus(target)

    allowed = VALID_POST_TRANSITIONS.get(curr_enum, set())
    if target_enum not in allowed:
        from agent.exceptions import InvalidStatusTransitionError

        allowed_names = [s.value for s in allowed] or ["None (Terminal State)"]
        raise InvalidStatusTransitionError(
            f"Cannot transition post status from '{curr_enum.value}' to '{target_enum.value}'. "
            f"Allowed next states: {', '.join(allowed_names)}"
        )
    return True


class Company(BaseModel):
    """Company entity model."""

    id: Optional[str] = None
    name: str = Field(..., description="Organization name")
    slug: str = Field(..., description="URL-safe unique company identifier")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Post(BaseModel):
    """Master record of a LinkedIn post reflecting its current state."""

    id: Optional[str] = None
    post_id: str = Field(..., description="Business post ID, e.g. JVY-20260929-001")
    company_id: Optional[str] = None
    status: PostStatus = Field(default=PostStatus.DRAFT)
    current_revision: int = Field(default=1, ge=1)
    content_type: str
    topic: str
    angle: str
    target_audience: str
    hook: str
    caption: str
    hashtags: List[str] = Field(default_factory=list)
    call_to_action: str
    visual_concept: str
    image_brief: Union[Dict[str, Any], Any]
    image_url: Optional[str] = None
    linkedin_post_id: Optional[str] = None
    linkedin_target: LinkedInTarget = Field(default=LinkedInTarget.COMPANY_PAGE)
    created_at: Optional[Union[datetime, str]] = None
    updated_at: Optional[Union[datetime, str]] = None
    approved_at: Optional[Union[datetime, str]] = None
    published_at: Optional[Union[datetime, str]] = None

    @field_validator("hashtags")
    @classmethod
    def clean_hashtags(cls, tags: List[str]) -> List[str]:
        cleaned = []
        for t in tags:
            tag_str = t.strip()
            if not tag_str.startswith("#"):
                tag_str = f"#{tag_str}"
            cleaned.append(tag_str)
        return cleaned


class PostRevision(BaseModel):
    """Historical snapshot of an iteration/revision of a post."""

    id: Optional[str] = None
    post_id: str = Field(..., description="Reference to parent post_id")
    revision_number: int = Field(..., ge=1)
    topic: str
    angle: str
    content_type: str
    target_audience: str
    hook: str
    caption: str
    hashtags: List[str] = Field(default_factory=list)
    call_to_action: str
    visual_concept: str
    image_brief: Union[Dict[str, Any], Any]
    image_url: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None

    @field_validator("hashtags")
    @classmethod
    def clean_hashtags(cls, tags: List[str]) -> List[str]:
        cleaned = []
        for t in tags:
            tag_str = t.strip()
            if not tag_str.startswith("#"):
                tag_str = f"#{tag_str}"
            cleaned.append(tag_str)
        return cleaned


class Approval(BaseModel):
    """Approval request and verification audit record."""

    id: Optional[str] = None
    post_id: str = Field(..., description="Reference to post_id")
    revision_number: int = Field(..., ge=1)
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    approval_token: str = Field(..., description="Cryptographically secure token")
    expires_at: Optional[Union[datetime, str]] = None
    approved_at: Optional[Union[datetime, str]] = None
    rejected_at: Optional[Union[datetime, str]] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None


class PublicationStatus(str, Enum):
    """Workflow states for post publication dispatches."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class Publication(BaseModel):
    """Publication audit record."""

    id: Optional[str] = None
    post_id: str = Field(..., description="Reference to parent post_id")
    revision_number: int = Field(..., ge=1)
    platform: str = Field(default="LINKEDIN")
    status: PublicationStatus = Field(default=PublicationStatus.PENDING)
    external_post_id: Optional[str] = None
    target_urn: Optional[str] = None
    error_message: Optional[str] = None
    published_at: Optional[Union[datetime, str]] = None
    created_at: Optional[Union[datetime, str]] = None

