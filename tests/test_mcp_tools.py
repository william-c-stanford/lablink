"""Tests for MCP server tool selection and toolset routing.

Covers:
- list_toolsets() returns all 4 toolsets with correct metadata
- get_toolset() returns the correct tool list for each toolset
- Agent can navigate from discovery tools to specific tool names
- Toolset consistency: tools listed in list_toolsets match those in get_toolset
- All toolsets are symmetric (every tool in _TOOLSETS appears in get_toolset output)
- Unknown toolset handling (error response, not exception)
- Tool entries have required fields (name, description)
- MCP server is importable and properly named
"""

from __future__ import annotations

import pytest

from lablink.mcp.server import _TOOLSETS, get_toolset, list_toolsets, mcp

# ---------------------------------------------------------------------------
# Expected tool inventories
# ---------------------------------------------------------------------------

EXPLORER_TOOLS = [
    "list_experiments",
    "get_experiment",
    "get_instrument_data",
    "search_catalog",
    "list_instruments",
    "list_uploads",
    "get_chart_data",
    "create_export",
]

PLANNER_TOOLS = [
    "create_experiment",
    "update_experiment",
    "record_outcome",
    "link_upload_to_experiment",
    "create_campaign",
    "get_campaign_progress",
    "list_campaigns",
]

INGESTOR_TOOLS = [
    "create_upload",
    "list_parsers",
    "get_upload",
    "reparse_upload",
]

ADMIN_TOOLS = [
    "get_usage_stats",
    "list_agents",
    "create_webhook",
    "list_audit_events",
]

ALL_TOOLSETS = {
    "explorer": EXPLORER_TOOLS,
    "planner": PLANNER_TOOLS,
    "ingestor": INGESTOR_TOOLS,
    "admin": ADMIN_TOOLS,
}


# ---------------------------------------------------------------------------
# Server instance tests
# ---------------------------------------------------------------------------


class TestMCPServerInstance:
    def test_server_is_importable(self):
        """The FastMCP server instance is importable from lablink.mcp.server."""
        assert mcp is not None

    def test_server_named_lablink(self):
        """Server is named 'LabLink' (agents use this to identify the server)."""
        assert mcp.name == "LabLink"

    def test_server_has_instructions(self):
        """Server has non-empty instructions for agent orientation."""
        assert mcp.instructions
        assert len(mcp.instructions) > 20

    def test_toolsets_metadata_is_accessible(self):
        """_TOOLSETS dict is importable and non-empty."""
        assert _TOOLSETS
        assert len(_TOOLSETS) == 4


# ---------------------------------------------------------------------------
# list_toolsets() — agent discovery entry point
# ---------------------------------------------------------------------------


class TestListToolsets:
    def test_returns_all_four_toolsets(self):
        """An agent calling list_toolsets sees all 4 toolset categories."""
        result = list_toolsets()
        assert "data" in result
        assert set(result["data"].keys()) == {"explorer", "planner", "ingestor", "admin"}

    def test_meta_total_toolsets(self):
        """list_toolsets meta includes total_toolsets = 4."""
        result = list_toolsets()
        assert result["meta"]["total_toolsets"] == 4

    def test_explorer_tool_count(self):
        """Explorer toolset reports 8 tools."""
        result = list_toolsets()
        assert result["data"]["explorer"]["tool_count"] == 8

    def test_planner_tool_count(self):
        """Planner toolset reports 7 tools."""
        result = list_toolsets()
        assert result["data"]["planner"]["tool_count"] == 7

    def test_ingestor_tool_count(self):
        """Ingestor toolset reports 4 tools."""
        result = list_toolsets()
        assert result["data"]["ingestor"]["tool_count"] == 4

    def test_admin_tool_count(self):
        """Admin toolset reports 4 tools."""
        result = list_toolsets()
        assert result["data"]["admin"]["tool_count"] == 4

    def test_toolset_descriptions_present(self):
        """Each toolset entry in list_toolsets has a description."""
        result = list_toolsets()
        for name, info in result["data"].items():
            assert "description" in info, f"'{name}' missing description"
            assert info["description"], f"'{name}' has empty description"

    def test_toolset_includes_tool_name_list(self):
        """Each toolset entry includes the list of tool names (for quick agent navigation)."""
        result = list_toolsets()
        for name, info in result["data"].items():
            assert "tools" in info, f"'{name}' missing tools list"
            assert isinstance(info["tools"], list)
            assert len(info["tools"]) > 0

    def test_tool_names_in_list_toolsets_match_toolset_contents(self):
        """Tool names in list_toolsets exactly match _TOOLSETS keys."""
        result = list_toolsets()
        for toolset_name in ALL_TOOLSETS:
            reported = set(result["data"][toolset_name]["tools"])
            expected = set(_TOOLSETS[toolset_name].keys())
            assert reported == expected, (
                f"list_toolsets tools for '{toolset_name}' don't match _TOOLSETS: "
                f"extra={reported - expected}, missing={expected - reported}"
            )


# ---------------------------------------------------------------------------
# get_toolset() — agent drills into a specific category
# ---------------------------------------------------------------------------


class TestGetToolset:
    @pytest.mark.parametrize(
        "toolset_name,expected_tools",
        [
            ("explorer", EXPLORER_TOOLS),
            ("planner", PLANNER_TOOLS),
            ("ingestor", INGESTOR_TOOLS),
            ("admin", ADMIN_TOOLS),
        ],
    )
    def test_returns_correct_tools_for_each_toolset(
        self, toolset_name: str, expected_tools: list[str]
    ):
        """get_toolset(name) returns exactly the expected tools for that category."""
        result = get_toolset(toolset_name)
        assert result["data"]["toolset"] == toolset_name
        returned_names = {t["name"] for t in result["data"]["tools"]}
        assert returned_names == set(expected_tools), (
            f"Toolset '{toolset_name}' mismatch: "
            f"extra={returned_names - set(expected_tools)}, "
            f"missing={set(expected_tools) - returned_names}"
        )

    @pytest.mark.parametrize(
        "toolset_name,expected_count",
        [
            ("explorer", 8),
            ("planner", 7),
            ("ingestor", 4),
            ("admin", 4),
        ],
    )
    def test_meta_tool_count_matches(self, toolset_name: str, expected_count: int):
        """meta.tool_count in get_toolset response matches actual tool count."""
        result = get_toolset(toolset_name)
        assert result["meta"]["tool_count"] == expected_count

    def test_each_tool_entry_has_name_and_description(self):
        """Every tool entry returned by get_toolset has both name and description."""
        for toolset_name in ALL_TOOLSETS:
            result = get_toolset(toolset_name)
            for tool_entry in result["data"]["tools"]:
                assert "name" in tool_entry, f"Tool entry in '{toolset_name}' missing 'name'"
                assert "description" in tool_entry, (
                    f"Tool '{tool_entry.get('name')}' in '{toolset_name}' missing 'description'"
                )
                assert tool_entry["description"], (
                    f"Tool '{tool_entry['name']}' has empty description"
                )

    def test_unknown_toolset_returns_error_not_exception(self):
        """get_toolset with an unknown name returns an error dict, not a Python exception."""
        result = get_toolset("nonexistent_toolset")
        assert "errors" in result
        assert result["data"] is None

    def test_error_response_includes_suggestion(self):
        """Error response for unknown toolset includes a suggestion with valid names."""
        result = get_toolset("unknown")
        errors = result["errors"]
        assert len(errors) > 0
        suggestion = errors[0].get("suggestion", "")
        # Suggestion should mention at least one valid toolset name
        assert any(name in suggestion for name in ALL_TOOLSETS), (
            f"Suggestion does not mention any valid toolset: {suggestion!r}"
        )

    def test_error_response_has_not_found_code(self):
        """Error response for unknown toolset has 'not_found' code."""
        result = get_toolset("missing")
        assert result["errors"][0]["code"] == "not_found"


# ---------------------------------------------------------------------------
# Agent workflow simulation — chaining discovery → selection
# ---------------------------------------------------------------------------


class TestAgentWorkflowSimulation:
    def test_agent_can_find_data_exploration_tools(self):
        """An agent querying for 'data exploration' can navigate to explorer tools."""
        # Step 1: list toolsets to learn what's available
        toolsets_result = list_toolsets()
        toolset_names = list(toolsets_result["data"].keys())
        assert "explorer" in toolset_names

        # Step 2: drill into explorer to get tool names
        explorer_result = get_toolset("explorer")
        tool_names = {t["name"] for t in explorer_result["data"]["tools"]}

        # Agent can find data access tools
        assert "get_instrument_data" in tool_names
        assert "search_catalog" in tool_names
        assert "list_experiments" in tool_names

    def test_agent_can_find_experiment_management_tools(self):
        """An agent planning an experiment navigates to planner toolset."""
        toolsets_result = list_toolsets()
        assert "planner" in toolsets_result["data"]

        planner_result = get_toolset("planner")
        tool_names = {t["name"] for t in planner_result["data"]["tools"]}

        assert "create_experiment" in tool_names
        assert "record_outcome" in tool_names
        assert "create_campaign" in tool_names

    def test_agent_can_find_file_ingestion_tools(self):
        """An agent uploading files navigates to ingestor toolset."""
        ingestor_result = get_toolset("ingestor")
        tool_names = {t["name"] for t in ingestor_result["data"]["tools"]}

        assert "create_upload" in tool_names
        assert "list_parsers" in tool_names

    def test_all_toolset_tools_consistently_listed(self):
        """Every tool name in _TOOLSETS is reachable via get_toolset."""
        for toolset_name, expected_tools in ALL_TOOLSETS.items():
            result = get_toolset(toolset_name)
            returned_names = {t["name"] for t in result["data"]["tools"]}
            for expected_name in expected_tools:
                assert expected_name in returned_names, (
                    f"Tool '{expected_name}' missing from get_toolset('{toolset_name}') output"
                )
