import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
    GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
    IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "gemini").lower().strip()
    REQUIRE_POST_IMAGE = os.getenv("REQUIRE_POST_IMAGE", "true").lower() in ("true", "1", "yes")

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    SUPABASE_IMAGE_BUCKET = os.getenv("SUPABASE_IMAGE_BUCKET", "post-images")

    LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
    LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
    LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
    LINKEDIN_ORGANIZATION_ID = os.getenv("LINKEDIN_ORGANIZATION_ID")
    AUTO_PUBLISH_ON_APPROVAL = os.getenv("AUTO_PUBLISH_ON_APPROVAL", "true").lower() in ("true", "1", "yes")
    LINKEDIN_MOCK_PUBLISHING = os.getenv("LINKEDIN_MOCK_PUBLISHING", "").lower() in ("true", "1", "yes")

    APP_BASE_URL = os.getenv("APP_BASE_URL") or "http://127.0.0.1:8000"
    APP_ENV = os.getenv("APP_ENV", "development")
    DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")
    APPROVAL_EXPIRATION_HOURS = int(os.getenv("APPROVAL_EXPIRATION_HOURS", "24"))
    API_HOST = os.getenv("API_HOST", "127.0.0.1")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    DEV_ENDPOINT_ENABLED = os.getenv("DEV_ENDPOINT_ENABLED", "true").lower() in ("true", "1", "yes")

    # Approval Provider Selection (telegram by default, or whatsapp)
    APPROVAL_PROVIDER = os.getenv("APPROVAL_PROVIDER", "telegram").lower().strip()

    # Telegram Bot Configuration (Phase 7)
    TELEGRAM_PROVIDER = os.getenv("TELEGRAM_PROVIDER", "").lower().strip()
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_FOUNDER_CHAT_ID = os.getenv("TELEGRAM_FOUNDER_CHAT_ID")
    TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org")

    WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "meta")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "jevyam_verify_token")
    WHATSAPP_FOUNDER_PHONE = os.getenv("WHATSAPP_FOUNDER_PHONE")
    WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v21.0")



settings = Settings()