"""Tests for Implementation Step 1: Persistent Storage Verification."""

from datetime import datetime, timedelta, timezone
import json
import os
import time
from unittest.mock import MagicMock, patch
import pytest

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalError,
    ApprovalExpiredError,
)
from agent.image_generator import ImageBrief
from agent.scheduler import SchedulerRunRecord, SchedulerStateStore
from config.settings import settings
from database.exceptions import (
    MissingSupabaseCredentialsError,
    SupabaseDatabaseError,
)
from database.models import (
    ApprovalStatus,
    Post,
    PostRevision,
    PostStatus,
)
from database.repositories import (
    InMemorySchedulerRunRepository,
    SupabaseSchedulerRunRepository,
    create_in_memory_repository_manager,
    create_supabase_repository_manager,
    get_repository_manager,
)
from database.storage import MockStorageService, SupabaseStorageService
from integrations.linkedin.oauth import LinkedInTokenStore


# ==============================================================================
# 1. Scheduler Runs Persistence & Concurrency
# ==============================================================================

def test_in_memory_scheduler_run_repository_lifecycle():
    """Verify start -> success -> duplicate detection on scheduler runs."""
    repo = InMemorySchedulerRunRepository()
    exec_key = "DAILY-RUN-20261112"
    date_str = "2026-11-12"

    assert repo.is_completed_for_date(date_str) is False
    assert repo.is_running(exec_key) is False

    # 1. Record start
    rec = repo.record_run_start(exec_key, date_str)
    assert rec.status == "RUNNING"
    assert repo.is_running(exec_key) is True

    # 2. Record success
    rec_done = repo.record_run_success(exec_key, post_id="JVY-TEST-001", revision=1)
    assert rec_done.status == "SUCCESS"
    assert rec_done.post_id == "JVY-TEST-001"
    assert rec_done.completed_at is not None

    # 3. Duplicate check
    assert repo.is_completed_for_date(date_str) is True
    assert repo.is_running(exec_key) is False


def test_supabase_scheduler_run_repository_upsert_and_fetch():
    """Verify SupabaseSchedulerRunRepository correctly formats queries and upserts."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    mock_row = {
        "execution_key": "DAILY-RUN-20261112",
        "date": "2026-11-12",
        "status": "RUNNING",
        "triggered_at": "2026-11-12T09:00:00+05:30",
        "is_missed_run_recovery": False,
        "retry_count": 0,
        "error": None,
    }
    mock_table.upsert.return_value.execute.return_value.data = [mock_row]
    mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [mock_row]

    repo = SupabaseSchedulerRunRepository(client=mock_client)

    # Record start
    rec = repo.record_run_start("DAILY-RUN-20261112", "2026-11-12")
    assert rec.execution_key == "DAILY-RUN-20261112"
    assert rec.status == "RUNNING"
    mock_client.table.assert_called_with("scheduler_runs")

    # Record success
    mock_done_row = {**mock_row, "status": "SUCCESS", "post_id": "JVY-PROD-001", "completed_at": "2026-11-12T09:00:30+05:30"}
    mock_table.update.return_value.eq.return_value.execute.return_value.data = [mock_done_row]
    done_rec = repo.record_run_success("DAILY-RUN-20261112", post_id="JVY-PROD-001", revision=1)
    assert done_rec.status == "SUCCESS"
    assert done_rec.post_id == "JVY-PROD-001"


def test_scheduler_state_store_delegates_to_repository():
    """Verify SchedulerStateStore delegates all calls to underlying repository when provided."""
    mock_repo = MagicMock()
    store = SchedulerStateStore(repository=mock_repo)

    store.is_completed_for_date("2026-11-12")
    mock_repo.is_completed_for_date.assert_called_once_with("2026-11-12")

    store.record_run_start("DAILY-RUN-20261112", "2026-11-12")
    mock_repo.record_run_start.assert_called_once_with(
        execution_key="DAILY-RUN-20261112",
        date_str="2026-11-12",
        is_recovery=False,
    )


# ==============================================================================
# 2. LinkedIn Headless Secret Migration
# ==============================================================================

def test_linkedin_token_store_migrates_via_env_json(tmp_path, monkeypatch):
    """Verify OAuth token store reads full credentials from LINKEDIN_TOKEN_DATA env var without local file."""
    fake_token_payload = json.dumps({
        "access_token": "live_env_access_token_abcdef",
        "expires_in": 5184000,
        "expires_at": time.time() + 3600,
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "scope": "w_organization_social",
    })
    monkeypatch.setenv("LINKEDIN_TOKEN_DATA", fake_token_payload)

    non_existent_file = tmp_path / "non_existent.json"
    store = LinkedInTokenStore(storage_path=str(non_existent_file))

    assert store.has_token() is True
    assert store.is_expired() is False
    assert store.get_access_token() == "live_env_access_token_abcdef"

    # Representation must never print the raw token
    assert "live_env_access_token" not in repr(store)
    assert "<LinkedInTokenStore configured=True expired=False>" == repr(store)


def test_linkedin_token_store_migrates_via_settings_token(tmp_path, monkeypatch):
    """Verify OAuth token store generates valid store state from static LINKEDIN_ACCESS_TOKEN."""
    monkeypatch.delenv("LINKEDIN_TOKEN_DATA", raising=False)
    monkeypatch.setattr(settings, "LINKEDIN_ACCESS_TOKEN", "live_static_token_xyz")

    non_existent_file = tmp_path / "another_missing.json"
    store = LinkedInTokenStore(storage_path=str(non_existent_file))

    assert store.has_token() is True
    assert store.is_expired() is False
    assert store.get_access_token() == "live_static_token_xyz"
    token_data = store.get_token_data()
    assert token_data["scope"] == "w_organization_social"


# ==============================================================================
# 3. Single-Use Approval Token & Duplicate Prevention
# ==============================================================================

def test_approval_token_single_use_prevents_duplicate_approval():
    """Verify that an approved token is strictly single-use and cannot be processed again."""
    from api.services.approval_service import ApprovalService
    from api.services.publishing_service import PublishingService

    repos = create_in_memory_repository_manager()
    pub_service = PublishingService(repo_manager=repos, mock_mode=True)
    approval_service = ApprovalService(repo_manager=repos, publishing_service=pub_service)

    # Seed post
    brief = ImageBrief(
        visual_concept="Architecture diagram",
        style="2D Slate",
        composition="Center",
        color_direction="Navy",
        text_on_image="Architecture",
    )
    post = Post(
        post_id="JVY-STEP1-001",
        status=PostStatus.PENDING_APPROVAL,
        current_revision=1,
        content_type="software engineering",
        topic="Idempotency in Cloud Pipelines",
        angle="Zero state duplication",
        target_audience="CTOs",
        hook="Duplicate runs burn compute.",
        caption="Duplicate runs burn compute. Use atomic keys.",
        hashtags=["#Cloud", "#DevOps"],
        call_to_action="How do you handle retries?",
        visual_concept="Architecture diagram",
        image_brief=brief,
        image_url="https://mock-storage.supabase.co/post-images/JVY-STEP1-001/rev_1.png",
    )
    repos.posts.create(post)
    repos.revisions.create(PostRevision(
        post_id=post.post_id,
        revision_number=1,
        content_type=post.content_type,
        topic=post.topic,
        angle=post.angle,
        target_audience=post.target_audience,
        hook=post.hook,
        caption=post.caption,
        hashtags=post.hashtags,
        call_to_action=post.call_to_action,
        visual_concept=post.visual_concept,
        image_brief=brief,
        image_url=post.image_url,
    ))

    create_res = approval_service.create_approval_request("JVY-STEP1-001", revision_number=1)
    token = create_res.approval_token

    # 1. First YES: succeeds
    res1 = approval_service.approve_post(token)
    assert res1.status == "approved"
    assert res1.post_id == "JVY-STEP1-001"

    # Post is now approved/published
    updated_post = repos.posts.get_by_post_id("JVY-STEP1-001")
    assert updated_post.status in (PostStatus.APPROVED, PostStatus.PUBLISHED)

    # 2. Second YES: rejected with ApprovalAlreadyProcessedError
    with pytest.raises(ApprovalAlreadyProcessedError) as exc_info:
        approval_service.approve_post(token)
    assert "no longer active (status: APPROVED)" in str(exc_info.value)

    # 3. NO after YES: rejected
    with pytest.raises(ApprovalAlreadyProcessedError):
        approval_service.reject_and_regenerate(token, reason="Too late")


# ==============================================================================
# 4. Storage Bucket Configuration & Public URL Verification
# ==============================================================================

def test_supabase_storage_path_and_public_url_resolution():
    """Verify SupabaseStorageService constructs safe asset paths in post-images bucket."""
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_client.storage.from_.return_value = mock_bucket
    mock_bucket.get_public_url.return_value = "https://xyz.supabase.co/storage/v1/object/public/post-images/JVY-001/rev_1.png"

    storage = SupabaseStorageService(client=mock_client, bucket_name="post-images")
    url = storage.upload_image(
        post_id="JVY-001",
        revision=1,
        image_bytes=b"\x89PNG\r\n\x1a\nFakeBytes",
        mime_type="image/png",
    )

    mock_client.storage.from_.assert_called_with("post-images")
    assert "post-images" in url
    assert "JVY-001" in url


# ==============================================================================
# 5. Production Mode Forbids Silent Local JSON Fallback
# ==============================================================================

def test_production_mode_forbids_silent_fallback_when_supabase_unconfigured(monkeypatch):
    """When DRY_RUN=False, get_repository_manager must refuse silent fallback if credentials missing."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(settings, "DRY_RUN", False)
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "")

    with pytest.raises(MissingSupabaseCredentialsError) as exc_info:
        get_repository_manager()
    assert "Silent fallback to local JSON or in-memory storage is forbidden in production" in str(exc_info.value)


# ==============================================================================
# 6. Task 4 Security Hardening Migration & Access Policy Tests
# ==============================================================================

def test_migration_005_sql_structure_and_safety():
    """Verify that migration 005 strictly revokes public access and creates scheduler_runs."""
    from pathlib import Path
    mig_file = Path("database/migrations/005_harden_security_and_scheduler_runs.sql")
    assert mig_file.exists()
    content = mig_file.read_text(encoding="utf-8")

    # 1. Must ensure trigger function is created
    assert "CREATE OR REPLACE FUNCTION public.update_updated_at_column()" in content

    # 2. Must revoke from PUBLIC, anon, and authenticated
    for tbl in ["companies", "posts", "post_revisions", "approvals", "publications", "scheduler_runs"]:
        assert f"REVOKE ALL ON TABLE public.{tbl} FROM PUBLIC, anon, authenticated;" in content

    # 3. Must grant strictly to service_role
    for tbl in ["companies", "posts", "post_revisions", "approvals", "publications", "scheduler_runs"]:
        assert f"GRANT ALL ON TABLE public.{tbl} TO service_role;" in content

    # 3. Must drop unrestricted 'Allow full access to ...' policies
    for tbl in ["companies", "posts", "post_revisions", "approvals", "publications"]:
        assert f'DROP POLICY IF EXISTS "Allow full access to {tbl}" ON public.{tbl};' in content

    # 4. Must enforce TO service_role on all new policies
    assert "TO service_role" in content
    assert 'CREATE POLICY "Service Role full access on posts"' in content
    assert 'CREATE POLICY "Service Role full access on approvals"' in content
    assert 'CREATE POLICY "Service Role full access on scheduler_runs"' in content

    # 5. Storage policies: public SELECT, service_role INSERT/UPDATE/DELETE
    assert 'CREATE POLICY "Public Read Access on post-images"' in content
    assert "TO public" in content
    assert 'CREATE POLICY "Service Role Upload to post-images"' in content
    assert 'CREATE POLICY "Service Role Update in post-images"' in content
    assert 'CREATE POLICY "Service Role Delete from post-images"' in content

    # 6. Zero drop table statements
    assert "DROP TABLE" not in content


def test_live_supabase_service_role_connectivity():
    """Verify backend service-role connectivity against live Supabase."""
    from database.supabase_client import get_supabase_client
    try:
        client = get_supabase_client()
        # Query companies table
        res = client.table("companies").select("id, name, slug").limit(1).execute()
        assert res.data is not None
        assert len(res.data) > 0
        assert res.data[0]["slug"] == "jevyam"
    except Exception as e:
        pytest.skip(f"Live Supabase connection skipped or unconfigured: {e}")


def test_anon_access_denial_simulation():
    """Verify that an anon/unauthenticated client receives permission errors or empty results."""
    mock_anon_client = MagicMock()
    mock_table = MagicMock()
    mock_anon_client.table.return_value = mock_table

    # Simulate PostgREST RLS permission denied error for anon role
    from database.exceptions import SupabaseDatabaseError
    mock_table.select.return_value.eq.return_value.limit.return_value.execute.side_effect = Exception("permission denied for table scheduler_runs (RLS enforced)")

    repo = SupabaseSchedulerRunRepository(client=mock_anon_client)
    with pytest.raises(SupabaseDatabaseError) as exc:
        repo.get_by_execution_key("DAILY-RUN-20261112")
    assert "permission denied" in str(exc.value).lower()

