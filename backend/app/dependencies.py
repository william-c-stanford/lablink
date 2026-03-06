"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.database import get_session
from app.exceptions import AuthenticationError
from app.models.identity import User
from app.services.auth import decode_access_token, get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Decode JWT and return the authenticated user.

    Raises:
        AuthenticationError: If the token is invalid or the user doesn't exist.
    """
    payload = decode_access_token(token, settings)
    user_id = payload["sub"]

    user = await get_user_by_id(session, user_id)
    if user is None:
        raise AuthenticationError(
            message="User not found for this token.",
            suggestion="The user may have been deleted. Obtain a new token via POST /auth/login.",
        )

    if not user.is_active:
        raise AuthenticationError(
            message="Account is deactivated.",
            suggestion="Contact your organization admin to reactivate your account.",
        )

    return user
