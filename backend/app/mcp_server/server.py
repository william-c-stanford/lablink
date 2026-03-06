"""FastMCP server for LabLink — agent-native lab data integration.

Provides up to 25 curated tools across 4 toolsets + 2 discovery tools:
  - discovery (2): list_toolsets, get_tool_help
  - explorer (8): search_files, list_experiments, get_file_metadata,
                   get_experiment_detail, list_datasets, get_parse_result,
                   list_instruments, get_dataset_summary
  - planner (7): stub — populated when planner toolset is built
  - ingestor (4): stub — populated when ingestor toolset is built
  - admin (4): stub — populated when admin toolset is built

All tool names follow verb_noun snake_case pattern.
All responses include a 'suggestion' field for agent recovery.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from fastmcp import FastMCP

from app.mcp_server.context import MCPContext
from app.mcp_server.tools.explorer import EXPLORER_TOOLS

# Type alias for tool handler (sync or async callable)
ToolHandler = Callable[..., Any]


# ---------------------------------------------------------------------------
# Toolset metadata registry
# ---------------------------------------------------------------------------

TOOLSET_DESCRIPTIONS: dict[str, str] = {
    "discovery": "Tools for discovering available capabilities and toolsets.",
    "explorer": "Read-only tools for browsing experiments, data, instruments, and datasets.",
    "planner": "Tools for creating and managing ingestion pipelines.",
    "ingestor": "Tools for uploading, parsing, and managing instrument files.",
    "admin": "Administrative tools for users, audit logs, settings, and system health.",
}

# Tool -> toolset mapping (built during registration)
_TOOL_TOOLSET_MAP: dict[str, str] = {}

# All registered handler functions (for help introspection)
_TOOL_HANDLERS: dict[str, ToolHandler] = {}


def _get_tool_parameters(fn: Any) -> list[dict[str, str]]:
    """Extract parameter info from a function signature."""
    params = []
    sig = inspect.signature(fn)
    for name, param in sig.parameters.items():
        if name == "ctx":
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            type_str = "any"
        elif hasattr(annotation, "__name__"):
            type_str = annotation.__name__
        else:
            type_str = str(annotation).replace("typing.", "")
        default = (
            repr(param.default)
            if param.default is not inspect.Parameter.empty
            else "required"
        )
        params.append({
            "name": name,
            "type": type_str,
            "default": default,
        })
    return params


def _strip_ctx_from_doc(doc: str) -> str:
    """Remove ctx parameter documentation from a docstring."""
    lines = doc.split("\n")
    clean = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("ctx:"):
            skip = True
            continue
        if skip:
            # Continue skipping indented continuation of ctx description
            if stripped and not stripped[0].isupper() and ":" not in stripped[:30]:
                continue
            skip = False
        clean.append(line)
    return "\n".join(clean)


# ---------------------------------------------------------------------------
# Discovery tools (2)
# ---------------------------------------------------------------------------


def list_toolsets(ctx: MCPContext) -> dict[str, Any]:
    """List all available MCP toolsets and their tool counts.

    Returns a summary of each toolset with its description and the names
    of all tools it contains. Use this as the starting point to discover
    what the LabLink MCP server can do.

    Args:
        ctx: MCP execution context.

    Returns:
        Dict with 'toolsets' list and 'total_tools' count.
    """
    # Build toolset summaries from the registry
    toolset_tools: dict[str, list[str]] = {}
    for tool_name, toolset_name in _TOOL_TOOLSET_MAP.items():
        toolset_tools.setdefault(toolset_name, []).append(tool_name)

    toolsets = []
    total_tools = 0
    for name in sorted(TOOLSET_DESCRIPTIONS.keys()):
        tools = sorted(toolset_tools.get(name, []))
        count = len(tools)
        toolsets.append({
            "name": name,
            "description": TOOLSET_DESCRIPTIONS[name],
            "tool_count": count,
            "tools": tools,
        })
        total_tools += count

    return {
        "toolsets": toolsets,
        "total_tools": total_tools,
        "suggestion": "Use get_tool_help with a tool name for detailed usage information.",
    }


def get_tool_help(ctx: MCPContext, tool_name: str) -> dict[str, Any]:
    """Get detailed help for a specific MCP tool.

    Returns the tool's full docstring, parameter list, toolset membership,
    and usage suggestion.

    Args:
        ctx: MCP execution context.
        tool_name: Name of the tool to get help for (e.g. 'search_files').

    Returns:
        Dict with tool help information including parameters and description.
    """
    fn = _TOOL_HANDLERS.get(tool_name)
    if fn is None:
        available = sorted(_TOOL_HANDLERS.keys())
        return {
            "error": "not_found",
            "message": f"Tool '{tool_name}' not found.",
            "available_tools": available,
            "suggestion": f"Available tools: {', '.join(available)}. Use list_toolsets for an overview.",
        }

    toolset = _TOOL_TOOLSET_MAP.get(tool_name, "unknown")
    docstring = inspect.getdoc(fn) or "No documentation available."
    parameters = _get_tool_parameters(fn)

    return {
        "name": tool_name,
        "toolset": toolset,
        "description": docstring,
        "parameters": parameters,
        "suggestion": f"This tool belongs to the '{toolset}' toolset. Use list_toolsets to see related tools.",
    }


# ---------------------------------------------------------------------------
# FastMCP wrapper helper
# ---------------------------------------------------------------------------


def _wrap_tool(fn: ToolHandler, ctx: MCPContext) -> ToolHandler:
    """Create a wrapper that injects ctx as the first argument.

    Removes the 'ctx' parameter from the signature so FastMCP
    doesn't expose it as a tool parameter.  If the function
    doesn't have a 'ctx' parameter, returns it unchanged.

    FastMCP uses typing.get_type_hints() for parameter introspection,
    so we must also copy __annotations__ and __module__ to the wrapper.
    """
    import functools
    import typing

    sig = inspect.signature(fn)
    has_ctx = "ctx" in sig.parameters

    if not has_ctx:
        # No ctx param — return function as-is for FastMCP
        return fn

    params = [
        p for name, p in sig.parameters.items()
        if name != "ctx"
    ]
    new_sig = sig.replace(parameters=params)
    clean_doc = _strip_ctx_from_doc(fn.__doc__ or "")

    # Build annotations without 'ctx' for get_type_hints() compatibility
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = getattr(fn, "__annotations__", {})
    new_annotations = {k: v for k, v in hints.items() if k != "ctx"}

    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def wrapper(**kwargs: Any) -> Any:
            return await fn(ctx, **kwargs)
    else:
        @functools.wraps(fn)
        def wrapper(**kwargs: Any) -> Any:
            return fn(ctx, **kwargs)

    wrapper.__name__ = fn.__name__
    wrapper.__qualname__ = fn.__qualname__
    wrapper.__doc__ = clean_doc
    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    wrapper.__annotations__ = new_annotations
    wrapper.__module__ = fn.__module__
    return wrapper


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_mcp_server(ctx: MCPContext | None = None) -> FastMCP:
    """Create and configure the LabLink FastMCP server.

    Registers all toolsets with FastMCP:
      - discovery (2): list_toolsets, get_tool_help
      - explorer (8): search_files, list_experiments, etc.
      - planner (7): create_pipeline, validate_pipeline, etc.
      - ingestor (4): ingest_file, check_ingest_status, etc.
      - admin (4): manage_users, get_audit_log, etc.

    Explorer and discovery tools receive ctx injection; other toolsets
    are self-contained (no ctx parameter).

    Args:
        ctx: Optional MCP context. If None, a default context is created.

    Returns:
        Configured FastMCP server instance with 25 tools.
    """
    if ctx is None:
        ctx = MCPContext()

    # Clear registries for fresh server
    _TOOL_TOOLSET_MAP.clear()
    _TOOL_HANDLERS.clear()

    mcp = FastMCP(
        name="LabLink",
        instructions=(
            "LabLink MCP server for lab data integration. "
            "Start with list_toolsets to discover available tools, "
            "then use get_tool_help for detailed usage of any tool. "
            "All tools return structured JSON with a 'suggestion' field for next steps."
        ),
    )

    def _register(name: str, fn: ToolHandler, toolset: str) -> None:
        """Register a tool in both FastMCP and our metadata registries."""
        _TOOL_TOOLSET_MAP[name] = toolset
        _TOOL_HANDLERS[name] = fn
        wrapped = _wrap_tool(fn, ctx)
        mcp.tool()(wrapped)

    # --- Discovery tools (2) ---
    _register("list_toolsets", list_toolsets, "discovery")
    _register("get_tool_help", get_tool_help, "discovery")

    # --- Explorer tools (8) ---
    for name, fn in EXPLORER_TOOLS.items():
        _register(name, fn, "explorer")

    # --- Planner tools (7) ---
    from app.mcp_server.tools.planner import PLANNER_TOOLS

    for name, fn in PLANNER_TOOLS.items():
        _register(name, fn, "planner")

    # --- Ingestor tools (4) ---
    from app.mcp_server.tools.ingestor import (
        check_ingest_status,
        ingest_file,
        list_parsers,
        retry_ingest,
    )

    _register("ingest_file", ingest_file, "ingestor")
    _register("check_ingest_status", check_ingest_status, "ingestor")
    _register("retry_ingest", retry_ingest, "ingestor")
    _register("list_parsers", list_parsers, "ingestor")

    # --- Admin tools (4) ---
    from app.mcp_server.tools.admin import (
        get_audit_log,
        get_system_health,
        manage_users,
        update_settings,
    )

    _register("manage_users", manage_users, "admin")
    _register("get_audit_log", get_audit_log, "admin")
    _register("update_settings", update_settings, "admin")
    _register("get_system_health", get_system_health, "admin")

    return mcp
