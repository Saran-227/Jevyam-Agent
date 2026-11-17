"""Telegram Bot API provider implementation using standard HTTPS Bot API."""

import html
import hmac
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from agent.image_generator import is_valid_image_url
from config.settings import settings
from integrations.telegram.base import BaseTelegramProvider
from integrations.telegram.models import (
    TelegramApprovalMessagePayload,
    TelegramMessageResponse,
    TelegramWebhookEvent,
)

logger = logging.getLogger("jevyam.telegram")


def mask_sensitive_url(url_or_text: str) -> str:
    """Mask Telegram bot token from URL strings or log text to prevent credential leaks."""
    if not url_or_text:
        return url_or_text
    return re.sub(r"/bot[a-zA-Z0-9_\-:]+", "/bot<MASKED_TELEGRAM_TOKEN>", str(url_or_text))


class TelegramApiProvider(BaseTelegramProvider):
    """Official HTTPS Bot API client provider for Telegram."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        founder_chat_id: Optional[str] = None,
        admin_chat_id: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        timeout: float = 15.0,
    ):
        self.bot_token = (bot_token if bot_token is not None else (settings.TELEGRAM_BOT_TOKEN or "")).strip()
        self.founder_chat_id = str(founder_chat_id if founder_chat_id is not None else (settings.TELEGRAM_FOUNDER_CHAT_ID or "")).strip()
        self.admin_chat_id = str(admin_chat_id if admin_chat_id is not None else (settings.TELEGRAM_ADMIN_CHAT_ID or "")).strip()
        self.webhook_secret = (webhook_secret if webhook_secret is not None else (settings.TELEGRAM_WEBHOOK_SECRET or "")).strip()

        self.base_url = (base_url or settings.TELEGRAM_API_BASE_URL or "https://api.telegram.org").rstrip("/")
        self.timeout = timeout
        self._http_client = http_client or httpx.Client(timeout=self.timeout)

    @property
    def _api_endpoint(self) -> str:
        return f"{self.base_url}/bot{self.bot_token}"

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Validate whether provider has required credentials for LIVE operations."""
        errors: List[str] = []

        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is missing or empty.")
        elif self.bot_token.lower().startswith("your_") or "placeholder" in self.bot_token.lower():
            errors.append("TELEGRAM_BOT_TOKEN contains an unconfigured placeholder value.")

        if not self.founder_chat_id:
            errors.append("TELEGRAM_FOUNDER_CHAT_ID is missing or empty.")
        elif self.founder_chat_id.lower().startswith("your_") or "placeholder" in self.founder_chat_id.lower():
            errors.append("TELEGRAM_FOUNDER_CHAT_ID contains an unconfigured placeholder value.")

        return len(errors) == 0, errors

    def verify_webhook_secret(self, secret_token_header: Optional[str]) -> bool:
        """Verify authenticity of incoming Telegram webhook requests."""
        if not self.webhook_secret:
            # If no secret is configured, allow in development/testing
            return True

        if not secret_token_header:
            return False

        return hmac.compare_digest(secret_token_header.strip(), self.webhook_secret)

    def _post_with_retry(
        self,
        method: str,
        json_payload: Optional[Dict[str, Any]] = None,
        data_payload: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Execute HTTP POST request to Telegram Bot API with retry on transient failures."""
        url = f"{self._api_endpoint}/{method}"
        masked_url = mask_sensitive_url(url)

        for attempt in range(max_retries + 1):
            try:
                if files is not None:
                    response = self._http_client.post(url, data=data_payload, files=files)
                else:
                    response = self._http_client.post(url, json=json_payload)
                data = response.json() if response.content else {}

                if response.status_code == 200 and data.get("ok"):
                    return data

                # Check if retryable (429 Too Many Requests or 5xx Server Error)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    retry_after = data.get("parameters", {}).get("retry_after", 1)
                    logger.warning(
                        f"[WARN] Telegram API returned HTTP {response.status_code} for {masked_url}. Retrying in {retry_after}s..."
                    )
                    time.sleep(retry_after)
                    continue

                error_desc = data.get("description", response.text)
                raise RuntimeError(
                    f"Telegram Bot API error HTTP {response.status_code} ({method}): {error_desc}"
                )

            except httpx.TimeoutException as te:
                if attempt < max_retries:
                    logger.warning(f"[WARN] Timeout calling Telegram {masked_url} on attempt {attempt + 1}. Retrying...")
                    time.sleep(1)
                    continue
                raise TimeoutError(f"Telegram Bot API request timed out after {self.timeout}s: {te}") from te

            except httpx.HTTPError as he:
                if attempt < max_retries:
                    logger.warning(f"[WARN] Network error calling Telegram {masked_url} on attempt {attempt + 1}: {he}. Retrying...")
                    time.sleep(1)
                    continue
                raise RuntimeError(f"Network error communicating with Telegram Bot API: {he}") from he

        raise RuntimeError(f"Failed to execute Telegram API call after {max_retries + 1} attempts.")

    def send_text_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = "HTML",
    ) -> TelegramMessageResponse:
        """Send plain or formatted text message to Telegram chat."""
        target_chat = str(chat_id or self.founder_chat_id).strip()
        if not target_chat:
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="telegram",
                error="Recipient Telegram chat ID is missing.",
            )

        payload: Dict[str, Any] = {
            "chat_id": target_chat,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            res = self._post_with_retry("sendMessage", payload)
            msg_id = str(res.get("result", {}).get("message_id", ""))
            return TelegramMessageResponse(
                success=True,
                message_id=msg_id,
                chat_id=target_chat,
                provider="telegram",
                raw_response=res,
            )
        except Exception as e:
            safe_error = mask_sensitive_url(str(e))
            logger.error(f"[ERROR] Failed to send Telegram text message: {safe_error}")
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="telegram",
                error=safe_error,
            )

    def format_approval_text(self, payload: TelegramApprovalMessagePayload) -> str:
        """Format the Telegram approval message body with company context, post caption, and instructions."""
        lines = [
            "<b>Jevyam Technologies — LinkedIn Post Approval</b>",
            f"<b>Revision:</b> #{payload.revision_number}",
            f"<b>Post ID:</b> <code>{html.escape(payload.post_id)}</code>",
            "",
            "<b>Caption:</b>",
            f"{html.escape(payload.caption)}",
        ]

        if payload.hashtags:
            lines.append("")
            lines.append(f"<b>Hashtags:</b> {' '.join(html.escape(tag) for tag in payload.hashtags)}")

        if payload.visual_concept:
            lines.append("")
            lines.append(f"<b>Visual Concept:</b> {html.escape(payload.visual_concept)}")

        lines.append("")
        lines.append("<b>Please approve this post:</b>")

        return "\n".join(lines)

    def send_approval_message(
        self,
        payload: TelegramApprovalMessagePayload,
        chat_id: Optional[str] = None,
    ) -> TelegramMessageResponse:
        """Send interactive approval message with YES/NO inline buttons."""
        target_chat = str(chat_id or payload.chat_id or self.founder_chat_id).strip()
        if not target_chat:
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="telegram",
                error="Missing founder chat ID for approval notification.",
            )

        message_text = self.format_approval_text(payload)

        # Telegram inline keyboard buttons: callback_data must be <= 64 bytes
        # Format: "approve:<token>" and "reject:<token>"
        inline_keyboard = [
            [
                {
                    "text": "✅ YES, PUBLISH",
                    "callback_data": f"approve:{payload.approval_token}",
                },
                {
                    "text": "❌ NO, REGENERATE",
                    "callback_data": f"reject:{payload.approval_token}",
                },
            ]
        ]
        reply_markup = {"inline_keyboard": inline_keyboard}

        has_valid_image = is_valid_image_url(payload.image_url)

        # Fail closed: reject text-only approval if image is required
        if getattr(settings, "REQUIRE_POST_IMAGE", True) and not has_valid_image:
            err_msg = (
                f"Post '{payload.post_id}' requires a companion image URL, but got '{payload.image_url}'. "
                "Refusing to send text-only Telegram approval message (fail-closed)."
            )
            logger.error(f"[ERROR] {err_msg}")
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="telegram",
                error=err_msg,
            )

        # Detect if a local image file is available on disk for fallback multipart delivery
        local_img_candidate = None
        for candidate_path in [
            Path(f"data/posts/{payload.post_id}.png"),
            Path(f"data/images/{payload.post_id}.png"),
            Path(payload.image_url) if payload.image_url and not payload.image_url.startswith("http") else None,
        ]:
            if candidate_path and candidate_path.exists():
                local_img_candidate = candidate_path
                break

        # Case 1: Image URL is present and short caption fits (<= 1024 chars), sendPhoto with inline buttons
        if has_valid_image and len(message_text) <= 1024:
            photo_payload: Dict[str, Any] = {
                "chat_id": target_chat,
                "photo": payload.image_url,
                "caption": message_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            try:
                res = self._post_with_retry("sendPhoto", photo_payload)
                msg_id = str(res.get("result", {}).get("message_id", ""))
                return TelegramMessageResponse(
                    success=True,
                    message_id=msg_id,
                    chat_id=target_chat,
                    provider="telegram",
                    raw_response=res,
                )
            except Exception as e:
                # Fallback to direct multipart upload if local file exists
                if local_img_candidate:
                    try:
                        logger.info(f"[INFO] Falling back to direct multipart image delivery from {local_img_candidate}...")
                        multipart_data = {
                            "chat_id": target_chat,
                            "caption": message_text,
                            "parse_mode": "HTML",
                            "reply_markup": json.dumps(reply_markup),
                        }
                        files = {"photo": (local_img_candidate.name, local_img_candidate.read_bytes(), "image/png")}
                        res = self._post_with_retry("sendPhoto", data_payload=multipart_data, files=files)
                        msg_id = str(res.get("result", {}).get("message_id", ""))
                        return TelegramMessageResponse(
                            success=True,
                            message_id=msg_id,
                            chat_id=target_chat,
                            provider="telegram",
                            raw_response=res,
                        )
                    except Exception as me:
                        logger.error(f"[ERROR] Direct multipart image delivery failed: {me}")
                safe_err = mask_sensitive_url(str(e))
                logger.error(f"[ERROR] Failed to deliver photo approval: {safe_err}")
                return TelegramMessageResponse(
                    success=False,
                    chat_id=target_chat,
                    provider="telegram",
                    error=f"Failed to deliver photo approval: {safe_err}",
                )

        # Case 2: Image URL is present but caption exceeds 1024 chars (linked messages: photo preview + text approval)
        elif has_valid_image:
            photo_caption = (
                f"<b>Jevyam Technologies — LinkedIn Visual Preview</b>\n"
                f"<b>Revision:</b> #{payload.revision_number}\n"
                f"<b>Post ID:</b> <code>{html.escape(payload.post_id)}</code>\n\n"
                f"<i>(Full post caption and approval options in message below 👇)</i>"
            )
            photo_payload: Dict[str, Any] = {
                "chat_id": target_chat,
                "photo": payload.image_url,
                "caption": photo_caption,
                "parse_mode": "HTML",
            }
            try:
                self._post_with_retry("sendPhoto", photo_payload)
            except Exception as e:
                delivered_fallback = False
                if local_img_candidate:
                    try:
                        logger.info(f"[INFO] Falling back to direct multipart preview image delivery from {local_img_candidate}...")
                        multipart_data = {
                            "chat_id": target_chat,
                            "caption": photo_caption,
                            "parse_mode": "HTML",
                        }
                        files = {"photo": (local_img_candidate.name, local_img_candidate.read_bytes(), "image/png")}
                        self._post_with_retry("sendPhoto", data_payload=multipart_data, files=files)
                        delivered_fallback = True
                    except Exception as me:
                        logger.error(f"[ERROR] Direct multipart preview delivery failed: {me}")
                if not delivered_fallback:
                    safe_err = mask_sensitive_url(str(e))
                    logger.error(f"[ERROR] Failed to deliver preview photo in linked approval: {safe_err}")
                    return TelegramMessageResponse(
                        success=False,
                        chat_id=target_chat,
                        provider="telegram",
                        error=f"Failed to deliver visual preview in linked approval: {safe_err}",
                    )

            # Send complete caption with inline buttons
            text_payload: Dict[str, Any] = {
                "chat_id": target_chat,
                "text": message_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            try:
                res = self._post_with_retry("sendMessage", text_payload)
                msg_id = str(res.get("result", {}).get("message_id", ""))
                return TelegramMessageResponse(
                    success=True,
                    message_id=msg_id,
                    chat_id=target_chat,
                    provider="telegram",
                    raw_response=res,
                )
            except Exception as e:
                safe_err = mask_sensitive_url(str(e))
                logger.error(f"[ERROR] Failed to send Telegram linked text approval: {safe_err}")
                return TelegramMessageResponse(
                    success=False,
                    chat_id=target_chat,
                    provider="telegram",
                    error=safe_err,
                )

        # Case 3: No image_url provided (plain text message - only allowed when REQUIRE_POST_IMAGE is disabled)
        else:
            text_payload: Dict[str, Any] = {
                "chat_id": target_chat,
                "text": message_text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            }
            try:
                res = self._post_with_retry("sendMessage", text_payload)
                msg_id = str(res.get("result", {}).get("message_id", ""))
                return TelegramMessageResponse(
                    success=True,
                    message_id=msg_id,
                    chat_id=target_chat,
                    provider="telegram",
                    raw_response=res,
                )
            except Exception as e:
                safe_error = mask_sensitive_url(str(e))
                logger.error(f"[ERROR] Failed to send Telegram approval notification: {safe_error}")
                return TelegramMessageResponse(
                    success=False,
                    chat_id=target_chat,
                    provider="telegram",
                    error=safe_error,
                )

    def send_post_preview(
        self,
        payload: TelegramApprovalMessagePayload,
        chat_id: Optional[str] = None,
        is_admin_preview: bool = True,
    ) -> TelegramMessageResponse:
        """Send formatted post preview and companion image without actionable approval buttons."""
        target_chat = str(chat_id or payload.chat_id or self.admin_chat_id).strip()
        if not target_chat:
            return TelegramMessageResponse(
                success=False,
                chat_id=target_chat,
                provider="telegram",
                error="Missing destination chat ID for post preview.",
            )

        header = "<b>Jevyam Technologies — Generated Post Preview (Admin Copy)</b>" if is_admin_preview else "<b>Jevyam Technologies — LinkedIn Post Preview</b>"
        lines = [
            header,
            f"<b>Revision:</b> #{payload.revision_number}",
            f"<b>Post ID:</b> <code>{html.escape(payload.post_id)}</code>",
            "",
            "<b>Caption:</b>",
            f"{html.escape(payload.caption)}",
        ]

        if payload.hashtags:
            lines.append("")
            lines.append(f"<b>Hashtags:</b> {' '.join(html.escape(tag) for tag in payload.hashtags)}")

        if payload.visual_concept:
            lines.append("")
            lines.append(f"<b>Visual Concept:</b> {html.escape(payload.visual_concept)}")

        if is_admin_preview:
            lines.append("")
            lines.append("<i>ℹ️ Admin Informational Copy — Actionable approval buttons sent exclusively to Founder.</i>")

        message_text = "\n".join(lines)
        has_valid_image = is_valid_image_url(payload.image_url)

        # Detect local image file candidate
        local_img_candidate = None
        for candidate_path in [
            Path(f"data/posts/{payload.post_id}.png"),
            Path(f"data/images/{payload.post_id}.png"),
            Path(payload.image_url) if payload.image_url and not payload.image_url.startswith("http") else None,
        ]:
            if candidate_path and candidate_path.exists():
                local_img_candidate = candidate_path
                break

        # Case 1: Photo with caption <= 1024 chars (NO inline buttons)
        if has_valid_image and len(message_text) <= 1024:
            photo_payload: Dict[str, Any] = {
                "chat_id": target_chat,
                "photo": payload.image_url,
                "caption": message_text,
                "parse_mode": "HTML",
            }
            try:
                res = self._post_with_retry("sendPhoto", photo_payload)
                msg_id = str(res.get("result", {}).get("message_id", ""))
                return TelegramMessageResponse(
                    success=True,
                    message_id=msg_id,
                    chat_id=target_chat,
                    provider="telegram",
                    raw_response=res,
                )
            except Exception as e:
                if local_img_candidate:
                    try:
                        multipart_data = {
                            "chat_id": target_chat,
                            "caption": message_text,
                            "parse_mode": "HTML",
                        }
                        files = {"photo": (local_img_candidate.name, local_img_candidate.read_bytes(), "image/png")}
                        res = self._post_with_retry("sendPhoto", data_payload=multipart_data, files=files)
                        msg_id = str(res.get("result", {}).get("message_id", ""))
                        return TelegramMessageResponse(
                            success=True,
                            message_id=msg_id,
                            chat_id=target_chat,
                            provider="telegram",
                            raw_response=res,
                        )
                    except Exception as me:
                        logger.error(f"[ERROR] Direct multipart image delivery failed for preview: {me}")
                safe_err = mask_sensitive_url(str(e))
                logger.error(f"[ERROR] Failed to deliver photo preview: {safe_err}")
                return TelegramMessageResponse(
                    success=False,
                    chat_id=target_chat,
                    provider="telegram",
                    error=f"Failed to deliver photo preview: {safe_err}",
                )

        # Case 2: Photo + separate long caption message (NO buttons)
        elif has_valid_image:
            photo_caption = (
                f"<b>Jevyam Technologies — Visual Preview (Admin Copy)</b>\n"
                f"<b>Revision:</b> #{payload.revision_number}\n"
                f"<b>Post ID:</b> <code>{html.escape(payload.post_id)}</code>\n\n"
                f"<i>(Full post caption in message below 👇)</i>"
            )
            try:
                self._post_with_retry("sendPhoto", {
                    "chat_id": target_chat,
                    "photo": payload.image_url,
                    "caption": photo_caption,
                    "parse_mode": "HTML",
                })
            except Exception as pe:
                safe_err = mask_sensitive_url(str(pe))
                logger.warning(f"[WARN] Failed to deliver photo preview: {safe_err}")

            text_payload = {
                "chat_id": target_chat,
                "text": message_text,
                "parse_mode": "HTML",
            }
            try:
                res = self._post_with_retry("sendMessage", text_payload)
                msg_id = str(res.get("result", {}).get("message_id", ""))
                return TelegramMessageResponse(
                    success=True,
                    message_id=msg_id,
                    chat_id=target_chat,
                    provider="telegram",
                    raw_response=res,
                )
            except Exception as e:
                safe_err = mask_sensitive_url(str(e))
                return TelegramMessageResponse(
                    success=False,
                    chat_id=target_chat,
                    provider="telegram",
                    error=safe_err,
                )

        # Case 3: Plain text message (NO buttons)
        else:
            text_payload = {
                "chat_id": target_chat,
                "text": message_text,
                "parse_mode": "HTML",
            }
            try:
                res = self._post_with_retry("sendMessage", text_payload)
                msg_id = str(res.get("result", {}).get("message_id", ""))
                return TelegramMessageResponse(
                    success=True,
                    message_id=msg_id,
                    chat_id=target_chat,
                    provider="telegram",
                    raw_response=res,
                )
            except Exception as e:
                safe_err = mask_sensitive_url(str(e))
                return TelegramMessageResponse(
                    success=False,
                    chat_id=target_chat,
                    provider="telegram",
                    error=safe_err,
                )

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge Telegram callback query so loading indicator terminates."""
        if not callback_query_id:
            return False

        payload: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text

        try:
            self._post_with_retry("answerCallbackQuery", payload)
            return True
        except Exception as e:
            logger.warning(f"[WARN] Failed to answer callback query: {mask_sensitive_url(str(e))}")
            return False

    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any],
    ) -> Optional[TelegramWebhookEvent]:
        """Normalize Telegram update payload into TelegramWebhookEvent."""
        if not payload_dict:
            return None

        # 1. Handle Inline Button Click (callback_query)
        if "callback_query" in payload_dict:
            cb = payload_dict["callback_query"]
            cb_id = str(cb.get("id", ""))
            cb_data = cb.get("data")
            msg = cb.get("message", {})
            sender = cb.get("from", {})
            chat = msg.get("chat", {})

            return TelegramWebhookEvent(
                event_type="callback_query",
                callback_query_id=cb_id,
                chat_id=str(chat.get("id", "")) if chat else str(sender.get("id", "")),
                sender_id=str(sender.get("id", "")),
                message_id=str(msg.get("message_id", "")),
                callback_data=cb_data,
                raw_data=payload_dict,
            )

        # 2. Handle Direct Message (e.g. founder replied with text YES / NO)
        if "message" in payload_dict:
            msg = payload_dict["message"]
            chat = msg.get("chat", {})
            sender = msg.get("from", {})
            text = msg.get("text")

            return TelegramWebhookEvent(
                event_type="message",
                chat_id=str(chat.get("id", "")),
                sender_id=str(sender.get("id", "")),
                message_id=str(msg.get("message_id", "")),
                text_body=text,
                raw_data=payload_dict,
            )

        return None
