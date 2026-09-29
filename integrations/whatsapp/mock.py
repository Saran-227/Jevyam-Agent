"""Mock WhatsApp provider implementation for automated tests and offline development."""

from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional, Tuple

from integrations.whatsapp.base import BaseWhatsAppProvider
from integrations.whatsapp.models import (
    WhatsAppApprovalMessagePayload,
    WhatsAppMessageResponse,
    WhatsAppWebhookEvent,
)


class MockWhatsAppProvider(BaseWhatsAppProvider):
    """In-memory mock WhatsApp provider that records sent messages without network calls."""

    def __init__(
        self,
        founder_phone: str = "+919876543210",
        should_fail: bool = False,
        failure_error: str = "Mock simulated dispatch failure",
    ):
        self.founder_phone = founder_phone
        self.should_fail = should_fail
        self.failure_error = failure_error
        self.sent_messages: List[Dict[str, Any]] = []

    def clear(self) -> None:
        """Clear recorded message history."""
        self.sent_messages.clear()

    def send_text_message(
        self,
        recipient_phone: str,
        text: str,
    ) -> WhatsAppMessageResponse:
        target = recipient_phone or self.founder_phone
        if self.should_fail:
            return WhatsAppMessageResponse(
                success=False,
                recipient_phone=target,
                provider="mock",
                error=self.failure_error,
            )

        msg_id = f"mock_wamid_{uuid.uuid4().hex[:12]}"
        record = {
            "type": "text",
            "message_id": msg_id,
            "to": target,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        }
        self.sent_messages.append(record)
        return WhatsAppMessageResponse(
            success=True,
            message_id=msg_id,
            recipient_phone=target,
            provider="mock",
            raw_response=record,
        )

    def send_image_message(
        self,
        recipient_phone: str,
        image_url: str,
        caption: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        target = recipient_phone or self.founder_phone
        if self.should_fail:
            return WhatsAppMessageResponse(
                success=False,
                recipient_phone=target,
                provider="mock",
                error=self.failure_error,
            )

        msg_id = f"mock_wamid_{uuid.uuid4().hex[:12]}"
        record = {
            "type": "image",
            "message_id": msg_id,
            "to": target,
            "image_url": image_url,
            "caption": caption,
            "timestamp": datetime.now().isoformat(),
        }
        self.sent_messages.append(record)
        return WhatsAppMessageResponse(
            success=True,
            message_id=msg_id,
            recipient_phone=target,
            provider="mock",
            raw_response=record,
        )

    def send_approval_message(
        self,
        payload: WhatsAppApprovalMessagePayload,
        recipient_phone: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        target = recipient_phone or payload.recipient_phone or self.founder_phone
        if self.should_fail:
            return WhatsAppMessageResponse(
                success=False,
                recipient_phone=target,
                provider="mock",
                error=self.failure_error,
            )

        msg_id = f"mock_wamid_{uuid.uuid4().hex[:12]}"
        record = {
            "type": "approval_interactive",
            "message_id": msg_id,
            "to": target,
            "payload": payload.model_dump(),
            "actions": [
                {"id": f"approve:{payload.approval_token}", "title": "APPROVE / YES"},
                {"id": f"regenerate:{payload.approval_token}", "title": "REGENERATE / NO"},
            ],
            "timestamp": datetime.now().isoformat(),
        }
        self.sent_messages.append(record)
        return WhatsAppMessageResponse(
            success=True,
            message_id=msg_id,
            recipient_phone=target,
            provider="mock",
            raw_response=record,
        )

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not self.founder_phone:
            errors.append("Founder phone is missing.")
        return len(errors) == 0, errors

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        # In mock provider, if signature is "invalid", reject; otherwise accept
        if signature_header == "invalid":
            return False
        return True

    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any],
    ) -> Optional[WhatsAppWebhookEvent]:
        # Handle Meta standard format or flat test format
        try:
            entries = payload_dict.get("entry", [])
            if entries:
                changes = entries[0].get("changes", [])
                if changes:
                    value = changes[0].get("value", {})
                    messages = value.get("messages", [])
                    if messages:
                        msg = messages[0]
                        sender = msg.get("from")
                        msg_id = msg.get("id")
                        ts = msg.get("timestamp")
                        msg_type = msg.get("type")

                        if msg_type == "interactive":
                            interactive = msg.get("interactive", {})
                            btn_reply = interactive.get("button_reply", {})
                            return WhatsAppWebhookEvent(
                                event_type="button_click",
                                sender_phone=sender,
                                message_id=msg_id,
                                timestamp=ts,
                                button_payload=btn_reply.get("id"),
                                button_title=btn_reply.get("title"),
                                raw_data=payload_dict,
                            )
                        elif msg_type == "button":
                            btn = msg.get("button", {})
                            return WhatsAppWebhookEvent(
                                event_type="button_click",
                                sender_phone=sender,
                                message_id=msg_id,
                                timestamp=ts,
                                button_payload=btn.get("payload"),
                                button_title=btn.get("text"),
                                raw_data=payload_dict,
                            )
                        elif msg_type == "text":
                            txt = msg.get("text", {}).get("body")
                            return WhatsAppWebhookEvent(
                                event_type="text_message",
                                sender_phone=sender,
                                message_id=msg_id,
                                timestamp=ts,
                                text_body=txt,
                                raw_data=payload_dict,
                            )

            # Flat test payload format fallback
            if "button_payload" in payload_dict:
                return WhatsAppWebhookEvent(
                    event_type="button_click",
                    sender_phone=payload_dict.get("sender_phone"),
                    message_id=payload_dict.get("message_id", f"mock_wamid_{uuid.uuid4().hex[:8]}"),
                    button_payload=payload_dict.get("button_payload"),
                    button_title=payload_dict.get("button_title", "Action"),
                    raw_data=payload_dict,
                )
        except Exception:
            return None

        return None
