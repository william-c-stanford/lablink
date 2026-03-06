"""Shared types and data structures for the MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """Metadata for a registered MCP tool."""

    name: str
    description: str
    toolset: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to MCP tool list format."""
        return {
            "name": self.name,
            "description": self.description,
            "toolset": self.toolset,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
            },
        }


@dataclass
class ToolResult:
    """Standard result wrapper for MCP tool calls."""

    data: Any = None
    meta: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    suggestion: str | None = None

    @property
    def is_error(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "data": self.data,
            "meta": self.meta,
        }
        if self.errors:
            result["errors"] = self.errors
        if self.suggestion:
            result["suggestion"] = self.suggestion
        return result

    @classmethod
    def ok(cls, data: Any, **meta: Any) -> ToolResult:
        return cls(data=data, meta=meta)

    @classmethod
    def error(
        cls,
        code: str,
        message: str,
        *,
        suggestion: str | None = None,
    ) -> ToolResult:
        return cls(
            errors=[{"code": code, "message": message}],
            suggestion=suggestion,
        )


@dataclass
class ToolsetInfo:
    """Metadata about a toolset category."""

    name: str
    description: str
    tool_count: int
    tool_names: list[str]
