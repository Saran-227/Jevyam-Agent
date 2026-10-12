"""Publishing Service managing LinkedIn publication, approval verification, and idempotency."""

from datetime import datetime
import logging
from typing import Any, Dict, Optional

from agent.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInDuplicatePostError,
    LinkedInError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInRateLimitError,
    LinkedInValidationError,
    MissingLinkedInCredentialsError,
    PostNotApprovedError,
    PostNotFoundError,
)
from config.settings import settings
from database.models import (
    ApprovalStatus,
    Post,
    PostRevision,
    PostStatus,
    Publication,
    PublicationStatus,
)
from database.repositories import RepositoryManager, get_repository_manager
from integrations.linkedin.client import LinkedInClient
from integrations.linkedin.publisher import LinkedInPublisher

logger = logging.getLogger(__name__)


class PublishingService:
    """Orchestrates publishing approved posts to the Jevyam LinkedIn Company Page."""

    def __init__(
        self,
        repo_manager: Optional[RepositoryManager] = None,
        publisher: Optional[LinkedInPublisher] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.repos = repo_manager or get_repository_manager()
        self.publisher = publisher or LinkedInPublisher()
        has_credentials = bool(
            settings.LINKEDIN_ACCESS_TOKEN
            and not settings.LINKEDIN_ACCESS_TOKEN.startswith("your_")
        )
        if mock_mode is not None:
            self.mock_mode = mock_mode
        elif publisher is not None:
            self.mock_mode = False
        elif settings.LINKEDIN_MOCK_PUBLISHING:
            self.mock_mode = True
        elif settings.DRY_RUN and publisher is None and has_credentials:
            self.mock_mode = True
        else:
            self.mock_mode = False

    def publish_approved_post(
        self,
        post_id: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Verify approval status and publish post to LinkedIn Company Page.

        Args:
            post_id: Business post ID (e.g. JVY-20260929-001).
            force: If True, bypasses idempotency duplicate check.

        Returns:
            Dictionary containing publishing status, external post ID, and permalink.

        Raises:
            PostNotFoundError: If post does not exist in repository.
            PostNotApprovedError: If post is not in APPROVED state or lacks valid approval.
            LinkedInDuplicatePostError: If post was already published and force is False.
            LinkedInError: If dispatch to LinkedIn fails.
        """
        # 1. Fetch post
        post = self.repos.posts.get_by_post_id(post_id)
        if not post:
            raise PostNotFoundError(f"Post with post_id '{post_id}' does not exist.")

        # 2. Idempotency Check: Already Published
        if not force:
            if post.status == PostStatus.PUBLISHED or post.linkedin_post_id:
                logger.info(f"Post '{post_id}' has already been published. Returning existing record.")
                return {
                    "status": "published",
                    "is_duplicate": True,
                    "post_id": post.post_id,
                    "revision": post.current_revision,
                    "external_post_id": post.linkedin_post_id,
                    "post_url": f"https://www.linkedin.com/feed/update/{post.linkedin_post_id}" if post.linkedin_post_id else None,
                    "published_at": str(post.published_at),
                    "message": f"Post '{post_id}' has already been published to LinkedIn.",
                }

        # 3. Approval Eligibility Check
        if post.status != PostStatus.APPROVED:
            raise PostNotApprovedError(
                f"Cannot publish post '{post_id}': current status is '{post.status.value}'. "
                f"Only posts in APPROVED status can be published to LinkedIn."
            )

        # Verify associated approval record
        approvals = self.repos.approvals.get_by_post_id(post_id)
        approved_record = next(
            (
                a for a in approvals
                if a.revision_number == post.current_revision and a.status == ApprovalStatus.APPROVED
            ),
            None,
        )
        if not approved_record:
            raise PostNotApprovedError(
                f"Cannot publish post '{post_id}': No APPROVED approval record found for revision {post.current_revision}."
            )

        # 4. Fetch active revision
        revisions = self.repos.revisions.get_by_post_id(post_id)
        active_rev = next(
            (r for r in revisions if r.revision_number == post.current_revision),
            None,
        )

        # 5. Create PENDING publication audit record
        target_urn = (
            self.publisher.client.organization_urn
            if (hasattr(self.publisher, "client") and getattr(self.publisher.client, "organization_id", None))
            else "urn:li:organization:mock_company"
        )
        pub_record = self.repos.publications.create(
            Publication(
                post_id=post.post_id,
                revision_number=post.current_revision,
                platform="LINKEDIN",
                status=PublicationStatus.PENDING,
                target_urn=target_urn,
            )
        )

        # 6. Dispatch: Mock Mode (Dry Run / Test Mode) vs Real LinkedIn API
        if self.mock_mode:
            now = datetime.now()
            mock_post_urn = f"urn:li:share:mock_{post.post_id}_rev{post.current_revision}"
            mock_post_url = f"https://www.linkedin.com/feed/update/{mock_post_urn}"
            has_image = bool((active_rev.image_url if active_rev else None) or post.image_url)
            mock_image_urn = f"urn:li:image:mock_{post.post_id}_rev{post.current_revision}" if has_image else None

            # 7. Update master post in database
            self.repos.posts.update_status(post.post_id, PostStatus.PUBLISHED)
            post.status = PostStatus.PUBLISHED
            post.linkedin_post_id = mock_post_urn
            post.published_at = now
            self.repos.posts.update(post)

            # 8. Update publication audit record
            self.repos.publications.update_status(
                publication_id=pub_record.id,
                status=PublicationStatus.PUBLISHED,
                external_post_id=mock_post_urn,
                published_at=now,
            )

            img_desc = f" with image asset ({mock_image_urn})" if mock_image_urn else ""
            logger.info(
                f"[MOCK] Simulated LinkedIn publication for post '{post_id}'{img_desc} (mock_mode=True). "
                f"Post URN: {mock_post_urn}"
            )

            return {
                "status": "published",
                "is_duplicate": False,
                "post_id": post.post_id,
                "revision": post.current_revision,
                "external_post_id": mock_post_urn,
                "image_urn": mock_image_urn,
                "post_url": mock_post_url,
                "published_at": now.isoformat(),
                "message": f"Successfully simulated publication for post '{post_id}' to LinkedIn Company Page (Mock Mode).",
            }

        # Real LinkedIn API dispatch
        try:
            publish_res = self.publisher.publish(post=post, revision=active_rev)
            now = datetime.now()

            # 7. Update master post in database
            self.repos.posts.update_status(post.post_id, PostStatus.PUBLISHED)
            post.status = PostStatus.PUBLISHED
            post.linkedin_post_id = publish_res.post_urn
            post.published_at = now
            self.repos.posts.update(post)

            # 8. Update publication audit record
            self.repos.publications.update_status(
                publication_id=pub_record.id,
                status=PublicationStatus.PUBLISHED,
                external_post_id=publish_res.post_urn,
                published_at=now,
            )

            logger.info(f"Successfully published post '{post_id}' to LinkedIn ({publish_res.post_urn})")

            return {
                "status": "published",
                "is_duplicate": False,
                "post_id": post.post_id,
                "revision": post.current_revision,
                "external_post_id": publish_res.post_urn,
                "post_url": publish_res.post_url,
                "published_at": now.isoformat(),
                "message": f"Successfully published post '{post_id}' to LinkedIn Company Page.",
            }

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to publish post '{post_id}' to LinkedIn: {err_msg}")

            # Transition post to FAILED status
            try:
                self.repos.posts.update_status(post.post_id, PostStatus.FAILED)
            except Exception:
                pass

            # Update audit record
            try:
                self.repos.publications.update_status(
                    publication_id=pub_record.id,
                    status=PublicationStatus.FAILED,
                    error_message=err_msg,
                )
            except Exception:
                pass

            raise
