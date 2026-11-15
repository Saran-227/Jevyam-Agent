"""Repository implementations for daily scheduler execution runs."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
from uuid import uuid4
from supabase import Client

from database.models import SchedulerRunRecord
from config.settings import settings
from database.exceptions import SupabaseDatabaseError

logger = logging.getLogger("jevyam.repositories.scheduler_runs")


def _get_ist_timezone():
    tz_name = getattr(settings, "TIMEZONE", "Asia/Kolkata") or "Asia/Kolkata"
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        from datetime import timezone, timedelta
        return timezone(timedelta(hours=5, minutes=30), name=tz_name)


class BaseSchedulerRunRepository(ABC):
    """Abstract interface for scheduler run persistence."""

    @abstractmethod
    def get_by_execution_key(self, execution_key: str) -> Optional[SchedulerRunRecord]:
        """Fetch run record by unique execution key."""
        pass

    @abstractmethod
    def is_completed_for_date(self, date_str: str) -> bool:
        """Check if an execution has completed successfully or skipped for date."""
        pass

    @abstractmethod
    def is_running(self, execution_key: str) -> bool:
        """Check if execution is currently in progress."""
        pass

    @abstractmethod
    def record_run_start(
        self,
        execution_key: str,
        date_str: str,
        is_recovery: bool = False,
    ) -> SchedulerRunRecord:
        """Record start of daily execution."""
        pass

    @abstractmethod
    def record_run_success(
        self,
        execution_key: str,
        post_id: Optional[str] = None,
        revision: Optional[int] = None,
        is_skipped: bool = False,
    ) -> SchedulerRunRecord:
        """Record successful execution completion."""
        pass

    @abstractmethod
    def record_run_failure(
        self,
        execution_key: str,
        error_msg: str,
        retry_count: int = 0,
    ) -> SchedulerRunRecord:
        """Record failed execution with sanitized error message."""
        pass


class InMemorySchedulerRunRepository(BaseSchedulerRunRepository):
    """In-memory & local JSON persistent store for testing and offline execution."""

    def __init__(self, persistence_file: Optional[Path] = None):
        self.persistence_file = persistence_file
        self._runs: Dict[str, SchedulerRunRecord] = {}
        self._lock = threading.Lock()
        if self.persistence_file and self.persistence_file.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.persistence_file.read_text(encoding="utf-8"))
            for key, item in data.items():
                try:
                    self._runs[key] = SchedulerRunRecord.model_validate(item)
                except Exception:
                    pass
        except Exception:
            pass

    def _save(self) -> None:
        if self.persistence_file:
            try:
                self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.persistence_file.with_suffix(".tmp")
                data = {k: v.model_dump(mode="json") for k, v in self._runs.items()}
                tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                tmp.replace(self.persistence_file)
            except Exception as e:
                logger.error(f"Failed to persist scheduler runs locally: {e}")

    def get_by_execution_key(self, execution_key: str) -> Optional[SchedulerRunRecord]:
        with self._lock:
            return self._runs.get(execution_key)

    def is_completed_for_date(self, date_str: str) -> bool:
        clean_date = date_str.replace("-", "").strip()
        key = f"DAILY-RUN-{clean_date}"
        with self._lock:
            rec = self._runs.get(key)
            return bool(rec and rec.status in ("SUCCESS", "SKIPPED"))

    def is_running(self, execution_key: str) -> bool:
        with self._lock:
            rec = self._runs.get(execution_key)
            return bool(rec and rec.status == "RUNNING")

    def record_run_start(
        self,
        execution_key: str,
        date_str: str,
        is_recovery: bool = False,
    ) -> SchedulerRunRecord:
        now_iso = datetime.now(_get_ist_timezone()).isoformat()
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
        post_id: Optional[str] = None,
        revision: Optional[int] = None,
        is_skipped: bool = False,
    ) -> SchedulerRunRecord:
        now_iso = datetime.now(_get_ist_timezone()).isoformat()
        with self._lock:
            rec = self._runs.get(execution_key)
            if not rec:
                rec = SchedulerRunRecord(
                    execution_key=execution_key,
                    date=execution_key.replace("DAILY-RUN-", ""),
                    status="SUCCESS",
                    triggered_at=now_iso,
                )
            rec.status = "SKIPPED" if is_skipped else "SUCCESS"
            rec.completed_at = now_iso
            rec.post_id = post_id
            rec.revision = revision
            self._runs[execution_key] = rec
            self._save()
            return rec

    def record_run_failure(
        self,
        execution_key: str,
        error_msg: str,
        retry_count: int = 0,
    ) -> SchedulerRunRecord:
        now_iso = datetime.now(_get_ist_timezone()).isoformat()
        with self._lock:
            rec = self._runs.get(execution_key)
            if not rec:
                rec = SchedulerRunRecord(
                    execution_key=execution_key,
                    date=execution_key.replace("DAILY-RUN-", ""),
                    status="FAILED",
                    triggered_at=now_iso,
                )
            rec.status = "FAILED"
            rec.completed_at = now_iso
            rec.error = error_msg[:500]
            rec.retry_count = retry_count
            self._runs[execution_key] = rec
            self._save()
            return rec


class SupabaseSchedulerRunRepository(BaseSchedulerRunRepository):
    """PostgreSQL / Supabase implementation for persistent cloud scheduler runs."""

    def __init__(self, client: Client):
        self.client = client

    def get_by_execution_key(self, execution_key: str) -> Optional[SchedulerRunRecord]:
        try:
            res = (
                self.client.table("scheduler_runs")
                .select("*")
                .eq("execution_key", execution_key)
                .limit(1)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return SchedulerRunRecord.model_validate(res.data[0])
            return None
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch scheduler run '{execution_key}': {e}") from e

    def is_completed_for_date(self, date_str: str) -> bool:
        clean_date = date_str.replace("-", "").strip()
        key = f"DAILY-RUN-{clean_date}"
        rec = self.get_by_execution_key(key)
        return bool(rec and rec.status in ("SUCCESS", "SKIPPED"))

    def is_running(self, execution_key: str) -> bool:
        rec = self.get_by_execution_key(execution_key)
        return bool(rec and rec.status == "RUNNING")

    def record_run_start(
        self,
        execution_key: str,
        date_str: str,
        is_recovery: bool = False,
    ) -> SchedulerRunRecord:
        now_iso = datetime.now(_get_ist_timezone()).isoformat()
        payload = {
            "execution_key": execution_key,
            "date": date_str,
            "status": "RUNNING",
            "triggered_at": now_iso,
            "is_missed_run_recovery": is_recovery,
            "retry_count": 0,
            "error": None,
        }
        try:
            # Upsert on execution_key
            res = (
                self.client.table("scheduler_runs")
                .upsert(payload, on_conflict="execution_key")
                .execute()
            )
            if res.data and len(res.data) > 0:
                return SchedulerRunRecord.model_validate(res.data[0])
            return SchedulerRunRecord.model_validate(payload)
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to record run start for '{execution_key}': {e}") from e

    def record_run_success(
        self,
        execution_key: str,
        post_id: Optional[str] = None,
        revision: Optional[int] = None,
        is_skipped: bool = False,
    ) -> SchedulerRunRecord:
        now_iso = datetime.now(_get_ist_timezone()).isoformat()
        payload = {
            "status": "SKIPPED" if is_skipped else "SUCCESS",
            "completed_at": now_iso,
            "post_id": post_id,
            "revision": revision,
            "error": None,
        }
        try:
            res = (
                self.client.table("scheduler_runs")
                .update(payload)
                .eq("execution_key", execution_key)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return SchedulerRunRecord.model_validate(res.data[0])
            # If not present yet, fetch or return minimal record
            rec = self.get_by_execution_key(execution_key)
            if rec:
                return rec
            raise SupabaseDatabaseError(f"No run found to update for '{execution_key}'.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to record run success for '{execution_key}': {e}") from e

    def record_run_failure(
        self,
        execution_key: str,
        error_msg: str,
        retry_count: int = 0,
    ) -> SchedulerRunRecord:
        now_iso = datetime.now(_get_ist_timezone()).isoformat()
        payload = {
            "status": "FAILED",
            "completed_at": now_iso,
            "error": error_msg[:500],
            "retry_count": retry_count,
        }
        try:
            res = (
                self.client.table("scheduler_runs")
                .update(payload)
                .eq("execution_key", execution_key)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return SchedulerRunRecord.model_validate(res.data[0])
            rec = self.get_by_execution_key(execution_key)
            if rec:
                return rec
            raise SupabaseDatabaseError(f"No run found to record failure for '{execution_key}'.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to record run failure for '{execution_key}': {e}") from e
