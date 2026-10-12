"""Mock Telegram provider for testing and offline local development."""

from typing import Any, Dict, List, Optional, Tuple
from config.settings import settings
from integrations.telegram.base import BaseTelegramProvider
from integrations.telegram.client import TelegramApiProvider
from integrations.telegram.models import (
    TelegramApprovalMessagePayload,
    TelegramMessageResponse,
    TelegramWebhookEvent,
)


class MockTelegramProvider(BaseTelegramProvider):
    """In-memory mock Telegram provider recording dispatched notifications without network traffic."""

    def __init__(
        self,
        founder_chat_id: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        should_fail: bool = False,
        failure_error: str = "Mock simulated Telegram dispatch failure",
    ):
        self.founder_chat_id = str(founder_chat_id if founder_chat_id is not None else (settings.TELEGRAM_FOUNDER_CHAT_ID or "123456789")).strip()
        self.webhook_secret = (webhook_secret or "").strip()

        self.should_fail = should_fail
        self.failure_error = failure_error
        self.sent_messages: List[Dict[str, Any]] = []
        self.answered_callbacks: List[Dict[str, Any]] = []
        self._msg_counter = 1000

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Mock provider is always considered valid."""
        return True, []

    def verify_webhook_secret(self, secret_token_header: Optional[str]) -> bool:
        """Verify webhook secret against configured mock secret."""
        if not self.webhook_secret:
            return True
        if not secret_token_header:
            return False
        return secret_token_header.strip() == self.webhook_secret

    def send_text_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = "HTML",
    ) -> TelegramMessageResponse:
        """Record mock text message dispatch."""
        target_chat = str(chat_id or self.founder_chat_id).strip()
        if self.should_fail:
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="mock",
                error=self.failure_error,
            )

        self._msg_counter += 1
        msg_id = f"mock_tg_msg_{self._msg_counter}"
        record = {
            "id": msg_id,
            "type": "text",
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
        }
        self.sent_messages.append(record)
        return TelegramMessageResponse(
            success=True,
            message_id=msg_id,
            chat_id=target_chat,
            provider="mock",
            raw_response=record,
        )

    def send_approval_message(
        self,
        payload: TelegramApprovalMessagePayload,
        chat_id: Optional[str] = None,
    ) -> TelegramMessageResponse:
        """Record mock interactive approval dispatch with inline buttons."""
        target_chat = str(chat_id or payload.chat_id or self.founder_chat_id).strip()
        if self.should_fail:
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="mock",
                error=self.failure_error,
            )

        self._msg_counter += 1
        msg_id = f"mock_tg_msg_{self._msg_counter}"

        # Standard inline buttons
        buttons = [
            {
                "text": "✅ YES, PUBLISH",
                "callback_data": f"approve:{payload.approval_token}",
            },
            {
                "text": "❌ NO, REGENERATE",
                "callback_data": f"reject:{payload.approval_token}",
            },
        ]

        text = TelegramApiProvider.format_approval_text(None, payload)  # type: ignore
        is_linked = bool(payload.image_url and len(text) > 1024)
        media_type = "linked_photo" if is_linked else ("photo" if payload.image_url else "text")

        record = {
            "id": msg_id,
            "type": "approval_interactive",
            "media_type": media_type,
            "chat_id": target_chat,
            "text": text,
            "buttons": buttons,
            "image_url": payload.image_url,
            "is_linked": is_linked,
            "payload": payload.model_dump(),
        }
        self.sent_messages.append(record)

        return TelegramMessageResponse(
            success=True,
            message_id=msg_id,
            chat_id=target_chat,
            provider="mock",
            raw_response=record,
        )

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Record mock callback query acknowledgement."""
        self.answered_callbacks.append({
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        })
        return True

    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any],
    ) -> Optional[TelegramWebhookEvent]:
        """Delegate event parsing to standard parser."""
        return TelegramApiProvider.parse_webhook_event(None, payload_dict)  # type: ignore
