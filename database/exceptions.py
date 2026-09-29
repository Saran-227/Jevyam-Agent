"""Database and lifecycle transition exceptions."""


class JevyamAgentError(Exception):
    """Base exception for all Jevyam Agent errors."""
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
