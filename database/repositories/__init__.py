"""Repository layer package and unified repository manager."""

from typing import Optional
from supabase import Client

from database.exceptions import MissingSupabaseCredentialsError
from config.settings import settings
from database.repositories.approvals import (
    BaseApprovalRepository,
    InMemoryApprovalRepository,
    SupabaseApprovalRepository,
)
from database.repositories.base import (
    BaseCompanyRepository,
    BasePostRepository,
    BaseRevisionRepository,
)
from database.repositories.companies import (
    InMemoryCompanyRepository,
    SupabaseCompanyRepository,
)
from database.repositories.posts import (
    InMemoryPostRepository,
    SupabasePostRepository,
)
from database.repositories.revisions import (
    InMemoryRevisionRepository,
    SupabaseRevisionRepository,
)
from database.supabase_client import get_supabase_client


class RepositoryManager:
    """Unified repository container holding repositories for all database entities."""

    def __init__(
        self,
        posts: BasePostRepository,
        revisions: BaseRevisionRepository,
        approvals: BaseApprovalRepository,
        companies: BaseCompanyRepository,
        is_in_memory: bool = False,
    ):
        self.posts = posts
        self.revisions = revisions
        self.approvals = approvals
        self.companies = companies
        self.is_in_memory = is_in_memory


def create_in_memory_repository_manager() -> RepositoryManager:
    """Instantiate an in-memory repository container for testing and offline development."""
    return RepositoryManager(
        posts=InMemoryPostRepository(),
        revisions=InMemoryRevisionRepository(),
        approvals=InMemoryApprovalRepository(),
        companies=InMemoryCompanyRepository(),
        is_in_memory=True,
    )


def create_supabase_repository_manager(client: Client) -> RepositoryManager:
    """Instantiate a repository container wired to live Supabase client."""
    return RepositoryManager(
        posts=SupabasePostRepository(client=client),
        revisions=SupabaseRevisionRepository(client=client),
        approvals=SupabaseApprovalRepository(client=client),
        companies=SupabaseCompanyRepository(client=client),
        is_in_memory=False,
    )


def get_repository_manager(
    client: Optional[Client] = None,
    use_in_memory: Optional[bool] = None,
) -> RepositoryManager:
    """Factory to retrieve the appropriate repository manager.

    Args:
        client: Optional explicit Supabase Client instance.
        use_in_memory:
            - True: Force in-memory repositories.
            - False: Strictly require live Supabase (raises error if missing).
            - None: Use Supabase if credentials are valid; otherwise fall back to in-memory.

    Returns:
        Configured RepositoryManager.
    """
    if use_in_memory is True:
        return create_in_memory_repository_manager()

    if client:
        return create_supabase_repository_manager(client)

    # Check credentials
    url = settings.SUPABASE_URL
    key = settings.SUPABASE_KEY
    has_creds = (
        bool(url)
        and bool(key)
        and not str(url).startswith("your_")
        and not str(key).startswith("your_")
    )

    if use_in_memory is False:
        # Strictly require credentials
        supabase_client = get_supabase_client()
        return create_supabase_repository_manager(supabase_client)

    # Default auto-detect
    if has_creds:
        try:
            supabase_client = get_supabase_client()
            return create_supabase_repository_manager(supabase_client)
        except Exception:
            return create_in_memory_repository_manager()

    return create_in_memory_repository_manager()


__all__ = [
    "BaseCompanyRepository",
    "BasePostRepository",
    "BaseRevisionRepository",
    "BaseApprovalRepository",
    "InMemoryCompanyRepository",
    "SupabaseCompanyRepository",
    "InMemoryPostRepository",
    "SupabasePostRepository",
    "InMemoryRevisionRepository",
    "SupabaseRevisionRepository",
    "InMemoryApprovalRepository",
    "SupabaseApprovalRepository",
    "RepositoryManager",
    "create_in_memory_repository_manager",
    "create_supabase_repository_manager",
    "get_repository_manager",
]
