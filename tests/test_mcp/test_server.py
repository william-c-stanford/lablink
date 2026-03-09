"""Tests for MCP server structure, registration, and constraints."""


from app.mcp_server.context import MCPContext
from app.mcp_server.server import (
    TOOLSET_DESCRIPTIONS,
    _TOOL_TOOLSET_MAP,
    create_mcp_server,
)


class TestMCPServerStructure:
    """Tests for the MCP server — tool count, naming, toolsets."""

    def test_server_creates_with_25_tools(self, tool_handlers):
        """Server must have exactly 25 tools (hard constraint)."""
        assert len(tool_handlers) == 25

    def test_five_toolsets_present(self, tool_toolset_map):
        """All 5 toolsets must be registered."""
        toolsets = set(tool_toolset_map.values())
        expected = {"admin", "discovery", "explorer", "ingestor", "planner"}
        assert toolsets == expected

    def test_toolset_sizes(self, tool_toolset_map):
        """Each toolset has the correct number of tools."""
        expected_sizes = {
            "discovery": 2,
            "explorer": 8,
            "planner": 7,
            "ingestor": 4,
            "admin": 4,
        }
        from collections import Counter

        actual = Counter(tool_toolset_map.values())
        for name, expected_count in expected_sizes.items():
            assert actual[name] == expected_count, (
                f"Toolset '{name}' has {actual[name]} tools, expected {expected_count}"
            )

    def test_all_tool_names_snake_case(self, tool_handlers):
        """All tool names must follow verb_noun snake_case pattern."""
        for name in tool_handlers.keys():
            assert "_" in name, f"Tool '{name}' is not snake_case (missing underscore)"
            assert name == name.lower(), f"Tool '{name}' has uppercase characters"
            assert not name.startswith("_"), f"Tool '{name}' starts with underscore"

    def test_no_duplicate_tool_names(self, tool_toolset_map):
        """No tool name appears in multiple toolsets."""
        names = list(tool_toolset_map.keys())
        assert len(names) == len(set(names))

    def test_toolset_descriptions_complete(self):
        """Every toolset must have a description."""
        for name in ["discovery", "explorer", "planner", "ingestor", "admin"]:
            assert name in TOOLSET_DESCRIPTIONS
            assert len(TOOLSET_DESCRIPTIONS[name]) > 10

    def test_server_name_is_lablink(self, mcp_server):
        """Server has the correct name."""
        assert mcp_server.name == "LabLink"

    def test_server_has_instructions(self, mcp_server):
        """Server has agent-friendly instructions."""
        assert mcp_server.instructions is not None
        assert "list_toolsets" in mcp_server.instructions

    def test_multiple_servers_independent(self):
        """Creating multiple servers populates the global registry."""
        ctx1 = MCPContext()
        ctx2 = MCPContext()
        create_mcp_server(ctx1)
        assert len(_TOOL_TOOLSET_MAP) == 25
        create_mcp_server(ctx2)
        assert len(_TOOL_TOOLSET_MAP) == 25


class TestToolsetCountInvariants:
    """Verify the 2+8+7+4+4=25 tool distribution."""

    def test_sum_to_25(self, tool_handlers):
        assert len(tool_handlers) == 25

    def test_explorer_has_expected_tools(self, tool_toolset_map):
        explorer_tools = {
            k for k, v in tool_toolset_map.items()
            if v == "explorer"
        }
        expected = {
            "search_files",
            "list_experiments",
            "get_file_metadata",
            "get_experiment_detail",
            "list_datasets",
            "get_parse_result",
            "list_instruments",
            "get_dataset_summary",
        }
        assert explorer_tools == expected

    def test_discovery_has_expected_tools(self, tool_toolset_map):
        discovery_tools = {
            k for k, v in tool_toolset_map.items()
            if v == "discovery"
        }
        expected = {"list_toolsets", "get_tool_help"}
        assert discovery_tools == expected
