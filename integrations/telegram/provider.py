"""Telegram provider factory."""

from typing import Optional
from config.settings import settings
from integrations.telegram.base import BaseTelegramProvider
from integrations.telegram.client import TelegramApiProvider
from integrations.telegram.mock import MockTelegramProvider


def get_telegram_provider(
    provider_type: Optional[str] = None,
    **overrides,
) -> BaseTelegramProvider:
    """Retrieve configured Telegram provider instance.

    Args:
        provider_type: Optional explicit provider identifier ("telegram" or "mock").
        overrides: Keyword arguments passed to provider constructor.

    Returns:
        Configured BaseTelegramProvider instance.
    """
    if provider_type:
        chosen_type = provider_type.lower().strip()
    elif settings.TELEGRAM_PROVIDER:
        chosen_type = settings.TELEGRAM_PROVIDER.lower().strip()
    elif settings.DRY_RUN:
        chosen_type = "mock"
    else:
        chosen_type = "telegram"

    if chosen_type == "mock":
        return MockTelegramProvider(
            founder_chat_id=overrides.get("founder_chat_id", settings.TELEGRAM_FOUNDER_CHAT_ID),
            webhook_secret=overrides.get("webhook_secret", settings.TELEGRAM_WEBHOOK_SECRET),
            should_fail=overrides.get("should_fail", False),
            failure_error=overrides.get("failure_error", "Mock simulated Telegram dispatch failure"),
        )

    # Default to Telegram HTTPS Bot API provider
    return TelegramApiProvider(
        bot_token=overrides.get("bot_token", settings.TELEGRAM_BOT_TOKEN),
        founder_chat_id=overrides.get("founder_chat_id", settings.TELEGRAM_FOUNDER_CHAT_ID),
        webhook_secret=overrides.get("webhook_secret", settings.TELEGRAM_WEBHOOK_SECRET),
        base_url=overrides.get("base_url", settings.TELEGRAM_API_BASE_URL),
        http_client=overrides.get("http_client"),
    )
