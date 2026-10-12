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


def get_publishing_service() -> "PublishingService":
    """Dependency provider for PublishingService."""
    from api.services.publishing_service import PublishingService
    from config.settings import settings

    repos = get_repository_manager()
    is_mock = settings.LINKEDIN_MOCK_PUBLISHING or settings.DRY_RUN
    return PublishingService(repo_manager=repos, mock_mode=is_mock)


def get_telegram_service() -> "TelegramService":
    """Dependency provider for TelegramService."""
    from api.services.telegram_service import TelegramService
    from integrations.telegram.provider import get_telegram_provider

    approval_service = get_approval_service()
    provider = get_telegram_provider()
    return TelegramService(approval_service=approval_service, provider=provider)



