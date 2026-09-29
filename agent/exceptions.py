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


class DatabaseError(JevyamAgentError):
    """Base exception for database and persistence errors."""
    pass


class MissingSupabaseCredentialsError(DatabaseError):
    """Raised when SUPABASE_URL or SUPABASE_KEY is missing or invalid."""
    pass


class SupabaseDatabaseError(DatabaseError):
    """Raised when an operation against Supabase fails."""
    pass


class PostNotFoundError(DatabaseError):
    """Raised when a requested post is not found in database."""
    pass


class InvalidStatusTransitionError(JevyamAgentError):
    """Raised when an illegal post lifecycle status transition is attempted."""
    pass

