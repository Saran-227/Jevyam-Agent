from datetime import datetime, timedelta
from typing import Dict, Optional
from uuid import uuid4
from supabase import Client

from database.exceptions import SupabaseDatabaseError
from database.models import Approval, ApprovalStatus
from database.repositories.base import BaseApprovalRepository
from database.tokens import generate_approval_token


class InMemoryApprovalRepository(BaseApprovalRepository):
    """In-memory approval repository for offline testing and local development."""

    def __init__(self):
        self._approvals: Dict[str, Approval] = {}

    def create_approval_request(
        self,
        post_id: str,
        revision_number: int,
        expires_at: Optional[datetime] = None,
    ) -> Approval:
        token = generate_approval_token()
        now = datetime.now()
        exp = expires_at or (now + timedelta(hours=24))
        approval = Approval(
            id=str(uuid4()),
            post_id=post_id,
            revision_number=revision_number,
            status=ApprovalStatus.PENDING,
            approval_token=token,
            expires_at=exp,
            created_at=now,
        )
        self._approvals[token] = approval.model_copy(deep=True)
        return approval

    def get_by_token(self, approval_token: str) -> Optional[Approval]:
        appr = self._approvals.get(approval_token)
        return appr.model_copy(deep=True) if appr else None

    def get_by_post_id(self, post_id: str) -> list[Approval]:
        return [
            a.model_copy(deep=True)
            for a in self._approvals.values()
            if a.post_id == post_id
        ]

    def update(self, approval: Approval) -> Approval:
        self._approvals[approval.approval_token] = approval.model_copy(deep=True)
        return approval

    def update_status(
        self,
        approval_token: str,
        status: ApprovalStatus,
        rejection_reason: Optional[str] = None,
    ) -> Approval:
        appr = self.get_by_token(approval_token)
        if not appr:
            raise ValueError(f"Approval with token '{approval_token}' not found.")

        now = datetime.now()
        appr.status = status
        if status == ApprovalStatus.APPROVED:
            appr.approved_at = now
        elif status == ApprovalStatus.REJECTED:
            appr.rejected_at = now
            appr.rejection_reason = rejection_reason

        self._approvals[approval_token] = appr.model_copy(deep=True)
        return appr


class SupabaseApprovalRepository(BaseApprovalRepository):
    """Supabase PostgreSQL approval repository."""

    def __init__(self, client: Client):
        self.client = client

    def create_approval_request(
        self,
        post_id: str,
        revision_number: int,
        expires_at: Optional[datetime] = None,
    ) -> Approval:
        token = generate_approval_token()
        now = datetime.now()
        exp = expires_at or (now + timedelta(hours=24))
        payload = {
            "post_id": post_id,
            "revision_number": revision_number,
            "status": ApprovalStatus.PENDING.value,
            "approval_token": token,
            "expires_at": exp.isoformat(),
            "created_at": now.isoformat(),
        }
        try:
            response = self.client.table("approvals").insert(payload).execute()
            if response.data and len(response.data) > 0:
                return Approval.model_validate(response.data[0])
            raise SupabaseDatabaseError("Approval insert succeeded but returned no data.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to create approval request for '{post_id}': {e}") from e

    def get_by_token(self, approval_token: str) -> Optional[Approval]:
        try:
            response = (
                self.client.table("approvals")
                .select("*")
                .eq("approval_token", approval_token)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Approval.model_validate(response.data[0])
            return None
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch approval for token '{approval_token}': {e}") from e

    def get_by_post_id(self, post_id: str) -> list[Approval]:
        try:
            response = (
                self.client.table("approvals")
                .select("*")
                .eq("post_id", post_id)
                .order("created_at", desc=True)
                .execute()
            )
            if response.data:
                return [Approval.model_validate(item) for item in response.data]
            return []
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch approvals for post '{post_id}': {e}") from e

    def update(self, approval: Approval) -> Approval:
        payload = approval.model_dump(mode="json")
        try:
            response = (
                self.client.table("approvals")
                .update(payload)
                .eq("approval_token", approval.approval_token)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Approval.model_validate(response.data[0])
            raise ValueError(f"Approval '{approval.approval_token}' was not updated.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to update approval '{approval.approval_token}': {e}") from e

    def update_status(
        self,
        approval_token: str,
        status: ApprovalStatus,
        rejection_reason: Optional[str] = None,
    ) -> Approval:
        now_str = datetime.now().isoformat()
        payload = {
            "status": status.value,
        }
        if status == ApprovalStatus.APPROVED:
            payload["approved_at"] = now_str
        elif status == ApprovalStatus.REJECTED:
            payload["rejected_at"] = now_str
            payload["rejection_reason"] = rejection_reason

        try:
            response = (
                self.client.table("approvals")
                .update(payload)
                .eq("approval_token", approval_token)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Approval.model_validate(response.data[0])
            raise ValueError(f"Approval record with token '{approval_token}' was not updated.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to update approval status: {e}") from e
