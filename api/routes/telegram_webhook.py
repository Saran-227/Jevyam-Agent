"""FastAPI router for Telegram Bot API webhook callbacks and inline button updates."""

import json
import logging
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from starlette.requests import ClientDisconnect

from api.dependencies import get_telegram_service
from api.services.telegram_service import TelegramService

logger = logging.getLogger("jevyam.telegram_webhook")
router = APIRouter(prefix="", tags=["Telegram Webhook"])


@router.post("/telegram/webhook", summary="Telegram Bot Webhook Inbound Updates")
@router.post("/webhook/telegram", summary="Telegram Bot Webhook Inbound Updates (Alias)")
async def receive_telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
    telegram_service: TelegramService = Depends(get_telegram_service),
):
    """Receives inbound Telegram Bot API updates (inline button callbacks and messages).

    Validates secret token header against configured TELEGRAM_WEBHOOK_SECRET,
    processes callback queries idempotently, and acknowledges rapidly (< 100ms)
    to prevent Telegram and Cloudflare proxy connection timeouts.

    Limitation: Long-running background operations (such as AI draft regeneration)
    scheduled via FastAPI BackgroundTasks run in-process on a worker thread pool and
    are not durable across sudden process crashes.
    """
    try:
        raw_body = await request.body()
    except ClientDisconnect:
        logger.warning("Telegram client disconnected before request body could be read.")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "aborted", "message": "Client disconnected before request body was received."},
        )

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "message": "Malformed JSON payload."},
        )

    result = telegram_service.handle_webhook_callback(
        payload_dict=payload,
        secret_token_header=x_telegram_bot_api_secret_token,
        background_tasks=background_tasks,
    )

    if result.get("code") == "AUTH_FAILED":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=result,
        )

    # For all processed or ignored callbacks, return HTTP 200 to acknowledge delivery to Telegram
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result,
    )
