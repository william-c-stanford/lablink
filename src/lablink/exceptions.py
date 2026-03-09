"""Application-level exceptions with agent-friendly error details.

All service-layer exceptions carry structured information that maps
directly to the :class:`~lablink.schemas.envelope.ErrorDetail` schema,
enabling routers to produce consistent Envelope error responses.

Every exception includes:
- ``code``: machine-readable error code (e.g. ``"not_found"``)
- ``message``: human-readable description
- ``suggestion``: agent-actionable hint for self-correction
- ``status_code``: HTTP status to use in the response
- ``field``: optional request field that caused the error
"""

from __future__ import annotations


class LabLinkError(Exception):
    """Base exception for all LabLink application errors.

    Subclasses set ``status_code`` and ``code`` so that routers can
    translate service errors into proper Envelope responses without
    leaking implementation details.
    """

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        suggestion: str | None = None,
        field: str | None = None,
    ) -> None:
        self.message = message
        self.suggestion = suggestion
        self.field = field
        super().__init__(message)


class NotFoundError(LabLinkError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    code = "not_found"

    def __init__(
        self,
        message: str = "Resource not found",
        *,
        suggestion: str | None = "Use the appropriate list endpoint to find valid resource IDs.",
        field: str | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, field=field)


class ValidationError(LabLinkError):
    """Raised when a business-rule validation fails (not Pydantic schema)."""

    status_code = 422
    code = "validation_error"

    def __init__(
        self,
        message: str = "Validation failed",
        *,
        suggestion: str | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, field=field)


class StateTransitionError(LabLinkError):
    """Raised when a state-machine transition is invalid."""

    status_code = 409
    code = "invalid_transition"

    def __init__(
        self,
        message: str = "Invalid state transition",
        *,
        suggestion: str | None = None,
        field: str | None = "status",
    ) -> None:
        super().__init__(message, suggestion=suggestion, field=field)


class DuplicateError(LabLinkError):
    """Raised when creating a resource that already exists."""

    status_code = 409
    code = "duplicate"

    def __init__(
        self,
        message: str = "Resource already exists",
        *,
        suggestion: str | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, field=field)


class ForbiddenError(LabLinkError):
    """Raised when the caller lacks permission for the operation."""

    status_code = 403
    code = "forbidden"

    def __init__(
        self,
        message: str = "Permission denied",
        *,
        suggestion: str | None = "Check your role permissions.",
        field: str | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, field=field)


class AuthenticationError(LabLinkError):
    """Raised when authentication fails (invalid credentials, expired token, etc.)."""

    status_code = 401
    code = "authentication_error"

    def __init__(
        self,
        message: str = "Authentication required",
        *,
        suggestion: str
        | None = "Provide a valid JWT token in the Authorization header as 'Bearer <token>'.",
    ) -> None:
        super().__init__(message, suggestion=suggestion)


class ConflictError(LabLinkError):
    """Raised when a resource conflict occurs (e.g. duplicate email, slug)."""

    status_code = 409
    code = "conflict"

    def __init__(
        self,
        message: str = "Resource already exists",
        *,
        suggestion: str | None = "Use a different value or update the existing resource.",
        field: str | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, field=field)
