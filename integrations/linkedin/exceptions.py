"""Exceptions for LinkedIn API integration and publishing."""


class LinkedInError(Exception):
    """Base exception for all LinkedIn integration and publishing errors."""
    pass


class MissingLinkedInCredentialsError(LinkedInError):
    """Raised when LinkedIn OAuth access token or organization ID is missing."""
    pass


class LinkedInAuthError(LinkedInError):
    """Raised when LinkedIn authentication fails (401 Unauthorized or expired token)."""
    pass


class LinkedInPermissionError(LinkedInError):
    """Raised when application lacks necessary scope or organizational admin permissions (403 Forbidden)."""
    pass


class LinkedInValidationError(LinkedInError):
    """Raised when LinkedIn rejects request payload formatting or content (400/422)."""
    pass


class LinkedInRateLimitError(LinkedInError):
    """Raised when LinkedIn API rate limits are exceeded (429 Too Many Requests)."""
    pass


class LinkedInNetworkError(LinkedInError):
    """Raised when network connectivity or request timeouts occur."""
    pass


class LinkedInAPIError(LinkedInError):
    """Raised when LinkedIn API returns unexpected server error responses (5xx)."""
    pass


class LinkedInDuplicatePostError(LinkedInError):
    """Raised when attempting to publish a post that has already been published."""
    pass


class PostNotApprovedError(LinkedInError):
    """Raised when attempting to publish content that is not in APPROVED state."""
    pass
