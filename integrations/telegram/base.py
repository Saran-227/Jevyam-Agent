"""Abstract base provider interface for Telegram Bot API integrations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from integrations.telegram.models import (
    TelegramApprovalMessagePayload,
    TelegramMessageResponse,
    TelegramWebhookEvent,
)


class BaseTelegramProvider(ABC):
    """Abstract interface defining required operations for a Telegram bot provider."""

    @abstractmethod
    def send_text_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = "HTML",
    ) -> TelegramMessageResponse:
        """Send a formatted text message to the specified Telegram chat.

        Args:
            chat_id: Destination Telegram chat ID.
            text: Message body text (formatted according to parse_mode).
            parse_mode: Formatting mode ('HTML', 'MarkdownV2', or None).

        Returns:
            TelegramMessageResponse with delivery status and message ID.
        """
        pass

    @abstractmethod
    def send_approval_message(
        self,
        payload: TelegramApprovalMessagePayload,
        chat_id: Optional[str] = None,
    ) -> TelegramMessageResponse:
        """Construct and dispatch a structured approval notification with inline YES/NO buttons.

        Args:
            payload: Structured post data and approval tokens.
            chat_id: Target chat ID (defaults to configured founder chat ID).

        Returns:
            TelegramMessageResponse with delivery status and message ID.
        """
        pass

    @abstractmethod
    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge an incoming inline keyboard callback query.

        Args:
            callback_query_id: Unique identifier for the query to be answered.
            text: Optional notification text displayed to the user.
            show_alert: If true, an alert will be shown to the user instead of a notification.

        Returns:
            True if acknowledgement succeeded, False otherwise.
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
    def verify_webhook_secret(
        self,
        secret_token_header: Optional[str],
    ) -> bool:
        """Verify authenticity of incoming Telegram webhook requests via secret token.

        Args:
            secret_token_header: Value of X-Telegram-Bot-Api-Secret-Token HTTP header.

        Returns:
            True if header matches configured secret or secret is unconfigured, False if mismatch.
        """
        pass

    @abstractmethod
    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any],
    ) -> Optional[TelegramWebhookEvent]:
        """Extract and normalize actionable events from incoming Telegram webhook update.

        Args:
            payload_dict: Decoded JSON dictionary from webhook body.

        Returns:
            Normalized TelegramWebhookEvent, or None if payload contains no actionable event.
        """
        pass
