"""Tests for webhook registration, HMAC signing, delivery, and retry logic.

Covers:
- generate_secret() — 64-char hex, cryptographically random
- sign_payload() — HMAC-SHA256 with sha256= prefix
- verify_signature() — constant-time comparison, accepts valid, rejects tampered
- WebhookService.create() — validation, auto-secret, FK creation
- WebhookService.get() — org-scoped lookup
- WebhookService.list() — pagination, active filter
- WebhookService.update() — partial updates, event validation
- WebhookService.delete() — returns bool, removes record
- WebhookService.dispatch() — fan-out to matching webhooks, skips inactive/unsubscribed
- WebhookDelivery — pending status, increments attempts on retry
- Webhook.SUPPORTED_EVENTS — validates against canonical event type set
- Webhook.subscribes_to() — active + event type check
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import lablink.models  # noqa: F401 — registers all models with Base.metadata
from lablink.database import Base
from lablink.models import (
    DeliveryStatus,
    Organization,
    User,
    Webhook,
    WebhookDelivery,
)
from lablink.services.webhook_service import (
    WebhookService,
    generate_secret,
    sign_payload,
    verify_signature,
)


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():
    """In-memory SQLite engine with all LabLink tables."""
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """Async session bound to the in-memory DB."""
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
async def org(session: AsyncSession) -> Organization:
    """Test organization."""
    o = Organization(
        name="Test Lab",
        slug=f"test-lab-{uuid.uuid4().hex[:8]}",
    )
    session.add(o)
    await session.flush()
    return o


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    """Test user."""
    u = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="$2b$12$placeholder",
        full_name="Test User",
    )
    session.add(u)
    await session.flush()
    return u


@pytest.fixture
def svc() -> WebhookService:
    return WebhookService()


# ---------------------------------------------------------------------------
# HMAC signing — pure unit tests (no DB)
# ---------------------------------------------------------------------------


class TestGenerateSecret:
    def test_returns_64_char_hex_string(self):
        """generate_secret() returns 64 hex characters (32 bytes)."""
        secret = generate_secret()
        assert len(secret) == 64
        assert all(c in "0123456789abcdef" for c in secret)

    def test_two_secrets_are_different(self):
        """generate_secret() is random — two calls never return the same value."""
        assert generate_secret() != generate_secret()


class TestSignPayload:
    def test_returns_sha256_prefixed_string(self):
        """sign_payload() returns 'sha256=<hex>' format."""
        sig = sign_payload({"event": "test"}, "mysecret")
        assert sig.startswith("sha256=")
        hex_part = sig[len("sha256=") :]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_same_payload_same_secret_gives_same_signature(self):
        """Signing is deterministic for the same payload and secret."""
        payload = {"event": "upload.completed", "id": "abc123"}
        secret = "deadbeef" * 8  # 64 hex chars
        sig1 = sign_payload(payload, secret)
        sig2 = sign_payload(payload, secret)
        assert sig1 == sig2

    def test_different_payload_gives_different_signature(self):
        """Different payloads produce different signatures."""
        secret = "deadbeef" * 8
        sig1 = sign_payload({"id": "1"}, secret)
        sig2 = sign_payload({"id": "2"}, secret)
        assert sig1 != sig2

    def test_different_secret_gives_different_signature(self):
        """Different secrets produce different signatures."""
        payload = {"event": "test"}
        sig1 = sign_payload(payload, "secret1" + "0" * 57)
        sig2 = sign_payload(payload, "secret2" + "0" * 57)
        assert sig1 != sig2


class TestVerifySignature:
    def test_valid_signature_returns_true(self):
        """verify_signature() returns True for a valid signature."""
        payload = {"event": "upload.completed", "upload_id": "abc"}
        secret = generate_secret()
        sig = sign_payload(payload, secret)
        assert verify_signature(payload, secret, sig) is True

    def test_tampered_payload_returns_false(self):
        """verify_signature() returns False when the payload has been tampered with."""
        payload = {"event": "upload.completed", "upload_id": "abc"}
        secret = generate_secret()
        sig = sign_payload(payload, secret)
        tampered = {**payload, "upload_id": "evil"}
        assert verify_signature(tampered, secret, sig) is False

    def test_wrong_secret_returns_false(self):
        """verify_signature() returns False when the secret doesn't match."""
        payload = {"event": "test"}
        secret = generate_secret()
        sig = sign_payload(payload, secret)
        assert verify_signature(payload, generate_secret(), sig) is False

    def test_tampered_signature_returns_false(self):
        """verify_signature() returns False when the signature itself is tampered."""
        payload = {"event": "test"}
        secret = generate_secret()
        sig = sign_payload(payload, secret)
        bad_sig = sig[:-4] + "0000"
        assert verify_signature(payload, secret, bad_sig) is False

    def test_uses_constant_time_comparison(self):
        """verify_signature uses hmac.compare_digest (timing-safe comparison)."""
        import inspect
        import lablink.services.webhook_service as ws_module

        source = inspect.getsource(ws_module.verify_signature)
        assert "compare_digest" in source


# ---------------------------------------------------------------------------
# Webhook model — unit tests
# ---------------------------------------------------------------------------


class TestWebhookModel:
    def test_supported_events_is_non_empty_set(self):
        """SUPPORTED_EVENTS is a non-empty set of event strings."""
        assert isinstance(Webhook.SUPPORTED_EVENTS, set)
        assert len(Webhook.SUPPORTED_EVENTS) > 0

    def test_known_events_in_supported_events(self):
        """Core event types are present in SUPPORTED_EVENTS."""
        for event in ("upload.completed", "parsing.completed", "parsing.failed"):
            assert event in Webhook.SUPPORTED_EVENTS, f"'{event}' missing from SUPPORTED_EVENTS"

    def test_subscribes_to_active_subscribed(self):
        """subscribes_to() returns True when active and event is subscribed."""
        wh = Webhook()
        wh.is_active = True
        wh.events = ["upload.completed"]
        assert wh.subscribes_to("upload.completed") is True

    def test_subscribes_to_inactive_returns_false(self):
        """subscribes_to() returns False when webhook is inactive."""
        wh = Webhook()
        wh.is_active = False
        wh.events = ["upload.completed"]
        assert wh.subscribes_to("upload.completed") is False

    def test_subscribes_to_unsubscribed_event_returns_false(self):
        """subscribes_to() returns False for events not in the subscription list."""
        wh = Webhook()
        wh.is_active = True
        wh.events = ["upload.completed"]
        assert wh.subscribes_to("experiment.created") is False


# ---------------------------------------------------------------------------
# WebhookService — CRUD registration
# ---------------------------------------------------------------------------


class TestWebhookRegistration:
    async def test_create_webhook_returns_webhook(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """create() returns a persisted Webhook record."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        assert wh.id
        assert wh.url == "https://example.com/hook"
        assert "upload.completed" in wh.events
        assert wh.is_active is True

    async def test_create_auto_generates_secret(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """create() auto-generates a 64-char hex secret when none is provided."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        assert wh.secret
        assert len(wh.secret) == 64

    async def test_create_with_explicit_secret(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """create() accepts a caller-provided secret."""
        my_secret = generate_secret()
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
            secret=my_secret,
        )
        assert wh.secret == my_secret

    async def test_create_rejects_empty_url(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """create() raises ValueError for empty URL."""
        with pytest.raises(ValueError, match="URL"):
            await svc.create(
                session,
                organization_id=org.id,
                url="   ",
                events=["upload.completed"],
                created_by=user.id,
            )

    async def test_create_rejects_empty_events(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """create() raises ValueError for empty events list."""
        with pytest.raises(ValueError, match="event"):
            await svc.create(
                session,
                organization_id=org.id,
                url="https://example.com/hook",
                events=[],
                created_by=user.id,
            )

    async def test_create_rejects_unsupported_events(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """create() raises ValueError for events not in SUPPORTED_EVENTS."""
        with pytest.raises(ValueError, match="Unsupported"):
            await svc.create(
                session,
                organization_id=org.id,
                url="https://example.com/hook",
                events=["fake.event"],
                created_by=user.id,
            )

    async def test_get_returns_webhook(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """get() returns the webhook by ID."""
        created = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        fetched = await svc.get(session, created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_org_scoped_rejects_wrong_org(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """get() with wrong org_id returns None (org-scoped isolation)."""
        created = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        other_org_id = uuid.uuid4()
        fetched = await svc.get(session, uuid.UUID(created.id), organization_id=other_org_id)
        assert fetched is None

    async def test_get_nonexistent_returns_none(self, svc: WebhookService, session: AsyncSession):
        """get() returns None for a non-existent webhook ID."""
        result = await svc.get(session, uuid.uuid4())
        assert result is None

    async def test_list_returns_all_org_webhooks(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """list() returns all webhooks for an organization."""
        for _ in range(3):
            await svc.create(
                session,
                organization_id=org.id,
                url="https://example.com/hook",
                events=["upload.completed"],
                created_by=user.id,
            )
        webhooks, total = await svc.list_webhooks(session, organization_id=org.id)
        assert total == 3
        assert len(webhooks) == 3

    async def test_list_filters_by_active_status(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """list(is_active=True) returns only active webhooks."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        # Deactivate it
        await svc.update(session, wh.id, is_active=False)

        active, active_count = await svc.list_webhooks(
            session, organization_id=org.id, is_active=True
        )
        assert active_count == 0

        inactive, inactive_count = await svc.list_webhooks(
            session, organization_id=org.id, is_active=False
        )
        assert inactive_count == 1

    async def test_update_url(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """update() can change the webhook URL."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://old.example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        updated = await svc.update(session, wh.id, url="https://new.example.com/hook")
        assert updated.url == "https://new.example.com/hook"

    async def test_update_deactivate(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """update(is_active=False) deactivates the webhook."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        updated = await svc.update(session, wh.id, is_active=False)
        assert updated.is_active is False

    async def test_update_nonexistent_returns_none(
        self, svc: WebhookService, session: AsyncSession
    ):
        """update() returns None for non-existent webhook."""
        result = await svc.update(session, uuid.uuid4(), url="https://new.example.com")
        assert result is None

    async def test_delete_returns_true_on_success(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """delete() returns True when the webhook exists and is deleted."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        result = await svc.delete(session, wh.id)
        assert result is True

    async def test_delete_removes_record(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """After delete(), get() returns None for the deleted webhook."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        wh_id = wh.id
        await svc.delete(session, wh_id)
        assert await svc.get(session, wh_id) is None

    async def test_delete_nonexistent_returns_false(
        self, svc: WebhookService, session: AsyncSession
    ):
        """delete() returns False when the webhook does not exist."""
        result = await svc.delete(session, uuid.uuid4())
        assert result is False


# ---------------------------------------------------------------------------
# WebhookService — dispatch (fan-out)
# ---------------------------------------------------------------------------


class TestWebhookDispatch:
    async def test_dispatch_creates_delivery_for_subscribed_webhook(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() creates a WebhookDelivery record for each subscribed webhook."""
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )

        # Mock httpx so no real HTTP call is made
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            deliveries = await svc.dispatch(
                session,
                event_type="upload.completed",
                payload={"upload_id": "test-123"},
                organization_id=org.id,
            )

        assert len(deliveries) == 1
        assert deliveries[0].event_type == "upload.completed"

    async def test_dispatch_skips_inactive_webhook(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() does not create deliveries for inactive webhooks."""
        wh = await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )
        await svc.update(session, wh.id, is_active=False)

        deliveries = await svc.dispatch(
            session,
            event_type="upload.completed",
            payload={"upload_id": "test-123"},
            organization_id=org.id,
        )
        assert len(deliveries) == 0

    async def test_dispatch_skips_unsubscribed_event(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() only delivers to webhooks subscribed to the specific event."""
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["experiment.created"],  # not upload.completed
            created_by=user.id,
        )

        deliveries = await svc.dispatch(
            session,
            event_type="upload.completed",
            payload={"upload_id": "test-123"},
            organization_id=org.id,
        )
        assert len(deliveries) == 0

    async def test_dispatch_fanout_multiple_webhooks(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() fans out to all matching active webhooks."""
        for i in range(3):
            await svc.create(
                session,
                organization_id=org.id,
                url=f"https://example.com/hook-{i}",
                events=["upload.completed"],
                created_by=user.id,
            )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            deliveries = await svc.dispatch(
                session,
                event_type="upload.completed",
                payload={"upload_id": "test-123"},
                organization_id=org.id,
            )

        assert len(deliveries) == 3

    async def test_dispatch_delivery_status_delivered_on_200(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() marks delivery as 'delivered' when endpoint returns 2xx."""
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            deliveries = await svc.dispatch(
                session,
                event_type="upload.completed",
                payload={"upload_id": "test-123"},
                organization_id=org.id,
            )

        assert deliveries[0].status == DeliveryStatus.delivered

    async def test_dispatch_delivery_status_failed_on_500(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() marks delivery as 'failed' when endpoint returns 5xx."""
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            deliveries = await svc.dispatch(
                session,
                event_type="upload.completed",
                payload={"upload_id": "test-123"},
                organization_id=org.id,
            )

        assert deliveries[0].status == DeliveryStatus.failed

    async def test_dispatch_sends_signature_header(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() sends X-LabLink-Signature header with HMAC-SHA256 value."""
        my_secret = generate_secret()
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
            secret=my_secret,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        payload = {"upload_id": "test-123"}
        with patch("httpx.AsyncClient", return_value=mock_client):
            await svc.dispatch(
                session,
                event_type="upload.completed",
                payload=payload,
                organization_id=org.id,
            )

        # Verify the post was called with the signature header
        call_kwargs = mock_client.post.call_args.kwargs
        headers = call_kwargs.get("headers", {})
        assert "X-LabLink-Signature" in headers
        sig = headers["X-LabLink-Signature"]
        assert sig.startswith("sha256=")
        # The signature should verify against the payload and secret
        assert verify_signature(payload, my_secret, sig)

    async def test_dispatch_sends_event_type_header(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() sends X-LabLink-Event header with the event type."""
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await svc.dispatch(
                session,
                event_type="upload.completed",
                payload={"upload_id": "test-123"},
                organization_id=org.id,
            )

        headers = mock_client.post.call_args.kwargs.get("headers", {})
        assert headers.get("X-LabLink-Event") == "upload.completed"

    async def test_dispatch_increments_attempts(
        self, svc: WebhookService, session: AsyncSession, org: Organization, user: User
    ):
        """dispatch() increments the attempts counter on the delivery record."""
        await svc.create(
            session,
            organization_id=org.id,
            url="https://example.com/hook",
            events=["upload.completed"],
            created_by=user.id,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            deliveries = await svc.dispatch(
                session,
                event_type="upload.completed",
                payload={"upload_id": "test-123"},
                organization_id=org.id,
            )

        assert deliveries[0].attempts == 1
        assert deliveries[0].last_attempt_at is not None


# ---------------------------------------------------------------------------
# WebhookDelivery model — unit tests
# ---------------------------------------------------------------------------


class TestWebhookDeliveryModel:
    def test_max_attempts_is_five(self):
        """WebhookDelivery.MAX_ATTEMPTS is 5 (configurable retry ceiling)."""
        assert WebhookDelivery.MAX_ATTEMPTS == 5

    def test_can_retry_when_failed_and_under_limit(self):
        """can_retry returns True when failed and attempts < MAX_ATTEMPTS."""
        delivery = WebhookDelivery()
        delivery.status = DeliveryStatus.failed.value
        delivery.attempts = 2
        assert delivery.can_retry is True

    def test_cannot_retry_when_at_max_attempts(self):
        """can_retry returns False when attempts >= MAX_ATTEMPTS."""
        delivery = WebhookDelivery()
        delivery.status = DeliveryStatus.failed.value
        delivery.attempts = WebhookDelivery.MAX_ATTEMPTS
        assert delivery.can_retry is False

    def test_cannot_retry_when_delivered(self):
        """can_retry returns False when delivery succeeded."""
        delivery = WebhookDelivery()
        delivery.status = DeliveryStatus.delivered.value
        delivery.attempts = 1
        assert delivery.can_retry is False
