"""Password hashing and JWT token utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import Settings, get_settings

# ---------------------------------------------------------------------------
# Password hashing (bcrypt)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


class TokenPayload:
    """Decoded JWT payload with typed attributes."""

    __slots__ = ("sub", "exp", "iat", "extra")

    def __init__(
        self,
        sub: str,
        exp: datetime,
        iat: datetime,
        extra: dict | None = None,
    ) -> None:
        self.sub = sub
        self.exp = exp
        self.iat = iat
        self.extra = extra or {}


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or is expired."""

    def __init__(self, message: str, *, suggestion: str | None = None) -> None:
        super().__init__(message)
        self.suggestion = suggestion


def create_access_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    extra_claims: dict | None = None,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    subject:
        The ``sub`` claim – typically a user ID or email.
    expires_delta:
        Custom lifetime.  Falls back to ``settings.jwt_expire_minutes``.
    extra_claims:
        Additional claims merged into the payload.
    settings:
        Override the global settings (useful in tests).
    """
    cfg = settings or get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta is not None else timedelta(minutes=cfg.jwt_expire_minutes))

    payload: dict = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, cfg.secret_key, algorithm=cfg.jwt_algorithm)


def decode_access_token(
    token: str,
    *,
    settings: Settings | None = None,
) -> TokenPayload:
    """Decode and validate a JWT access token.

    Raises
    ------
    TokenError
        If the token is expired, malformed, or otherwise invalid.
    """
    cfg = settings or get_settings()
    try:
        raw = jwt.decode(token, cfg.secret_key, algorithms=[cfg.jwt_algorithm])
    except ExpiredSignatureError:
        raise TokenError(
            "Token has expired",
            suggestion="Re-authenticate to obtain a fresh access token.",
        )
    except JWTError as exc:
        raise TokenError(
            f"Invalid token: {exc}",
            suggestion="Ensure the token is correctly formatted and has not been tampered with.",
        )

    return TokenPayload(
        sub=raw["sub"],
        exp=datetime.fromtimestamp(raw["exp"], tz=timezone.utc),
        iat=datetime.fromtimestamp(raw["iat"], tz=timezone.utc),
        extra={k: v for k, v in raw.items() if k not in ("sub", "exp", "iat")},
    )
