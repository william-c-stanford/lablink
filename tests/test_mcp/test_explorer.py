"""Tests for Explorer toolset (8 tools).

Explorer tools operate on MCPContext in-memory stores.
Tests verify:
  - Tool registration and metadata
  - Each tool's filtering, pagination, error handling
  - Suggestion field present in all responses
  - Not-found error paths
"""

import pytest

from app.mcp_server.context import MCPContext
from app.mcp_server.tools.explorer import (
    EXPLORER_TOOLS,
    get_dataset_summary,
    get_experiment_detail,
    get_file_metadata,
    get_parse_result,
    list_datasets,
    list_experiments,
    list_instruments,
    search_files,
)


class TestExplorerToolRegistration:
    """Tests for explorer tool registration and naming."""

    def test_eight_tools_registered(self):
        """EXPLORER_TOOLS has exactly 8 entries."""
        assert len(EXPLORER_TOOLS) == 8

    def test_expected_tool_names(self):
        """Explorer tools have the expected names."""
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
        assert set(EXPLORER_TOOLS.keys()) == expected

    def test_all_explorer_tools_are_sync(self):
        """All explorer tools are sync functions (not coroutine)."""
        import inspect

        for name, func in EXPLORER_TOOLS.items():
            assert not inspect.iscoroutinefunction(func), (
                f"Explorer tool '{name}' should be sync"
            )

    def test_all_tools_take_ctx_as_first_param(self):
        """All explorer tools take MCPContext as first parameter."""
        import inspect

        for name, func in EXPLORER_TOOLS.items():
            sig = inspect.signature(func)
            first_param = list(sig.parameters.keys())[0]
            assert first_param == "ctx", (
                f"Explorer tool '{name}' first param should be 'ctx', got '{first_param}'"
            )


class TestSearchFiles:
    """Tests for search_files tool."""

    def test_empty_store_returns_empty(self):
        ctx = MCPContext()
        result = search_files(ctx, query="test")
        assert result["total"] == 0
        assert result["files"] == []
        assert "suggestion" in result

    def test_search_by_name(self, populated_ctx):
        result = search_files(populated_ctx, query="hplc")
        assert result["total"] == 1
        assert result["files"][0]["file_name"] == "hplc_run_001.csv"

    def test_search_by_hash(self, populated_ctx):
        result = search_files(populated_ctx, query="abc123")
        assert result["total"] == 1

    def test_filter_by_status(self, populated_ctx):
        result = search_files(populated_ctx, status="uploaded")
        assert result["total"] == 1
        assert result["files"][0]["status"] == "uploaded"

    def test_filter_by_instrument_type(self, populated_ctx):
        result = search_files(populated_ctx, instrument_type="balance")
        assert result["total"] == 1

    def test_pagination_limit(self, populated_ctx):
        result = search_files(populated_ctx, limit=1)
        assert len(result["files"]) == 1
        assert result["total"] == 3

    def test_pagination_offset(self, populated_ctx):
        result = search_files(populated_ctx, limit=1, offset=1)
        assert len(result["files"]) == 1
        # Second file in sorted order

    def test_limit_capped_at_100(self, populated_ctx):
        result = search_files(populated_ctx, limit=999)
        assert result["limit"] == 100

    def test_suggestion_present_on_results(self, populated_ctx):
        result = search_files(populated_ctx, query="hplc")
        assert "suggestion" in result
        assert "get_file_metadata" in result["suggestion"]

    def test_suggestion_on_empty_results(self):
        ctx = MCPContext()
        result = search_files(ctx, query="nothing")
        assert "broadening" in result["suggestion"]


class TestListExperiments:
    """Tests for list_experiments tool."""

    def test_empty_store(self):
        ctx = MCPContext()
        result = list_experiments(ctx)
        assert result["total"] == 0
        assert "suggestion" in result

    def test_returns_all_experiments(self, populated_ctx):
        result = list_experiments(populated_ctx)
        assert result["total"] == 3
        assert len(result["experiments"]) == 3

    def test_filter_by_status(self, populated_ctx):
        result = list_experiments(populated_ctx, status="draft")
        assert result["total"] == 1
        assert result["experiments"][0]["status"] == "draft"

    def test_filter_by_org_id(self, populated_ctx):
        result = list_experiments(populated_ctx, org_id="org-1")
        assert result["total"] == 2

    def test_pagination(self, populated_ctx):
        result = list_experiments(populated_ctx, page=1, page_size=2)
        assert len(result["experiments"]) == 2
        assert result["total"] == 3
        assert result["page"] == 1
        assert result["page_size"] == 2

    def test_page_size_capped(self, populated_ctx):
        result = list_experiments(populated_ctx, page_size=999)
        assert result["page_size"] == 100

    def test_sorted_by_created_at_desc(self, populated_ctx):
        result = list_experiments(populated_ctx)
        dates = [e.get("created_at", "") for e in result["experiments"]]
        assert dates == sorted(dates, reverse=True)


class TestGetFileMetadata:
    """Tests for get_file_metadata tool."""

    def test_returns_file_data(self, populated_ctx):
        result = get_file_metadata(populated_ctx, "file-1")
        assert result["file_name"] == "hplc_run_001.csv"
        assert "suggestion" in result

    def test_enriches_with_instrument(self, populated_ctx):
        result = get_file_metadata(populated_ctx, "file-1")
        assert result["instrument"] is not None
        assert result["instrument"]["name"] == "HPLC-1"

    def test_not_found_returns_error(self, populated_ctx):
        result = get_file_metadata(populated_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result
        assert "search_files" in result["suggestion"]


class TestGetExperimentDetail:
    """Tests for get_experiment_detail tool."""

    def test_returns_experiment_data(self, populated_ctx):
        result = get_experiment_detail(populated_ctx, "exp-1")
        assert result["name"] == "Protein assay v2"
        assert result["status"] == "running"
        assert "suggestion" in result

    def test_includes_valid_transitions(self, populated_ctx):
        result = get_experiment_detail(populated_ctx, "exp-1")
        assert "valid_transitions" in result
        assert "completed" in result["valid_transitions"]
        assert "failed" in result["valid_transitions"]

    def test_draft_transitions(self, populated_ctx):
        result = get_experiment_detail(populated_ctx, "exp-2")
        assert "running" in result["valid_transitions"]
        assert "cancelled" in result["valid_transitions"]

    def test_terminal_state_no_transitions(self, populated_ctx):
        result = get_experiment_detail(populated_ctx, "exp-3")
        assert result["valid_transitions"] == []
        assert "terminal" in result["suggestion"]

    def test_includes_linked_files(self, populated_ctx):
        result = get_experiment_detail(populated_ctx, "exp-1")
        assert "linked_files" in result
        # file-3 has experiment_id=exp-1
        assert len(result["linked_files"]) == 1

    def test_not_found_returns_error(self, populated_ctx):
        result = get_experiment_detail(populated_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result


class TestListDatasets:
    """Tests for list_datasets tool."""

    def test_empty_store(self):
        ctx = MCPContext()
        result = list_datasets(ctx)
        assert result["total"] == 0
        assert "suggestion" in result
        assert "Ingest" in result["suggestion"]

    def test_returns_datasets(self, populated_ctx):
        result = list_datasets(populated_ctx)
        assert result["total"] == 2

    def test_filter_by_instrument_type(self, populated_ctx):
        result = list_datasets(populated_ctx, instrument_type="hplc")
        assert result["total"] == 1

    def test_filter_by_org_id(self, populated_ctx):
        result = list_datasets(populated_ctx, org_id="org-1")
        assert result["total"] == 2

    def test_pagination(self, populated_ctx):
        result = list_datasets(populated_ctx, limit=1)
        assert len(result["datasets"]) == 1
        assert result["total"] == 2


class TestGetParseResult:
    """Tests for get_parse_result tool."""

    def test_returns_parse_result(self, populated_ctx):
        result = get_parse_result(populated_ctx, "file-1")
        assert result["file_id"] == "file-1"
        assert result["parser_name"] == "hplc"
        assert "suggestion" in result

    def test_not_parsed_returns_error(self, populated_ctx):
        result = get_parse_result(populated_ctx, "file-2")
        assert result["error"] == "not_parsed"
        assert "suggestion" in result
        assert "queue" in result["suggestion"]

    def test_file_not_found_returns_error(self, populated_ctx):
        result = get_parse_result(populated_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result


class TestListInstruments:
    """Tests for list_instruments tool."""

    def test_empty_store(self):
        ctx = MCPContext()
        result = list_instruments(ctx)
        assert result["total"] == 0
        assert "suggestion" in result

    def test_returns_instruments(self, populated_ctx):
        # Default active_only=True filters out inst-3 (is_active=False)
        result = list_instruments(populated_ctx)
        assert result["total"] == 2

    def test_include_inactive(self, populated_ctx):
        result = list_instruments(populated_ctx, active_only=False)
        assert result["total"] == 3

    def test_filter_by_lab_id(self, populated_ctx):
        result = list_instruments(populated_ctx, lab_id="lab-1", active_only=False)
        assert result["total"] == 2

    def test_filter_by_instrument_type(self, populated_ctx):
        result = list_instruments(populated_ctx, instrument_type="hplc")
        assert result["total"] == 1
        assert result["instruments"][0]["name"] == "HPLC-1"

    def test_sorted_by_name(self, populated_ctx):
        result = list_instruments(populated_ctx, active_only=False)
        names = [i["name"] for i in result["instruments"]]
        assert names == sorted(names)


class TestGetDatasetSummary:
    """Tests for get_dataset_summary tool."""

    def test_returns_summary(self, populated_ctx):
        result = get_dataset_summary(populated_ctx, "ds-1")
        assert result["id"] == "ds-1"
        assert result["instrument_type"] == "hplc"
        assert "statistics" in result
        assert "suggestion" in result

    def test_statistics_computed(self, populated_ctx):
        result = get_dataset_summary(populated_ctx, "ds-1")
        stats = result["statistics"]
        assert stats["data_point_count"] == 3
        assert stats["unique_samples"] == 2
        assert stats["unique_measurement_types"] == 2
        assert stats["min_value"] == 3.14
        assert stats["max_value"] == 2345.6
        assert stats["average_value"] is not None

    def test_quality_breakdown(self, populated_ctx):
        result = get_dataset_summary(populated_ctx, "ds-1")
        qb = result["quality_breakdown"]
        assert qb["good"] == 2
        assert qb["suspect"] == 1

    def test_not_found_returns_error(self, populated_ctx):
        result = get_dataset_summary(populated_ctx, "nonexistent")
        assert result["error"] == "not_found"
        assert "suggestion" in result

    def test_empty_measurements_stats(self):
        """Dataset with no measurements returns None stats."""
        ctx = MCPContext(
            search_index=[
                {
                    "type": "dataset",
                    "id": "ds-empty",
                    "name": "Empty",
                    "instrument_type": "balance",
                    "measurements": [],
                    "created_at": "2026-01-01T00:00:00",
                },
            ]
        )
        result = get_dataset_summary(ctx, "ds-empty")
        assert result["statistics"]["data_point_count"] == 0
        assert result["statistics"]["average_value"] is None
        assert result["statistics"]["min_value"] is None
