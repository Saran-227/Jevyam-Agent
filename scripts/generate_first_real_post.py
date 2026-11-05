"""Script to generate a fresh First Real LinkedIn Post for Jevyam Technologies and dispatch Telegram preview."""

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys

# Ensure repository root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.image_generator import BrandedPillowImageProvider
from agent.pipeline import LinkedInDraft, run_content_pipeline
from agent.strategist import ContentIdea
from api.services.approval_service import ApprovalService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from database.storage import MockStorageService
from integrations.gemini import get_gemini_client
from integrations.telegram.provider import get_telegram_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jevyam.first_post")


def main():
    parser = argparse.ArgumentParser(description="Generate First Real LinkedIn Post and dispatch preview to Telegram")
    parser.add_argument("--reuse", action="store_true", help="Reuse existing post if available instead of generating fresh")
    args = parser.parse_args()

    print("=" * 70)
    print("JEVYAM TECHNOLOGIES -- FIRST REAL LINKEDIN POST WORKFLOW")
    print("=" * 70)

    repo_manager = create_in_memory_repository_manager()
    today_str = datetime.now().strftime("%Y%m%d")
    today_post_id = f"JVY-{today_str}-001"
    existing_draft_file = Path(f"data/posts/{today_post_id}.json")
    local_img_path = Path(f"data/posts/{today_post_id}.png")

    if args.reuse and existing_draft_file.exists() and local_img_path.exists():
        print(f"[INFO] Reusing existing generated draft and branded PNG image ({today_post_id}):")
        print(f"  Draft: {existing_draft_file}")
        print(f"  Image: {local_img_path} ({local_img_path.stat().st_size} bytes)")
        raw_data = json.loads(existing_draft_file.read_text(encoding="utf-8"))
        draft = LinkedInDraft.model_validate(raw_data)
    else:
        print("\n[1/3] Generating fresh LinkedIn post and branded companion graphic...")
        first_post_idea = ContentIdea(
            topic='Company Introduction: "Your Business Needs More Than Just Software. It Needs the Right Technology Partner."',
            angle=(
                "Positioning Jevyam Technologies as an end-to-end technology and digital solutions partner, "
                "highlighting our full scope of practical business capabilities across: business management & CRM systems, "
                "custom software & mobile apps, digital marketing & SEO, practical AI & automation, and IT consultancy & support."
            ),
            content_type="03. Custom Software Development | Service Spotlight / Agency Introduction",
            target_audience="Founders, operations leaders, SME owners, and enterprise decision-makers seeking practical technology solutions",
            reason="Establishes credible agency positioning, dispels the misconception of one-size-fits-all software, and shows how a true technology partner aligns engineering with real business ROI.",
            estimated_value="Establishes credible agency positioning, dispels the misconception of one-size-fits-all software, and shows how a true technology partner aligns engineering with real business ROI.",
            service_pillar="03. Custom Software Development",
            content_format="Service Spotlight / Agency Introduction",
        )

        gemini_client = get_gemini_client()
        storage_service = MockStorageService()
        image_provider = BrandedPillowImageProvider(storage_service=storage_service)

        draft = run_content_pipeline(
            client=gemini_client,
            override_idea=first_post_idea,
            repo_manager=repo_manager,
            image_provider=image_provider,
            save_local_copy=True,
        )
        local_img_path = Path(f"data/posts/{draft.post_id}.png")

    # Seed in repository
    post_record = repo_manager.posts.get_by_post_id(draft.post_id)
    if not post_record:
        post_record = Post(
            post_id=draft.post_id,
            current_revision=draft.revision,
            status=PostStatus.PENDING_APPROVAL,
            topic=draft.topic,
            angle=draft.angle,
            target_audience=draft.target_audience,
            content_type=draft.content_type,
            hook=draft.hook,
            caption=draft.caption,
            hashtags=draft.hashtags,
            call_to_action=draft.call_to_action,
            visual_concept=draft.visual_concept,
            image_url=draft.image_url,
            image_brief=draft.image_brief.model_dump() if hasattr(draft.image_brief, "model_dump") else draft.image_brief,
        )
        repo_manager.posts.create(post_record)

        rev_record = PostRevision(
            post_id=draft.post_id,
            revision_number=draft.revision,
            topic=draft.topic,
            angle=draft.angle,
            target_audience=draft.target_audience,
            content_type=draft.content_type,
            hook=draft.hook,
            caption=draft.caption,
            hashtags=draft.hashtags,
            call_to_action=draft.call_to_action,
            visual_concept=draft.visual_concept,
            image_url=draft.image_url,
            image_brief=draft.image_brief.model_dump() if hasattr(draft.image_brief, "model_dump") else draft.image_brief,
        )
        repo_manager.revisions.create(rev_record)
    elif post_record.status == PostStatus.DRAFT:
        post_record = repo_manager.posts.update_status(post_record.post_id, PostStatus.PENDING_APPROVAL)

    print("\n[OK] Post registered in repository:")
    print(f"  Post ID: {post_record.post_id}")
    print(f"  Status: {post_record.status.value}")
    print(f"  Content Type: {draft.content_type}")
    print(f"  Image: {local_img_path.resolve()}")

    assert post_record.status == PostStatus.PENDING_APPROVAL, "Post status must be PENDING_APPROVAL"

    # Invalidate any prior pending approval tokens for this post to ensure freshness
    for prior_appr in repo_manager.approvals.get_by_post_id(draft.post_id):
        if prior_appr.status == ApprovalStatus.PENDING:
            repo_manager.approvals.update_status(prior_appr.approval_token, ApprovalStatus.REJECTED)

    # Create fresh approval request
    approval_service = ApprovalService(repo_manager=repo_manager)
    fresh_approval = approval_service.create_approval_request(
        post_id=draft.post_id,
        revision_number=draft.revision,
    )
    print(f"  Fresh Approval Token: {fresh_approval.approval_token}")

    # Dispatch Telegram approval preview to Founder
    print(f"\n[2/3] Dispatching preview to Telegram Founder (Chat ID: {settings.TELEGRAM_FOUNDER_CHAT_ID})...")
    telegram_provider = get_telegram_provider()
    telegram_service = TelegramService(approval_service=approval_service, provider=telegram_provider)

    telegram_resp = telegram_service.send_post_approval_notification(draft.post_id)

    print(f"\n[3/3] Telegram Dispatch Result:")
    print(f"  Success: {telegram_resp.success}")
    print(f"  Message ID: {telegram_resp.message_id}")
    print(f"  Chat ID: {telegram_resp.chat_id}")
    if telegram_resp.error:
        print(f"  Error: {telegram_resp.error}")

    # Print Post Caption for review
    print("\n" + "=" * 70)
    print("FIRST REAL LINKEDIN POST CAPTION:")
    print("=" * 70)
    print(draft.caption)
    print("\nHashtags: " + " ".join(draft.hashtags))
    print("=" * 70)

    # Save summary metadata
    summary_path = Path("data/posts/first_real_post_summary.json")
    summary_data = {
        "post_id": draft.post_id,
        "approval_token": fresh_approval.approval_token,
        "hook": draft.hook,
        "caption": draft.caption,
        "hashtags": draft.hashtags,
        "content_type": draft.content_type,
        "service_pillar": draft.content_type.split(" | ")[0] if " | " in draft.content_type else draft.content_type,
        "content_format": draft.content_format if hasattr(draft, "content_format") else "Service Spotlight",
        "image_url": draft.image_url,
        "local_image_path": str(local_img_path.resolve()) if local_img_path.exists() else None,
        "telegram_success": telegram_resp.success,
        "telegram_message_id": telegram_resp.message_id,
        "status": post_record.status.value,
        "dry_run": settings.DRY_RUN,
        "linkedin_mock_publishing": settings.LINKEDIN_MOCK_PUBLISHING,
    }
    summary_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    print(f"\nSummary metadata saved to {summary_path}")


if __name__ == "__main__":
    main()
