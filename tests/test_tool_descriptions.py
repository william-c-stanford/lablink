"""Quality checks on the LabLink MCP server tool registry.

Covers:
- All 4 toolsets present with correct tool counts
- All tool names follow verb_noun snake_case convention
- All tool descriptions are non-empty and mention a return type
- Discovery tools (list_toolsets, get_toolset) are registered and callable
- Total domain tool count is exactly 23 (8+7+4+4) with 2 discovery = 25 total
- Toolset descriptions are non-empty
- No duplicate tool names across toolsets
"""

from __future__ import annotations

import re

import pytest

from lablink.mcp.server import _TOOLSETS, get_toolset, list_toolsets

# ---------------------------------------------------------------------------
# Expected counts
# ---------------------------------------------------------------------------

EXPECTED_TOOLSETS = {
    "explorer": 8,
    "planner": 7,
    "ingestor": 4,
    "admin": 4,
}
EXPECTED_DOMAIN_TOOL_COUNT = sum(EXPECTED_TOOLSETS.values())  # 23

VERB_NOUN_PATTERN = re.compile(r"^[a-z]+(_[a-z]+)+$")

DISCOVERY_TOOL_NAMES = {"list_toolsets", "get_toolset"}


# ---------------------------------------------------------------------------
# Toolset structure tests
# ---------------------------------------------------------------------------


class TestToolsetStructure:
    def test_all_four_toolsets_present(self):
        """_TOOLSETS contains exactly the 4 required toolset keys."""
        assert set(_TOOLSETS.keys()) == set(EXPECTED_TOOLSETS.keys())

    def test_toolset_tool_counts(self):
        """Each toolset has the exact number of tools specified in the roadmap."""
        for name, expected_count in EXPECTED_TOOLSETS.items():
            actual = len(_TOOLSETS[name])
            assert actual == expected_count, (
                f"Toolset '{name}' has {actual} tools, expected {expected_count}"
            )

    def test_total_domain_tool_count(self):
        """Total domain tool count is 23 (guards against accidental additions/removals)."""
        total = sum(len(tools) for tools in _TOOLSETS.values())
        assert total == EXPECTED_DOMAIN_TOOL_COUNT

    def test_no_duplicate_tool_names(self):
        """No tool name appears in more than one toolset."""
        all_names: list[str] = []
        for tools in _TOOLSETS.values():
            all_names.extend(tools.keys())
        assert len(all_names) == len(set(all_names)), (
            f"Duplicate tool names found: "
            f"{[n for n in all_names if all_names.count(n) > 1]}"
        )


# ---------------------------------------------------------------------------
# Naming convention tests
# ---------------------------------------------------------------------------


class TestToolNamingConvention:
    @pytest.mark.parametrize("toolset_name", list(EXPECTED_TOOLSETS.keys()))
    def test_all_tools_follow_verb_noun_pattern(self, toolset_name: str):
        """All tool names in a toolset match ^[a-z]+(_[a-z]+)+$."""
        for tool_name in _TOOLSETS[toolset_name]:
            assert VERB_NOUN_PATTERN.match(tool_name), (
                f"Tool '{tool_name}' in '{toolset_name}' does not follow "
                f"verb_noun snake_case convention"
            )

    def test_explorer_tools_have_expected_names(self):
        """Explorer toolset contains exactly the 8 expected named tools."""
        expected = {
            "list_experiments",
            "get_experiment",
            "get_instrument_data",
            "search_catalog",
            "list_instruments",
            "list_uploads",
            "get_chart_data",
            "create_export",
        }
        assert set(_TOOLSETS["explorer"].keys()) == expected

    def test_planner_tools_have_expected_names(self):
        """Planner toolset contains exactly the 7 expected named tools."""
        expected = {
            "create_experiment",
            "update_experiment",
            "record_outcome",
            "link_upload_to_experiment",
            "create_campaign",
            "get_campaign_progress",
            "list_campaigns",
        }
        assert set(_TOOLSETS["planner"].keys()) == expected

    def test_ingestor_tools_have_expected_names(self):
        """Ingestor toolset contains exactly the 4 expected named tools."""
        expected = {"create_upload", "list_parsers", "get_upload", "reparse_upload"}
        assert set(_TOOLSETS["ingestor"].keys()) == expected

    def test_admin_tools_have_expected_names(self):
        """Admin toolset contains exactly the 4 expected named tools."""
        expected = {
            "get_usage_stats",
            "list_agents",
            "create_webhook",
            "list_audit_events",
        }
        assert set(_TOOLSETS["admin"].keys()) == expected


# ---------------------------------------------------------------------------
# Description quality tests
# ---------------------------------------------------------------------------


class TestToolDescriptions:
    @pytest.mark.parametrize("toolset_name", list(EXPECTED_TOOLSETS.keys()))
    def test_all_descriptions_are_non_empty(self, toolset_name: str):
        """Every tool in every toolset has a non-empty description string."""
        for tool_name, description in _TOOLSETS[toolset_name].items():
            assert description and description.strip(), (
                f"Tool '{tool_name}' in '{toolset_name}' has an empty description"
            )

    @pytest.mark.parametrize("toolset_name", list(EXPECTED_TOOLSETS.keys()))
    def test_all_descriptions_mention_returns(self, toolset_name: str):
        """Every description includes a 'Returns' clause (agent-readability requirement)."""
        for tool_name, description in _TOOLSETS[toolset_name].items():
            assert "Returns" in description, (
                f"Tool '{tool_name}' description missing 'Returns' clause: {description!r}"
            )

    @pytest.mark.parametrize("toolset_name", list(EXPECTED_TOOLSETS.keys()))
    def test_all_descriptions_minimum_length(self, toolset_name: str):
        """Every description is at least 20 characters (not a placeholder)."""
        for tool_name, description in _TOOLSETS[toolset_name].items():
            assert len(description) >= 20, (
                f"Tool '{tool_name}' has suspiciously short description: {description!r}"
            )


# ---------------------------------------------------------------------------
# Discovery tool tests
# ---------------------------------------------------------------------------


class TestDiscoveryTools:
    def test_list_toolsets_is_callable(self):
        """list_toolsets is importable and callable as a plain function."""
        assert callable(list_toolsets)

    def test_get_toolset_is_callable(self):
        """get_toolset is importable and callable as a plain function."""
        assert callable(get_toolset)

    def test_list_toolsets_returns_dict(self):
        """list_toolsets() returns a dict with a 'data' key."""
        result = list_toolsets()
        assert isinstance(result, dict)
        assert "data" in result

    def test_list_toolsets_has_all_four_toolsets(self):
        """list_toolsets() data contains all 4 toolset keys."""
        result = list_toolsets()
        assert set(result["data"].keys()) == set(EXPECTED_TOOLSETS.keys())

    def test_list_toolsets_tool_counts_in_output(self):
        """list_toolsets() output reports correct tool_count for each toolset."""
        result = list_toolsets()
        for name, expected_count in EXPECTED_TOOLSETS.items():
            actual = result["data"][name]["tool_count"]
            assert actual == expected_count, (
                f"list_toolsets() reports {actual} tools for '{name}', "
                f"expected {expected_count}"
            )

    def test_list_toolsets_includes_tool_names(self):
        """list_toolsets() data includes the 'tools' list for each toolset."""
        result = list_toolsets()
        for name in EXPECTED_TOOLSETS:
            assert "tools" in result["data"][name]
            assert isinstance(result["data"][name]["tools"], list)

    def test_get_toolset_explorer_returns_correct_count(self):
        """get_toolset('explorer') returns 8 tools."""
        result = get_toolset("explorer")
        assert result["data"]["toolset"] == "explorer"
        assert result["meta"]["tool_count"] == 8

    def test_get_toolset_planner_returns_correct_count(self):
        """get_toolset('planner') returns 7 tools."""
        result = get_toolset("planner")
        assert result["meta"]["tool_count"] == 7

    def test_get_toolset_ingestor_returns_correct_count(self):
        """get_toolset('ingestor') returns 4 tools."""
        result = get_toolset("ingestor")
        assert result["meta"]["tool_count"] == 4

    def test_get_toolset_admin_returns_correct_count(self):
        """get_toolset('admin') returns 4 tools."""
        result = get_toolset("admin")
        assert result["meta"]["tool_count"] == 4

    def test_get_toolset_invalid_name_returns_error(self):
        """get_toolset with unknown name returns error dict (not exception)."""
        result = get_toolset("nonexistent")
        assert result["data"] is None
        assert "errors" in result
        assert len(result["errors"]) > 0
        # Error should include suggestion for valid names
        suggestion = result["errors"][0].get("suggestion", "")
        assert "explorer" in suggestion

    def test_get_toolset_tools_have_name_and_description(self):
        """Each tool entry returned by get_toolset has name and description."""
        result = get_toolset("explorer")
        tools = result["data"]["tools"]
        for tool_entry in tools:
            assert "name" in tool_entry
            assert "description" in tool_entry
            assert tool_entry["name"]
            assert tool_entry["description"]

    def test_discovery_tool_names_not_in_domain_toolsets(self):
        """'list_toolsets' and 'get_toolset' are not listed in any domain toolset."""
        for toolset_name, tools in _TOOLSETS.items():
            for discovery_name in DISCOVERY_TOOL_NAMES:
                assert discovery_name not in tools, (
                    f"Discovery tool '{discovery_name}' should not appear in "
                    f"domain toolset '{toolset_name}'"
                )
