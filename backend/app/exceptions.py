"""Application exception hierarchy with agent-friendly suggestions."""

from __future__ import annotations


class LabLinkError(Exception):
    """Base exception for all LabLink errors."""

    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        status_code: int = 500,
        suggestion: str | None = None,
        field: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.suggestion = suggestion
        self.field = field


class NotFoundError(LabLinkError):
    """Resource not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "not_found",
        suggestion: str | None = "Check the resource ID and try again.",
        field: str | None = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=404,
            suggestion=suggestion,
            field=field,
        )


class ConflictError(LabLinkError):
    """Resource conflict (e.g., duplicate)."""

    def __init__(
        self,
        message: str = "Resource already exists",
        code: str = "conflict",
        suggestion: str | None = "A resource with this identifier already exists. Use a different value or update the existing resource.",
        field: str | None = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=409,
            suggestion=suggestion,
            field=field,
        )


class ValidationError(LabLinkError):
    """Business logic validation error."""

    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "validation_error",
        suggestion: str | None = None,
        field: str | None = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=422,
            suggestion=suggestion,
            field=field,
        )


class AuthenticationError(LabLinkError):
    """Authentication failure."""

    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "authentication_error",
        suggestion: str | None = "Provide a valid JWT token in the Authorization header as 'Bearer <token>'.",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=401,
            suggestion=suggestion,
        )


class AuthorizationError(LabLinkError):
    """Insufficient permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        code: str = "authorization_error",
        suggestion: str | None = "Your API token lacks the required scope. Request an upgraded token or contact an admin.",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=403,
            suggestion=suggestion,
        )


class ParseError(LabLinkError):
    """Instrument file parsing error."""

    def __init__(
        self,
        message: str = "Failed to parse instrument file",
        code: str = "parse_error",
        suggestion: str | None = "Verify the file is a valid instrument export. Check the file format and ensure it is not corrupted.",
        field: str | None = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=422,
            suggestion=suggestion,
            field=field,
        )


class StateTransitionError(LabLinkError):
    """Invalid state machine transition."""

    def __init__(
        self,
        message: str = "Invalid state transition",
        code: str = "invalid_state_transition",
        suggestion: str | None = None,
        field: str | None = None,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=409,
            suggestion=suggestion,
            field=field,
        )
