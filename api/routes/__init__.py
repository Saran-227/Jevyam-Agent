"""API route modules."""

from api.routes.approval import router as approval_router
from api.routes.dev import router as dev_router
from api.routes.health import router as health_router
from api.routes.linkedin_auth import router as linkedin_auth_router
from api.routes.publishing import router as publishing_router
from api.routes.telegram_webhook import router as telegram_router
from api.routes.whatsapp_webhook import router as whatsapp_router

__all__ = [
    "health_router",
    "approval_router",
    "dev_router",
    "telegram_router",
    "whatsapp_router",
    "publishing_router",
    "linkedin_auth_router",
]


