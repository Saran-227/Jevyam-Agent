"""Cryptographically secure token utilities."""

import secrets


def generate_approval_token(prefix: str = "appr_") -> str:
    """Generate a cryptographically secure, URL-safe random token.

    Uses secrets.token_urlsafe(32) generating 256 bits of entropy.
    Ensures unpredictable, non-enumerable tokens for approval verification.

    Args:
        prefix: Optional identifier prefix (defaults to 'appr_').

    Returns:
        Secure random token string, e.g. 'appr_aB3...4xY'.
    """
    token_entropy = secrets.token_urlsafe(32)
    return f"{prefix}{token_entropy}"
