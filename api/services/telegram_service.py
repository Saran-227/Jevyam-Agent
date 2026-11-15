"""Telegram approval notification service orchestrating dispatches and webhook callback execution."""

import html
import logging
import threading
from typing import Any, Dict, Optional, Set

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExpiredError,
    ApprovalInProgressError,
    ApprovalNotFoundError,
    ApprovalSupersededError,
    PostNotEligibleForApprovalError,
    PostNotFoundError,
)
from agent.image_generator import is_valid_image_url
from api.services.approval_service import ApprovalService
from config.settings import settings
from database.models import ApprovalStatus, PostStatus
from integrations.telegram.base import BaseTelegramProvider
from integrations.telegram.models import (
    TelegramApprovalMessagePayload,
    TelegramMessageResponse,
)
from integrations.telegram.provider import get_telegram_provider

logger = logging.getLogger("jevyam.telegram_service")


class TelegramService:
    """Orchestrates Telegram notifications and incoming interactive button webhook events."""

    def __init__(
        self,
        approval_service: Optional[ApprovalService] = None,
        provider: Optional[BaseTelegramProvider] = None,
        founder_chat_id: Optional[str] = None,
    ):
        self.approval_service = approval_service or ApprovalService()
        self.provider = provider or get_telegram_provider()
        self._founder_chat_id = str(founder_chat_id).strip() if founder_chat_id is not None else None
        self._processed_callback_ids: Set[str] = set()
        self._in_flight_tokens: Set[str] = set()
        self._lock = threading.Lock()

    @property
    def founder_chat_id(self) -> str:
        """Resolve current configured founder Chat ID."""
        if self._founder_chat_id is not None:
            return self._founder_chat_id
        provider_id = getattr(self.provider, "founder_chat_id", None)
        return str(provider_id or settings.TELEGRAM_FOUNDER_CHAT_ID or "").strip()

    @founder_chat_id.setter
    def founder_chat_id(self, val: Optional[str]) -> None:
        self._founder_chat_id = str(val).strip() if val is not None else None

    def is_authorized_user(
        self,
        chat_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> bool:
        """Validate whether the incoming interaction originates strictly from the authorized founder.

        Both chat_id and sender_id are validated against the configured founder Chat ID.
        In Telegram direct chats with bots, chat.id and from.id both match the user's ID.
        If an unauthorized user in a group or someone who obtained an approval message attempts to click,
        the request is strictly rejected.
        """
        expected = self.founder_chat_id
        if not expected:
            return True  # If unconfigured in local dev/mock test without restrictions

        clean_chat = str(chat_id or "").strip()
        clean_sender = str(sender_id or "").strip()

        # When both chat_id and sender_id are present, both must match the authorized founder
        if clean_chat and clean_sender:
            return clean_chat == expected and clean_sender == expected
        if clean_sender:
            return clean_sender == expected
        if clean_chat:
            return clean_chat == expected
        return False

    def send_post_approval_notification(
        self,
        post_id: str,
        chat_id: Optional[str] = None,
    ) -> TelegramMessageResponse:
        """Construct and send an interactive approval notification to founder via Telegram."""
        post = self.approval_service.repos.posts.get_by_post_id(post_id)
        if not post:
            raise PostNotFoundError(f"Post '{post_id}' does not exist.")

        # Fail closed: reject text-only approval if companion image is required
        if getattr(settings, "REQUIRE_POST_IMAGE", True) and not is_valid_image_url(post.image_url):
            raise PostNotEligibleForApprovalError(
                f"Post '{post_id}' does not have a valid companion image URL (got '{post.image_url}'). "
                "Text-only Telegram approval is prohibited when REQUIRE_POST_IMAGE=True."
            )

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

        target_recipient = str(chat_id or self.founder_chat_id or settings.TELEGRAM_FOUNDER_CHAT_ID).strip()

        # Build payload
        payload = TelegramApprovalMessagePayload(
            post_id=post.post_id,
            revision_number=post.current_revision,
            hook=post.hook,
            caption=post.caption,
            hashtags=post.hashtags,
            visual_concept=post.visual_concept,
            approval_token=approval_token,
            approval_url=approval_url,
            image_url=post.image_url,
            expires_at=expires_at,
            chat_id=target_recipient,
        )

        return self.provider.send_approval_message(payload, chat_id=target_recipient)

    def handle_webhook_callback(
        self,
        payload_dict: Dict[str, Any],
        secret_token_header: Optional[str] = None,
        background_tasks: Optional[Any] = None,
        is_polling: bool = False,
    ) -> Dict[str, Any]:
        """Process incoming Telegram webhook payload securely and idempotently."""
        # 1. Verify webhook secret token (skipped for long-polling as client is authenticated directly via Bot Token)
        if not is_polling and not self.provider.verify_webhook_secret(secret_token_header):
            logger.warning("[WARN] Telegram webhook secret verification failed.")
            return {
                "status": "error",
                "code": "AUTH_FAILED",
                "message": "Webhook secret token verification failed.",
            }

        # 2. Parse event
        event = self.provider.parse_webhook_event(payload_dict)
        if not event:
            return {
                "status": "ignored",
                "message": "Payload contained no actionable event or messages.",
            }

        # Fast acknowledgement of Telegram callback query to stop loading spinner
        if event.callback_query_id:
            self.provider.answer_callback_query(
                callback_query_id=event.callback_query_id,
                text="Processing decision...",
            )

        # 3. Check duplicate callback query ID
        if event.callback_query_id and event.callback_query_id in self._processed_callback_ids:
            return {
                "status": "ignored",
                "code": "DUPLICATE_CALLBACK",
                "message": f"Callback ID '{event.callback_query_id}' already processed.",
            }

        # 3b. Handle Informational Commands (/start, /chatid, /id)
        if event.text_body:
            cmd = event.text_body.strip().lower()
            if cmd in ("/start", "/id", "/chatid", "start", "id", "chatid"):
                is_auth = self.is_authorized_user(chat_id=event.chat_id, sender_id=event.sender_id)
                status_badge = "Authorized Founder ✅" if is_auth else "Unregistered User ⚠️"
                info_msg = (
                    f"👋 <b>Jevyam Technologies AI Marketing Bot</b>\n\n"
                    f"🆔 <b>Chat ID:</b> <code>{event.chat_id}</code>\n"
                    f"👤 <b>Sender ID:</b> <code>{event.sender_id}</code>\n"
                    f"📋 <b>Status:</b> {status_badge}\n\n"
                )
                if is_auth:
                    info_msg += (
                        "You are configured as the authorized founder. You will receive daily post previews, "
                        "branded images, approval buttons, and publishing notifications here."
                    )
                else:
                    info_msg += (
                        "This chat is not registered as the authorized founder. "
                        "To authorize, update <code>TELEGRAM_FOUNDER_CHAT_ID</code> in the agent configuration."
                    )
                if event.chat_id:
                    self.provider.send_text_message(chat_id=event.chat_id, text=info_msg)
                return {
                    "status": "info",
                    "code": "COMMAND_HANDLED",
                    "chat_id": event.chat_id,
                    "sender_id": event.sender_id,
                    "is_authorized": is_auth,
                    "message": f"Handled {cmd} command.",
                }

        # 4. Extract action and token
        action: Optional[str] = None
        token: Optional[str] = None

        if event.callback_data:
            data_str = event.callback_data.strip()
            if ":" in data_str:
                parts = data_str.split(":", 1)
                action = parts[0].lower().strip()
                token = parts[1].strip()
            else:
                action = data_str.lower().strip()
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

        # 4b. Strict Founder Authorization Check
        if not self.is_authorized_user(chat_id=event.chat_id, sender_id=event.sender_id):
            logger.warning(
                f"[UNAUTHORIZED] Telegram callback rejected: chat_id='{event.chat_id}', "
                f"sender_id='{event.sender_id}'. Expected founder_chat_id='{self.founder_chat_id}'."
            )
            if event.chat_id:
                try:
                    self.provider.send_text_message(
                        chat_id=event.chat_id,
                        text="⛔ <b>Access Denied:</b> You are not authorized to approve or regenerate posts for Jevyam Technologies.",
                    )
                except Exception as notify_err:
                    logger.warning(f"Failed to send access-denied message to chat '{event.chat_id}': {notify_err}")

            return {
                "status": "unauthorized",
                "code": "UNAUTHORIZED_USER",
                "message": "Only the authorized founder may approve or reject posts.",
            }

        target_chat = self.founder_chat_id or event.chat_id or settings.TELEGRAM_FOUNDER_CHAT_ID

        # 5. Route to authoritative ApprovalService
        if action in ("approve", "yes"):
            try:
                result = self.approval_service.approve_post(token)
                if event.callback_query_id:
                    self._processed_callback_ids.add(event.callback_query_id)

                # Send confirmation text back to founder
                if target_chat:
                    if result.published and result.post_url:
                        pub_text = (
                            f" and published to LinkedIn Company Page!\n\n"
                            f"🔗 <b>LinkedIn URL:</b> {result.post_url}\n"
                            f"🆔 <b>Post URN:</b> <code>{result.external_post_id or 'N/A'}</code>"
                        )
                    elif result.published:
                        pub_text = (
                            f" and published to LinkedIn Company Page.\n\n"
                            f"🆔 <b>Post URN:</b> <code>{result.external_post_id or 'N/A'}</code>"
                        )
                    else:
                        pub_text = "."

                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"✅ <b>Approved!</b> Post <code>{result.post_id}</code> (Rev #{result.revision}) approved{pub_text}",
                    )

                return {
                    "status": "approved",
                    "post_id": result.post_id,
                    "revision": result.revision,
                    "published": result.published,
                    "message": "Post approved successfully via Telegram.",
                }
            except ApprovalAlreadyProcessedError as e:
                if target_chat:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"ℹ️ <b>Already Processed:</b> {html.escape(str(e))}",
                    )
                return {
                    "status": "ignored",
                    "code": "ALREADY_PROCESSED",
                    "message": str(e),
                }
            except ApprovalInProgressError as e:
                if target_chat:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"⏳ <b>In Progress:</b> {html.escape(str(e))}",
                    )
                return {
                    "status": "ignored",
                    "code": "IN_PROGRESS",
                    "message": str(e),
                }
            except ApprovalExpiredError as e:
                if target_chat:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"⚠️ <b>Approval Expired:</b> {html.escape(str(e))}",
                    )
                return {
                    "status": "expired",
                    "code": "APPROVAL_EXPIRED",
                    "message": str(e),
                }
            except ApprovalNotFoundError as e:
                if target_chat:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text="❌ <b>Approval Not Found:</b> The requested post or token was not found.",
                    )
                return {
                    "status": "error",
                    "code": "TOKEN_NOT_FOUND",
                    "message": str(e),
                }
            except ApprovalSupersededError as e:
                if target_chat:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"ℹ️ <b>Revision Superseded:</b> {html.escape(str(e))}",
                    )
                return {
                    "status": "ignored",
                    "code": "APPROVAL_SUPERSEDED",
                    "message": str(e),
                }
            except Exception as e:
                if target_chat:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"❌ <b>Approval Error:</b> Failed to approve post: {html.escape(str(e))}",
                    )
                return {
                    "status": "error",
                    "code": "PROCESSING_ERROR",
                    "message": f"Failed to approve post: {str(e)}",
                }

        elif action in ("regenerate", "reject", "no"):
            # Reliable idempotency: check in-flight tokens
            with self._lock:
                if token in self._in_flight_tokens:
                    logger.info(f"Callback query for token '{token}' ignored: already in flight.")
                    return {
                        "status": "ignored",
                        "code": "IN_PROGRESS",
                        "message": f"Regeneration already in progress for token '{token}'.",
                    }

            # Reliable idempotency: check database post status
            approval_record = self.approval_service.repos.approvals.get_by_token(token)
            if approval_record:
                post_record = self.approval_service.repos.posts.get_by_post_id(approval_record.post_id)
                if post_record and post_record.status == PostStatus.REGENERATING:
                    logger.info(f"Callback for post '{post_record.post_id}' ignored: already in REGENERATING state.")
                    return {
                        "status": "ignored",
                        "code": "IN_PROGRESS",
                        "message": f"Post '{post_record.post_id}' is currently being regenerated.",
                    }

            if background_tasks is not None:
                # Mark in-flight immediately to prevent concurrent deliveries
                with self._lock:
                    self._in_flight_tokens.add(token)

                background_tasks.add_task(
                    self._execute_rejection_task,
                    token=token,
                    target_chat=target_chat,
                    callback_query_id=event.callback_query_id,
                )

                post_id_val = approval_record.post_id if approval_record else None
                rev_val = approval_record.revision_number if approval_record else None

                return {
                    "status": "accepted",
                    "code": "REGENERATION_SCHEDULED",
                    "post_id": post_id_val,
                    "revision": rev_val,
                    "message": "Post rejection received. Generating new revision in background.",
                }
            else:
                return self._execute_rejection_task(
                    token=token,
                    target_chat=target_chat,
                    callback_query_id=event.callback_query_id,
                )

        return {
            "status": "error",
            "code": "UNKNOWN_ACTION",
            "message": f"Unrecognized action '{action}'.",
        }

    def _execute_rejection_task(
        self,
        token: str,
        target_chat: Optional[str] = None,
        callback_query_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute post rejection, AI regeneration, and new approval dispatch outside the async request loop."""
        with self._lock:
            self._in_flight_tokens.add(token)

        try:
            result = self.approval_service.reject_and_regenerate(
                token=token,
                reason="Founder requested revision via Telegram button",
            )
            if callback_query_id:
                self._processed_callback_ids.add(callback_query_id)

            # Dispatch the new approval message to founder for the newly generated revision!
            if target_chat:
                self.send_post_approval_notification(
                    post_id=result.post_id,
                    chat_id=target_chat,
                )

            return {
                "status": "regenerated",
                "post_id": result.post_id,
                "revision": result.revision,
                "approval_url": result.approval_url,
                "message": "Post regenerated and new approval request dispatched via Telegram.",
            }
        except ApprovalInProgressError as e:
            logger.info(f"Regeneration already in progress for token: {e}")
            if target_chat:
                self.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"⏳ <b>Regeneration in Progress:</b> {html.escape(str(e))}",
                )
            return {
                "status": "ignored",
                "code": "IN_PROGRESS",
                "message": str(e),
            }
        except ApprovalAlreadyProcessedError as e:
            if target_chat:
                self.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"ℹ️ <b>Already Processed:</b> {html.escape(str(e))}",
                )
            return {
                "status": "ignored",
                "code": "ALREADY_PROCESSED",
                "message": str(e),
            }
        except ApprovalExpiredError as e:
            if target_chat:
                self.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"⚠️ <b>Approval Expired:</b> {html.escape(str(e))}",
                )
            return {
                "status": "expired",
                "code": "APPROVAL_EXPIRED",
                "message": str(e),
            }
        except ApprovalNotFoundError as e:
            if target_chat:
                self.provider.send_text_message(
                    chat_id=target_chat,
                    text="❌ <b>Approval Not Found:</b> The requested post or token was not found.",
                )
            return {
                "status": "error",
                "code": "TOKEN_NOT_FOUND",
                "message": str(e),
            }
        except ApprovalSupersededError as e:
            if target_chat:
                self.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"ℹ️ <b>Revision Superseded:</b> {html.escape(str(e))}",
                )
            return {
                "status": "ignored",
                "code": "APPROVAL_SUPERSEDED",
                "message": str(e),
            }
        except Exception as e:
            logger.error(f"[ERROR] Failed to regenerate post via Telegram: {str(e)}", exc_info=True)
            # Notify founder on Telegram cleanly without leaking secrets or exception internals
            if target_chat:
                try:
                    self.provider.send_text_message(
                        chat_id=target_chat,
                        text=(
                            "⚠️ <b>Post Regeneration Delayed</b>\n\n"
                            "The AI service is temporarily unavailable or experiencing high demand.\n\n"
                            "Your draft remains pending review. Please tap <b>NO — REGENERATE</b> again in a few moments to retry."
                        ),
                    )
                except Exception as notify_err:
                    logger.warning(f"Failed to send failure notice to Telegram: {notify_err}")

            return {
                "status": "error",
                "code": "PROCESSING_ERROR",
                "message": f"Failed to regenerate post: {str(e)}",
            }
        finally:
            with self._lock:
                self._in_flight_tokens.discard(token)
