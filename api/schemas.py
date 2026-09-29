"""Pydantic schemas for the FastAPI approval system."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check endpoint response schema."""

    status: str = Field(default="ok", description="Health status string")
    service: str = Field(
        default="jevyam-approval-api",
        description="Service identifier",
    )


class RejectApprovalRequest(BaseModel):
    """Optional rejection request payload with founder feedback."""

    reason: Optional[str] = Field(
        default=None,
        description="Optional feedback explaining why the draft was rejected",
        max_length=1000,
    )


class ApprovalActionResponse(BaseModel):
    """Response returned upon approving or regenerating a post."""

    status: str = Field(..., description="Action outcome: approved, regenerated, expired, etc.")
    post_id: str = Field(..., description="Target business post identifier")
    revision: int = Field(..., description="Active or new revision number")
    message: Optional[str] = Field(default=None, description="Descriptive status message")
    approval_url: Optional[str] = Field(
        default=None,
        description="New approval URL if post was regenerated",
    )


class CreateApprovalResponse(BaseModel):
    """Response returned when an approval request is generated."""

    post_id: str = Field(..., description="Target post ID")
    revision_number: int = Field(..., description="Target revision number")
    approval_token: str = Field(..., description="Cryptographically secure approval token")
    approval_url: str = Field(..., description="Absolute or relative web approval URL")
    expires_at: Optional[str] = Field(default=None, description="ISO timestamp of token expiration")


class ApprovalPageResponse(BaseModel):
    """Structured representation of content rendered on the approval page."""

    post_id: str
    revision_number: int
    content_type: str
    topic: str
    angle: str
    target_audience: str
    hook: str
    caption: str
    hashtags: List[str] = Field(default_factory=list)
    call_to_action: str
    visual_concept: str
    image_url: Optional[str] = None
    image_brief: Optional[Dict[str, Any]] = None
    status: str
    expires_at: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standardized error response payload."""

    status: str = Field(default="error")
    message: str = Field(..., description="Safe, client-facing error description")
