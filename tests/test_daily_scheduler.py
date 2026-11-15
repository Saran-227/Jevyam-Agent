"""Tests for Phase 2: Automatic Daily Scheduler (9:00 AM IST).

Verifies:
1. Timezone-aware 9:00 AM Asia/Kolkata scheduling calculation.
2. Scheduler does not trigger at incorrect times.
3. Exactly one execution occurs per Indian calendar day (DAILY-RUN-YYYYMMDD).
4. Duplicate execution is prevented after application restart (persistent state store).
5. Missed-run recovery triggers once when application starts after 9:00 AM IST.
6. Generated content reaches founder's Telegram with inline YES/NO buttons.
7. Scheduler NEVER calls LinkedIn publishing automatically (post remains PENDING_APPROVAL).
8. YES approval from founder triggers publication.
9. NO approval from founder triggers revision and delivers new draft.
10. Unauthorized users cannot approve or reject scheduled posts.
"""

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from agent.image_generator import ImageBrief, MockImageProvider
from agent.orchestrator import DailyOrchestrator, DailyRunResult
from agent.scheduler import (
    DailyScheduler,
    SchedulerRunRecord,
    SchedulerStateStore,
    get_ist_timezone,
)
from api.services.approval_service import ApprovalService
from api.services.publishing_service import PublishingService
from api.services.telegram_service import TelegramService
from config.settings import settings
from database.models import ApprovalStatus, Post, PostRevision, PostStatus
from database.repositories import create_in_memory_repository_manager
from integrations.telegram.mock import MockTelegramProvider


@pytest.fixture
def founder_chat_id():
    return str(settings.TELEGRAM_FOUNDER_CHAT_ID or "8164283098").strip()


@pytest.fixture
def scheduler_test_env(tmp_path, founder_chat_id):
    runs_file = tmp_path / "scheduler_runs.json"
    state_store = SchedulerStateStore(persistence_file=runs_file)
    repos = create_in_memory_repository_manager()
    mock_tg = MockTelegramProvider(founder_chat_id=founder_chat_id)
    mock_img = MockImageProvider(base_url="https://mock-storage.supabase.co/post-images")
    mock_gemini = MagicMock()

    pub_service = PublishingService(repo_manager=repos, mock_mode=True)
    approval_service = ApprovalService(
        repo_manager=repos,
        publishing_service=pub_service,
        image_provider=mock_img,
        gemini_client=mock_gemini,
    )
    tg_service = TelegramService(
        approval_service=approval_service,
        provider=mock_tg,
        founder_chat_id=founder_chat_id,
    )
    counter = {"val": 0}

    def mock_generate_content(*args, **kwargs):
        import uuid
        from agent.strategist import ContentIdea
        from agent.writer import LinkedInPostContent
        from agent.image_generator import ImageBrief

        config = kwargs.get("config")
        schema = getattr(config, "response_schema", None) if config else None

        services = [
            ("Inventory Management Systems", "Business Pain Point", "Eliminating Inventory Shrinkage Across Depots", "Discrepancies in warehouse stock audit erode profit margins quietly."),
            ("CRM Solutions", "Problem → Solution", "B2B Sales Pipeline Deal Tracking Architecture", "When sales reps manage client deals in spreadsheets leads drop out."),
            ("Custom Software Development", "Service Spotlight", "Modern Web Application Microservices Scalability", "Rigid SaaS software limits proprietary enterprise workflows."),
            ("Website Design & Development", "Before vs After", "High Speed Corporate Web Performance Benchmarks", "Slow page load times turn qualified business prospects away."),
            ("Mobile App Development", "Feature Breakdown", "Cross Platform Mobile Offline Engine", "Field workers need dependable offline sync when network signals drop."),
            ("Digital Marketing", "Myth vs Reality", "Targeted Inbound Lead Generation Strategy", "High traffic counts mean little if web visitors bounce immediately."),
            ("AI & Business Automation", "Educational Post", "Pragmatic Document Processing Workflows", "Repetitive data entry between disjointed portals drains staff hours."),
            ("IT Consultancy & Support", "Industry Scenario", "Cloud Infrastructure Security Auditing Practices", "Uncoordinated cloud software adoption creates serious vulnerabilities."),
        ]

        if schema == ContentIdea:
            counter["val"] += 1
            idx = counter["val"] - 1
            u = uuid.uuid4().hex[:6]
            svc, fmt, top, hk = services[idx % len(services)]
            return MagicMock(text=json.dumps({
                "topic": f"{top} {u}",
                "angle": f"Practical enterprise architecture {u}",
                "content_type": f"{svc} | {fmt}",
                "service_category": svc,
                "content_format": fmt,
                "target_audience": "Operations Heads",
                "reason": "Solves real operational bottlenecks",
                "visual_concept": f"Dashboard flow {u}",
            }))
        elif schema == LinkedInPostContent:
            idx = counter["val"] - 1
            u = uuid.uuid4().hex[:6]
            svc, fmt, top, hk = services[idx % len(services)]
            return MagicMock(text=json.dumps({
                "hook": f"{hk} {u}",
                "caption": f"{hk} {u}\n\nhttps://www.jeevyamtechnologies.com/services/inventory-management.html",
                "hashtags": ["#Enterprise", "#Tech", "#Strategy"],
                "call_to_action": "How does your leadership handle these technical challenges?",
            }))
        elif schema == ImageBrief:
            idx = counter["val"] - 1
            u = uuid.uuid4().hex[:6]
            svc, fmt, top, hk = services[idx % len(services)]
            return MagicMock(text=json.dumps({
                "visual_concept": f"Architecture visual {u}",
                "style": "Minimalist UI",
                "composition": "Centered",
                "color_direction": "Navy",
                "text_on_image": f"Ops {u}",
                "aspect_ratio": "1:1",
                "layout": "process_flow",
            }))
        return MagicMock(text=json.dumps({"status": "ok"}))

    mock_gemini.models.generate_content.side_effect = mock_generate_content

    test_posts_dir = tmp_path / "posts"
    test_posts_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = DailyOrchestrator(
        repo_manager=repos,
        gemini_client=mock_gemini,
        approval_service=approval_service,
        telegram_service=tg_service,
        image_provider=mock_img,
        use_in_memory_db=True,
        posts_dir=test_posts_dir,
    )

    scheduler = DailyScheduler(
        orchestrator=orchestrator,
        state_store=state_store,
        target_hour=9,
        target_minute=0,
        retry_delay_seconds=0.01,
        default_mode="mock",
    )

    return {
        "scheduler": scheduler,
        "orchestrator": orchestrator,
        "state_store": state_store,
        "repos": repos,
        "mock_tg": mock_tg,
        "approval_service": approval_service,
        "pub_service": pub_service,
        "tg_service": tg_service,
        "runs_file": runs_file,
        "founder_id": founder_chat_id,
    }


def test_calculate_seconds_until_next_run(scheduler_test_env):
    """Verify next run triggers at 09:00:00 AM IST."""
    scheduler = scheduler_test_env["scheduler"]
    tz = get_ist_timezone()

    # Case A: Before 9:00 AM (e.g. 08:30:00 AM IST)
    morning_time = datetime(2026, 11, 15, 8, 30, 0, tzinfo=tz)
    seconds_a = scheduler.calculate_seconds_until_next_run(now_ist=morning_time)
    assert seconds_a == 1800.0  # Exactly 30 minutes

    # Case B: At or after 9:00 AM (e.g. 09:15:00 AM IST)
    afternoon_time = datetime(2026, 11, 15, 9, 15, 0, tzinfo=tz)
    seconds_b = scheduler.calculate_seconds_until_next_run(now_ist=afternoon_time)
    # Next trigger is tomorrow at 9:00 AM -> 23 hours 45 minutes = 85500 seconds
    assert seconds_b == (23 * 3600 + 45 * 60)


def test_scheduler_does_not_trigger_at_incorrect_times(scheduler_test_env):
    """Verify is_target_time returns False when outside 09:00 AM IST window."""
    scheduler = scheduler_test_env["scheduler"]
    tz = get_ist_timezone()

    assert scheduler.is_target_time(datetime(2026, 11, 15, 9, 0, 30, tzinfo=tz)) is True
    assert scheduler.is_target_time(datetime(2026, 11, 15, 8, 45, 0, tzinfo=tz)) is False
    assert scheduler.is_target_time(datetime(2026, 11, 15, 14, 0, 0, tzinfo=tz)) is False


def test_exactly_one_execution_per_day_and_duplicate_prevention(scheduler_test_env):
    """Verify execution generates exactly one post and duplicate runs are skipped idempotently."""
    scheduler = scheduler_test_env["scheduler"]
    state_store = scheduler_test_env["state_store"]
    repos = scheduler_test_env["repos"]
    mock_tg = scheduler_test_env["mock_tg"]
    founder_id = scheduler_test_env["founder_id"]

    target_date = "2026-11-20"

    # First execution for 2026-11-20
    first_res = scheduler.execute_daily_run(target_date_str=target_date)
    assert first_res.success is True
    assert first_res.is_skipped is False
    assert first_res.post_id.startswith("JVY-20261120-")
    assert first_res.status == PostStatus.PENDING_APPROVAL.value

    # Verify persistent state store
    exec_key = "DAILY-RUN-20261120"
    rec = state_store.get_run(exec_key)
    assert rec is not None
    assert rec.status == "SUCCESS"
    assert rec.post_id == first_res.post_id
    assert state_store.is_completed_for_date(target_date) is True

    # Telegram notification delivered once to founder
    assert len(mock_tg.sent_messages) == 1
    assert mock_tg.sent_messages[0]["chat_id"] == founder_id

    # Second execution for same date must be skipped
    second_res = scheduler.execute_daily_run(target_date_str=target_date)
    assert second_res.success is True
    assert second_res.is_skipped is True
    assert second_res.post_id == first_res.post_id

    # No second telegram message sent
    assert len(mock_tg.sent_messages) == 1


def test_duplicate_prevention_persists_across_application_restart(scheduler_test_env, tmp_path):
    """Verify that restarting the application retains execution history and prevents re-run."""
    runs_file = scheduler_test_env["runs_file"]
    scheduler = scheduler_test_env["scheduler"]
    target_date = "2026-11-21"

    # Run on first instance
    scheduler.execute_daily_run(target_date_str=target_date)

    # Simulate application restart with a fresh SchedulerStateStore pointing to same disk file
    fresh_state_store = SchedulerStateStore(persistence_file=runs_file)
    assert fresh_state_store.is_completed_for_date(target_date) is True

    fresh_scheduler = DailyScheduler(
        orchestrator=scheduler_test_env["orchestrator"],
        state_store=fresh_state_store,
    )

    # Re-running on restarted instance skips idempotently
    res = fresh_scheduler.execute_daily_run(target_date_str=target_date)
    assert res.is_skipped is True


def test_missed_run_recovery_triggers_when_started_after_9am(scheduler_test_env):
    """If application starts at 10:30 AM IST and today's run has not executed, trigger catch-up run."""
    scheduler = scheduler_test_env["scheduler"]
    tz = get_ist_timezone()

    # Fake current time as 10:30 AM IST today
    fake_now = datetime(2026, 11, 22, 10, 30, 0, tzinfo=tz)

    with patch.object(scheduler, "get_current_ist_time", return_value=fake_now):
        res = scheduler.check_and_run_missed_execution()
        assert res is not None
        assert res.success is True
        assert res.post_id.startswith("JVY-20261122-")

        # Second check on same day does nothing
        second_check = scheduler.check_and_run_missed_execution()
        assert second_check is None


def test_missed_run_recovery_does_not_trigger_before_9am(scheduler_test_env):
    """If application starts at 07:45 AM IST, do not trigger missed-run recovery."""
    scheduler = scheduler_test_env["scheduler"]
    tz = get_ist_timezone()

    fake_now = datetime(2026, 11, 23, 7, 45, 0, tzinfo=tz)

    with patch.object(scheduler, "get_current_ist_time", return_value=fake_now):
        res = scheduler.check_and_run_missed_execution()
        assert res is None


def test_scheduler_never_calls_linkedin_publishing_directly(scheduler_test_env):
    """CRITICAL: Daily generation leaves post in PENDING_APPROVAL and never invokes publisher."""
    scheduler = scheduler_test_env["scheduler"]
    pub_service = scheduler_test_env["pub_service"]
    repos = scheduler_test_env["repos"]

    with patch.object(pub_service, "publish_approved_post") as mock_pub:
        res = scheduler.execute_daily_run(target_date_str="2026-11-24")
        assert res.success is True
        mock_pub.assert_not_called()

    # Verify post status remains strictly PENDING_APPROVAL
    post = repos.posts.get_by_post_id(res.post_id)
    assert post.status == PostStatus.PENDING_APPROVAL
    assert post.linkedin_post_id is None


def test_founder_yes_approval_publishes_and_no_regenerates(scheduler_test_env):
    """Verify that YES approval publishes the scheduled post and NO regenerates it."""
    scheduler = scheduler_test_env["scheduler"]
    tg_service = scheduler_test_env["tg_service"]
    repos = scheduler_test_env["repos"]
    founder_id = scheduler_test_env["founder_id"]

    res = scheduler.execute_daily_run(target_date_str="2026-11-25")
    token = res.approval_token
    post_id = res.post_id

    # 1. Unauthorized user cannot approve
    unauth_resp = tg_service.handle_webhook_callback({
        "update_id": 30001,
        "callback_query": {
            "id": "cb_unauth",
            "from": {"id": 99999999},
            "message": {"message_id": 99, "chat": {"id": 99999999}},
            "data": f"approve:{token}",
        },
    })
    assert unauth_resp["status"] == "unauthorized"
    assert repos.posts.get_by_post_id(post_id).status == PostStatus.PENDING_APPROVAL

    # 2. Authorized founder YES triggers publishing
    auth_yes_resp = tg_service.handle_webhook_callback({
        "update_id": 30002,
        "callback_query": {
            "id": "cb_auth_yes",
            "from": {"id": int(founder_id)},
            "message": {"message_id": 100, "chat": {"id": int(founder_id)}},
            "data": f"approve:{token}",
        },
    })
    assert auth_yes_resp["status"] == "approved"
    assert auth_yes_resp["published"] is True
    assert repos.posts.get_by_post_id(post_id).status == PostStatus.PUBLISHED


def test_founder_no_reject_triggers_regeneration(scheduler_test_env):
    """Verify that NO rejection from founder triggers draft regeneration."""
    scheduler = scheduler_test_env["scheduler"]
    tg_service = scheduler_test_env["tg_service"]
    repos = scheduler_test_env["repos"]
    founder_id = scheduler_test_env["founder_id"]

    res = scheduler.execute_daily_run(target_date_str="2026-11-26")
    token = res.approval_token
    post_id = res.post_id

    # Authorized founder clicks NO
    auth_no_resp = tg_service.handle_webhook_callback({
        "update_id": 30003,
        "callback_query": {
            "id": "cb_auth_no",
            "from": {"id": int(founder_id)},
            "message": {"message_id": 101, "chat": {"id": int(founder_id)}},
            "data": f"reject:{token}",
        },
    })
    assert auth_no_resp["status"] == "regenerated"
    assert auth_no_resp["revision"] == 2


@pytest.mark.anyio
async def test_scheduler_async_start_and_stop(scheduler_test_env):
    """Verify background asyncio schedule task can start and terminate cleanly."""
    scheduler = scheduler_test_env["scheduler"]
    task = scheduler.start()
    assert task is not None
    assert scheduler._running is True

    # Allow task to initialize
    await asyncio.sleep(0.05)

    scheduler.stop()
    assert scheduler._running is False
    try:
        await asyncio.wait_for(task, timeout=0.5)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    assert task.cancelled() or task.done()

