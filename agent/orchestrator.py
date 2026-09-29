"""Daily Orchestration Layer for Jevyam Technologies AI Marketing Agent (Phase 6).

Coordinates:
Daily schedule -> Idempotency Check -> Gemini Content Engine -> Supabase Persistence -> Approval Request Creation -> WhatsApp Notification Dispatch.
"""

from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agent.exceptions import (
    ConfigurationError,
    DailyOrchestrationError,
    DuplicateContentError,
    JevyamAgentError,
    MissingGeminiApiKeyError,
)
from agent.pipeline import LinkedInDraft, run_content_pipeline
from api.services.approval_service import ApprovalService
from api.services.whatsapp_service import WhatsAppService
from config.settings import settings
from database.models import Post, PostStatus
from database.repositories import RepositoryManager, get_repository_manager
from integrations.whatsapp.mock import MockWhatsAppProvider
from integrations.whatsapp.provider import get_whatsapp_provider

logger = logging.getLogger("jevyam.orchestrator")


class DailyRunResult(BaseModel):
    """Structured result of a daily scheduled agent execution."""

    success: bool = Field(..., description="Whether the scheduled run completed successfully")
    is_skipped: bool = Field(default=False, description="Whether the run was skipped due to idempotency")
    mode: str = Field(..., description="Execution mode: mock or live")
    post_id: Optional[str] = Field(default=None, description="Generated or existing Post ID")
    revision_number: Optional[int] = Field(default=None, description="Draft revision number")
    status: Optional[str] = Field(default=None, description="Current post status")
    topic: Optional[str] = Field(default=None, description="Topic of the post")
    approval_token: Optional[str] = Field(default=None, description="Approval token generated")
    approval_url: Optional[str] = Field(default=None, description="Approval URL link")
    whatsapp_message_id: Optional[str] = Field(default=None, description="WhatsApp dispatched message ID")
    error: Optional[str] = Field(default=None, description="Error message if run failed")
    message: str = Field(..., description="Human-readable execution outcome summary")


class DailyOrchestrator:
    """Orchestrates the daily automated execution cycle of the Jevyam AI Marketing Agent."""

    def __init__(
        self,
        repo_manager: Optional[RepositoryManager] = None,
        gemini_client: Optional[Any] = None,
        approval_service: Optional[ApprovalService] = None,
        whatsapp_service: Optional[WhatsAppService] = None,
        use_in_memory_db: bool = False,
        company_dir: Optional[Path] = None,
        prompts_dir: Optional[Path] = None,
        posts_dir: Optional[Path] = None,
    ):
        self.use_in_memory_db = use_in_memory_db
        self.repos = repo_manager or get_repository_manager(use_in_memory=use_in_memory_db)
        self.gemini_client = gemini_client
        self.approval_service = approval_service or ApprovalService(
            repo_manager=self.repos,
            gemini_client=self.gemini_client,
        )
        self.whatsapp_service = whatsapp_service
        self.company_dir = company_dir
        self.prompts_dir = prompts_dir
        self.posts_dir = posts_dir

    def validate_configuration(self, mode: str) -> None:
        """Validate required configuration and credentials for the specified execution mode.

        Args:
            mode: "mock" or "live"

        Raises:
            ConfigurationError: If required credentials are missing, empty, or placeholders.
        """
        clean_mode = (mode or "mock").lower().strip()
        missing_errors: List[str] = []

        if clean_mode == "live":
            # In LIVE mode, strictly verify all end-to-end production requirements
            required_live_vars = [
                ("GEMINI_API_KEY", settings.GEMINI_API_KEY),
                ("SUPABASE_URL", settings.SUPABASE_URL),
                ("SUPABASE_KEY", settings.SUPABASE_KEY),
                ("WHATSAPP_ACCESS_TOKEN", settings.WHATSAPP_ACCESS_TOKEN),
                ("WHATSAPP_PHONE_NUMBER_ID", settings.WHATSAPP_PHONE_NUMBER_ID),
                ("WHATSAPP_FOUNDER_PHONE", settings.WHATSAPP_FOUNDER_PHONE),
                ("LINKEDIN_ACCESS_TOKEN", settings.LINKEDIN_ACCESS_TOKEN),
                ("LINKEDIN_ORGANIZATION_ID", settings.LINKEDIN_ORGANIZATION_ID),
            ]

            for var_name, var_val in required_live_vars:
                val_str = str(var_val or "").strip()
                if not val_str or val_str.startswith("your_"):
                    missing_errors.append(var_name)

            if missing_errors:
                raise ConfigurationError(
                    f"LIVE mode cannot proceed: missing or placeholder credentials for: "
                    f"{', '.join(missing_errors)}. Refusing to start live external operations."
                )

        elif clean_mode == "mock":
            # In MOCK mode, if no mock gemini client is injected, verify GEMINI_API_KEY is configured
            if self.gemini_client is None:
                val_str = str(settings.GEMINI_API_KEY or "").strip()
                if not val_str or val_str.startswith("your_"):
                    missing_errors.append("GEMINI_API_KEY")

            if missing_errors:
                raise ConfigurationError(
                    f"MOCK mode requires GEMINI_API_KEY for real content generation, "
                    f"or an injected mock client / --mock-gemini flag for offline testing."
                )
        else:
            raise ConfigurationError(f"Unknown execution mode '{mode}'. Must be 'mock' or 'live'.")

    def check_daily_idempotency(self, target_date_str: str) -> Optional[Post]:
        """Check if an active post has already been generated for the target date.

        Args:
            target_date_str: Date string formatted as 'YYYYMMDD' or 'YYYY-MM-DD'.

        Returns:
            Existing Post if one already exists for this date in an active state, else None.
        """
        clean_date = target_date_str.replace("-", "").strip()
        recent_posts = self.repos.posts.get_previous_posts(limit=30)
        target_prefix = f"JVY-{clean_date}-"

        for post in recent_posts:
            if post.post_id.startswith(target_prefix):
                if post.status in (
                    PostStatus.DRAFT,
                    PostStatus.PENDING_APPROVAL,
                    PostStatus.APPROVED,
                    PostStatus.PUBLISHED,
                ):
                    return post
        return None

    def run(
        self,
        mode: str = "mock",
        force: bool = False,
        date_str: Optional[str] = None,
        activity: Optional[str] = None,
    ) -> DailyRunResult:
        """Execute the daily agent workflow end-to-end.

        Args:
            mode: 'mock' (default) or 'live'
            force: If True, bypasses daily idempotency guard and generates a new post.
            date_str: Optional date string ('YYYY-MM-DD'). Defaults to today's date.
            activity: Optional context on company focus or recent activity.

        Returns:
            DailyRunResult indicating outcome, post IDs, and status.

        Raises:
            ConfigurationError: If configuration validation fails.
            DailyOrchestrationError: If generation, persistence, or notifications fail.
        """
        clean_mode = (mode or "mock").lower().strip()
        target_date = date_str or datetime.now().strftime("%Y-%m-%d")
        clean_date_digits = target_date.replace("-", "").strip()

        logger.info("=" * 60)
        logger.info(f"[INFO] Starting Jevyam Daily AI Marketing Agent (Mode: {clean_mode.upper()})")
        logger.info(f"[INFO] Target Date: {target_date} | Force: {force}")
        logger.info("=" * 60)

        # 1. Configuration Validation
        logger.info("[INFO] Validating environment and credential configuration...")
        self.validate_configuration(mode=clean_mode)
        logger.info(f"[INFO] Configuration validated successfully for {clean_mode.upper()} mode.")

        # 2. Daily Idempotency Protection
        if not force:
            logger.info(f"[INFO] Checking daily idempotency for date: {clean_date_digits}...")
            existing_post = self.check_daily_idempotency(clean_date_digits)
            if existing_post:
                msg = (
                    f"Daily post '{existing_post.post_id}' already exists for date {target_date} "
                    f"with status '{existing_post.status.value}'. Skipping generation to prevent duplicate post."
                )
                logger.info(f"[INFO] {msg}")
                logger.info("=" * 60)
                logger.info("[INFO] Daily workflow completed (Idempotent Skip).")
                logger.info("=" * 60)
                return DailyRunResult(
                    success=True,
                    is_skipped=True,
                    mode=clean_mode,
                    post_id=existing_post.post_id,
                    revision_number=existing_post.current_revision,
                    status=existing_post.status.value,
                    topic=existing_post.topic,
                    message=msg,
                )

        # 3. Content Pipeline Execution
        logger.info("[INFO] Loading company knowledge and generating LinkedIn content draft...")
        try:
            draft: LinkedInDraft = run_content_pipeline(
                client=self.gemini_client,
                repo_manager=self.repos,
                current_date=target_date,
                recent_activity=activity,
                company_dir=self.company_dir,
                prompts_dir=self.prompts_dir,
                posts_dir=self.posts_dir,
                use_in_memory=self.use_in_memory_db,
            )
            logger.info(f"[INFO] Draft created: {draft.post_id} (Revision {draft.revision})")
            logger.info(f"[INFO] Topic: {draft.topic}")
        except Exception as e:
            err_msg = f"Content generation pipeline failed: {e}"
            logger.error(f"[ERROR] {err_msg}")
            raise DailyOrchestrationError(err_msg) from e

        # 4. Approval Request Creation
        logger.info(f"[INFO] Creating approval request for post '{draft.post_id}'...")
        try:
            approval_res = self.approval_service.create_approval_request(
                post_id=draft.post_id,
                revision_number=draft.revision,
            )
            token = approval_res.approval_token
            masked_token = f"{token[:4]}...{token[-4:]}" if len(token) >= 8 else "***"
            base_url = settings.APP_BASE_URL.rstrip("/")
            logger.info(f"[INFO] Approval request created: Token={masked_token}")
            logger.info(f"[INFO] Approval URL: {base_url}/approve/{masked_token}")
        except Exception as e:
            err_msg = f"Failed to create approval request: {e}"
            logger.error(f"[ERROR] {err_msg}")
            raise DailyOrchestrationError(err_msg) from e

        # 5. WhatsApp Approval Notification Dispatch
        logger.info(f"[INFO] Preparing WhatsApp notification for post '{draft.post_id}'...")
        try:
            whatsapp_svc = self.whatsapp_service
            if whatsapp_svc is None:
                if clean_mode == "mock":
                    mock_provider = MockWhatsAppProvider()
                    whatsapp_svc = WhatsAppService(
                        approval_service=self.approval_service,
                        provider=mock_provider,
                    )
                else:
                    whatsapp_svc = WhatsAppService(
                        approval_service=self.approval_service,
                        provider=get_whatsapp_provider("meta"),
                    )

            notification_res = whatsapp_svc.send_post_approval_notification(
                post_id=draft.post_id,
            )

            if not notification_res.success:
                raise DailyOrchestrationError(
                    f"WhatsApp provider returned error: {notification_res.error}"
                )

            logger.info(
                f"[INFO] WhatsApp approval notification sent successfully "
                f"(Provider: {notification_res.provider}, Message ID: {notification_res.message_id})"
            )
        except Exception as e:
            err_msg = f"WhatsApp notification dispatch failed: {e}"
            logger.error(f"[ERROR] {err_msg}")
            raise DailyOrchestrationError(err_msg) from e

        logger.info("=" * 60)
        logger.info(f"[INFO] Daily workflow completed successfully for {draft.post_id}.")
        logger.info("=" * 60)

        return DailyRunResult(
            success=True,
            is_skipped=False,
            mode=clean_mode,
            post_id=draft.post_id,
            revision_number=draft.revision,
            status=PostStatus.PENDING_APPROVAL.value,
            topic=draft.topic,
            approval_token=approval_res.approval_token,
            approval_url=approval_res.approval_url,
            whatsapp_message_id=notification_res.message_id,
            message=f"Post '{draft.post_id}' generated and approval notification sent via WhatsApp.",
        )
