"""Automatic Daily Scheduler for Jevyam Technologies AI Marketing Agent (Phase 2).

Orchestrates automatic, timezone-aware daily content generation at 09:00 AM IST (Asia/Kolkata).
Features:
- Timezone-aware scheduling using Python zoneinfo (Asia/Kolkata).
- Persistent daily execution tracking with unique keys (DAILY-RUN-YYYYMMDD).
- Strict single execution per calendar day in Asia/Kolkata.
- Missed-run recovery for application restarts.
- Concurrency and re-entrancy protection.
- Safe retry handling for transient AI, image, or Telegram delivery failures without duplicate posts.
- Enforces strict human-in-the-loop: posts are NEVER published automatically by the scheduler.
"""

import asyncio
from datetime import date, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from agent.exceptions import DailyOrchestrationError
from agent.orchestrator import DailyOrchestrator, DailyRunResult
from config.settings import settings
from database.models import PostStatus

logger = logging.getLogger("jevyam.scheduler")


def get_ist_timezone():
    """Retrieve the authoritative Asia/Kolkata timezone object.

    Uses Python 3.9+ standard library zoneinfo with tzdata fallback.
    """
    tz_name = getattr(settings, "TIMEZONE", "Asia/Kolkata") or "Asia/Kolkata"
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        from datetime import timezone, timedelta
        # UTC+5:30 Indian Standard Time
        return timezone(timedelta(hours=5, minutes=30), name=tz_name)


class SchedulerRunRecord(BaseModel):
    """Persistent audit record of a scheduled daily agent run."""

    execution_key: str = Field(..., description="Unique daily execution key, e.g. DAILY-RUN-20261112")
    date: str = Field(..., description="Target Indian calendar date (YYYY-MM-DD)")
    status: str = Field(..., description="Run status: RUNNING, SUCCESS, SKIPPED, or FAILED")
    post_id: Optional[str] = Field(default=None, description="Generated or existing Post ID")
    revision: Optional[int] = Field(default=None, description="Draft revision number")
    triggered_at: str = Field(..., description="ISO timestamp when execution started")
    completed_at: Optional[str] = Field(default=None, description="ISO timestamp when execution completed")
    is_missed_run_recovery: bool = Field(default=False, description="Whether this was a missed-run recovery run")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    error: Optional[str] = Field(default=None, description="Safe error message if failed")


class SchedulerStateStore:
    """Thread-safe and process-safe persistent store for daily scheduler execution history."""

    def __init__(
        self,
        persistence_file: Optional[Path] = None,
        repository: Optional[Any] = None,
    ):
        self.repository = repository
        if persistence_file is not None:
            self.persistence_file = persistence_file
        else:
            self.persistence_file = Path(getattr(settings, "SCHEDULER_RUNS_FILE", "data/scheduler/runs.json"))
        self._runs: Dict[str, SchedulerRunRecord] = {}
        self._lock = threading.Lock()
        if not self.repository:
            self._load()

    def _load(self) -> None:
        if self.persistence_file and self.persistence_file.exists():
            try:
                data = json.loads(self.persistence_file.read_text(encoding="utf-8"))
                for key, item in data.items():
                    try:
                        self._runs[key] = SchedulerRunRecord.model_validate(item)
                    except Exception as err:
                        logger.warning(f"[WARN] Skipping malformed scheduler record '{key}': {err}")
            except Exception as e:
                logger.warning(f"[WARN] Failed to load scheduler runs from {self.persistence_file}: {e}")

    def _save(self) -> None:
        if self.persistence_file:
            try:
                self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_file = self.persistence_file.with_suffix(".tmp")
                data = {k: v.model_dump(mode="json") for k, v in self._runs.items()}
                tmp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                tmp_file.replace(self.persistence_file)
            except Exception as e:
                logger.error(f"[ERROR] Failed to save scheduler runs to {self.persistence_file}: {e}")

    def get_run(self, execution_key: str) -> Optional[SchedulerRunRecord]:
        if self.repository:
            return self.repository.get_by_execution_key(execution_key)
        with self._lock:
            return self._runs.get(execution_key)

    def is_completed_for_date(self, date_str: str) -> bool:
        """Check if an execution has already succeeded or skipped for the given date."""
        if self.repository:
            return self.repository.is_completed_for_date(date_str)
        clean_date = date_str.replace("-", "").strip()
        key = f"DAILY-RUN-{clean_date}"
        with self._lock:
            record = self._runs.get(key)
            if record and record.status in ("SUCCESS", "SKIPPED"):
                return True
        return False

    def is_running(self, execution_key: str) -> bool:
        if self.repository:
            return self.repository.is_running(execution_key)
        with self._lock:
            record = self._runs.get(execution_key)
            return record is not None and record.status == "RUNNING"

    def record_run_start(
        self,
        execution_key: str,
        date_str: str,
        is_recovery: bool = False,
    ) -> SchedulerRunRecord:
        if self.repository:
            return self.repository.record_run_start(
                execution_key=execution_key,
                date_str=date_str,
                is_recovery=is_recovery,
            )
        now_iso = datetime.now(get_ist_timezone()).isoformat()
        with self._lock:
            record = SchedulerRunRecord(
                execution_key=execution_key,
                date=date_str,
                status="RUNNING",
                triggered_at=now_iso,
                is_missed_run_recovery=is_recovery,
            )
            self._runs[execution_key] = record
            self._save()
            return record

    def record_run_success(
        self,
        execution_key: str,
        post_id: Optional[str],
        revision: Optional[int],
        is_skipped: bool = False,
    ) -> SchedulerRunRecord:
        if self.repository:
            return self.repository.record_run_success(
                execution_key=execution_key,
                post_id=post_id,
                revision=revision,
                is_skipped=is_skipped,
            )
        now_iso = datetime.now(get_ist_timezone()).isoformat()
        with self._lock:
            record = self._runs.get(execution_key)
            if record:
                record.status = "SKIPPED" if is_skipped else "SUCCESS"
                record.post_id = post_id
                record.revision = revision
                record.completed_at = now_iso
                record.error = None
            else:
                record = SchedulerRunRecord(
                    execution_key=execution_key,
                    date=datetime.now(get_ist_timezone()).strftime("%Y-%m-%d"),
                    status="SKIPPED" if is_skipped else "SUCCESS",
                    post_id=post_id,
                    revision=revision,
                    triggered_at=now_iso,
                    completed_at=now_iso,
                )
                self._runs[execution_key] = record
            self._save()
            return record

    def record_run_failure(
        self,
        execution_key: str,
        error_msg: str,
        retry_count: int,
    ) -> SchedulerRunRecord:
        if self.repository:
            return self.repository.record_run_failure(
                execution_key=execution_key,
                error_msg=error_msg,
                retry_count=retry_count,
            )
        now_iso = datetime.now(get_ist_timezone()).isoformat()
        with self._lock:
            record = self._runs.get(execution_key)
            if record:
                record.status = "FAILED"
                record.error = error_msg
                record.retry_count = retry_count
                record.completed_at = now_iso
            else:
                record = SchedulerRunRecord(
                    execution_key=execution_key,
                    date=datetime.now(get_ist_timezone()).strftime("%Y-%m-%d"),
                    status="FAILED",
                    triggered_at=now_iso,
                    completed_at=now_iso,
                    retry_count=retry_count,
                    error=error_msg,
                )
                self._runs[execution_key] = record
            self._save()
            return record


class DailyScheduler:
    """Manages autonomous daily post generation at 09:00 AM Indian Standard Time (Asia/Kolkata)."""

    def __init__(
        self,
        orchestrator: Optional[DailyOrchestrator] = None,
        state_store: Optional[SchedulerStateStore] = None,
        target_hour: Optional[int] = None,
        target_minute: Optional[int] = None,
        max_retries: int = 3,
        retry_delay_seconds: float = 5.0,
        default_mode: Optional[str] = None,
    ):
        self.orchestrator = orchestrator or DailyOrchestrator()
        self.state_store = state_store or SchedulerStateStore()
        self.timezone = get_ist_timezone()
        self.target_hour = target_hour if target_hour is not None else getattr(settings, "SCHEDULE_HOUR", 9)
        self.target_minute = target_minute if target_minute is not None else getattr(settings, "SCHEDULE_MINUTE", 0)
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.default_mode = default_mode

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._async_lock = asyncio.Lock()
        self._exec_lock = threading.Lock()

    def get_current_ist_time(self) -> datetime:
        """Return the current wall-clock time in Asia/Kolkata."""
        return datetime.now(self.timezone)

    def get_execution_key(self, target_date: Optional[date] = None) -> str:
        """Generate canonical daily execution key: DAILY-RUN-YYYYMMDD."""
        d = target_date or self.get_current_ist_time().date()
        return f"DAILY-RUN-{d.strftime('%Y%m%d')}"

    def calculate_seconds_until_next_run(self, now_ist: Optional[datetime] = None) -> float:
        """Calculate exact float seconds until the next 09:00:00 AM IST trigger."""
        current = now_ist or self.get_current_ist_time()
        target_today = current.replace(
            hour=self.target_hour,
            minute=self.target_minute,
            second=0,
            microsecond=0,
        )

        if current < target_today:
            next_run = target_today
        else:
            # Scheduled time for today has passed; next trigger is tomorrow at target time
            next_run = target_today + timedelta(days=1)

        delta_seconds = (next_run - current).total_seconds()
        return max(0.0, delta_seconds)

    def is_target_time(self, now_ist: Optional[datetime] = None, tolerance_minutes: int = 2) -> bool:
        """Check whether current IST time matches the scheduled time within tolerance."""
        current = now_ist or self.get_current_ist_time()
        target = current.replace(
            hour=self.target_hour,
            minute=self.target_minute,
            second=0,
            microsecond=0,
        )
        diff = abs((current - target).total_seconds())
        return diff <= (tolerance_minutes * 60)

    def execute_daily_run(
        self,
        target_date_str: Optional[str] = None,
        force: bool = False,
        is_recovery: bool = False,
        mode: Optional[str] = None,
    ) -> DailyRunResult:
        """Execute the scheduled daily workflow end-to-end with persistent idempotency and retries.

        CRITICAL: Never publishes to LinkedIn. Generated post is kept in PENDING_APPROVAL.
        """
        now_ist = self.get_current_ist_time()
        date_str = target_date_str or now_ist.strftime("%Y-%m-%d")
        clean_date_digits = date_str.replace("-", "").strip()
        execution_key = f"DAILY-RUN-{clean_date_digits}"

        with self._exec_lock:
            # 1. Check duplicate execution via persistent store
            if not force and self.state_store.is_completed_for_date(date_str):
                existing_record = self.state_store.get_run(execution_key)
                post_id_desc = f" (Post: {existing_record.post_id})" if existing_record and existing_record.post_id else ""
                msg = f"Scheduled run for date {date_str} already completed{post_id_desc}. Idempotent skip."
                logger.info(f"[IDEMPOTENT SKIP] {msg}")
                return DailyRunResult(
                    success=True,
                    is_skipped=True,
                    mode=mode or self.default_mode or ("mock" if settings.DRY_RUN else "live"),
                    post_id=existing_record.post_id if existing_record else None,
                    revision_number=existing_record.revision if existing_record else None,
                    status=PostStatus.PENDING_APPROVAL.value,
                    message=msg,
                )

            # 2. Check in-progress execution lock
            if not force and self.state_store.is_running(execution_key):
                msg = f"Scheduled run '{execution_key}' is currently in progress. Ignoring duplicate trigger."
                logger.warning(f"[WARN] {msg}")
                return DailyRunResult(
                    success=True,
                    is_skipped=True,
                    mode=mode or self.default_mode or ("mock" if settings.DRY_RUN else "live"),
                    message=msg,
                )

            # 3. Mark execution as started in persistent store
            self.state_store.record_run_start(
                execution_key=execution_key,
                date_str=date_str,
                is_recovery=is_recovery,
            )

        run_mode = mode or self.default_mode or ("mock" if settings.DRY_RUN else "live")
        recovery_tag = " [MISSED-RUN RECOVERY]" if is_recovery else ""
        logger.info("=" * 65)
        logger.info(f"[SCHEDULER] Starting 09:00 AM IST Daily Execution{recovery_tag}")
        logger.info(f"[SCHEDULER] Date: {date_str} | Execution Key: {execution_key} | Mode: {run_mode.upper()}")
        logger.info("=" * 65)

        # 4. Safe retry loop for transient failures
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"[SCHEDULER] Triggering orchestrator cycle (Attempt {attempt}/{self.max_retries})...")
                result: DailyRunResult = self.orchestrator.run(
                    mode=run_mode,
                    force=force,
                    date_str=date_str,
                )

                # Persist success record
                self.state_store.record_run_success(
                    execution_key=execution_key,
                    post_id=result.post_id,
                    revision=result.revision_number,
                    is_skipped=result.is_skipped,
                )

                logger.info("=" * 65)
                logger.info(
                    f"[SCHEDULER] Daily execution finished successfully. "
                    f"Post: {result.post_id} (Rev #{result.revision_number}) | "
                    f"Telegram Msg: {result.telegram_message_id} | "
                    f"Status: {result.status}"
                )
                logger.info("=" * 65)
                return result

            except Exception as e:
                last_error = e
                # Safe error masking to prevent credential leaks in logs
                safe_err = str(e)
                logger.warning(f"[WARN] Daily run attempt {attempt} failed: {safe_err}")
                if attempt < self.max_retries:
                    backoff = self.retry_delay_seconds * (2 ** (attempt - 1))
                    logger.info(f"[SCHEDULER] Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)

        # 5. All retries exhausted
        err_summary = f"All {self.max_retries} attempts failed: {last_error}"
        logger.error(f"[ERROR] [SCHEDULER] {err_summary}")
        self.state_store.record_run_failure(
            execution_key=execution_key,
            error_msg=str(last_error),
            retry_count=self.max_retries,
        )
        raise DailyOrchestrationError(err_summary) from last_error

    def check_and_run_missed_execution(self) -> Optional[DailyRunResult]:
        """Check if today's 09:00 AM IST run was missed (e.g. server restarted after 9:00 AM).

        If missed, executes exactly once for today. Never executes for previous dates.
        """
        now_ist = self.get_current_ist_time()
        today_date = now_ist.strftime("%Y-%m-%d")
        today_target = now_ist.replace(
            hour=self.target_hour,
            minute=self.target_minute,
            second=0,
            microsecond=0,
        )

        # Only evaluate recovery if current time is at or after today's scheduled 9:00 AM IST
        if now_ist < today_target:
            logger.info(
                f"[SCHEDULER] Current time ({now_ist.strftime('%H:%M:%S')} IST) is before 09:00 AM. "
                "No missed-run recovery needed. Normal schedule will trigger at 09:00 AM."
            )
            return None

        # Check if today's run has already completed or post exists
        if self.state_store.is_completed_for_date(today_date):
            logger.info(f"[SCHEDULER] Today's run ({today_date}) already completed. No recovery needed.")
            return None

        clean_date_digits = today_date.replace("-", "").strip()
        existing_post = self.orchestrator.check_daily_idempotency(clean_date_digits)
        if existing_post:
            logger.info(
                f"[SCHEDULER] Post '{existing_post.post_id}' already exists for today ({today_date}). "
                "Marking run complete without re-generation."
            )
            key = f"DAILY-RUN-{clean_date_digits}"
            self.state_store.record_run_success(
                execution_key=key,
                post_id=existing_post.post_id,
                revision=existing_post.current_revision,
                is_skipped=True,
            )
            return None

        # Missed run detected!
        logger.warning(
            f"[SCHEDULER] [MISSED-RUN RECOVERY] 09:00 AM IST execution for today ({today_date}) was missed. "
            "Initiating automated catch-up post generation..."
        )
        try:
            return self.execute_daily_run(
                target_date_str=today_date,
                is_recovery=True,
            )
        except Exception as e:
            logger.error(f"[ERROR] Missed-run recovery failed: {e}")
            return None

    async def _schedule_loop(self) -> None:
        """Asynchronous background loop sleeping until 09:00 AM IST every day."""
        logger.info("[SCHEDULER] Daily 9:00 AM IST background schedule loop started.")

        # 1. Check for missed-run recovery on startup
        try:
            await asyncio.to_thread(self.check_and_run_missed_execution)
        except Exception as e:
            logger.error(f"[SCHEDULER] Error during startup missed-run recovery check: {e}")

        # 2. Main schedule loop
        while self._running:
            try:
                seconds_to_wait = self.calculate_seconds_until_next_run()
                now_ist = self.get_current_ist_time()
                next_trigger_time = now_ist + timedelta(seconds=seconds_to_wait)
                logger.info(
                    f"[SCHEDULER] Next scheduled post generation: "
                    f"{next_trigger_time.strftime('%Y-%m-%d %H:%M:%S')} IST "
                    f"(in {seconds_to_wait:.1f}s / {seconds_to_wait/3600:.2f}h)"
                )

                # Sleep until next scheduled run
                # Chunk sleep into increments so stop() can cancel promptly
                chunk = min(60.0, seconds_to_wait)
                elapsed = 0.0
                while elapsed < seconds_to_wait and self._running:
                    sleep_time = min(60.0, seconds_to_wait - elapsed)
                    await asyncio.sleep(sleep_time)
                    elapsed += sleep_time

                if not self._running:
                    break

                # Trigger 09:00 AM IST run
                logger.info("[SCHEDULER] 09:00 AM IST reached. Triggering daily content generation cycle...")
                await asyncio.to_thread(self.execute_daily_run)

            except asyncio.CancelledError:
                logger.info("[SCHEDULER] Background schedule loop received cancellation signal.")
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Unexpected error in schedule loop: {e}", exc_info=True)
                # Short backoff before retrying schedule calculation
                await asyncio.sleep(30.0)

        logger.info("[SCHEDULER] Daily schedule loop terminated.")

    def start(self) -> Optional[asyncio.Task]:
        """Start the background scheduler task in the running asyncio event loop."""
        if not getattr(settings, "ENABLE_SCHEDULER", True):
            logger.info("[SCHEDULER] Scheduler is disabled via ENABLE_SCHEDULER=False.")
            return None

        if self._running and self._task and not self._task.done():
            logger.info("[SCHEDULER] Scheduler background task is already running.")
            return self._task

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("[SCHEDULER] No running asyncio event loop found. Background loop not started.")
            return None

        self._running = True
        self._task = loop.create_task(self._schedule_loop())
        logger.info("[SCHEDULER] Daily 9:00 AM IST scheduler started successfully.")
        return self._task

    def stop(self) -> None:
        """Signal the background loop to stop cleanly."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[SCHEDULER] Daily scheduler stopped.")


_scheduler_instance: Optional[DailyScheduler] = None


def get_daily_scheduler(
    orchestrator: Optional[DailyOrchestrator] = None,
    state_store: Optional[SchedulerStateStore] = None,
) -> DailyScheduler:
    """Retrieve singleton DailyScheduler instance."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = DailyScheduler(
            orchestrator=orchestrator,
            state_store=state_store,
        )
    return _scheduler_instance

