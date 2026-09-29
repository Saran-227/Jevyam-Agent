"""Official Meta WhatsApp Cloud API provider implementation."""

import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx

from integrations.whatsapp.base import BaseWhatsAppProvider
from integrations.whatsapp.models import (
    WhatsAppApprovalMessagePayload,
    WhatsAppMessageResponse,
    WhatsAppWebhookEvent,
)

logger = logging.getLogger(__name__)


class MetaWhatsAppCloudProvider(BaseWhatsAppProvider):
    """Direct integration with Meta's WhatsApp Cloud API (Graph API)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        business_account_id: Optional[str] = None,
        founder_phone: Optional[str] = None,
        app_secret: Optional[str] = None,
        api_version: str = "v21.0",
        http_client: Optional[httpx.Client] = None,
    ):
        self.access_token = (access_token or "").strip()
        self.phone_number_id = (phone_number_id or "").strip()
        self.business_account_id = (business_account_id or "").strip()
        self.founder_phone = (founder_phone or "").strip()
        self.app_secret = (app_secret or "").strip()
        self.api_version = api_version
        self._client = http_client

    @property
    def messages_endpoint(self) -> str:
        """Fully-qualified Graph API endpoint for sending WhatsApp messages."""
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _execute_post(self, payload: Dict[str, Any], recipient: str) -> WhatsAppMessageResponse:
        """Execute HTTP POST dispatch to Meta Graph API safely."""
        client = self._client or httpx.Client(timeout=15.0)
        try:
            response = client.post(
                self.messages_endpoint,
                json=payload,
                headers=self._get_headers(),
            )
            data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                messages = data.get("messages", [])
                msg_id = messages[0].get("id") if messages else None
                return WhatsAppMessageResponse(
                    success=True,
                    message_id=msg_id,
                    recipient_phone=recipient,
                    provider="meta",
                    raw_response=data,
                )
            else:
                # Extract error without leaking access tokens
                err_dict = data.get("error", {})
                err_msg = err_dict.get("message") or f"Meta API HTTP {response.status_code}"
                err_code = err_dict.get("code")
                return WhatsAppMessageResponse(
                    success=False,
                    recipient_phone=recipient,
                    provider="meta",
                    error=f"Error {err_code}: {err_msg}" if err_code else err_msg,
                    raw_response=data,
                )
        except Exception as e:
            return WhatsAppMessageResponse(
                success=False,
                recipient_phone=recipient,
                provider="meta",
                error=f"Network or request error dispatching message: {str(e)}",
            )
        finally:
            if not self._client:
                client.close()

    def send_text_message(
        self,
        recipient_phone: str,
        text: str,
    ) -> WhatsAppMessageResponse:
        target = recipient_phone or self.founder_phone
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target,
            "type": "text",
            "text": {
                "preview_url": True,
                "body": text,
            },
        }
        return self._execute_post(payload, target)

    def send_image_message(
        self,
        recipient_phone: str,
        image_url: str,
        caption: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        target = recipient_phone or self.founder_phone
        image_obj: Dict[str, Any] = {"link": image_url}
        if caption:
            image_obj["caption"] = caption[:1024]

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target,
            "type": "image",
            "image": image_obj,
        }
        return self._execute_post(payload, target)

    def send_approval_message(
        self,
        payload: WhatsAppApprovalMessagePayload,
        recipient_phone: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        target = recipient_phone or payload.recipient_phone or self.founder_phone

        # Assemble formatted body text
        hashtags_str = " ".join(payload.hashtags) if payload.hashtags else ""
        expiry_info = f"\n⏳ Expires: {payload.expires_at}" if payload.expires_at else ""

        # Limit body text cleanly to under Meta's 1024-character button body limit
        body_text = (
            f"🚀 *Jevyam Technologies — New Post Approval*\n\n"
            f"📌 *Post ID:* {payload.post_id} (Rev #{payload.revision_number}){expiry_info}\n\n"
            f"🎣 *Hook:*\n\"{payload.hook}\"\n\n"
            f"📝 *Caption:*\n{payload.caption}\n\n"
            f"🏷️ {hashtags_str}\n\n"
            f"Tap an action below to approve or regenerate:"
        )

        if len(body_text) > 1020:
            allowed_caption_len = 1020 - (len(body_text) - len(payload.caption)) - 20
            short_caption = payload.caption[:max(100, allowed_caption_len)] + "..."
            body_text = (
                f"🚀 *Jevyam Technologies — New Post Approval*\n\n"
                f"📌 *Post ID:* {payload.post_id} (Rev #{payload.revision_number}){expiry_info}\n\n"
                f"🎣 *Hook:*\n\"{payload.hook}\"\n\n"
                f"📝 *Caption:*\n{short_caption}\n\n"
                f"🏷️ {hashtags_str}\n\n"
                f"Tap an action below to approve or regenerate:"
            )

        interactive_dict: Dict[str, Any] = {
            "type": "button",
            "body": {"text": body_text},
            "footer": {"text": "Jevyam AI Marketing Agent"},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"approve:{payload.approval_token}",
                            "title": "APPROVE / YES",
                        },
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": f"regenerate:{payload.approval_token}",
                            "title": "REGENERATE / NO",
                        },
                    },
                ]
            },
        }

        # Add image header if valid public HTTP(S) image URL is present
        if payload.image_url and (payload.image_url.startswith("http://") or payload.image_url.startswith("https://")):
            interactive_dict["header"] = {
                "type": "image",
                "image": {"link": payload.image_url},
            }
        else:
            interactive_dict["header"] = {
                "type": "text",
                "text": "Post Ready for Approval",
            }

        request_payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target,
            "type": "interactive",
            "interactive": interactive_dict,
        }

        return self._execute_post(request_payload, target)

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not self.access_token:
            errors.append("WHATSAPP_ACCESS_TOKEN is missing or empty.")
        elif self.access_token.startswith("your_"):
            errors.append("WHATSAPP_ACCESS_TOKEN contains a placeholder value.")

        if not self.phone_number_id:
            errors.append("WHATSAPP_PHONE_NUMBER_ID is missing or empty.")
        elif self.phone_number_id.startswith("your_"):
            errors.append("WHATSAPP_PHONE_NUMBER_ID contains a placeholder value.")

        if not self.founder_phone:
            errors.append("WHATSAPP_FOUNDER_PHONE is missing or empty.")
        elif self.founder_phone.startswith("your_"):
            errors.append("WHATSAPP_FOUNDER_PHONE contains a placeholder value.")

        return len(errors) == 0, errors

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        if not self.app_secret:
            # If no app secret configured in dev mode, allow pass-through
            return True

        if not signature_header:
            return False

        # Header format: sha256=<hex_digest>
        prefix = "sha256="
        if not signature_header.startswith(prefix):
            return False

        expected_sig = signature_header[len(prefix):]
        computed_sig = hmac.new(
            self.app_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_sig, computed_sig)

    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any],
    ) -> Optional[WhatsAppWebhookEvent]:
        try:
            entries = payload_dict.get("entry", [])
            if not entries:
                return None

            changes = entries[0].get("changes", [])
            if not changes:
                return None

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

                if msg_type == "button":
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

                if msg_type == "text":
                    txt = msg.get("text", {}).get("body")
                    return WhatsAppWebhookEvent(
                        event_type="text_message",
                        sender_phone=sender,
                        message_id=msg_id,
                        timestamp=ts,
                        text_body=txt,
                        raw_data=payload_dict,
                    )

            # Check status updates
            statuses = value.get("statuses", [])
            if statuses:
                st = statuses[0]
                return WhatsAppWebhookEvent(
                    event_type="status_update",
                    sender_phone=st.get("recipient_id"),
                    message_id=st.get("id"),
                    timestamp=st.get("timestamp"),
                    raw_data=payload_dict,
                )

        except Exception as e:
            logger.debug(f"Failed to parse WhatsApp webhook: {e}")
            return None

        return None
