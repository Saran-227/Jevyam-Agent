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
        admin_chat_id: Optional[str] = None,
    ):
        self.approval_service = approval_service or ApprovalService()
        self.provider = provider or get_telegram_provider()
        self._founder_chat_id = str(founder_chat_id).strip() if founder_chat_id is not None else None
        self._admin_chat_id = str(admin_chat_id).strip() if admin_chat_id is not None else None
        self._processed_callback_ids: Set[str] = set()
        self._in_flight_tokens: Set[str] = set()
        self._lock = threading.Lock()

    @property
    def founder_chat_id(self) -> str:
        """Resolve current configured founder Chat ID."""
        if self._founder_chat_id is not None:
            return self._founder_chat_id
        if hasattr(self.provider, "founder_chat_id"):
            provider_id = getattr(self.provider, "founder_chat_id")
            if provider_id is not None:
                return str(provider_id).strip()
        return str(settings.TELEGRAM_FOUNDER_CHAT_ID or "").strip()

    @founder_chat_id.setter
    def founder_chat_id(self, val: Optional[str]) -> None:
        self._founder_chat_id = str(val).strip() if val is not None else None

    @property
    def admin_chat_id(self) -> str:
        """Resolve current configured admin Chat ID."""
        if self._admin_chat_id is not None:
            return self._admin_chat_id
        if hasattr(self.provider, "admin_chat_id"):
            provider_id = getattr(self.provider, "admin_chat_id")
            if provider_id is not None:
                return str(provider_id).strip()
        return str(settings.TELEGRAM_ADMIN_CHAT_ID or "").strip()

    @admin_chat_id.setter
    def admin_chat_id(self, val: Optional[str]) -> None:
        self._admin_chat_id = str(val).strip() if val is not None else None

    def is_authorized_founder(
        self,
        chat_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> bool:
        """Validate whether the incoming interaction originates strictly from the authorized founder.

        Both chat_id and sender_id are validated against the configured founder Chat ID (8164283098).
        """
        expected = self.founder_chat_id
        if not expected:
            return True

        clean_chat = str(chat_id or "").strip()
        clean_sender = str(sender_id or "").strip()

        if clean_chat and clean_sender:
            return clean_chat == expected and clean_sender == expected
        if clean_sender:
            return clean_sender == expected
        if clean_chat:
            return clean_chat == expected
        return False

    def is_authorized_admin(
        self,
        chat_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> bool:
        """Validate whether the incoming interaction originates strictly from the authorized admin (1293148688)."""
        expected = self.admin_chat_id
        if not expected:
            return False

        clean_chat = str(chat_id or "").strip()
        clean_sender = str(sender_id or "").strip()

        if clean_chat and clean_sender:
            return clean_chat == expected and clean_sender == expected
        if clean_sender:
            return clean_sender == expected
        if clean_chat:
            return clean_chat == expected
        return False

    def is_authorized_user(
        self,
        chat_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> bool:
        """Validate whether the incoming interaction originates from an authorized user (Founder or Admin)."""
        return self.is_authorized_founder(chat_id=chat_id, sender_id=sender_id) or self.is_authorized_admin(chat_id=chat_id, sender_id=sender_id)

    def send_post_approval_notification(
        self,
        post_id: str,
        chat_id: Optional[str] = None,
        notify_admin: bool = True,
    ) -> TelegramMessageResponse:
        """Construct and send an interactive approval notification to founder, and an informational preview copy to admin."""
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

        # Build payload for founder (interactive card with buttons)
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

        founder_res = self.provider.send_approval_message(payload, chat_id=target_recipient)

        # Dispatch read-only post preview copy to Admin (NO approval buttons)
        if notify_admin and self.admin_chat_id:
            try:
                self.send_admin_post_preview(post_id=post_id)
            except Exception as admin_err:
                logger.warning(f"Failed to dispatch post preview copy to admin: {admin_err}")

        return founder_res

    def send_admin_post_preview(
        self,
        post_id: str,
        chat_id: Optional[str] = None,
    ) -> Optional[TelegramMessageResponse]:
        """Deliver a read-only post preview with companion visual and caption to Admin (NO approval buttons)."""
        target_chat = str(chat_id or self.admin_chat_id).strip()
        if not target_chat:
            return None

        post = self.approval_service.repos.posts.get_by_post_id(post_id)
        if not post:
            raise PostNotFoundError(f"Post '{post_id}' does not exist.")

        payload = TelegramApprovalMessagePayload(
            post_id=post.post_id,
            revision_number=post.current_revision,
            hook=post.hook,
            caption=post.caption,
            hashtags=post.hashtags,
            visual_concept=post.visual_concept,
            approval_token="",  # No token needed for admin copy
            approval_url="",
            image_url=post.image_url,
            chat_id=target_chat,
        )
        return self.provider.send_post_preview(payload, chat_id=target_chat, is_admin_preview=True)

    def send_admin_notification(
        self,
        text: str,
        chat_id: Optional[str] = None,
    ) -> Optional[TelegramMessageResponse]:
        """Send an operational text notification to the Admin Telegram account."""
        target_chat = str(chat_id or self.admin_chat_id).strip()
        if not target_chat:
            return None
        return self.provider.send_text_message(chat_id=target_chat, text=text)

    def get_system_status(self) -> str:
        """Generate human-readable operational status report for Admin (/status command)."""
        # 1. Database & Repositories Check
        db_status = "Connected ✅"
        last_post_info = "None"
        try:
            posts = self.approval_service.repos.posts.get_previous_posts(limit=10)
            if posts:
                latest = sorted(posts, key=lambda p: str(getattr(p, "created_at", None) or p.post_id), reverse=True)[0]
                last_post_info = f"<code>{latest.post_id}</code> (Rev #{latest.current_revision}, Status: <b>{latest.status.value}</b>)"
        except Exception as e:
            db_status = f"Degraded ⚠️ ({html.escape(str(e)[:50])})"

        # 2. Scheduler Check
        sched_time = f"{settings.SCHEDULE_HOUR:02d}:{settings.SCHEDULE_MINUTE:02d} {settings.TIMEZONE}"
        scheduler_status = f"Active ✅ (Daily at {sched_time})"

        # 3. Execution Mode Check
        mode = "MOCK / DRY-RUN ⚠️" if settings.DRY_RUN else "PRODUCTION (LIVE) 🚀"

        return (
            f"📊 <b>Jevyam Agent System Status</b>\n\n"
            f"⚙️ <b>Execution Mode:</b> {mode}\n"
            f"💾 <b>Database:</b> {db_status}\n"
            f"📝 <b>Latest Post:</b> {last_post_info}\n"
            f"⏰ <b>Daily Scheduler:</b> {scheduler_status}\n"
            f"👤 <b>Founder Chat ID:</b> <code>{self.founder_chat_id or 'Not Configured'}</code> (Approver ✅)\n"
            f"🛠️ <b>Admin Chat ID:</b> <code>{self.admin_chat_id or 'Not Configured'}</code> (Administrator ✅)\n"
            f"🔗 <b>LinkedIn Target Org:</b> <code>{settings.LINKEDIN_ORGANIZATION_ID or '108376955'}</code>"
        )

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

        # 3b. Handle Commands (/start, /help, /status, /run, /id, /chatid)
        if event.text_body:
            raw_text = event.text_body.strip()
            cmd = raw_text.split()[0].lower() if raw_text else ""
            if not cmd.startswith("/"):
                cmd = f"/{cmd}"

            # 1. /start, /id, /chatid
            if cmd in ("/start", "/id", "/chatid"):
                is_admin = self.is_authorized_admin(chat_id=event.chat_id, sender_id=event.sender_id)
                is_founder = self.is_authorized_founder(chat_id=event.chat_id, sender_id=event.sender_id)

                if is_admin:
                    info_msg = (
                        f"👋 <b>Jevyam Technologies AI Marketing Bot</b>\n\n"
                        f"🆔 <b>Chat ID:</b> <code>{event.chat_id}</code>\n"
                        f"👤 <b>Sender ID:</b> <code>{event.sender_id}</code>\n"
                        f"📋 <b>Role:</b> ADMIN ✅\n\n"
                        f"You are configured as the authorized administrator. You will receive copies of generated "
                        f"post previews, operational alerts, publishing notifications, and scheduler status.\n\n"
                        f"Type <code>/help</code> to view available admin commands."
                    )
                    if event.chat_id:
                        self.provider.send_text_message(chat_id=event.chat_id, text=info_msg)
                    return {
                        "status": "info",
                        "code": "ADMIN_IDENTIFIED",
                        "role": "admin",
                        "is_authorized": True,
                        "chat_id": event.chat_id,
                        "sender_id": event.sender_id,
                        "message": "Admin identified successfully.",
                    }
                elif is_founder:
                    info_msg = (
                        f"👋 <b>Jevyam Technologies AI Marketing Bot</b>\n\n"
                        f"🆔 <b>Chat ID:</b> <code>{event.chat_id}</code>\n"
                        f"👤 <b>Sender ID:</b> <code>{event.sender_id}</code>\n"
                        f"📋 <b>Status:</b> Authorized Founder ✅\n\n"
                        f"You are configured as the authorized founder. You will receive daily post previews, "
                        f"branded visual images, approval buttons, and publishing notifications here."
                    )
                    if event.chat_id:
                        self.provider.send_text_message(chat_id=event.chat_id, text=info_msg)
                    return {
                        "status": "info",
                        "code": "FOUNDER_IDENTIFIED",
                        "role": "founder",
                        "is_authorized": True,
                        "chat_id": event.chat_id,
                        "sender_id": event.sender_id,
                        "message": "Founder identified successfully.",
                    }
                else:
                    info_msg = (
                        f"👋 <b>Jevyam Technologies AI Marketing Bot</b>\n\n"
                        f"🆔 <b>Chat ID:</b> <code>{event.chat_id}</code>\n"
                        f"👤 <b>Sender ID:</b> <code>{event.sender_id}</code>\n"
                        f"📋 <b>Status:</b> Unregistered User ⚠️\n\n"
                        f"This chat is not registered as the authorized founder or administrator. "
                        f"To authorize, update <code>TELEGRAM_FOUNDER_CHAT_ID</code> or <code>TELEGRAM_ADMIN_CHAT_ID</code>."
                    )
                    if event.chat_id:
                        self.provider.send_text_message(chat_id=event.chat_id, text=info_msg)
                    return {
                        "status": "info",
                        "code": "UNAUTHORIZED_USER",
                        "role": "unregistered",
                        "is_authorized": False,
                        "chat_id": event.chat_id,
                        "sender_id": event.sender_id,
                        "message": "Unregistered user identified.",
                    }

            # 2. /help
            elif cmd in ("/help", "/commands"):
                is_admin = self.is_authorized_admin(chat_id=event.chat_id, sender_id=event.sender_id)
                if not is_admin:
                    if event.chat_id:
                        self.provider.send_text_message(
                            chat_id=event.chat_id,
                            text="⛔ <b>Access Denied:</b> Administrative commands are restricted to authorized administrators.",
                        )
                    return {"status": "unauthorized", "code": "ADMIN_ONLY"}

                help_msg = (
                    f"🛠️ <b>Jevyam Technologies Admin Commands</b>\n\n"
                    f"• <code>/status</code> — Inspect system health, database, scheduler, and latest post.\n"
                    f"• <code>/run</code> — Trigger daily post generation immediately.\n"
                    f"• <code>/id</code> — Show your account identifiers.\n"
                    f"• <code>/help</code> — Show this commands manual."
                )
                if event.chat_id:
                    self.provider.send_text_message(chat_id=event.chat_id, text=help_msg)
                return {"status": "info", "code": "HELP_HANDLED"}

            # 3. /status
            elif cmd == "/status":
                is_admin = self.is_authorized_admin(chat_id=event.chat_id, sender_id=event.sender_id)
                if not is_admin:
                    if event.chat_id:
                        self.provider.send_text_message(
                            chat_id=event.chat_id,
                            text="⛔ <b>Access Denied:</b> Administrative commands are restricted to authorized administrators.",
                        )
                    return {"status": "unauthorized", "code": "ADMIN_ONLY"}

                status_report = self.get_system_status()
                if event.chat_id:
                    self.provider.send_text_message(chat_id=event.chat_id, text=status_report)
                return {"status": "info", "code": "STATUS_REPORTED", "report": status_report}

            # 4. /run
            elif cmd == "/run":
                is_admin = self.is_authorized_admin(chat_id=event.chat_id, sender_id=event.sender_id)
                if not is_admin:
                    if event.chat_id:
                        self.provider.send_text_message(
                            chat_id=event.chat_id,
                            text="⛔ <b>Access Denied:</b> Administrative commands are restricted to authorized administrators.",
                        )
                    return {"status": "unauthorized", "code": "ADMIN_ONLY"}

                if event.chat_id:
                    self.provider.send_text_message(
                        chat_id=event.chat_id,
                        text="⏳ <b>Manual Run Triggered:</b> Initiating daily post generation...",
                    )

                try:
                    from agent.orchestrator import DailyOrchestrator
                    orchestrator = DailyOrchestrator(
                        repo_manager=self.approval_service.repos,
                        approval_service=self.approval_service,
                        telegram_service=self,
                    )
                    run_res = orchestrator.run(force=True)
                    if event.chat_id:
                        self.provider.send_text_message(
                            chat_id=event.chat_id,
                            text=f"✅ <b>Manual Run Completed!</b>\n\nPost: <code>{run_res.post_id}</code> (Rev #{run_res.revision_number})\nTopic: {run_res.topic}\nStatus: {run_res.status}",
                        )
                    return {"status": "accepted", "code": "MANUAL_RUN_COMPLETED", "post_id": run_res.post_id}
                except Exception as run_err:
                    err_str = html.escape(str(run_err))
                    if event.chat_id:
                        self.provider.send_text_message(
                            chat_id=event.chat_id,
                            text=f"❌ <b>Manual Run Failed:</b> {err_str}",
                        )
                    return {"status": "error", "code": "MANUAL_RUN_FAILED", "error": str(run_err)}

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

        # 4b. Strict Founder Authorization Check (Only Founder 8164283098 can approve/reject)
        if not self.is_authorized_founder(chat_id=event.chat_id, sender_id=event.sender_id):
            logger.warning(
                f"[UNAUTHORIZED] Telegram callback rejected: chat_id='{event.chat_id}', "
                f"sender_id='{event.sender_id}'. Expected founder_chat_id='{self.founder_chat_id}'."
            )
            if self.is_authorized_admin(chat_id=event.chat_id, sender_id=event.sender_id):
                denial_text = (
                    "⛔ <b>Access Denied:</b> As Admin, you cannot approve, reject, or regenerate posts. "
                    "Actionable approval buttons are reserved exclusively for the Founder (<code>8164283098</code>)."
                )
            else:
                denial_text = "⛔ <b>Access Denied:</b> You are not authorized to approve or regenerate posts for Jevyam Technologies."

            if event.chat_id:
                try:
                    self.provider.send_text_message(
                        chat_id=event.chat_id,
                        text=denial_text,
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
                    if result.published is True:
                        if result.post_url:
                            pub_text = (
                                f" and published to LinkedIn Company Page!\n\n"
                                f"🔗 <b>LinkedIn URL:</b> {result.post_url}\n"
                                f"🆔 <b>Post URN:</b> <code>{result.external_post_id or 'N/A'}</code>"
                            )
                        else:
                            pub_text = (
                                f" and published to LinkedIn Company Page.\n\n"
                                f"🆔 <b>Post URN:</b> <code>{result.external_post_id or 'N/A'}</code>"
                            )

                        self.provider.send_text_message(
                            chat_id=target_chat,
                            text=f"✅ <b>Approved!</b> Post <code>{result.post_id}</code> (Rev #{result.revision}) approved{pub_text}",
                        )

                        # Send publication update to admin
                        if self.admin_chat_id:
                            self.send_admin_notification(
                                f"📢 <b>LinkedIn Publishing Notice (Admin Copy)</b>\n\n"
                                f"Founder approved Post <code>{result.post_id}</code> (Rev #{result.revision}){pub_text}"
                            )
                    else:
                        fail_msg = (
                            f"⚠️ <b>Post Approved, But Publishing Failed</b>\n\n"
                            f"Post <code>{result.post_id}</code> (Rev #{result.revision}) was approved by Founder, "
                            f"but real LinkedIn publishing could not proceed.\n\n"
                            f"<b>Details:</b> {html.escape(result.message or 'LinkedIn API error')}\n\n"
                            f"The post has been placed in FAILED status."
                        )
                        self.provider.send_text_message(
                            chat_id=target_chat,
                            text=fail_msg,
                        )

                        if self.admin_chat_id:
                            self.send_admin_notification(
                                f"🚨 <b>LinkedIn Publishing Failure Alert (Admin Copy)</b>\n\n"
                                f"Founder approved Post <code>{result.post_id}</code> (Rev #{result.revision}), "
                                f"but publishing to LinkedIn failed.\n\n"
                                f"<b>Details:</b> {html.escape(result.message or 'LinkedIn API error')}"
                            )

                return {
                    "status": "approved",
                    "post_id": result.post_id,
                    "revision": result.revision,
                    "published": bool(result.published),
                    "message": result.message or "Post approved successfully via Telegram.",
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

            # Operational notification to admin
            if self.admin_chat_id:
                self.send_admin_notification(
                    f"🔄 <b>Post Rejection Notice (Admin Copy)</b>\n\n"
                    f"Founder requested revision for Post <code>{result.post_id}</code>. "
                    f"New revision Rev #{result.revision} was generated and delivered to Founder for approval."
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
