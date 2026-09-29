"""Approval business logic service layer."""

from datetime import datetime
from typing import Any, Optional, Tuple
from google import genai

from agent.exceptions import (
    ApprovalAlreadyProcessedError,
    ApprovalError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalSupersededError,
    PostNotEligibleForApprovalError,
    PostNotFoundError,
)
from agent.pipeline import regenerate_draft
from api.schemas import (
    ApprovalActionResponse,
    ApprovalPageResponse,
    CreateApprovalResponse,
)
from config.settings import settings
from database.models import (
    Approval,
    ApprovalStatus,
    Post,
    PostRevision,
    PostStatus,
)
from database.repositories import RepositoryManager, get_repository_manager


class ApprovalService:
    """Service orchestrating approval lifecycle, token verification, and draft regeneration."""

    def __init__(
        self,
        repo_manager: Optional[RepositoryManager] = None,
        gemini_client: Optional[genai.Client] = None,
        publishing_service: Optional[Any] = None,
    ):
        self.repos = repo_manager or get_repository_manager()
        self.gemini_client = gemini_client
        self.publishing_service = publishing_service

    def create_approval_request(
        self,
        post_id: str,
        revision_number: Optional[int] = None,
    ) -> CreateApprovalResponse:
        """Create a secure pending approval request for a post.

        Args:
            post_id: Business post ID (e.g. JVY-20260929-001).
            revision_number: Target revision number (defaults to current revision).

        Returns:
            CreateApprovalResponse with unguessable approval token and URL.
        """
        post = self.repos.posts.get_by_post_id(post_id)
        if not post:
            raise PostNotFoundError(f"Post with post_id '{post_id}' does not exist.")

        target_revision = revision_number if revision_number is not None else post.current_revision
        if target_revision != post.current_revision:
            raise ApprovalError(
                f"Cannot create approval request for revision {target_revision}; "
                f"current active revision is {post.current_revision}."
            )

        if post.status == PostStatus.PUBLISHED:
            raise PostNotEligibleForApprovalError(
                f"Post '{post_id}' is already PUBLISHED and cannot be approved again."
            )

        # Ensure post status is PENDING_APPROVAL
        if post.status == PostStatus.DRAFT:
            self.repos.posts.update_status(post.post_id, PostStatus.PENDING_APPROVAL)
        elif post.status != PostStatus.PENDING_APPROVAL:
            post.status = PostStatus.PENDING_APPROVAL
            self.repos.posts.update(post)

        approval = self.repos.approvals.create_approval_request(
            post_id=post.post_id,
            revision_number=target_revision,
        )

        base_url = settings.APP_BASE_URL.rstrip("/")
        approval_url = f"{base_url}/approve/{approval.approval_token}"

        return CreateApprovalResponse(
            post_id=approval.post_id,
            revision_number=approval.revision_number,
            approval_token=approval.approval_token,
            approval_url=approval_url,
            expires_at=str(approval.expires_at) if approval.expires_at else None,
        )

    def validate_and_get_approval(
        self,
        token: str,
    ) -> Tuple[Approval, Post, PostRevision]:
        """Validate token activity, expiration, idempotency, and return entity tuple.

        Raises:
            ApprovalNotFoundError: If token does not exist.
            ApprovalExpiredError: If token expiration has elapsed.
            ApprovalAlreadyProcessedError: If token was already consumed.
            ApprovalSupersededError: If revision is no longer current.
            PostNotFoundError: If parent post was deleted.
        """
        approval = self.repos.approvals.get_by_token(token)
        if not approval:
            raise ApprovalNotFoundError("Approval token was not found or is invalid.")

        # Expiration check
        if approval.expires_at:
            exp_dt = (
                datetime.fromisoformat(approval.expires_at)
                if isinstance(approval.expires_at, str)
                else approval.expires_at
            )
            now_dt = datetime.now(exp_dt.tzinfo) if exp_dt.tzinfo else datetime.now()
            if now_dt > exp_dt:
                if approval.status == ApprovalStatus.PENDING:
                    self.repos.approvals.update_status(token, ApprovalStatus.EXPIRED)
                raise ApprovalExpiredError("This approval request has expired.")

        # Idempotency / consumed check
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyProcessedError(
                f"This approval request is no longer active (status: {approval.status.value})."
            )

        post = self.repos.posts.get_by_post_id(approval.post_id)
        if not post:
            raise PostNotFoundError(f"Associated post '{approval.post_id}' could not be found.")

        # Revision currency check
        if approval.revision_number != post.current_revision:
            raise ApprovalSupersededError(
                f"Revision {approval.revision_number} has been superseded by revision {post.current_revision}."
            )

        # Fetch revision data
        revisions = self.repos.revisions.get_by_post_id(approval.post_id)
        active_rev = next(
            (r for r in revisions if r.revision_number == approval.revision_number),
            None,
        )
        if not active_rev:
            # Fallback to post fields if historical revision record was not loaded
            active_rev = PostRevision(
                post_id=post.post_id,
                revision_number=post.current_revision,
                topic=post.topic,
                angle=post.angle,
                content_type=post.content_type,
                target_audience=post.target_audience,
                hook=post.hook,
                caption=post.caption,
                hashtags=post.hashtags,
                call_to_action=post.call_to_action,
                visual_concept=post.visual_concept,
                image_brief=post.image_brief,
                image_url=post.image_url,
            )

        return approval, post, active_rev

    def get_approval_page_data(self, token: str) -> ApprovalPageResponse:
        """Fetch content for the founder-facing approval web interface."""
        approval, post, revision = self.validate_and_get_approval(token)

        image_brief_dict = None
        if hasattr(revision.image_brief, "model_dump"):
            image_brief_dict = revision.image_brief.model_dump()
        elif isinstance(revision.image_brief, dict):
            image_brief_dict = revision.image_brief

        return ApprovalPageResponse(
            post_id=post.post_id,
            revision_number=revision.revision_number,
            content_type=revision.content_type,
            topic=revision.topic,
            angle=revision.angle,
            target_audience=revision.target_audience,
            hook=revision.hook,
            caption=revision.caption,
            hashtags=revision.hashtags,
            call_to_action=revision.call_to_action,
            visual_concept=revision.visual_concept,
            image_url=revision.image_url or post.image_url,
            image_brief=image_brief_dict,
            status=post.status.value,
            expires_at=str(approval.expires_at) if approval.expires_at else None,
        )

    def approve_post(
        self,
        token: str,
        auto_publish: Optional[bool] = None,
    ) -> ApprovalActionResponse:
        """Approve post, consume token, and dispatch to LinkedIn."""
        approval, post, _ = self.validate_and_get_approval(token)

        # 1. Invalidate current approval token
        self.repos.approvals.update_status(token, ApprovalStatus.APPROVED)

        # 2. Transition post to APPROVED
        updated_post = self.repos.posts.update_status(post.post_id, PostStatus.APPROVED)

        # 3. Publish to LinkedIn if enabled
        should_publish = auto_publish if auto_publish is not None else settings.AUTO_PUBLISH_ON_APPROVAL
        pub_service = self.publishing_service
        if pub_service is None and should_publish and settings.LINKEDIN_ACCESS_TOKEN and not settings.LINKEDIN_ACCESS_TOKEN.startswith("your_"):
            try:
                from api.services.publishing_service import PublishingService
                pub_service = PublishingService(repo_manager=self.repos)
            except Exception:
                pub_service = None

        published_flag = None
        ext_post_id = None
        post_url = None
        msg = "Post approved successfully."

        if should_publish and pub_service:
            try:
                pub_result = pub_service.publish_approved_post(updated_post.post_id)
                published_flag = True
                ext_post_id = pub_result.get("external_post_id")
                post_url = pub_result.get("post_url")
                msg = "Post approved and published to LinkedIn Company Page."
            except Exception as e:
                published_flag = False
                msg = f"Post approved, but LinkedIn publishing failed: {str(e)}"

        return ApprovalActionResponse(
            status="approved",
            post_id=updated_post.post_id,
            revision=updated_post.current_revision,
            message=msg,
            published=published_flag,
            external_post_id=ext_post_id,
            post_url=post_url,
        )

    def reject_and_regenerate(
        self,
        token: str,
        reason: Optional[str] = None,
    ) -> ApprovalActionResponse:
        """Reject current revision and trigger generation of new revision."""
        approval, post, _ = self.validate_and_get_approval(token)

        # 1. Invalidate current approval token as REJECTED
        self.repos.approvals.update_status(
            token,
            ApprovalStatus.REJECTED,
            rejection_reason=reason,
        )

        # 2. Transition post status: PENDING_APPROVAL -> REJECTED -> REGENERATING
        self.repos.posts.update_status(post.post_id, PostStatus.REJECTED)
        self.repos.posts.update_status(post.post_id, PostStatus.REGENERATING)

        # 3. Call pipeline regeneration
        regenerated_draft = regenerate_draft(
            rejected_draft=post.post_id,
            rejection_reason=reason,
            client=self.gemini_client,
            repo_manager=self.repos,
        )

        # 4. Generate NEW approval request with NEW secure token
        new_approval = self.create_approval_request(
            post_id=post.post_id,
            revision_number=regenerated_draft.revision,
        )

        return ApprovalActionResponse(
            status="regenerated",
            post_id=post.post_id,
            revision=regenerated_draft.revision,
            approval_url=new_approval.approval_url,
            message="New version generated and ready for review.",
        )
