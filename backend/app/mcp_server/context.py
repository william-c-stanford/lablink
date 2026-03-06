"""MCP execution context — provides dependencies to tool handlers.

In production, this wraps real database sessions, storage backends, etc.
In tests, it can be constructed with mock/in-memory dependencies.

Provides two context classes:
  - ToolContext: Thread-local context with async session factory for DB-dependent tools
  - MCPContext: Dataclass-based context for in-memory tool handlers
"""

from __future__ import annotations

import contextvars
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# ToolContext — used by explorer tools that need DB access
# ---------------------------------------------------------------------------

_current_context: contextvars.ContextVar["ToolContext | None"] = contextvars.ContextVar(
    "_current_context", default=None
)


class ToolContext:
    """Context var-based context that provides async DB sessions.

    Used by explorer and other DB-dependent tools. Set via ToolContext.set()
    before calling tools that need database access.

    Usage:
        ctx = ToolContext(session_factory=get_session)
        ToolContext.set(ctx)
        # Now tools can do: ctx = ToolContext.get(); async with ctx.session() as s: ...
    """

    def __init__(
        self,
        session_factory: Callable[..., AsyncIterator[AsyncSession]] | None = None,
        org_id: str = "org-default",
        user_id: str | None = "user-default",
    ) -> None:
        self._session_factory = session_factory
        self.org_id = org_id
        self.user_id = user_id

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide an async database session."""
        if self._session_factory is None:
            raise RuntimeError(
                "No session factory configured. Set a session_factory on ToolContext."
            )
        async with self._session_factory() as session:
            yield session

    @classmethod
    def get(cls) -> ToolContext:
        """Get the current ToolContext from context vars."""
        ctx = _current_context.get()
        if ctx is None:
            raise RuntimeError(
                "No ToolContext set. Call ToolContext.set() before using DB-dependent MCP tools."
            )
        return ctx

    @classmethod
    def set(cls, ctx: ToolContext) -> None:
        """Set the current ToolContext in context vars."""
        _current_context.set(ctx)

    @classmethod
    def reset(cls) -> None:
        """Clear the current ToolContext."""
        _current_context.set(None)


# ---------------------------------------------------------------------------
# MCPContext — simple dataclass for in-memory tool handlers
# ---------------------------------------------------------------------------


@dataclass
class MCPContext:
    """Execution context with in-memory stores for tool handlers.

    Used by tools that don't need database access (planner, admin, etc. in dev).

    Attributes:
        org_id: The authenticated organization's ID.
        user_id: The authenticated user's ID (None for service accounts).
    """

    org_id: str = "org-default"
    user_id: str | None = "user-default"

    # In-memory stores (used directly in dev/test, replaced by DB in prod)
    experiments: dict[str, dict[str, Any]] = field(default_factory=dict)
    uploads: dict[str, dict[str, Any]] = field(default_factory=dict)
    instruments: dict[str, dict[str, Any]] = field(default_factory=dict)
    parsers: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    campaigns: dict[str, dict[str, Any]] = field(default_factory=dict)
    agents: list[dict[str, Any]] = field(default_factory=list)
    webhooks: list[dict[str, Any]] = field(default_factory=list)
    search_index: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    usage_stats: dict[str, Any] = field(default_factory=dict)
