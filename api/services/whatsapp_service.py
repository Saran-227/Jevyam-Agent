"""WhatsApp approval notification service orchestrating dispatches and webhook callback execution."""

import logging
from typing import Any, Dict, Optional, Set

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalSupersededError,
    PostNotFoundError,
)
from api.services.approval_service import ApprovalService
from config.settings import settings
from database.models import ApprovalStatus, PostStatus
from integrations.whatsapp.base import BaseWhatsAppProvider
from integrations.whatsapp.models import (
    WhatsAppApprovalMessagePayload,
    WhatsAppMessageResponse,
)
from integrations.whatsapp.provider import get_whatsapp_provider

logger = logging.getLogger(__name__)


class WhatsAppService:
    """Orchestrates WhatsApp notifications and incoming interactive button webhook events."""

    def __init__(
        self,
        approval_service: Optional[ApprovalService] = None,
        provider: Optional[BaseWhatsAppProvider] = None,
    ):
        self.approval_service = approval_service or ApprovalService()
        self.provider = provider or get_whatsapp_provider()
        self._processed_message_ids: Set[str] = set()

    def send_post_approval_notification(
        self,
        post_id: str,
        recipient_phone: Optional[str] = None,
    ) -> WhatsAppMessageResponse:
        """Construct and send an interactive approval notification to founder via WhatsApp."""
        post = self.approval_service.repos.posts.get_by_post_id(post_id)
        if not post:
            raise PostNotFoundError(f"Post '{post_id}' does not exist.")

        # Find or create active approval request for this post's current revision
        existing_approvals = self.approval_service.repos.approvals.get_by_post_id(post_id)
        active_approval = next(
            (
                a for a in existing_approvals
                if a.revision_number == post.current_revision and a.status == ApprovalStatus.PENDING
            ),
            None,
        )

        if not active_approval:
            approval_res = self.approval_service.create_approval_request(
                post_id=post_id,
                revision_number=post.current_revision,
            )
            approval_token = approval_res.approval_token
            approval_url = approval_res.approval_url
            expires_at = approval_res.expires_at
        else:
            base_url = settings.APP_BASE_URL.rstrip("/")
            approval_token = active_approval.approval_token
            approval_url = f"{base_url}/approve/{approval_token}"
            expires_at = str(active_approval.expires_at) if active_approval.expires_at else None

        # Build payload
        payload = WhatsAppApprovalMessagePayload(
            post_id=post.post_id,
            revision_number=post.current_revision,
            hook=post.hook,
            caption=post.caption,
            hashtags=post.hashtags,
            approval_token=approval_token,
            approval_url=approval_url,
            image_url=post.image_url,
            expires_at=expires_at,
            recipient_phone=recipient_phone or settings.WHATSAPP_FOUNDER_PHONE,
        )

        return self.provider.send_approval_message(payload, recipient_phone=recipient_phone)

    def handle_webhook_callback(
        self,
        payload_dict: Dict[str, Any],
        raw_body: bytes,
        signature_header: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process incoming WhatsApp webhook payload securely and idempotently."""
        # 1. Verify webhook signature
        if not self.provider.verify_webhook_signature(raw_body, signature_header):
            return {
                "status": "error",
                "code": "AUTH_FAILED",
                "message": "Webhook signature verification failed.",
            }

        # 2. Parse event
        event = self.provider.parse_webhook_event(payload_dict)
        if not event:
            return {
                "status": "ignored",
                "message": "Payload contained no actionable event or messages.",
            }

        if event.event_type == "status_update":
            return {
                "status": "acknowledged",
                "type": "status_update",
                "message_id": event.message_id,
            }

        # 3. Check duplicate callback message ID
        if event.message_id and event.message_id in self._processed_message_ids:
            return {
                "status": "ignored",
                "code": "DUPLICATE_CALLBACK",
                "message": f"Message ID '{event.message_id}' already processed.",
            }

        # 4. Extract action and token
        action: Optional[str] = None
        token: Optional[str] = None

        if event.button_payload:
            payload_str = event.button_payload.strip()
            if ":" in payload_str:
                parts = payload_str.split(":", 1)
                action = parts[0].lower().strip()
                token = parts[1].strip()
            else:
                action = payload_str.lower().strip()
        elif event.text_body:
            body_upper = event.text_body.strip().upper()
            if body_upper in ("YES", "APPROVE", "APPROVED"):
                action = "approve"
            elif body_upper in ("NO", "REGENERATE", "REJECT"):
                action = "regenerate"

        if not action or not token:
            return {
                "status": "error",
                "code": "INVALID_CALLBACK",
                "message": "Missing actionable command or approval token in callback.",
            }

        target_phone = event.sender_phone or settings.WHATSAPP_FOUNDER_PHONE

        # 5. Route to authoritative ApprovalService
        if action in ("approve", "yes"):
            try:
                result = self.approval_service.approve_post(token)
                if event.message_id:
                    self._processed_message_ids.add(event.message_id)

                # Send confirmation text back to founder
                if target_phone:
                    self.provider.send_text_message(
                        recipient_phone=target_phone,
                        text=f"✅ *Approved!* Post `{result.post_id}` (Rev #{result.revision}) is approved.",
                    )

                return {
                    "status": "approved",
                    "post_id": result.post_id,
                    "revision": result.revision,
                    "message": "Post approved successfully via WhatsApp.",
                }
            except ApprovalAlreadyProcessedError as e:
                return {
                    "status": "ignored",
                    "code": "ALREADY_PROCESSED",
                    "message": str(e),
                }
            except ApprovalExpiredError as e:
                return {
                    "status": "expired",
                    "code": "APPROVAL_EXPIRED",
                    "message": str(e),
                }
            except ApprovalNotFoundError as e:
                return {
                    "status": "error",
                    "code": "TOKEN_NOT_FOUND",
                    "message": str(e),
                }
            except ApprovalSupersededError as e:
                return {
                    "status": "ignored",
                    "code": "APPROVAL_SUPERSEDED",
                    "message": str(e),
                }
            except Exception as e:
                return {
                    "status": "error",
                    "code": "PROCESSING_ERROR",
                    "message": f"Failed to approve post: {str(e)}",
                }

        elif action in ("regenerate", "no"):
            try:
                result = self.approval_service.reject_and_regenerate(
                    token=token,
                    reason="Founder requested revision via WhatsApp button",
                )
                if event.message_id:
                    self._processed_message_ids.add(event.message_id)

                # Dispatch the new approval message to founder for the newly generated revision!
                if target_phone:
                    self.send_post_approval_notification(
                        post_id=result.post_id,
                        recipient_phone=target_phone,
                    )

                return {
                    "status": "regenerated",
                    "post_id": result.post_id,
                    "revision": result.revision,
                    "approval_url": result.approval_url,
                    "message": "Post regenerated and new approval request dispatched via WhatsApp.",
                }
            except ApprovalAlreadyProcessedError as e:
                return {
                    "status": "ignored",
                    "code": "ALREADY_PROCESSED",
                    "message": str(e),
                }
            except ApprovalExpiredError as e:
                return {
                    "status": "expired",
                    "code": "APPROVAL_EXPIRED",
                    "message": str(e),
                }
            except ApprovalNotFoundError as e:
                return {
                    "status": "error",
                    "code": "TOKEN_NOT_FOUND",
                    "message": str(e),
                }
            except ApprovalSupersededError as e:
                return {
                    "status": "ignored",
                    "code": "APPROVAL_SUPERSEDED",
                    "message": str(e),
                }
            except Exception as e:
                return {
                    "status": "error",
                    "code": "PROCESSING_ERROR",
                    "message": f"Failed to regenerate post: {str(e)}",
                }

        return {
            "status": "error",
            "code": "UNKNOWN_ACTION",
            "message": f"Unrecognized action '{action}'.",
        }
