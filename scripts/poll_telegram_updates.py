"""Interactive long-polling listener for Telegram bot approvals (No tunnel required).

Allows the founder to test inline buttons (YES, PUBLISH / NO, REGENERATE) locally
without needing a public HTTPS webhook URL or tunnel.
"""

import logging
from pathlib import Path
import sys
import time

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.dependencies import get_telegram_service
from config.settings import settings
from integrations.telegram.client import mask_sensitive_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jevyam.telegram_poller")


def main():
    print("=" * 70)
    print("JEVYAM TECHNOLOGIES -- TELEGRAM APPROVAL POLLING LISTENER")
    print("=" * 70)

    tg_service = get_telegram_service()
    provider = tg_service.provider

    # 1. Inspect and clear webhook if set so getUpdates can receive callbacks
    print("\n[1/3] Inspecting webhook status...")
    info = provider._http_client.get(f"{provider._api_endpoint}/getWebhookInfo").json()
    webhook_url = info.get("result", {}).get("url")

    if webhook_url:
        print(f"  Notice: Active webhook was pointing to: {webhook_url}")
        print("  Temporarily deleting webhook to enable local getUpdates polling...")
        del_res = provider._http_client.post(f"{provider._api_endpoint}/deleteWebhook").json()
        print(f"  deleteWebhook response: {del_res.get('description', 'OK')}")

    print("\n[2/3] Initializing Telegram approval listener...")
    print(f"  Target Founder Chat ID: {settings.TELEGRAM_FOUNDER_CHAT_ID}")
    print(f"  Publishing Mode: DRY_RUN={settings.DRY_RUN}, MOCK={settings.LINKEDIN_MOCK_PUBLISHING}")
    print("\n[3/3] Listening for inline button clicks in Telegram...")
    print("  Go to Telegram (@jeevyam_bot) and tap [YES, PUBLISH] or [NO, REGENERATE]")
    print("  Press Ctrl+C to stop listening at any time.\n")

    offset = 0
    try:
        while True:
            try:
                resp = provider._http_client.get(
                    f"{provider._api_endpoint}/getUpdates",
                    params={"offset": offset, "timeout": 15},
                    timeout=20.0,
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.warning(f"getUpdates error: {data}")
                    time.sleep(2)
                    continue

                updates = data.get("result", [])
                for update in updates:
                    offset = max(offset, update["update_id"] + 1)
                    if "callback_query" in update:
                        cb = update["callback_query"]
                        data_val = cb.get("data", "")
                        user = cb.get("from", {}).get("first_name", "Founder")
                        print(f"\n[EVENT] Received button click from {user}: '{data_val}'")

                        # Process through authoritative TelegramService
                        result = tg_service.handle_webhook_callback(
                            update,
                            secret_token_header=settings.TELEGRAM_WEBHOOK_SECRET,
                            is_polling=True,
                        )
                        print(f"[RESULT] Decision outcome: {result}")

                    elif "message" in update and update["message"].get("text"):
                        txt = update["message"].get("text")
                        print(f"\n[MESSAGE] Received message: '{txt}'")
                        result = tg_service.handle_webhook_callback(
                            update,
                            secret_token_header=settings.TELEGRAM_WEBHOOK_SECRET,
                            is_polling=True,
                        )
                        print(f"[RESULT] Outcome: {result}")

            except Exception as e:
                safe_err = mask_sensitive_url(str(e))
                logger.warning(f"Transient polling error: {safe_err}")
                time.sleep(2)

    except KeyboardInterrupt:
        print("\nPolling stopped by user.")


if __name__ == "__main__":
    main()

