"""Abstract base provider interface for WhatsApp integrations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from integrations.whatsapp.models import (
    WhatsAppApprovalMessagePayload,
    WhatsAppMessageResponse,
    WhatsAppWebhookEvent,
)


class BaseWhatsAppProvider(ABC):
    """Abstract interface defining required operations for a WhatsApp notification provider."""

    @abstractmethod
    def send_text_message(
        self,
        recipient_phone: str,
        text: str,
    ) -> WhatsAppMessageResponse:
        """Send a plain text message to the specified recipient.

        Args:
            recipient_phone: Destination phone number with country code (e.g. +91XXXXXXXXXX).
            text: Message body text.

        Returns:
            WhatsAppMessageResponse with delivery status and message ID.
        """
        pass

    @abstractmethod
    def send_image_message(
        self,
        recipient_phone: str,
        image_url: str,
        caption: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        """Send an image attachment with an optional caption.

        Args:
            recipient_phone: Destination phone number.
            image_url: Publicly accessible URL of the image.
            caption: Optional caption accompanying the image.

        Returns:
            WhatsAppMessageResponse.
        """
        pass

    @abstractmethod
    def send_approval_message(
        self,
        payload: WhatsAppApprovalMessagePayload,
        recipient_phone: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        """Construct and dispatch a structured approval notification with interactive actions.

        Args:
            payload: Structured post data and approval tokens.
            recipient_phone: Target phone (defaults to configured founder phone).

        Returns:
            WhatsAppMessageResponse.
        """
        pass

    @abstractmethod
    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Validate whether provider has necessary credentials and configuration.

        Returns:
            (is_valid: bool, error_messages: List[str])
        """
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        """Cryptographically verify authenticity of incoming webhook requests.

        Args:
            payload_bytes: Raw HTTP request body bytes.
            signature_header: Signature header value (e.g. X-Hub-Signature-256).

        Returns:
            True if signature is valid or verification not configured, False if invalid.
        """
        pass

    @abstractmethod
    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any],
    ) -> Optional[WhatsAppWebhookEvent]:
        """Extract and normalize actionable events from incoming webhook payload.

        Args:
            payload_dict: Decoded JSON dictionary from webhook body.

        Returns:
            Normalized WhatsAppWebhookEvent, or None if payload contains no actionable event.
        """
        pass
