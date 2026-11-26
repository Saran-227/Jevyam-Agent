"""Tests for Member 2 (Dr. Sanjeev Sharma) informational Telegram notifications and v2/v3 alternation."""

from api.services.approval_service import ApprovalService
from api.services.telegram_service import TelegramService
from agent.design_system import select_alternating_v2_v3_layout
from database.models import Post, PostRevision, PostStatus
from database.repositories import RepositoryManager, get_repository_manager
from integrations.telegram.provider import MockTelegramProvider


def _seed_post(repos: RepositoryManager, post_id: str = "JVY-20261126-001") -> Post:
    brief_dict = {
        "visual_concept": "Clean blue and white editorial banner",
        "style": "Editorial",
        "composition": "Split",
        "color_direction": "Blue and white",
        "text_on_image": "Website Speed Matters",
    }
    post = Post(
        post_id=post_id,
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        topic="Website speed and lead conversion",
        angle="Slow templates lose buyers",
        content_type="Website Design & Development | Problem → Solution",
        target_audience="Founders",
        hook="Your website speed decides whether buyers stay.",
        caption="Your website speed decides whether buyers stay.\n\nClean engineering helps convert visitors.",
        hashtags=["#WebDesign", "#B2B", "#JevyamTechnologies"],
        call_to_action="When did you last test your mobile load speed?",
        visual_concept="Clean blue and white editorial banner",
        image_brief=brief_dict,
        image_url="https://mock-storage.supabase.co/storage/v1/object/public/post-images/JVY-20261126-001/rev_1.png",
    )
    repos.posts.create(post)
    repos.revisions.create(
        PostRevision(
            post_id=post_id,
            revision_number=1,
            topic=post.topic,
            angle=post.angle,
            content_type=post.content_type,
            target_audience=post.target_audience,
            hook=post.hook,
            caption=post.caption,
            hashtags=post.hashtags,
            call_to_action=post.call_to_action,
            visual_concept=post.visual_concept,
            image_brief=brief_dict,
            image_url=post.image_url,
        )
    )
    return post


def test_member2_receives_informational_preview_without_approval_buttons():
    repos = get_repository_manager(use_in_memory=True)
    _seed_post(repos, "JVY-20261126-001")
    provider = MockTelegramProvider(founder_chat_id="8164283098", admin_chat_id="1293148688")
    svc = TelegramService(
        approval_service=ApprovalService(repo_manager=repos),
        provider=provider,
        founder_chat_id="8164283098",
        admin_chat_id="1293148688",
        member2_chat_id="9988776655",
    )

    svc.send_post_approval_notification("JVY-20261126-001")

    approvals = [m for m in provider.sent_messages if m.get("type") == "approval_interactive"]
    previews = [m for m in provider.sent_messages if m.get("type") == "admin_preview"]
    assert len(approvals) == 1
    assert approvals[0]["chat_id"] == "8164283098"
    assert approvals[0]["buttons"] is not None
    assert len(previews) == 2
    assert [p["chat_id"] for p in previews] == ["1293148688", "9988776655"]
    for p in previews:
        assert p["buttons"] is None
        assert p["payload"]["post_id"] == "JVY-20261126-001"
        assert p["payload"]["revision_number"] == 1


def test_member2_receives_operational_notifications_without_duplicates():
    repos = get_repository_manager(use_in_memory=True)
    provider = MockTelegramProvider(founder_chat_id="8164283098", admin_chat_id="1293148688")
    svc = TelegramService(
        approval_service=ApprovalService(repo_manager=repos),
        provider=provider,
        founder_chat_id="8164283098",
        admin_chat_id="1293148688",
        member2_chat_id="9988776655",
    )

    svc.send_admin_notification("Daily run completed for JVY-20261126-001")
    text_chats = [m["chat_id"] for m in provider.sent_messages if m.get("type") == "text"]
    assert text_chats == ["1293148688", "9988776655"]

    # If Member 2 ID matches Admin ID, do not send duplicate
    provider.sent_messages.clear()
    svc.member2_chat_id = "1293148688"
    svc.send_admin_notification("No duplicate test")
    text_chats_after = [m["chat_id"] for m in provider.sent_messages if m.get("type") == "text"]
    assert len(text_chats_after) == 1


def test_member2_cannot_approve_reject_or_run_admin_commands():
    repos = get_repository_manager(use_in_memory=True)
    provider = MockTelegramProvider(founder_chat_id="8164283098", admin_chat_id="1293148688")
    svc = TelegramService(
        approval_service=ApprovalService(repo_manager=repos),
        provider=provider,
        founder_chat_id="8164283098",
        admin_chat_id="1293148688",
        member2_chat_id="9988776655",
    )

    assert svc.is_authorized_founder(chat_id="9988776655", sender_id="9988776655") is False
    assert svc.is_authorized_admin(chat_id="9988776655", sender_id="9988776655") is False
    assert svc.is_authorized_user(chat_id="9988776655", sender_id="9988776655") is False


def test_member2_notification_failure_does_not_interrupt_workflow():
    repos = get_repository_manager(use_in_memory=True)
    _seed_post(repos, "JVY-20261126-001")
    provider = MockTelegramProvider(founder_chat_id="8164283098", admin_chat_id="1293148688")

    orig_send_preview = provider.send_post_preview

    def flaky_preview(payload, chat_id=None, is_admin_preview=True):
        if str(chat_id) == "9988776655":
            raise RuntimeError("Simulated Telegram network error for Member 2")
        return orig_send_preview(payload, chat_id=chat_id, is_admin_preview=is_admin_preview)

    provider.send_post_preview = flaky_preview
    svc = TelegramService(
        approval_service=ApprovalService(repo_manager=repos),
        provider=provider,
        founder_chat_id="8164283098",
        admin_chat_id="1293148688",
        member2_chat_id="9988776655",
    )

    res = svc.send_post_approval_notification("JVY-20261126-001")
    assert res.success is True


def test_member2_invalid_chat_id_ignored():
    repos = get_repository_manager(use_in_memory=True)
    svc = TelegramService(
        approval_service=ApprovalService(repo_manager=repos),
        provider=MockTelegramProvider(),
        member2_chat_id="your_chat_id_here",
    )
    assert svc.member2_chat_id == ""


def test_v2_v3_alternating_layout_selection():
    l1 = select_alternating_v2_v3_layout("CRM Solutions", post_id="JVY-20261126-001")
    assert l1 != "landscape_banner"
    l2 = select_alternating_v2_v3_layout("CRM Solutions", post_id="JVY-20261126-002")
    assert l2 == "landscape_banner"
    l3 = select_alternating_v2_v3_layout("CRM Solutions", previous_layouts=["landscape_banner"])
    assert l3 != "landscape_banner"
    l4 = select_alternating_v2_v3_layout("CRM Solutions", previous_layouts=[l1])
    assert l4 == "landscape_banner"
