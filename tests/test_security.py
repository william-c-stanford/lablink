"""Tests for password hashing and JWT token utilities."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app.config import Settings
from backend.app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        secret_key="test-secret-key-for-unit-tests",
        jwt_algorithm="HS256",
        jwt_expire_minutes=30,
    )


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_returns_bcrypt_string(self):
        hashed = hash_password("mypassword")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_hash_is_not_plaintext(self):
        assert hash_password("secret") != "secret"

    def test_verify_correct_password(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("wrong-password", hashed) is False

    def test_same_password_produces_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # salt differs

    def test_empty_password_hashes(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ---------------------------------------------------------------------------
# JWT creation
# ---------------------------------------------------------------------------


class TestJWTCreation:
    def test_create_returns_string(self, test_settings: Settings):
        token = create_access_token("user-123", settings=test_settings)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_subject(self, test_settings: Settings):
        token = create_access_token("user-456", settings=test_settings)
        payload = decode_access_token(token, settings=test_settings)
        assert payload.sub == "user-456"

    def test_custom_expiry(self, test_settings: Settings):
        token = create_access_token(
            "user-789",
            expires_delta=timedelta(minutes=5),
            settings=test_settings,
        )
        payload = decode_access_token(token, settings=test_settings)
        diff = (payload.exp - payload.iat).total_seconds()
        assert 290 <= diff <= 310  # ~5 minutes

    def test_extra_claims(self, test_settings: Settings):
        token = create_access_token(
            "user-abc",
            extra_claims={"role": "admin", "lab_id": "lab-1"},
            settings=test_settings,
        )
        payload = decode_access_token(token, settings=test_settings)
        assert payload.extra["role"] == "admin"
        assert payload.extra["lab_id"] == "lab-1"

    def test_default_expiry_uses_settings(self, test_settings: Settings):
        token = create_access_token("user-def", settings=test_settings)
        payload = decode_access_token(token, settings=test_settings)
        diff = (payload.exp - payload.iat).total_seconds()
        assert 1790 <= diff <= 1810  # ~30 minutes from fixture


# ---------------------------------------------------------------------------
# JWT decoding / validation
# ---------------------------------------------------------------------------


class TestJWTDecoding:
    def test_decode_valid_token(self, test_settings: Settings):
        token = create_access_token("u1", settings=test_settings)
        payload = decode_access_token(token, settings=test_settings)
        assert payload.sub == "u1"
        assert payload.exp is not None
        assert payload.iat is not None

    def test_expired_token_raises(self, test_settings: Settings):
        token = create_access_token(
            "u2",
            expires_delta=timedelta(seconds=-1),
            settings=test_settings,
        )
        with pytest.raises(TokenError, match="expired") as exc_info:
            decode_access_token(token, settings=test_settings)
        assert exc_info.value.suggestion is not None

    def test_invalid_token_string_raises(self, test_settings: Settings):
        with pytest.raises(TokenError, match="Invalid token"):
            decode_access_token("not.a.valid.jwt", settings=test_settings)

    def test_wrong_secret_raises(self, test_settings: Settings):
        token = create_access_token("u3", settings=test_settings)
        other_settings = Settings(
            environment="test",
            secret_key="different-secret-key",
        )
        with pytest.raises(TokenError):
            decode_access_token(token, settings=other_settings)

    def test_token_error_has_suggestion(self, test_settings: Settings):
        with pytest.raises(TokenError) as exc_info:
            decode_access_token("garbage", settings=test_settings)
        assert exc_info.value.suggestion is not None
        assert len(exc_info.value.suggestion) > 0
