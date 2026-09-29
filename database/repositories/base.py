from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from database.models import (
    Approval,
    ApprovalStatus,
    Company,
    Post,
    PostRevision,
    PostStatus,
    Publication,
    PublicationStatus,
)


class BaseCompanyRepository(ABC):
    """Abstract repository for companies."""

    @abstractmethod
    def get_by_slug(self, slug: str) -> Optional[Company]:
        """Fetch company by slug."""
        pass

    @abstractmethod
    def create(self, company: Company) -> Company:
        """Create or persist a company."""
        pass


class BasePostRepository(ABC):
    """Abstract repository for posts."""

    @abstractmethod
    def create(self, post: Post) -> Post:
        """Persist a new post."""
        pass

    @abstractmethod
    def get_by_post_id(self, post_id: str) -> Optional[Post]:
        """Fetch post by human-readable post_id (e.g. JVY-20260929-001)."""
        pass

    @abstractmethod
    def update(self, post: Post) -> Post:
        """Update existing post attributes."""
        pass

    @abstractmethod
    def update_status(self, post_id: str, new_status: PostStatus) -> Post:
        """Validate and transition post status."""
        pass

    @abstractmethod
    def get_previous_posts(self, limit: int = 50) -> List[Post]:
        """Fetch recent posts ordered by newest first."""
        pass

    @abstractmethod
    def get_next_sequence_for_date(self, date_str: str) -> int:
        """Calculate next available 1-based sequence number for date (YYYYMMDD)."""
        pass


class BaseRevisionRepository(ABC):
    """Abstract repository for post revisions."""

    @abstractmethod
    def create(self, revision: PostRevision) -> PostRevision:
        """Persist a new post revision snapshot."""
        pass

    @abstractmethod
    def get_by_post_id(self, post_id: str) -> List[PostRevision]:
        """Fetch all historical revisions for a post, ordered by revision_number ascending."""
        pass

    @abstractmethod
    def get_latest_revision(self, post_id: str) -> Optional[PostRevision]:
        """Fetch the most recent revision for a post."""
        pass


class BaseApprovalRepository(ABC):
    """Abstract repository for approvals."""

    @abstractmethod
    def create_approval_request(
        self,
        post_id: str,
        revision_number: int,
        expires_at: Optional[datetime] = None,
    ) -> Approval:
        """Generate secure token and persist pending approval request."""
        pass

    @abstractmethod
    def get_by_token(self, approval_token: str) -> Optional[Approval]:
        """Fetch approval record by unique token."""
        pass

    @abstractmethod
    def get_by_post_id(self, post_id: str) -> List[Approval]:
        """Fetch all approval records associated with post_id."""
        pass

    @abstractmethod
    def update_status(
        self,
        approval_token: str,
        status: ApprovalStatus,
        rejection_reason: Optional[str] = None,
    ) -> Approval:
        """Update approval record status and audit timestamps."""
        pass


class BasePublicationRepository(ABC):
    """Abstract repository for publications."""

    @abstractmethod
    def create(self, publication: "Publication") -> "Publication":
        """Persist a publication audit record."""
        pass

    @abstractmethod
    def get_by_post_id(self, post_id: str) -> List["Publication"]:
        """Fetch all publication records for a post."""
        pass

    @abstractmethod
    def get_latest_by_post_id(self, post_id: str) -> Optional["Publication"]:
        """Fetch most recent publication record for a post."""
        pass

    @abstractmethod
    def update_status(
        self,
        publication_id: str,
        status: "PublicationStatus",
        external_post_id: Optional[str] = None,
        error_message: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> "Publication":
        """Update publication status and external ID."""
        pass


