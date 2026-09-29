"""Company repository implementations."""

from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4
from supabase import Client

from database.exceptions import SupabaseDatabaseError
from database.models import Company
from database.repositories.base import BaseCompanyRepository


class InMemoryCompanyRepository(BaseCompanyRepository):
    """In-memory company repository for offline local testing and development."""

    def __init__(self):
        self._companies: Dict[str, Company] = {}
        # Pre-seed Jevyam Technologies
        default_company = Company(
            id=str(uuid4()),
            name="Jevyam Technologies",
            slug="jevyam",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._companies[default_company.slug] = default_company

    def get_by_slug(self, slug: str) -> Optional[Company]:
        return self._companies.get(slug)

    def create(self, company: Company) -> Company:
        if not company.id:
            company.id = str(uuid4())
        now = datetime.now()
        company.created_at = company.created_at or now
        company.updated_at = now
        self._companies[company.slug] = company
        return company


class SupabaseCompanyRepository(BaseCompanyRepository):
    """Supabase PostgreSQL company repository."""

    def __init__(self, client: Client):
        self.client = client

    def get_by_slug(self, slug: str) -> Optional[Company]:
        try:
            response = (
                self.client.table("companies")
                .select("*")
                .eq("slug", slug)
                .limit(1)
                .execute()
            )
            if response.data and len(response.data) > 0:
                return Company.model_validate(response.data[0])
            return None
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to fetch company by slug '{slug}': {e}") from e

    def create(self, company: Company) -> Company:
        try:
            payload = company.model_dump(exclude_none=True)
            response = self.client.table("companies").insert(payload).execute()
            if response.data and len(response.data) > 0:
                return Company.model_validate(response.data[0])
            raise SupabaseDatabaseError("Company insert succeeded but returned no data.")
        except Exception as e:
            raise SupabaseDatabaseError(f"Failed to create company: {e}") from e
