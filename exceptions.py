"""
Custom exception hierarchy for MeGPT.

This module defines a structured exception hierarchy for consistent error handling
across the MeGPT codebase. Exceptions are organized by domain and include
appropriate HTTP status codes for API error responses.

Design principles:
1. Domain-specific exceptions for better error discrimination
2. Consistent error message formatting
3. HTTP status code mapping for API responses
4. Backward compatibility with existing exception handling
5. Rich error context (user_id, chat_id, operation, etc.)

Usage:
    raise DatabaseError("Failed to connect to database", user_id="user123")
    raise LLMError("LLM service timeout", operation="chat_completion", status_code=503)
"""

from typing import Optional, Dict, Any, Union


class MeGPTError(Exception):
    """Base exception for all MeGPT errors."""

    def __init__(
        self,
        message: str,
        *args,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize a MeGPT error.

        Args:
            message: Human-readable error message
            status_code: HTTP status code for API responses (default: 500)
            error_code: Machine-readable error code (e.g., "database_connection_failed")
            details: Additional error context (user_id, chat_id, operation, etc.)
            **kwargs: Additional context fields (shortcut for details dict)
        """
        super().__init__(message, *args)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}

        # Add kwargs to details for convenience
        if kwargs:
            self.details.update(kwargs)

    def __str__(self) -> str:
        """String representation with error code if present."""
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        result = {
            "error": self.message,
            "status_code": self.status_code,
        }
        if self.error_code:
            result["error_code"] = self.error_code
        if self.details:
            result["details"] = self.details
        return result


# ========== Database Errors ==========


class DatabaseError(MeGPTError):
    """Base exception for database-related errors."""

    def __init__(
        self,
        message: str,
        *args,
        status_code: int = 500,
        error_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            status_code=status_code,
            error_code=error_code or "database_error",
            **kwargs,
        )


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to database."""

    def __init__(
        self,
        message: str = "Failed to connect to database",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="database_connection_failed",
            status_code=503,  # Service Unavailable
            **kwargs,
        )


class DatabaseSchemaError(DatabaseError):
    """Database schema migration or validation error."""

    def __init__(
        self,
        message: str = "Database schema error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="database_schema_error",
            status_code=500,
            **kwargs,
        )


class DatabaseQueryError(DatabaseError):
    """Error executing database query."""

    def __init__(
        self,
        message: str = "Database query error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="database_query_error",
            status_code=500,
            **kwargs,
        )


# ========== External Service Errors ==========


class ExternalServiceError(MeGPTError):
    """Base exception for external service errors (calendar, email, web search, etc.)."""

    def __init__(
        self,
        message: str,
        *args,
        status_code: int = 500,
        error_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            status_code=status_code,
            error_code=error_code or "external_service_error",
            **kwargs,
        )


# ========== Memory Service Errors (Qdrant) ==========


class MemoryServiceError(MeGPTError):
    """Base exception for vector memory service errors."""

    def __init__(
        self,
        message: str,
        *args,
        status_code: int = 500,
        error_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            status_code=status_code,
            error_code=error_code or "memory_service_error",
            **kwargs,
        )


class MemoryConnectionError(MemoryServiceError):
    """Failed to connect to vector memory service (Qdrant)."""

    def __init__(
        self,
        message: str = "Failed to connect to memory service",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="memory_connection_failed",
            status_code=503,
            **kwargs,
        )


class MemoryQueryError(MemoryServiceError):
    """Error querying vector memory."""

    def __init__(
        self,
        message: str = "Memory query error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="memory_query_error",
            status_code=500,
            **kwargs,
        )


# ========== LLM & Embedding Service Errors ==========


class LLMError(MeGPTError):
    """Base exception for LLM service errors."""

    def __init__(
        self,
        message: str,
        *args,
        status_code: int = 500,
        error_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            status_code=status_code,
            error_code=error_code or "llm_error",
            **kwargs,
        )


class LLMServiceError(LLMError):
    """LLM service unavailable or internal error."""

    def __init__(
        self,
        message: str = "LLM service error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="llm_service_error",
            status_code=503,
            **kwargs,
        )


class LLMTimeoutError(LLMError):
    """LLM request timeout."""

    def __init__(
        self,
        message: str = "LLM request timeout",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="llm_timeout",
            status_code=504,  # Gateway Timeout
            **kwargs,
        )


class EmbeddingError(LLMError):
    """Embedding service error."""

    def __init__(
        self,
        message: str = "Embedding service error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="embedding_error",
            status_code=500,
            **kwargs,
        )


# ========== Authentication & Authorization Errors ==========


class AuthenticationError(MeGPTError):
    """Authentication failure."""

    def __init__(
        self,
        message: str = "Authentication failed",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="authentication_error",
            status_code=401,  # Unauthorized
            **kwargs,
        )


class AuthorizationError(MeGPTError):
    """Insufficient permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="authorization_error",
            status_code=403,  # Forbidden
            **kwargs,
        )


# ========== Validation Errors ==========


class ValidationError(MeGPTError):
    """Input validation error."""

    def __init__(
        self,
        message: str = "Validation error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="validation_error",
            status_code=400,  # Bad Request
            **kwargs,
        )


class InvalidInputError(ValidationError):
    """Invalid user input."""

    def __init__(
        self,
        message: str = "Invalid input",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="invalid_input",
            status_code=400,
            **kwargs,
        )


# ========== Configuration Errors ==========


class ConfigurationError(MeGPTError):
    """Configuration error."""

    def __init__(
        self,
        message: str = "Configuration error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="configuration_error",
            status_code=500,
            **kwargs,
        )


class MissingConfigurationError(ConfigurationError):
    """Required configuration missing."""

    def __init__(
        self,
        message: str = "Required configuration missing",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="missing_configuration",
            status_code=500,
            **kwargs,
        )


# ========== Domain-Specific Errors ==========


class DomainError(MeGPTError):
    """Base exception for domain-specific errors."""

    def __init__(
        self,
        message: str,
        *args,
        status_code: int = 500,
        error_code: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            status_code=status_code,
            error_code=error_code or "domain_error",
            **kwargs,
        )


class EmailError(DomainError):
    """Email-related error."""

    def __init__(
        self,
        message: str = "Email error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="email_error",
            status_code=500,
            **kwargs,
        )


class CalendarError(DomainError):
    """Calendar-related error."""

    def __init__(
        self,
        message: str = "Calendar error",
        *args,
        **kwargs,
    ):
        super().__init__(
            message,
            *args,
            error_code="calendar_error",
            status_code=500,
            **kwargs,
        )


# ========== Utility Functions ==========


def wrap_exception(
    exception: Exception,
    wrapper_class: type[MeGPTError],
    message: Optional[str] = None,
    **kwargs,
) -> MeGPTError:
    """
    Wrap a generic exception with a MeGPT exception.

    Useful for converting built-in exceptions (sqlite3.OperationalError,
    httpx.TimeoutException, etc.) to domain-specific MeGPT exceptions
    while preserving the original cause.

    Args:
        exception: Original exception to wrap
        wrapper_class: MeGPT exception class to wrap with
        message: Optional custom message (default: str(original_exception))
        **kwargs: Additional context for the wrapper exception

    Returns:
        Wrapped MeGPT exception
    """
    if message is None:
        message = str(exception)

    wrapped = wrapper_class(message, **kwargs)
    # Preserve original traceback
    wrapped.__cause__ = exception
    return wrapped


def is_retryable_error(exception: Exception) -> bool:
    """
    Check if an error is retryable.

    Determines whether an operation that failed with this exception
    should be retried (e.g., network timeouts, temporary service
    unavailability).

    Args:
        exception: Exception to check

    Returns:
        True if the error is likely transient and retryable
    """
    if isinstance(exception, MeGPTError):
        # Check status codes that indicate retryable errors
        retryable_status_codes = {
            503,
            504,
            429,
        }  # Service Unavailable, Gateway Timeout, Too Many Requests
        if (
            hasattr(exception, "status_code")
            and exception.status_code in retryable_status_codes
        ):
            return True

        # Check specific error types that are retryable
        retryable_types = {
            DatabaseConnectionError,
            MemoryConnectionError,
            LLMServiceError,
            LLMTimeoutError,
        }
        return any(isinstance(exception, t) for t in retryable_types)

    # For non-MeGPT exceptions, check common retryable patterns
    exception_name = exception.__class__.__name__
    retryable_patterns = {
        "Timeout",
        "ConnectionError",
        "NetworkError",
        "TemporaryFailure",
    }

    return any(pattern in exception_name for pattern in retryable_patterns)
