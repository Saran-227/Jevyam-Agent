"""Script to invalidate exposed approval tokens, generate a fresh token, and resend Telegram preview."""

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.services.approval_service import ApprovalService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from integrations.telegram.models import TelegramApprovalMessagePayload
from integrations.telegram.provider import get_telegram_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jevyam.resend_approval")


def main():
    print("=" * 70)
    print("JEVYAM TECHNOLOGIES -- SECURE APPROVAL TOKEN ROTATION & DISPATCH")
    print("=" * 70)

    post_id = "JVY-20261105-001"
    post_file = Path(f"data/posts/{post_id}.json")
    img_file = Path(f"data/posts/{post_id}.png")

    assert post_file.exists(), f"Post file {post_file} not found"
    assert img_file.exists(), f"Image file {img_file} not found"

    # 1. Invalidate all existing tokens for this post in data/approvals/approvals.json
    approvals_path = Path("data/approvals/approvals.json")
    invalidated_count = 0
    if approvals_path.exists():
        approvals_data = json.loads(approvals_path.read_text(encoding="utf-8"))
        now_iso = datetime.now().isoformat()
        for tok, appr in approvals_data.items():
            if appr.get("post_id") == post_id and appr.get("status") == "PENDING":
                appr["status"] = "REJECTED"
                appr["rejected_at"] = now_iso
                appr["rejection_reason"] = "Security rotation: previously exposed token invalidated."
                invalidated_count += 1
        approvals_path.write_text(json.dumps(approvals_data, indent=2), encoding="utf-8")
        print(f"[1/4] Invalidated {invalidated_count} prior pending approval token(s) for {post_id}.")

    # 2. Initialize repository manager and load post
    repo_manager = create_in_memory_repository_manager()
    post_record = repo_manager.posts.get_by_post_id(post_id)
    if not post_record:
        raw_post = json.loads(post_file.read_text(encoding="utf-8"))
        post_record = Post(
            post_id=post_id,
            current_revision=raw_post.get("revision", 1),
            status=PostStatus.PENDING_APPROVAL,
            topic=raw_post.get("topic", ""),
            angle=raw_post.get("angle", ""),
            target_audience=raw_post.get("target_audience", ""),
            content_type=raw_post.get("content_type", "03. Custom Software Development | Service Spotlight"),
            hook=raw_post.get("hook", ""),
            caption=raw_post.get("caption", ""),
            hashtags=raw_post.get("hashtags", []),
            call_to_action=raw_post.get("call_to_action", ""),
            visual_concept=raw_post.get("visual_concept", ""),
            image_url=raw_post.get("image_url"),
            image_brief=raw_post.get("image_brief", {}),
        )
        repo_manager.posts.create(post_record)
    else:
        post_record.status = PostStatus.PENDING_APPROVAL
        repo_manager.posts.update(post_record)

    # 3. Create fresh approval token
    approval_service = ApprovalService(repo_manager=repo_manager)
    fresh_approval = approval_service.create_approval_request(
        post_id=post_id,
        revision_number=post_record.current_revision,
    )
    fresh_token = fresh_approval.approval_token
    print(f"[2/4] Generated brand-new secure approval token: {fresh_token[:10]}...[REDACTED]")
    print(f"      Mapped Post ID: {fresh_approval.post_id}, Revision: {fresh_approval.revision_number}")

    # 4. Dispatch Telegram approval preview with fresh buttons
    print(f"[3/4] Dispatching fresh Telegram approval message to Chat ID: {settings.TELEGRAM_FOUNDER_CHAT_ID}...")
    telegram_provider = get_telegram_provider()
    
    base_url = settings.APP_BASE_URL.rstrip("/")
    payload = TelegramApprovalMessagePayload(
        post_id=post_record.post_id,
        revision_number=post_record.current_revision,
        hook=post_record.hook,
        caption=post_record.caption,
        hashtags=post_record.hashtags,
        visual_concept=post_record.visual_concept,
        approval_token=fresh_token,
        approval_url=f"{base_url}/approve/{fresh_token}",
        image_url=post_record.image_url,
        expires_at=fresh_approval.expires_at,
        chat_id=settings.TELEGRAM_FOUNDER_CHAT_ID,
    )

    telegram_resp = telegram_provider.send_approval_message(payload)
    print(f"[4/4] Telegram Dispatch Outcome:")
    print(f"      Success: {telegram_resp.success}")
    print(f"      Message ID: {telegram_resp.message_id}")
    print(f"      Chat ID: {telegram_resp.chat_id}")
    if telegram_resp.error:
        print(f"      Error: {telegram_resp.error}")

    # Update summary file
    summary_path = Path("data/posts/first_real_post_summary.json")
    if summary_path.exists():
        summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_data["post_id"] = post_id
        summary_data["approval_token"] = "[REDACTED_SECURE_TOKEN]"
        summary_data["telegram_message_id"] = telegram_resp.message_id
        summary_data["status"] = "PENDING_APPROVAL"
        summary_data["dry_run"] = settings.DRY_RUN
        summary_data["linkedin_mock_publishing"] = settings.LINKEDIN_MOCK_PUBLISHING
        summary_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    print("\n" + "=" * 70)
    print("FRESH APPROVAL READY")
    print(f"Post ID: {post_id}")
    print(f"Telegram Message ID: {telegram_resp.message_id}")
    print(f"Database Status: {post_record.status.value}")
    print(f"Safety: DRY_RUN={settings.DRY_RUN}, MOCK={settings.LINKEDIN_MOCK_PUBLISHING}")
    print("=" * 70)


if __name__ == "__main__":
    main()
