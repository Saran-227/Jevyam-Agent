"""CLI tool to publish or retry publishing an approved post to LinkedIn.

Usage:
    python scripts/publish_post.py --post-id JVY-20261122-001
    python scripts/publish_post.py --post-id JVY-20261120-001 --force
    python scripts/publish_post.py --post-id JVY-20261122-001 --dry-run
"""

import argparse
import html
import logging
from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from database.repositories import get_repository_manager
from api.services.publishing_service import PublishingService
from api.services.telegram_service import TelegramService

logger = logging.getLogger("jevyam.publisher_cli")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish an approved post to LinkedIn Company Page.")
    parser.add_argument("--post-id", required=True, help="Post ID (e.g. JVY-20261122-001)")
    parser.add_argument("--force", action="store_true", help="Bypass idempotency duplicate check")
    parser.add_argument("--dry-run", action="store_true", help="Simulate publication without live LinkedIn API calls")
    parser.add_argument("--notify-telegram", action="store_true", help="Send publication notification to Telegram")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    post_id = args.post_id.strip()
    is_mock = args.dry_run or settings.DRY_RUN or settings.LINKEDIN_MOCK_PUBLISHING

    logger.info(f"Initializing PublishingService (mock_mode={is_mock}) for post: {post_id}")
    repo_manager = get_repository_manager()
    publishing_service = PublishingService(repo_manager=repo_manager, mock_mode=is_mock)

    try:
        result = publishing_service.publish_approved_post(post_id=post_id, force=args.force)
        print("\n" + "=" * 60)
        print("PUBLICATION RESULT:")
        print(f"Status: {result.get('status')}")
        print(f"Post ID: {result.get('post_id')}")
        print(f"Revision: {result.get('revision')}")
        print(f"External Post ID / URN: {result.get('external_post_id')}")
        print(f"Post URL: {result.get('post_url')}")
        print(f"Message: {result.get('message')}")
        print("=" * 60 + "\n")

        if args.notify_telegram:
            telegram_service = TelegramService()
            founder_chat = settings.TELEGRAM_FOUNDER_CHAT_ID
            admin_chat = settings.TELEGRAM_ADMIN_CHAT_ID

            pub_text = (
                f"🔗 <b>LinkedIn URL:</b> {result.get('post_url')}\n"
                f"🆔 <b>Post URN:</b> <code>{result.get('external_post_id') or 'N/A'}</code>"
            )
            msg = f"✅ <b>Post Published!</b> Post <code>{post_id}</code> published to LinkedIn Company Page.\n\n{pub_text}"

            if founder_chat:
                telegram_service.provider.send_text_message(chat_id=founder_chat, text=msg)
            if admin_chat:
                telegram_service.send_admin_notification(msg)

        return 0

    except Exception as e:
        logger.error(f"Publication failed: {e}")
        print("\n" + "!" * 60)
        print(f"ERROR: {e}")
        print("!" * 60 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
