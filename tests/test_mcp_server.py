"""Tests for the MCP server — all 25 tools across 5 toolsets.

Verifies:
1. Server creation and tool registration (exactly 25 tools)
2. Tool-to-toolset mapping correctness
3. Discovery tools (2): list_toolsets, get_tool_help
4. Explorer tools (8): search_files, list_experiments, get_file_metadata,
   get_experiment_detail, list_datasets, get_parse_result, list_instruments,
   get_dataset_summary
5. Planner tools (7): create_pipeline, validate_pipeline, estimate_duration,
   list_pipelines, get_pipeline, update_pipeline, delete_pipeline
6. Ingestor tools (4): ingest_file, check_ingest_status, retry_ingest, list_parsers
7. Admin tools (4): manage_users, get_audit_log, update_settings, get_system_health
8. All tool responses include 'suggestion' field
9. verb_noun snake_case naming convention
"""

from __future__ import annotations

import re

import pytest

from app.mcp_server.context import MCPContext
from app.mcp_server.server import (
    _TOOL_HANDLERS,
    _TOOL_TOOLSET_MAP,
    create_mcp_server,
    get_tool_help,
    list_toolsets,
)
from app.mcp_server.tools.explorer import EXPLORER_TOOLS
from app.mcp_server.tools.planner import PLANNER_TOOLS, get_pipeline_store


# ---------------------------------------------------------------------------
# Expected tool names per toolset
# ---------------------------------------------------------------------------

EXPECTED_DISCOVERY_TOOLS = {"list_toolsets", "get_tool_help"}
EXPECTED_EXPLORER_TOOLS = {
    "search_files", "list_experiments", "get_file_metadata",
    "get_experiment_detail", "list_datasets", "get_parse_result",
    "list_instruments", "get_dataset_summary",
}
EXPECTED_PLANNER_TOOLS = {
    "create_pipeline", "validate_pipeline", "estimate_duration",
    "list_pipelines", "get_pipeline", "update_pipeline", "delete_pipeline",
}
EXPECTED_INGESTOR_TOOLS = {
    "ingest_file", "check_ingest_status", "retry_ingest", "list_parsers",
}
EXPECTED_ADMIN_TOOLS = {
    "manage_users", "get_audit_log", "update_settings", "get_system_health",
}

ALL_EXPECTED_TOOLS = (
    EXPECTED_DISCOVERY_TOOLS
    | EXPECTED_EXPLORER_TOOLS
    | EXPECTED_PLANNER_TOOLS
    | EXPECTED_INGESTOR_TOOLS
    | EXPECTED_ADMIN_TOOLS
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mcp_ctx() -> MCPContext:
    """Create a fresh MCPContext with sample data."""
    ctx = MCPContext(org_id="org-test", user_id="user-test")

    # Seed sample uploads
    ctx.uploads["file-1"] = {
        "file_id": "file-1",
        "file_name": "spectrum_001.csv",
        "file_hash": "abc123",
        "instrument_type": "spectrophotometer",
        "instrument_id": "inst-1",
        "status": "parsed",
        "experiment_id": "exp-1",
        "created_at": "2025-01-01T10:00:00Z",
        "parse_result": {
            "parser_name": "spectrophotometer",
            "instrument_type": "spectrophotometer",
            "measurements": [
                {"name": "absorbance", "value": 0.52, "sample_id": "s1"},
                {"name": "absorbance", "value": 0.89, "sample_id": "s2"},
            ],
        },
    }
    ctx.uploads["file-2"] = {
        "file_id": "file-2",
        "file_name": "hplc_run.csv",
        "file_hash": "def456",
        "instrument_type": "hplc",
        "instrument_id": "inst-2",
        "status": "uploaded",
        "created_at": "2025-01-02T10:00:00Z",
    }

    # Seed experiments
    ctx.experiments["exp-1"] = {
        "experiment_id": "exp-1",
        "name": "UV-Vis Calibration",
        "org_id": "org-test",
        "status": "running",
        "created_at": "2025-01-01T09:00:00Z",
    }
    ctx.experiments["exp-2"] = {
        "experiment_id": "exp-2",
        "name": "HPLC Method Dev",
        "org_id": "org-other",
        "status": "draft",
        "created_at": "2025-01-02T09:00:00Z",
    }

    # Seed instruments
    ctx.instruments["inst-1"] = {
        "id": "inst-1",
        "name": "UV-Vis 3000",
        "instrument_type": "spectrophotometer",
        "lab_id": "lab-1",
        "is_active": True,
    }
    ctx.instruments["inst-2"] = {
        "id": "inst-2",
        "name": "HPLC Agilent 1260",
        "instrument_type": "hplc",
        "lab_id": "lab-1",
        "is_active": True,
    }
    ctx.instruments["inst-3"] = {
        "id": "inst-3",
        "name": "Old Balance",
        "instrument_type": "balance",
        "lab_id": "lab-2",
        "is_active": False,
    }

    # Seed search_index (datasets)
    ctx.search_index.append({
        "type": "dataset",
        "id": "ds-1",
        "name": "UV-Vis Dataset #1",
        "instrument_type": "spectrophotometer",
        "org_id": "org-test",
        "sample_count": 2,
        "measurement_count": 6,
        "warning_count": 0,
        "error_count": 0,
        "parser_name": "spectrophotometer",
        "created_at": "2025-01-01T12:00:00Z",
        "measurements": [
            {"name": "absorbance", "value": 0.52, "sample_id": "s1", "quality": "good"},
            {"name": "absorbance", "value": 0.89, "sample_id": "s2", "quality": "good"},
            {"name": "absorbance", "value": 1.23, "sample_id": "s3", "quality": "warning"},
        ],
        "instrument_settings": {"wavelength_range": "200-800nm"},
    })
    ctx.search_index.append({
        "type": "dataset",
        "id": "ds-2",
        "name": "HPLC Dataset #1",
        "instrument_type": "hplc",
        "org_id": "org-test",
        "created_at": "2025-01-02T12:00:00Z",
        "measurements": [],
    })

    return ctx


@pytest.fixture()
def mcp_server(mcp_ctx: MCPContext):
    """Create MCP server with seeded context."""
    server = create_mcp_server(mcp_ctx)
    yield server
    # Clean up pipeline store
    get_pipeline_store().clear()


# ===================================================================
# 1. REGISTRATION TESTS — verifying all 25 tools are correctly wired
# ===================================================================


class TestToolRegistration:
    """Verify that create_mcp_server registers exactly 25 tools."""

    def test_total_tool_count(self, mcp_server):
        """Exactly 25 tools are registered."""
        assert len(_TOOL_TOOLSET_MAP) == 25

    def test_all_expected_tools_registered(self, mcp_server):
        """All expected tool names appear in the registry."""
        registered = set(_TOOL_TOOLSET_MAP.keys())
        assert registered == ALL_EXPECTED_TOOLS

    def test_discovery_toolset_count(self, mcp_server):
        tools = {k for k, v in _TOOL_TOOLSET_MAP.items() if v == "discovery"}
        assert tools == EXPECTED_DISCOVERY_TOOLS

    def test_explorer_toolset_count(self, mcp_server):
        tools = {k for k, v in _TOOL_TOOLSET_MAP.items() if v == "explorer"}
        assert tools == EXPECTED_EXPLORER_TOOLS

    def test_planner_toolset_count(self, mcp_server):
        tools = {k for k, v in _TOOL_TOOLSET_MAP.items() if v == "planner"}
        assert tools == EXPECTED_PLANNER_TOOLS

    def test_ingestor_toolset_count(self, mcp_server):
        tools = {k for k, v in _TOOL_TOOLSET_MAP.items() if v == "ingestor"}
        assert tools == EXPECTED_INGESTOR_TOOLS

    def test_admin_toolset_count(self, mcp_server):
        tools = {k for k, v in _TOOL_TOOLSET_MAP.items() if v == "admin"}
        assert tools == EXPECTED_ADMIN_TOOLS

    def test_all_handlers_callable(self, mcp_server):
        """Every registered handler is a callable."""
        for name, fn in _TOOL_HANDLERS.items():
            assert callable(fn), f"Handler for '{name}' is not callable"

    def test_tool_names_snake_case(self, mcp_server):
        """All tool names use verb_noun snake_case pattern."""
        snake = re.compile(r"^[a-z]+(_[a-z]+)+$")
        for name in _TOOL_TOOLSET_MAP:
            assert snake.match(name), f"Tool '{name}' does not match snake_case pattern"

    def test_server_name(self, mcp_server):
        """Server is named 'LabLink'."""
        assert mcp_server.name == "LabLink"

    def test_server_has_instructions(self, mcp_server):
        """Server has non-empty instructions."""
        assert mcp_server.instructions is not None


# ===================================================================
# 2. DISCOVERY TOOLS (2)
# ===================================================================


class TestListToolsets:
    """Tests for the list_toolsets discovery tool."""

    def test_returns_five_toolsets(self, mcp_server, mcp_ctx):
        result = list_toolsets(mcp_ctx)
        assert len(result["toolsets"]) == 5
        names = {t["name"] for t in result["toolsets"]}
        assert names == {"discovery", "explorer", "planner", "ingestor", "admin"}

    def test_total_tools_is_25(self, mcp_server, mcp_ctx):
        result = list_toolsets(mcp_ctx)
        assert result["total_tools"] == 25

    def test_each_toolset_has_tools(self, mcp_server, mcp_ctx):
        result = list_toolsets(mcp_ctx)
        for ts in result["toolsets"]:
            assert ts["tool_count"] > 0
            assert isinstance(ts["tools"], list)
            assert len(ts["tools"]) == ts["tool_count"]

    def test_toolset_has_description(self, mcp_server, mcp_ctx):
        result = list_toolsets(mcp_ctx)
        for ts in result["toolsets"]:
            assert "description" in ts
            assert len(ts["description"]) > 0

    def test_has_suggestion(self, mcp_server, mcp_ctx):
        result = list_toolsets(mcp_ctx)
        assert "suggestion" in result
        assert "get_tool_help" in result["suggestion"]


class TestGetToolHelp:
    """Tests for the get_tool_help discovery tool."""

    def test_valid_tool_returns_help(self, mcp_server, mcp_ctx):
        result = get_tool_help(mcp_ctx, "search_files")
        assert result["name"] == "search_files"
        assert result["toolset"] == "explorer"
        assert "description" in result
        assert "parameters" in result
        assert "suggestion" in result

    def test_valid_tool_has_parameters(self, mcp_server, mcp_ctx):
        result = get_tool_help(mcp_ctx, "search_files")
        params = result["parameters"]
        assert isinstance(params, list)
        param_names = {p["name"] for p in params}
        assert "query" in param_names

    def test_unknown_tool_returns_error(self, mcp_server, mcp_ctx):
        result = get_tool_help(mcp_ctx, "nonexistent_tool")
        assert result["error"] == "not_found"
        assert "available_tools" in result
        assert "suggestion" in result

    def test_help_for_each_toolset(self, mcp_server, mcp_ctx):
        """Get help for one tool from each toolset."""
        samples = {
            "list_toolsets": "discovery",
            "search_files": "explorer",
            "create_pipeline": "planner",
            "ingest_file": "ingestor",
            "manage_users": "admin",
        }
        for tool_name, expected_toolset in samples.items():
            result = get_tool_help(mcp_ctx, tool_name)
            assert result["toolset"] == expected_toolset, f"{tool_name} expected {expected_toolset}"


# ===================================================================
# 3. EXPLORER TOOLS (8)
# ===================================================================


class TestSearchFiles:
    """Tests for the search_files explorer tool."""

    def test_list_all_files(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx)
        assert result["total"] == 2
        assert len(result["files"]) == 2
        assert "suggestion" in result

    def test_search_by_name(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx, query="spectrum")
        assert result["total"] == 1
        assert result["files"][0]["file_name"] == "spectrum_001.csv"

    def test_search_by_hash(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx, query="abc123")
        assert result["total"] == 1

    def test_filter_by_instrument_type(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx, instrument_type="hplc")
        assert result["total"] == 1
        assert result["files"][0]["instrument_type"] == "hplc"

    def test_filter_by_status(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx, status="parsed")
        assert result["total"] == 1

    def test_pagination(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx, limit=1, offset=0)
        assert result["total"] == 2
        assert len(result["files"]) == 1
        assert result["limit"] == 1
        assert result["offset"] == 0

    def test_empty_results_suggestion(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["search_files"](mcp_ctx, query="nonexistent")
        assert result["total"] == 0
        assert "broadening" in result["suggestion"].lower()


class TestListExperiments:
    """Tests for the list_experiments explorer tool."""

    def test_list_all(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_experiments"](mcp_ctx)
        assert result["total"] == 2
        assert "suggestion" in result

    def test_filter_by_org(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_experiments"](mcp_ctx, org_id="org-test")
        assert result["total"] == 1
        assert result["experiments"][0]["org_id"] == "org-test"

    def test_filter_by_status(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_experiments"](mcp_ctx, status="draft")
        assert result["total"] == 1
        assert result["experiments"][0]["status"] == "draft"

    def test_pagination(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_experiments"](mcp_ctx, page=1, page_size=1)
        assert result["total"] == 2
        assert len(result["experiments"]) == 1

    def test_empty_suggestion(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_experiments"](mcp_ctx, org_id="no-such-org")
        assert result["total"] == 0
        assert "suggestion" in result


class TestGetFileMetadata:
    """Tests for the get_file_metadata explorer tool."""

    def test_valid_file(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_file_metadata"](mcp_ctx, "file-1")
        assert result["file_name"] == "spectrum_001.csv"
        assert result["instrument"] is not None
        assert "suggestion" in result

    def test_file_not_found(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_file_metadata"](mcp_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result


class TestGetExperimentDetail:
    """Tests for the get_experiment_detail explorer tool."""

    def test_valid_experiment(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_experiment_detail"](mcp_ctx, "exp-1")
        assert result["name"] == "UV-Vis Calibration"
        assert "valid_transitions" in result
        assert "linked_files" in result
        assert "suggestion" in result

    def test_experiment_not_found(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_experiment_detail"](mcp_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result

    def test_linked_files(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_experiment_detail"](mcp_ctx, "exp-1")
        assert len(result["linked_files"]) == 1
        assert result["linked_files"][0]["file_id"] == "file-1"


class TestListDatasets:
    """Tests for the list_datasets explorer tool."""

    def test_list_all(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_datasets"](mcp_ctx)
        assert result["total"] == 2
        assert "suggestion" in result

    def test_filter_by_instrument_type(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_datasets"](mcp_ctx, instrument_type="hplc")
        assert result["total"] == 1
        assert result["datasets"][0]["instrument_type"] == "hplc"

    def test_filter_by_org(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_datasets"](mcp_ctx, org_id="org-test")
        assert result["total"] == 2

    def test_empty_results(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_datasets"](mcp_ctx, instrument_type="nonexistent")
        assert result["total"] == 0
        assert "ingest" in result["suggestion"].lower()


class TestGetParseResult:
    """Tests for the get_parse_result explorer tool."""

    def test_parsed_file(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_parse_result"](mcp_ctx, "file-1")
        assert result["file_id"] == "file-1"
        assert result["parser_name"] == "spectrophotometer"
        assert "suggestion" in result

    def test_unparsed_file(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_parse_result"](mcp_ctx, "file-2")
        assert result["error"] == "not_parsed"
        assert "suggestion" in result

    def test_file_not_found(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_parse_result"](mcp_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result


class TestListInstruments:
    """Tests for the list_instruments explorer tool."""

    def test_active_only(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_instruments"](mcp_ctx)
        assert result["total"] == 2  # inst-3 is inactive
        assert "suggestion" in result

    def test_include_inactive(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_instruments"](mcp_ctx, active_only=False)
        assert result["total"] == 3

    def test_filter_by_lab(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_instruments"](mcp_ctx, lab_id="lab-1")
        assert result["total"] == 2

    def test_filter_by_type(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["list_instruments"](mcp_ctx, instrument_type="hplc")
        assert result["total"] == 1
        assert result["instruments"][0]["instrument_type"] == "hplc"


class TestGetDatasetSummary:
    """Tests for the get_dataset_summary explorer tool."""

    def test_valid_dataset(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_dataset_summary"](mcp_ctx, "ds-1")
        assert result["id"] == "ds-1"
        assert result["instrument_type"] == "spectrophotometer"
        assert "statistics" in result
        assert "quality_breakdown" in result
        assert "suggestion" in result

    def test_statistics(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_dataset_summary"](mcp_ctx, "ds-1")
        stats = result["statistics"]
        assert stats["data_point_count"] == 3
        assert stats["unique_samples"] == 3
        assert stats["average_value"] is not None
        assert stats["min_value"] == 0.52
        assert stats["max_value"] == 1.23

    def test_quality_breakdown(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_dataset_summary"](mcp_ctx, "ds-1")
        qb = result["quality_breakdown"]
        assert qb["good"] == 2
        assert qb["warning"] == 1

    def test_dataset_not_found(self, mcp_server, mcp_ctx):
        result = EXPLORER_TOOLS["get_dataset_summary"](mcp_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result


# ===================================================================
# 4. PLANNER TOOLS (7)
# ===================================================================


class TestCreatePipeline:
    """Tests for the create_pipeline planner tool."""

    def test_create_valid_pipeline(self, mcp_server):
        fn = PLANNER_TOOLS["create_pipeline"]
        result = fn(
            org_id="org-1",
            name="HPLC QC Pipeline",
            instrument_type="hplc",
            steps=[
                {"step_type": "parse", "config": {"parser": "hplc"}},
                {"step_type": "validate"},
                {"step_type": "store"},
            ],
        )
        assert result["success"] is True
        assert result["pipeline"]["name"] == "HPLC QC Pipeline"
        assert result["pipeline"]["step_count"] == 3
        assert "suggestion" in result

    def test_create_invalid_instrument_type(self, mcp_server):
        fn = PLANNER_TOOLS["create_pipeline"]
        result = fn(
            org_id="org-1",
            name="Bad Pipeline",
            instrument_type="nonexistent",
            steps=[{"step_type": "parse"}],
        )
        assert result["success"] is False
        assert "suggestion" in result

    def test_create_empty_name(self, mcp_server):
        fn = PLANNER_TOOLS["create_pipeline"]
        result = fn(
            org_id="org-1",
            name="",
            instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        assert result["success"] is False

    def test_create_invalid_steps(self, mcp_server):
        fn = PLANNER_TOOLS["create_pipeline"]
        result = fn(
            org_id="org-1",
            name="Bad Steps",
            instrument_type="hplc",
            steps=[{"step_type": "invalid_step"}],
        )
        assert result["success"] is False
        assert "details" in result


class TestValidatePipeline:
    """Tests for the validate_pipeline planner tool."""

    def _create_pipeline(self):
        return PLANNER_TOOLS["create_pipeline"](
            org_id="org-1",
            name="Test Pipeline",
            instrument_type="hplc",
            steps=[
                {"step_type": "parse"},
                {"step_type": "validate"},
                {"step_type": "store"},
            ],
        )

    def test_valid_pipeline(self, mcp_server):
        create_result = self._create_pipeline()
        pid = create_result["pipeline"]["id"]

        result = PLANNER_TOOLS["validate_pipeline"](pid)
        assert result["valid"] is True
        assert "suggestion" in result

    def test_validate_not_found(self, mcp_server):
        result = PLANNER_TOOLS["validate_pipeline"]("nonexistent-id")
        assert result["valid"] is False
        assert "suggestion" in result

    def test_validate_warnings(self, mcp_server):
        """Pipeline without store step triggers warning."""
        create_result = PLANNER_TOOLS["create_pipeline"](
            org_id="org-1",
            name="No Store",
            instrument_type="hplc",
            steps=[{"step_type": "parse"}, {"step_type": "validate"}],
        )
        pid = create_result["pipeline"]["id"]

        result = PLANNER_TOOLS["validate_pipeline"](pid)
        assert result["valid"] is True
        assert len(result["warnings"]) > 0


class TestEstimateDuration:
    """Tests for the estimate_duration planner tool."""

    def test_estimate_with_pipeline(self, mcp_server):
        create_result = PLANNER_TOOLS["create_pipeline"](
            org_id="org-1",
            name="Est Pipeline",
            instrument_type="hplc",
            steps=[{"step_type": "parse"}, {"step_type": "store"}],
        )
        pid = create_result["pipeline"]["id"]

        result = PLANNER_TOOLS["estimate_duration"](pipeline_id=pid)
        assert result["success"] is True
        assert result["estimated_total_seconds"] > 0
        assert "suggestion" in result

    def test_estimate_with_steps(self, mcp_server):
        result = PLANNER_TOOLS["estimate_duration"](
            steps=[{"step_type": "parse"}, {"step_type": "validate"}],
            file_count=10,
        )
        assert result["success"] is True
        assert result["file_count"] == 10
        assert result["estimated_total_seconds"] > 0

    def test_estimate_no_input(self, mcp_server):
        result = PLANNER_TOOLS["estimate_duration"]()
        assert result["success"] is False
        assert "suggestion" in result

    def test_estimate_scales_with_file_count(self, mcp_server):
        r1 = PLANNER_TOOLS["estimate_duration"](
            steps=[{"step_type": "parse"}], file_count=1,
        )
        r10 = PLANNER_TOOLS["estimate_duration"](
            steps=[{"step_type": "parse"}], file_count=10,
        )
        assert r10["estimated_total_seconds"] > r1["estimated_total_seconds"]


class TestListPipelines:
    """Tests for the list_pipelines planner tool."""

    def test_list_empty(self, mcp_server):
        result = PLANNER_TOOLS["list_pipelines"](org_id="org-1")
        assert result["success"] is True
        assert result["total"] == 0
        assert "suggestion" in result

    def test_list_with_pipelines(self, mcp_server):
        PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="P1", instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        result = PLANNER_TOOLS["list_pipelines"](org_id="org-1")
        assert result["total"] == 1

    def test_list_filter_by_status(self, mcp_server):
        PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="P1", instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        result = PLANNER_TOOLS["list_pipelines"](org_id="org-1", status="active")
        assert result["total"] == 0  # newly created is "draft"

    def test_list_invalid_status(self, mcp_server):
        result = PLANNER_TOOLS["list_pipelines"](org_id="org-1", status="bogus")
        assert result["success"] is False
        assert "suggestion" in result


class TestGetPipeline:
    """Tests for the get_pipeline planner tool."""

    def test_get_existing(self, mcp_server):
        create_result = PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="P1", instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        pid = create_result["pipeline"]["id"]
        result = PLANNER_TOOLS["get_pipeline"](pid)
        assert result["success"] is True
        assert result["pipeline"]["id"] == pid
        assert "suggestion" in result

    def test_get_not_found(self, mcp_server):
        result = PLANNER_TOOLS["get_pipeline"]("nonexistent")
        assert result["success"] is False
        assert "suggestion" in result


class TestUpdatePipeline:
    """Tests for the update_pipeline planner tool."""

    def _create_pipeline(self):
        return PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="Updatable",
            instrument_type="hplc", steps=[{"step_type": "parse"}],
        )

    def test_update_name(self, mcp_server):
        pid = self._create_pipeline()["pipeline"]["id"]
        result = PLANNER_TOOLS["update_pipeline"](pid, name="New Name")
        assert result["success"] is True
        assert result["pipeline"]["name"] == "New Name"

    def test_update_status_transition(self, mcp_server):
        pid = self._create_pipeline()["pipeline"]["id"]
        result = PLANNER_TOOLS["update_pipeline"](pid, status="active")
        assert result["success"] is True
        assert result["pipeline"]["status"] == "active"

    def test_invalid_transition(self, mcp_server):
        pid = self._create_pipeline()["pipeline"]["id"]
        result = PLANNER_TOOLS["update_pipeline"](pid, status="paused")
        assert result["success"] is False
        assert "suggestion" in result

    def test_update_not_found(self, mcp_server):
        result = PLANNER_TOOLS["update_pipeline"]("nonexistent", name="X")
        assert result["success"] is False

    def test_update_no_fields(self, mcp_server):
        pid = self._create_pipeline()["pipeline"]["id"]
        result = PLANNER_TOOLS["update_pipeline"](pid)
        assert result["success"] is False
        assert "suggestion" in result


class TestDeletePipeline:
    """Tests for the delete_pipeline planner tool."""

    def test_delete_pipeline(self, mcp_server):
        create_result = PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="To Delete", instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        pid = create_result["pipeline"]["id"]

        result = PLANNER_TOOLS["delete_pipeline"](pid)
        assert result["success"] is True
        assert result["current_status"] == "archived"
        assert "suggestion" in result

    def test_delete_already_archived(self, mcp_server):
        create_result = PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="Already Archived", instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        pid = create_result["pipeline"]["id"]
        PLANNER_TOOLS["delete_pipeline"](pid)  # first delete

        result = PLANNER_TOOLS["delete_pipeline"](pid)  # second
        assert result["success"] is False
        assert "suggestion" in result

    def test_delete_not_found(self, mcp_server):
        result = PLANNER_TOOLS["delete_pipeline"]("nonexistent")
        assert result["success"] is False
        assert "suggestion" in result


# ===================================================================
# 5. INGESTOR TOOLS (4) — invocation through server wrappers
# ===================================================================


class TestIngestorToolsRegistered:
    """Verify ingestor tools are registered and invocable."""

    def test_ingest_file_registered(self, mcp_server):
        assert "ingest_file" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["ingest_file"] == "ingestor"

    def test_check_ingest_status_registered(self, mcp_server):
        assert "check_ingest_status" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["check_ingest_status"] == "ingestor"

    def test_retry_ingest_registered(self, mcp_server):
        assert "retry_ingest" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["retry_ingest"] == "ingestor"

    def test_list_parsers_registered(self, mcp_server):
        assert "list_parsers" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["list_parsers"] == "ingestor"

    @pytest.mark.asyncio
    async def test_list_parsers_invocation(self, mcp_server):
        """Verify list_parsers can be called directly and returns expected structure."""
        from app.mcp_server.tools.ingestor import list_parsers
        result = await list_parsers()
        assert result["total"] == 5
        assert "suggestion" in result


# ===================================================================
# 6. ADMIN TOOLS (4) — invocation through server wrappers
# ===================================================================


class TestAdminToolsRegistered:
    """Verify admin tools are registered and invocable."""

    def test_manage_users_registered(self, mcp_server):
        assert "manage_users" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["manage_users"] == "admin"

    def test_get_audit_log_registered(self, mcp_server):
        assert "get_audit_log" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["get_audit_log"] == "admin"

    def test_update_settings_registered(self, mcp_server):
        assert "update_settings" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["update_settings"] == "admin"

    def test_get_system_health_registered(self, mcp_server):
        assert "get_system_health" in _TOOL_TOOLSET_MAP
        assert _TOOL_TOOLSET_MAP["get_system_health"] == "admin"

    @pytest.mark.asyncio
    async def test_get_system_health_invocation(self, mcp_server):
        """Verify get_system_health returns healthy status."""
        from app.mcp_server.tools.admin import get_system_health
        result = await get_system_health()
        assert result["status"] == "healthy"
        assert "suggestion" in result

    @pytest.mark.asyncio
    async def test_manage_users_invocation(self, mcp_server):
        """Verify manage_users list returns structured result."""
        from app.mcp_server.tools.admin import manage_users
        result = await manage_users(action="list")
        assert result["status"] == "ok"
        assert "suggestion" in result


# ===================================================================
# 7. CROSS-CUTTING CONCERNS
# ===================================================================


class TestSuggestionField:
    """Verify every tool response includes a 'suggestion' field."""

    def test_discovery_tools_have_suggestion(self, mcp_server, mcp_ctx):
        r1 = list_toolsets(mcp_ctx)
        assert "suggestion" in r1
        r2 = get_tool_help(mcp_ctx, "search_files")
        assert "suggestion" in r2
        r3 = get_tool_help(mcp_ctx, "nonexistent")
        assert "suggestion" in r3

    def test_explorer_tools_have_suggestion(self, mcp_server, mcp_ctx):
        for name, fn in EXPLORER_TOOLS.items():
            # Call each with minimal args — use defaults or fixture data
            if "file_id" in fn.__code__.co_varnames:
                result = fn(mcp_ctx, "file-1")
            elif "experiment_id" in fn.__code__.co_varnames:
                result = fn(mcp_ctx, "exp-1")
            elif "dataset_id" in fn.__code__.co_varnames:
                result = fn(mcp_ctx, "ds-1")
            else:
                result = fn(mcp_ctx)
            assert "suggestion" in result, f"Explorer tool '{name}' missing suggestion"

    def test_planner_tools_have_suggestion(self, mcp_server):
        # create_pipeline
        r = PLANNER_TOOLS["create_pipeline"](
            org_id="org-1", name="P", instrument_type="hplc",
            steps=[{"step_type": "parse"}],
        )
        assert "suggestion" in r

        pid = r["pipeline"]["id"]

        # validate_pipeline
        assert "suggestion" in PLANNER_TOOLS["validate_pipeline"](pid)

        # estimate_duration
        assert "suggestion" in PLANNER_TOOLS["estimate_duration"](pipeline_id=pid)

        # list_pipelines
        assert "suggestion" in PLANNER_TOOLS["list_pipelines"](org_id="org-1")

        # get_pipeline
        assert "suggestion" in PLANNER_TOOLS["get_pipeline"](pid)

        # update_pipeline
        assert "suggestion" in PLANNER_TOOLS["update_pipeline"](pid, name="Updated")

        # delete_pipeline
        assert "suggestion" in PLANNER_TOOLS["delete_pipeline"](pid)


class TestToolNamingConvention:
    """Verify all tool names follow verb_noun snake_case."""

    VERB_NOUN_PATTERN = re.compile(r"^[a-z]+_[a-z_]+$")

    def test_all_tools_match_pattern(self, mcp_server):
        for name in _TOOL_TOOLSET_MAP:
            assert self.VERB_NOUN_PATTERN.match(name), (
                f"Tool '{name}' does not match verb_noun snake_case"
            )

    def test_tools_start_with_verb(self, mcp_server):
        """All tool names start with a known verb."""
        known_verbs = {
            "list", "get", "search", "create", "validate", "estimate",
            "update", "delete", "ingest", "check", "retry", "manage",
        }
        for name in _TOOL_TOOLSET_MAP:
            verb = name.split("_")[0]
            assert verb in known_verbs, (
                f"Tool '{name}' starts with unknown verb '{verb}'"
            )


class TestToolsetCounts:
    """Verify each toolset has the expected tool count (capped at 25 total)."""

    def test_discovery_2(self, mcp_server):
        count = sum(1 for v in _TOOL_TOOLSET_MAP.values() if v == "discovery")
        assert count == 2

    def test_explorer_8(self, mcp_server):
        count = sum(1 for v in _TOOL_TOOLSET_MAP.values() if v == "explorer")
        assert count == 8

    def test_planner_7(self, mcp_server):
        count = sum(1 for v in _TOOL_TOOLSET_MAP.values() if v == "planner")
        assert count == 7

    def test_ingestor_4(self, mcp_server):
        count = sum(1 for v in _TOOL_TOOLSET_MAP.values() if v == "ingestor")
        assert count == 4

    def test_admin_4(self, mcp_server):
        count = sum(1 for v in _TOOL_TOOLSET_MAP.values() if v == "admin")
        assert count == 4

    def test_cap_25(self, mcp_server):
        assert len(_TOOL_TOOLSET_MAP) == 25
