"""Custom exceptions for the Jevyam Marketing Agent."""


class JevyamAgentError(Exception):
    """Base exception for all Jevyam Agent errors."""
    pass


class MissingGeminiApiKeyError(JevyamAgentError):
    """Raised when the GEMINI_API_KEY environment variable is missing or empty."""
    pass


class CompanyKnowledgeError(JevyamAgentError):
    """Raised when there is an issue with company knowledge files."""
    pass


class MissingKnowledgeFileError(CompanyKnowledgeError):
    """Raised when a required company knowledge markdown file cannot be found."""
    pass


class GeminiAPIError(JevyamAgentError):
    """Raised when communication with Gemini API fails."""
    pass


class InvalidGeminiResponseError(JevyamAgentError):
    """Raised when Gemini returns a malformed response or fails schema validation."""
    pass


class DuplicateContentError(JevyamAgentError):
    """Raised when content is too similar to previous posts after maximum retries."""
    pass


class ContentGenerationError(JevyamAgentError):
    """Raised when the content generation pipeline fails to produce a draft."""
    pass


from database.exceptions import (
    DatabaseError,
    InvalidStatusTransitionError,
    MissingSupabaseCredentialsError,
    PostNotFoundError,
    SupabaseDatabaseError,
)


class ApprovalError(JevyamAgentError):
    """Base exception for approval workflows."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval token cannot be found."""
    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when an approval token has passed its expiration time."""
    pass


class ApprovalAlreadyProcessedError(ApprovalError):
    """Raised when an approval token was already approved, rejected, or consumed."""
    pass


class ApprovalSupersededError(ApprovalError):
    """Raised when an approval token points to a superseded revision."""
    pass


class PostNotEligibleForApprovalError(ApprovalError):
    """Raised when attempting to create an approval request for an ineligible post."""
    pass


from integrations.linkedin.exceptions import (
    LinkedInAPIError,
    LinkedInAuthError,
    LinkedInDuplicatePostError,
    LinkedInError,
    LinkedInNetworkError,
    LinkedInPermissionError,
    LinkedInRateLimitError,
    LinkedInValidationError,
    MissingLinkedInCredentialsError,
    PostNotApprovedError,
)


class ConfigurationError(JevyamAgentError):
    """Raised when application or environment configuration is invalid, missing, or lacks credentials for the requested mode."""
    pass


class DailyOrchestrationError(JevyamAgentError):
    """Raised when daily scheduled agent orchestration fails."""
    pass


