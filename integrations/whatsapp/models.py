"""Pydantic data models for WhatsApp integration messages, payloads, and events."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WhatsAppMessageResponse(BaseModel):
    """Normalized response from a WhatsApp message send attempt."""

    success: bool = Field(..., description="Whether the message dispatch was successful")
    message_id: Optional[str] = Field(None, description="Unique WhatsApp message ID (e.g. wamid.HBgL...)")
    recipient_phone: str = Field(..., description="Destination recipient phone number")
    provider: str = Field(..., description="Name of provider fulfilling request (e.g. meta, mock)")
    error: Optional[str] = Field(None, description="Descriptive error message if dispatch failed")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Raw HTTP response payload")


class WhatsAppApprovalMessagePayload(BaseModel):
    """Structured data required to assemble an approval request notification."""

    post_id: str = Field(..., description="Unique post ID (e.g. JVY-20260929-001)")
    revision_number: int = Field(default=1, description="Post revision number")
    hook: str = Field(..., description="Opening hook of the LinkedIn post")
    caption: str = Field(..., description="Main post caption text")
    hashtags: List[str] = Field(default_factory=list, description="Associated hashtags")
    approval_token: str = Field(..., description="Cryptographically secure approval token")
    approval_url: str = Field(..., description="Browser approval URL fallback")
    image_url: Optional[str] = Field(None, description="Publicly accessible image URL if available")
    expires_at: Optional[str] = Field(None, description="ISO timestamp of approval expiry")
    recipient_phone: Optional[str] = Field(None, description="Optional override for recipient phone")


class WhatsAppWebhookEvent(BaseModel):
    """Normalized event extracted from incoming WhatsApp webhook callbacks."""

    event_type: str = Field(..., description="Category: 'button_click', 'text_message', 'status_update', or 'unknown'")
    sender_phone: Optional[str] = Field(None, description="Phone number of user sending message/click")
    message_id: Optional[str] = Field(None, description="Unique incoming message ID")
    timestamp: Optional[str] = Field(None, description="Event generation timestamp")
    button_payload: Optional[str] = Field(None, description="Payload ID returned by button click (e.g. approve:<token>)")
    button_title: Optional[str] = Field(None, description="User-visible button text selected")
    text_body: Optional[str] = Field(None, description="Body text if user replied with text")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Full raw incoming webhook payload")
