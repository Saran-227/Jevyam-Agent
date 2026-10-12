"""Pydantic data models for Telegram integration messages, payloads, and events."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TelegramMessageResponse(BaseModel):
    """Normalized response from a Telegram message send attempt."""

    success: bool = Field(..., description="Whether the message dispatch was successful")
    message_id: Optional[str] = Field(None, description="Unique Telegram message ID")
    chat_id: Optional[str] = Field(None, description="Destination Telegram chat ID")
    provider: str = Field(default="telegram", description="Name of provider fulfilling request (e.g. telegram, mock)")
    error: Optional[str] = Field(None, description="Descriptive error message if dispatch failed")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Raw API response dictionary")


class TelegramApprovalMessagePayload(BaseModel):
    """Structured data required to assemble an approval request notification on Telegram."""

    post_id: str = Field(..., description="Unique post ID (e.g. JVY-20261006-001)")
    revision_number: int = Field(default=1, description="Post revision number")
    hook: str = Field(..., description="Opening hook of the LinkedIn post")
    caption: str = Field(..., description="Main post caption text")
    hashtags: List[str] = Field(default_factory=list, description="Associated hashtags")
    visual_concept: Optional[str] = Field(None, description="Visual concept or image direction")
    approval_token: str = Field(..., description="Cryptographically secure approval token")
    approval_url: str = Field(..., description="Browser approval URL fallback")
    image_url: Optional[str] = Field(None, description="Publicly accessible image URL if available")
    expires_at: Optional[str] = Field(None, description="ISO timestamp of approval expiry")
    chat_id: Optional[str] = Field(None, description="Optional override for recipient chat ID")


class TelegramWebhookEvent(BaseModel):
    """Normalized event extracted from incoming Telegram webhook updates."""

    event_type: str = Field(..., description="Category: 'callback_query', 'message', or 'unknown'")
    callback_query_id: Optional[str] = Field(None, description="ID of the callback query for acknowledging")
    chat_id: Optional[str] = Field(None, description="Chat ID where the update originated")
    sender_id: Optional[str] = Field(None, description="User ID of the sender / button clicker")
    message_id: Optional[str] = Field(None, description="Message ID associated with the interaction")
    callback_data: Optional[str] = Field(None, description="Payload data returned by inline button click (e.g. approve:<token>)")
    button_title: Optional[str] = Field(None, description="Button title clicked if available")
    text_body: Optional[str] = Field(None, description="Body text if user replied with plain text")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Full raw incoming webhook payload dictionary")
