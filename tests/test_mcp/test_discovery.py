"""Tests for Discovery tools: list_toolsets, get_tool_help."""


from app.mcp_server.server import list_toolsets, get_tool_help


class TestListToolsets:
    """Tests for the list_toolsets discovery tool."""

    def test_returns_all_five_toolsets(self, mcp_server, mcp_ctx):
        """list_toolsets returns all 5 toolset categories."""
        result = list_toolsets(mcp_ctx)
        assert "toolsets" in result
        names = {ts["name"] for ts in result["toolsets"]}
        assert names == {"admin", "discovery", "explorer", "ingestor", "planner"}

    def test_each_toolset_has_description(self, mcp_server, mcp_ctx):
        """Every toolset entry has a non-empty description."""
        result = list_toolsets(mcp_ctx)
        for ts in result["toolsets"]:
            assert "description" in ts
            assert len(ts["description"]) > 0

    def test_each_toolset_has_tool_count(self, mcp_server, mcp_ctx):
        """Each toolset shows its tool count."""
        result = list_toolsets(mcp_ctx)
        for ts in result["toolsets"]:
            assert "tool_count" in ts
            assert ts["tool_count"] > 0

    def test_each_toolset_lists_tool_names(self, mcp_server, mcp_ctx):
        """Each toolset lists its tool names."""
        result = list_toolsets(mcp_ctx)
        for ts in result["toolsets"]:
            assert "tools" in ts
            assert isinstance(ts["tools"], list)
            assert len(ts["tools"]) == ts["tool_count"]

    def test_total_tools_is_25(self, mcp_server, mcp_ctx):
        """Total tools across all toolsets is 25."""
        result = list_toolsets(mcp_ctx)
        assert result["total_tools"] == 25

    def test_includes_suggestion(self, mcp_server, mcp_ctx):
        """list_toolsets includes an agent-friendly suggestion."""
        result = list_toolsets(mcp_ctx)
        assert "suggestion" in result
        assert "get_tool_help" in result["suggestion"]

    def test_explorer_toolset_has_8_tools(self, mcp_server, mcp_ctx):
        """The explorer toolset entry shows 8 tools."""
        result = list_toolsets(mcp_ctx)
        explorer = next(ts for ts in result["toolsets"] if ts["name"] == "explorer")
        assert explorer["tool_count"] == 8
        assert "search_files" in explorer["tools"]

    def test_discovery_toolset_has_2_tools(self, mcp_server, mcp_ctx):
        """The discovery toolset entry shows 2 tools."""
        result = list_toolsets(mcp_ctx)
        discovery = next(ts for ts in result["toolsets"] if ts["name"] == "discovery")
        assert discovery["tool_count"] == 2
        assert "list_toolsets" in discovery["tools"]
        assert "get_tool_help" in discovery["tools"]


class TestGetToolHelp:
    """Tests for the get_tool_help discovery tool."""

    def test_returns_help_for_explorer_tool(self, mcp_server, mcp_ctx):
        """get_tool_help returns help for search_files."""
        result = get_tool_help(mcp_ctx, "search_files")
        assert result["name"] == "search_files"
        assert result["toolset"] == "explorer"
        assert "description" in result
        assert "parameters" in result
        assert len(result["parameters"]) > 0

    def test_returns_help_for_discovery_tool(self, mcp_server, mcp_ctx):
        """get_tool_help returns help for list_toolsets."""
        result = get_tool_help(mcp_ctx, "list_toolsets")
        assert result["name"] == "list_toolsets"
        assert result["toolset"] == "discovery"

    def test_parameters_have_name_type_default(self, mcp_server, mcp_ctx):
        """Tool parameters include name, type, and default."""
        result = get_tool_help(mcp_ctx, "search_files")
        for param in result["parameters"]:
            assert "name" in param
            assert "type" in param
            assert "default" in param

    def test_search_files_has_query_param(self, mcp_server, mcp_ctx):
        """search_files parameters include 'query'."""
        result = get_tool_help(mcp_ctx, "search_files")
        param_names = [p["name"] for p in result["parameters"]]
        assert "query" in param_names

    def test_unknown_tool_returns_error(self, mcp_server, mcp_ctx):
        """get_tool_help with unknown name returns error with suggestion."""
        result = get_tool_help(mcp_ctx, "nonexistent_tool")
        assert result["error"] == "not_found"
        assert "suggestion" in result
        assert "available_tools" in result
        assert len(result["available_tools"]) == 25

    def test_includes_suggestion(self, mcp_server, mcp_ctx):
        """get_tool_help includes agent-friendly suggestion."""
        result = get_tool_help(mcp_ctx, "list_experiments")
        assert "suggestion" in result
        assert "toolset" in result["suggestion"]

    def test_help_for_all_explorer_tools(self, mcp_server, mcp_ctx):
        """get_tool_help works for every explorer tool."""
        explorer_tools = [
            "search_files", "list_experiments", "get_file_metadata",
            "get_experiment_detail", "list_datasets", "get_parse_result",
            "list_instruments", "get_dataset_summary",
        ]
        for tool_name in explorer_tools:
            result = get_tool_help(mcp_ctx, tool_name)
            assert "error" not in result, f"get_tool_help failed for {tool_name}"
            assert result["toolset"] == "explorer"
