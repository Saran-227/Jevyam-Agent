"""WhatsApp provider factory."""

from typing import Optional
from config.settings import settings
from integrations.whatsapp.base import BaseWhatsAppProvider
from integrations.whatsapp.meta_cloud import MetaWhatsAppCloudProvider
from integrations.whatsapp.mock import MockWhatsAppProvider


def get_whatsapp_provider(
    provider_type: Optional[str] = None,
    **overrides,
) -> BaseWhatsAppProvider:
    """Retrieve configured WhatsApp provider instance.

    Args:
        provider_type: Optional explicit provider identifier ("meta" or "mock").
        overrides: Keyword arguments passed to provider constructor.

    Returns:
        Configured BaseWhatsAppProvider instance.
    """
    chosen_type = (provider_type or settings.WHATSAPP_PROVIDER or "meta").lower().strip()

    if chosen_type == "mock":
        return MockWhatsAppProvider(
            founder_phone=overrides.get("founder_phone", settings.WHATSAPP_FOUNDER_PHONE or "+919876543210"),
            should_fail=overrides.get("should_fail", False),
            failure_error=overrides.get("failure_error", "Mock simulated dispatch failure"),
        )

    # Default to Meta WhatsApp Cloud API
    return MetaWhatsAppCloudProvider(
        access_token=overrides.get("access_token", settings.WHATSAPP_ACCESS_TOKEN),
        phone_number_id=overrides.get("phone_number_id", settings.WHATSAPP_PHONE_NUMBER_ID),
        business_account_id=overrides.get("business_account_id", settings.WHATSAPP_BUSINESS_ACCOUNT_ID),
        founder_phone=overrides.get("founder_phone", settings.WHATSAPP_FOUNDER_PHONE),
        app_secret=overrides.get("app_secret", settings.WHATSAPP_APP_SECRET),
        api_version=overrides.get("api_version", settings.WHATSAPP_API_VERSION),
        http_client=overrides.get("http_client"),
    )
