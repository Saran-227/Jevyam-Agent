"""Process interactive Telegram approval callbacks dispatched from Cloudflare Worker (Phase B).

Usage:
    python scripts/process_telegram_callback.py --action approve --token <token> --chat-id 8164283098 --user-id 8164283098
    python scripts/process_telegram_callback.py --action reject --token <token> --chat-id 8164283098 --user-id 8164283098
"""

import argparse
import html
import logging
import os
from pathlib import Path
import sys
from typing import Optional

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalExpiredError,
    ApprovalInProgressError,
    ApprovalNotFoundError,
    ApprovalSupersededError,
    PostNotApprovedError,
    PostNotFoundError,
)
from api.services.approval_service import ApprovalService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.repositories import get_repository_manager
from integrations.telegram.provider import get_telegram_provider

logger = logging.getLogger("jevyam.callback_processor")


def configure_logging(verbose: bool = False) -> None:
    """Configure structured console logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)


def mask_token(token: Optional[str]) -> str:
    """Mask sensitive tokens for safe logging."""
    if not token or len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process founder Telegram approval or rejection callback",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["approve", "reject", "yes", "no", "regenerate"],
        help="Action to execute (approve or reject/regenerate)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Single-use approval token",
    )
    parser.add_argument(
        "--chat-id",
        required=False,
        default=None,
        help="Telegram chat ID of sender",
    )
    parser.add_argument(
        "--user-id",
        required=False,
        default=None,
        help="Telegram user/sender ID",
    )
    parser.add_argument(
        "--callback-query-id",
        required=False,
        default=None,
        help="Optional Telegram callback query ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution without live LinkedIn publication",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()
    configure_logging(verbose=args.verbose)

    # Tell GitHub Actions runner to mask this token in all stdout
    token = args.token.strip()
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{token}")

    action = args.action.lower().strip()
    chat_id = str(args.chat_id or "").strip()
    user_id = str(args.user_id or "").strip()
    masked = mask_token(token)

    logger.info(f"Starting callback processing: action='{action}', token={masked}")

    if args.dry_run:
        settings.DRY_RUN = True

    # 1. Initialize TelegramService, PublishingService, and authoritative Repositories
    repo_manager = get_repository_manager()
    is_mock = bool(args.dry_run or settings.DRY_RUN or settings.LINKEDIN_MOCK_PUBLISHING)
    from api.services.publishing_service import PublishingService
    publishing_service = PublishingService(
        repo_manager=repo_manager,
        mock_mode=is_mock,
    )
    approval_service = ApprovalService(
        repo_manager=repo_manager,
        publishing_service=publishing_service,
    )
    telegram_service = TelegramService(
        approval_service=approval_service,
        founder_chat_id=settings.TELEGRAM_FOUNDER_CHAT_ID,
        admin_chat_id=settings.TELEGRAM_ADMIN_CHAT_ID,
    )

    target_chat = settings.TELEGRAM_FOUNDER_CHAT_ID or chat_id

    # 2. Strict Founder Authorization Verification (Only Founder 8164283098 can approve/reject)
    if chat_id or user_id:
        if not telegram_service.is_authorized_founder(chat_id=chat_id, sender_id=user_id):
            logger.warning(
                f"[SECURITY] Unauthorized approval callback rejected. chat_id='{chat_id}', "
                f"user_id='{user_id}'. Expected founder_chat_id='{settings.TELEGRAM_FOUNDER_CHAT_ID}'."
            )
            if telegram_service.is_authorized_admin(chat_id=chat_id, sender_id=user_id):
                denial_text = (
                    "⛔ <b>Access Denied:</b> As Admin, you cannot approve, reject, or regenerate posts. "
                    "Actionable approval buttons are reserved exclusively for the Founder (<code>8164283098</code>)."
                )
            else:
                denial_text = "⛔ <b>Access Denied:</b> You are not authorized to approve or regenerate posts for Jevyam Technologies."

            if chat_id:
                try:
                    telegram_service.provider.send_text_message(
                        chat_id=chat_id,
                        text=denial_text,
                    )
                except Exception as notify_err:
                    logger.warning(f"Failed to send access-denied message to chat '{chat_id}': {notify_err}")
            return 1

    # 3. Handle YES (Approval & Publication)
    if action in ("approve", "yes"):
        try:
            logger.info(f"Validating and approving post with token {masked}...")
            auto_pub = not (args.dry_run or settings.DRY_RUN)
            result = telegram_service.approval_service.approve_post(
                token=token,
                auto_publish=auto_pub,
            )

            # Send publication confirmation or failure notification to founder and admin
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

                if target_chat:
                    telegram_service.provider.send_text_message(
                        chat_id=target_chat,
                        text=f"✅ <b>Approved!</b> Post <code>{result.post_id}</code> (Rev #{result.revision}) approved{pub_text}",
                    )

                # Operational notification to Admin
                if telegram_service.admin_chat_id:
                    try:
                        telegram_service.send_admin_notification(
                            f"📢 <b>LinkedIn Publishing Notice (Admin Copy)</b>\n\n"
                            f"Founder approved Post <code>{result.post_id}</code> (Rev #{result.revision}){pub_text}"
                        )
                    except Exception as notify_err:
                        logger.warning(f"Failed to send admin publication alert: {notify_err}")

                logger.info(
                    f"[SUCCESS] Post '{result.post_id}' (Rev #{result.revision}) approved and published. "
                    f"URN: {result.external_post_id}, URL: {result.post_url}"
                )
                return 0
            else:
                fail_msg = (
                    f"⚠️ <b>Post Approved, But Publishing Failed</b>\n\n"
                    f"Post <code>{result.post_id}</code> (Rev #{result.revision}) was approved by Founder, "
                    f"but real LinkedIn publishing failed.\n\n"
                    f"<b>Details:</b> {html.escape(result.message or 'LinkedIn API error')}\n\n"
                    f"The post has been placed in FAILED status."
                )
                if target_chat:
                    telegram_service.provider.send_text_message(
                        chat_id=target_chat,
                        text=fail_msg,
                    )
                if telegram_service.admin_chat_id:
                    try:
                        telegram_service.send_admin_notification(
                            f"🚨 <b>LinkedIn Publishing Failure Alert (Admin Copy)</b>\n\n"
                            f"Founder approved Post <code>{result.post_id}</code> (Rev #{result.revision}), "
                            f"but publishing to LinkedIn failed.\n\n"
                            f"<b>Details:</b> {html.escape(result.message or 'LinkedIn API error')}"
                        )
                    except Exception as notify_err:
                        logger.warning(f"Failed to send admin publication failure alert: {notify_err}")

                logger.error(
                    f"[FAILURE] Post '{result.post_id}' (Rev #{result.revision}) approved, but real LinkedIn publishing failed: "
                    f"{result.message}"
                )
                return 1

        except ApprovalAlreadyProcessedError as ape:
            logger.info(f"[IDEMPOTENT SKIP] Approval already processed: {ape}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"ℹ️ <b>Already Processed:</b> {html.escape(str(ape))}",
                )
            return 0

        except ApprovalExpiredError as aee:
            logger.warning(f"[EXPIRED] Approval token expired: {aee}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"⚠️ <b>Approval Expired:</b> {html.escape(str(aee))}",
                )
            return 1

        except ApprovalNotFoundError as ane:
            logger.error(f"[NOT FOUND] Approval token not found: {ane}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text="❌ <b>Approval Not Found:</b> The requested post or token was not found.",
                )
            return 1

        except ApprovalSupersededError as ase:
            logger.info(f"[SUPERSEDED] Revision superseded: {ase}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"ℹ️ <b>Revision Superseded:</b> {html.escape(str(ase))}",
                )
            return 0

        except Exception as e:
            logger.error(f"[ERROR] Failed to approve post: {e}", exc_info=True)
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"❌ <b>Approval Error:</b> Failed to approve post: {html.escape(str(e))}",
                )
            return 1

    # 4. Handle NO (Rejection & Regeneration)
    elif action in ("reject", "no", "regenerate"):
        try:
            logger.info(f"Rejecting revision with token {masked} and generating next revision...")
            result = telegram_service.approval_service.reject_and_regenerate(
                token=token,
                reason="Founder requested revision via Telegram button",
            )

            # Deliver the newly generated revision preview and inline buttons to founder
            if target_chat:
                telegram_service.send_post_approval_notification(
                    post_id=result.post_id,
                    chat_id=target_chat,
                )

            # Operational notification to Admin
            if telegram_service.admin_chat_id:
                try:
                    telegram_service.send_admin_notification(
                        f"🔄 <b>Post Rejection Notice (Admin Copy)</b>\n\n"
                        f"Founder requested revision for Post <code>{result.post_id}</code>. "
                        f"New Rev #{result.revision} was generated and dispatched to Founder for approval."
                    )
                except Exception as notify_err:
                    logger.warning(f"Failed to send admin rejection alert: {notify_err}")

            logger.info(
                f"[SUCCESS] Post '{result.post_id}' revision regenerated to Rev #{result.revision} "
                f"and delivered to founder on Telegram."
            )
            return 0

        except ApprovalAlreadyProcessedError as ape:
            logger.info(f"[IDEMPOTENT SKIP] Rejection already processed: {ape}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"ℹ️ <b>Already Processed:</b> {html.escape(str(ape))}",
                )
            return 0

        except ApprovalInProgressError as aie:
            logger.info(f"[IN PROGRESS] Regeneration already in progress: {aie}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"⏳ <b>In Progress:</b> {html.escape(str(aie))}",
                )
            return 0

        except ApprovalExpiredError as aee:
            logger.warning(f"[EXPIRED] Approval token expired: {aee}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"⚠️ <b>Approval Expired:</b> {html.escape(str(aee))}",
                )
            return 1

        except ApprovalNotFoundError as ane:
            logger.error(f"[NOT FOUND] Approval token not found: {ane}")
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text="❌ <b>Approval Not Found:</b> The requested post or token was not found.",
                )
            return 1

        except Exception as e:
            logger.error(f"[ERROR] Failed to reject and regenerate post: {e}", exc_info=True)
            if target_chat:
                telegram_service.provider.send_text_message(
                    chat_id=target_chat,
                    text=f"❌ <b>Regeneration Error:</b> Failed to regenerate post: {html.escape(str(e))}",
                )
            return 1

    else:
        logger.error(f"[ERROR] Unrecognized action '{action}'.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

