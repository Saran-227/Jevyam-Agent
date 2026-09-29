"""Supabase client initialization and connection helper."""

from typing import Optional
from supabase import Client, create_client

from agent.exceptions import (
    MissingSupabaseCredentialsError,
    SupabaseDatabaseError,
)
from config.settings import settings


def get_supabase_client(
    url: Optional[str] = None,
    key: Optional[str] = None,
) -> Client:
    """Initialize and return a validated Supabase client.

    Args:
        url: Optional Supabase URL override (defaults to settings.SUPABASE_URL).
        key: Optional Supabase API key override (defaults to settings.SUPABASE_KEY).

    Returns:
        Configured Supabase Client instance.

    Raises:
        MissingSupabaseCredentialsError: If URL or key is missing or unconfigured.
        SupabaseDatabaseError: If client instantiation fails.
    """
    target_url = url or settings.SUPABASE_URL
    target_key = key or settings.SUPABASE_KEY

    if not target_url or not str(target_url).strip():
        raise MissingSupabaseCredentialsError(
            "SUPABASE_URL is missing or empty. Please configure it in your .env file."
        )

    if not target_key or not str(target_key).strip():
        raise MissingSupabaseCredentialsError(
            "SUPABASE_KEY is missing or empty. Please configure it in your .env file."
        )

    cleaned_url = str(target_url).strip()
    cleaned_key = str(target_key).strip()

    if cleaned_url.startswith("your_") or cleaned_key.startswith("your_"):
        raise MissingSupabaseCredentialsError(
            "SUPABASE_URL or SUPABASE_KEY contains a placeholder value. Please set valid credentials in .env."
        )

    try:
        return create_client(cleaned_url, cleaned_key)
    except Exception as e:
        # Note: Do not log or print credentials in error messages
        raise SupabaseDatabaseError(f"Failed to initialize Supabase client: {e}") from e
