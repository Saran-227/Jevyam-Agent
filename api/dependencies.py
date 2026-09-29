"""Dependency injection providers for FastAPI routes."""

from typing import Generator
from api.services.approval_service import ApprovalService
from database.repositories import get_repository_manager


def get_approval_service() -> ApprovalService:
    """Dependency provider for ApprovalService."""
    repos = get_repository_manager()
    return ApprovalService(repo_manager=repos)


def get_whatsapp_service() -> "WhatsAppService":
    """Dependency provider for WhatsAppService."""
    from api.services.whatsapp_service import WhatsAppService
    from integrations.whatsapp.provider import get_whatsapp_provider

    approval_service = get_approval_service()
    provider = get_whatsapp_provider()
    return WhatsAppService(approval_service=approval_service, provider=provider)

