"""FastAPI router for Meta WhatsApp Cloud API webhook callbacks and verification."""

import json
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from api.dependencies import get_whatsapp_service
from api.services.whatsapp_service import WhatsAppService
from config.settings import settings

router = APIRouter(prefix="", tags=["WhatsApp Webhook"])


@router.get("/webhook/whatsapp", summary="Meta WhatsApp Webhook Verification Challenge")
async def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Handles the Meta developer challenge during webhook subscription setup.

    Meta sends:
    - hub.mode = 'subscribe'
    - hub.verify_token = <configured verification token>
    - hub.challenge = <random challenge string>

    Returns plain text challenge string with HTTP 200 on success.
    """
    expected_token = settings.WHATSAPP_VERIFY_TOKEN

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        return PlainTextResponse(content=hub_challenge or "", status_code=status.HTTP_200_OK)

    return PlainTextResponse(
        content="Forbidden: Verification token mismatch.",
        status_code=status.HTTP_403_FORBIDDEN,
    )


@router.post("/webhook/whatsapp", summary="Meta WhatsApp Incoming Events & Button Callbacks")
async def receive_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    whatsapp_service: WhatsAppService = Depends(get_whatsapp_service),
):
    """Receives inbound messages, statuses, and interactive button callbacks from Meta.

    Returns HTTP 200 rapidly to satisfy Meta webhook SLA, or HTTP 403 on signature failure.
    """
    raw_body = await request.body()

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"status": "error", "message": "Malformed JSON payload."},
        )

    result = whatsapp_service.handle_webhook_callback(
        payload_dict=payload,
        raw_body=raw_body,
        signature_header=x_hub_signature_256,
    )

    if result.get("code") == "AUTH_FAILED":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=result,
        )

    # For all processed or ignored callbacks, return HTTP 200 to acknowledge delivery
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result,
    )
