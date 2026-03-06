"""Tests for the MCP planner toolset (7 tools).

Covers create, validate, estimate, list, get, update, delete pipelines
with both happy-path and error scenarios. Every error response must
include a 'suggestion' field for agent-native recovery.
"""

from __future__ import annotations

import pytest

from app.mcp_server.tools.planner import (
    PLANNER_TOOLS,
    PipelineStatus,
    PipelineStepType,
    VALID_INSTRUMENT_TYPES,
    create_pipeline,
    delete_pipeline,
    estimate_duration,
    get_pipeline,
    get_pipeline_store,
    list_pipelines,
    update_pipeline,
    validate_pipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_store():
    """Clear the in-memory pipeline store before each test."""
    store = get_pipeline_store()
    store.clear()
    yield
    store.clear()


def _default_steps() -> list[dict]:
    """A standard parse->validate->store step list."""
    return [
        {"step_type": "parse", "config": {"parser": "hplc"}, "description": "Parse HPLC CSV"},
        {"step_type": "validate", "config": {}, "description": "Validate parsed data"},
        {"step_type": "store", "config": {"backend": "local"}, "description": "Store results"},
    ]


def _create_default_pipeline(
    org_id: str = "org-1",
    name: str = "Test Pipeline",
    instrument_type: str = "hplc",
) -> dict:
    """Helper to create a pipeline with default steps."""
    return create_pipeline(
        org_id=org_id,
        name=name,
        instrument_type=instrument_type,
        steps=_default_steps(),
        description="A test pipeline",
        created_by="user-1",
    )


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """Verify the planner toolset has exactly 7 tools."""

    def test_planner_has_7_tools(self):
        assert len(PLANNER_TOOLS) == 7

    def test_all_tool_names_are_verb_noun(self):
        for name in PLANNER_TOOLS:
            parts = name.split("_")
            assert len(parts) >= 2, f"Tool '{name}' should follow verb_noun pattern"

    def test_all_tools_are_callable(self):
        for name, fn in PLANNER_TOOLS.items():
            assert callable(fn), f"Tool '{name}' is not callable"

    def test_tool_names(self):
        expected = {
            "create_pipeline",
            "validate_pipeline",
            "estimate_duration",
            "list_pipelines",
            "get_pipeline",
            "update_pipeline",
            "delete_pipeline",
        }
        assert set(PLANNER_TOOLS.keys()) == expected


# ---------------------------------------------------------------------------
# create_pipeline
# ---------------------------------------------------------------------------

class TestCreatePipeline:

    def test_create_success(self):
        result = _create_default_pipeline()
        assert result["success"] is True
        assert "pipeline" in result
        assert result["pipeline"]["name"] == "Test Pipeline"
        assert result["pipeline"]["instrument_type"] == "hplc"
        assert result["pipeline"]["status"] == "draft"
        assert result["pipeline"]["step_count"] == 3
        assert "suggestion" in result

    def test_create_returns_valid_uuid(self):
        result = _create_default_pipeline()
        pipeline_id = result["pipeline"]["id"]
        assert len(pipeline_id) == 36  # UUID format

    def test_create_invalid_instrument_type(self):
        result = create_pipeline(
            org_id="org-1",
            name="Bad",
            instrument_type="mass_spec",
            steps=_default_steps(),
        )
        assert result["success"] is False
        assert "suggestion" in result
        assert "mass_spec" in result["error"]

    def test_create_empty_name(self):
        result = create_pipeline(
            org_id="org-1",
            name="",
            instrument_type="hplc",
            steps=_default_steps(),
        )
        assert result["success"] is False
        assert "suggestion" in result

    def test_create_whitespace_name(self):
        result = create_pipeline(
            org_id="org-1",
            name="   ",
            instrument_type="hplc",
            steps=_default_steps(),
        )
        assert result["success"] is False

    def test_create_no_steps(self):
        result = create_pipeline(
            org_id="org-1",
            name="Empty",
            instrument_type="hplc",
            steps=[],
        )
        assert result["success"] is False
        assert "suggestion" in result

    def test_create_invalid_step_type(self):
        result = create_pipeline(
            org_id="org-1",
            name="Bad Steps",
            instrument_type="hplc",
            steps=[{"step_type": "explode"}],
        )
        assert result["success"] is False
        assert "suggestion" in result

    def test_create_invalid_parser_in_step(self):
        result = create_pipeline(
            org_id="org-1",
            name="Bad Parser",
            instrument_type="hplc",
            steps=[{"step_type": "parse", "config": {"parser": "nonexistent"}}],
        )
        assert result["success"] is False

    def test_create_strips_name(self):
        result = create_pipeline(
            org_id="org-1",
            name="  Trimmed  ",
            instrument_type="hplc",
            steps=_default_steps(),
        )
        assert result["success"] is True
        assert result["pipeline"]["name"] == "Trimmed"

    def test_create_all_instrument_types(self):
        for itype in VALID_INSTRUMENT_TYPES:
            result = create_pipeline(
                org_id="org-1",
                name=f"{itype} pipeline",
                instrument_type=itype,
                steps=[{"step_type": "parse"}],
            )
            assert result["success"] is True, f"Failed for {itype}"

    def test_create_all_step_types(self):
        steps = [{"step_type": st.value} for st in PipelineStepType]
        result = create_pipeline(
            org_id="org-1",
            name="All Steps",
            instrument_type="hplc",
            steps=steps,
        )
        assert result["success"] is True
        assert result["pipeline"]["step_count"] == len(PipelineStepType)


# ---------------------------------------------------------------------------
# validate_pipeline
# ---------------------------------------------------------------------------

class TestValidatePipeline:

    def test_validate_good_pipeline(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = validate_pipeline(pid)
        assert result["valid"] is True
        assert result["errors"] == []
        assert "suggestion" in result

    def test_validate_not_found(self):
        result = validate_pipeline("nonexistent-id")
        assert result["valid"] is False
        assert "suggestion" in result

    def test_validate_warns_no_parse_first(self):
        created = create_pipeline(
            org_id="org-1",
            name="No Parse",
            instrument_type="hplc",
            steps=[
                {"step_type": "validate"},
                {"step_type": "store"},
            ],
        )
        pid = created["pipeline"]["id"]
        result = validate_pipeline(pid)
        assert result["valid"] is True  # Warnings don't make it invalid
        assert any("parse" in w.lower() for w in result["warnings"])

    def test_validate_warns_no_store_last(self):
        created = create_pipeline(
            org_id="org-1",
            name="No Store",
            instrument_type="hplc",
            steps=[
                {"step_type": "parse"},
                {"step_type": "validate"},
            ],
        )
        pid = created["pipeline"]["id"]
        result = validate_pipeline(pid)
        assert result["valid"] is True
        assert any("store" in w.lower() for w in result["warnings"])

    def test_validate_warns_duplicate_consecutive(self):
        created = create_pipeline(
            org_id="org-1",
            name="Dupes",
            instrument_type="hplc",
            steps=[
                {"step_type": "parse"},
                {"step_type": "parse"},
                {"step_type": "store"},
            ],
        )
        pid = created["pipeline"]["id"]
        result = validate_pipeline(pid)
        assert any("both" in w.lower() or "unusual" in w.lower() for w in result["warnings"])

    def test_validate_returns_step_count(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = validate_pipeline(pid)
        assert result["step_count"] == 3


# ---------------------------------------------------------------------------
# estimate_duration
# ---------------------------------------------------------------------------

class TestEstimateDuration:

    def test_estimate_by_pipeline_id(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = estimate_duration(pipeline_id=pid)
        assert result["success"] is True
        assert result["estimated_total_seconds"] > 0
        assert "steps" in result
        assert len(result["steps"]) == 3
        assert "suggestion" in result

    def test_estimate_by_steps(self):
        result = estimate_duration(
            steps=[
                {"step_type": "parse"},
                {"step_type": "store"},
            ],
        )
        assert result["success"] is True
        assert result["estimated_total_seconds"] > 0

    def test_estimate_scales_with_file_count(self):
        steps = [{"step_type": "parse"}, {"step_type": "store"}]
        r1 = estimate_duration(steps=steps, file_count=1)
        r10 = estimate_duration(steps=steps, file_count=10)
        assert r10["estimated_total_seconds"] == pytest.approx(
            r1["estimated_total_seconds"] * 10, rel=0.01
        )

    def test_estimate_scales_with_file_size(self):
        steps = [{"step_type": "parse"}]
        r1 = estimate_duration(steps=steps, avg_file_size_mb=1.0)
        r5 = estimate_duration(steps=steps, avg_file_size_mb=5.0)
        assert r5["estimated_total_seconds"] > r1["estimated_total_seconds"]

    def test_estimate_not_found(self):
        result = estimate_duration(pipeline_id="bad-id")
        assert result["success"] is False
        assert "suggestion" in result

    def test_estimate_no_input(self):
        result = estimate_duration()
        assert result["success"] is False
        assert "suggestion" in result

    def test_estimate_invalid_steps(self):
        result = estimate_duration(steps=[{"step_type": "bad"}])
        assert result["success"] is False

    def test_estimate_zero_file_count(self):
        result = estimate_duration(
            steps=[{"step_type": "parse"}],
            file_count=0,
        )
        assert result["success"] is False
        assert "suggestion" in result

    def test_estimate_returns_minutes(self):
        result = estimate_duration(
            steps=[{"step_type": "parse"}],
            file_count=100,
            avg_file_size_mb=10.0,
        )
        assert result["success"] is True
        assert "estimated_total_minutes" in result
        assert result["estimated_total_minutes"] > 0


# ---------------------------------------------------------------------------
# list_pipelines
# ---------------------------------------------------------------------------

class TestListPipelines:

    def test_list_empty(self):
        result = list_pipelines(org_id="org-1")
        assert result["success"] is True
        assert result["total"] == 0
        assert result["pipelines"] == []
        assert "suggestion" in result

    def test_list_returns_created(self):
        _create_default_pipeline(org_id="org-1")
        _create_default_pipeline(org_id="org-1", name="Second")
        result = list_pipelines(org_id="org-1")
        assert result["success"] is True
        assert result["total"] == 2

    def test_list_filters_by_org(self):
        _create_default_pipeline(org_id="org-1")
        _create_default_pipeline(org_id="org-2")
        result = list_pipelines(org_id="org-1")
        assert result["total"] == 1

    def test_list_filters_by_status(self):
        created = _create_default_pipeline(org_id="org-1")
        pid = created["pipeline"]["id"]
        update_pipeline(pipeline_id=pid, status="active")
        _create_default_pipeline(org_id="org-1", name="Draft One")

        result = list_pipelines(org_id="org-1", status="active")
        assert result["total"] == 1
        assert result["pipelines"][0]["status"] == "active"

    def test_list_excludes_archived_by_default(self):
        created = _create_default_pipeline(org_id="org-1")
        pid = created["pipeline"]["id"]
        delete_pipeline(pid)

        result = list_pipelines(org_id="org-1")
        assert result["total"] == 0

    def test_list_includes_archived_when_requested(self):
        created = _create_default_pipeline(org_id="org-1")
        pid = created["pipeline"]["id"]
        delete_pipeline(pid)

        result = list_pipelines(org_id="org-1", include_archived=True)
        assert result["total"] == 1

    def test_list_invalid_status(self):
        result = list_pipelines(org_id="org-1", status="bogus")
        assert result["success"] is False
        assert "suggestion" in result


# ---------------------------------------------------------------------------
# get_pipeline
# ---------------------------------------------------------------------------

class TestGetPipeline:

    def test_get_success(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = get_pipeline(pid)
        assert result["success"] is True
        assert result["pipeline"]["id"] == pid
        assert result["pipeline"]["name"] == "Test Pipeline"
        assert "suggestion" in result

    def test_get_not_found(self):
        result = get_pipeline("nonexistent-id")
        assert result["success"] is False
        assert "suggestion" in result

    def test_get_includes_all_fields(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = get_pipeline(pid)
        pipeline = result["pipeline"]
        required_fields = {
            "id", "org_id", "name", "description", "instrument_type",
            "steps", "status", "created_at", "updated_at", "step_count",
        }
        assert required_fields.issubset(set(pipeline.keys()))


# ---------------------------------------------------------------------------
# update_pipeline
# ---------------------------------------------------------------------------

class TestUpdatePipeline:

    def test_update_name(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, name="Renamed")
        assert result["success"] is True
        assert result["pipeline"]["name"] == "Renamed"
        assert "suggestion" in result

    def test_update_description(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, description="Updated desc")
        assert result["success"] is True
        assert result["pipeline"]["description"] == "Updated desc"

    def test_update_steps_in_draft(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        new_steps = [{"step_type": "parse"}, {"step_type": "store"}]
        result = update_pipeline(pipeline_id=pid, steps=new_steps)
        assert result["success"] is True
        assert result["pipeline"]["step_count"] == 2

    def test_update_status_draft_to_active(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, status="active")
        assert result["success"] is True
        assert result["pipeline"]["status"] == "active"

    def test_update_status_active_to_paused(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        update_pipeline(pipeline_id=pid, status="active")
        result = update_pipeline(pipeline_id=pid, status="paused")
        assert result["success"] is True
        assert result["pipeline"]["status"] == "paused"

    def test_update_status_invalid_transition(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        # draft -> paused is not valid
        result = update_pipeline(pipeline_id=pid, status="paused")
        assert result["success"] is False
        assert "suggestion" in result

    def test_update_steps_blocked_when_active(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        update_pipeline(pipeline_id=pid, status="active")
        result = update_pipeline(
            pipeline_id=pid,
            steps=[{"step_type": "parse"}],
        )
        assert result["success"] is False
        assert "suggestion" in result
        assert "pause" in result["suggestion"].lower() or "paused" in result["suggestion"].lower()

    def test_update_not_found(self):
        result = update_pipeline(pipeline_id="bad-id", name="Nope")
        assert result["success"] is False
        assert "suggestion" in result

    def test_update_archived_blocked(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        delete_pipeline(pid)
        result = update_pipeline(pipeline_id=pid, name="Nope")
        assert result["success"] is False
        assert "suggestion" in result

    def test_update_empty_name_rejected(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, name="")
        assert result["success"] is False

    def test_update_no_fields(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid)
        assert result["success"] is False
        assert "suggestion" in result

    def test_update_invalid_status_value(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, status="running")
        assert result["success"] is False
        assert "suggestion" in result


# ---------------------------------------------------------------------------
# delete_pipeline
# ---------------------------------------------------------------------------

class TestDeletePipeline:

    def test_delete_success(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        result = delete_pipeline(pid)
        assert result["success"] is True
        assert result["current_status"] == "archived"
        assert result["previous_status"] == "draft"
        assert "suggestion" in result

    def test_delete_not_found(self):
        result = delete_pipeline("bad-id")
        assert result["success"] is False
        assert "suggestion" in result

    def test_delete_already_archived(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        delete_pipeline(pid)
        result = delete_pipeline(pid)
        assert result["success"] is False
        assert "suggestion" in result

    def test_delete_active_pipeline(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        update_pipeline(pipeline_id=pid, status="active")
        result = delete_pipeline(pid)
        assert result["success"] is True
        assert result["previous_status"] == "active"

    def test_delete_preserves_in_store(self):
        created = _create_default_pipeline()
        pid = created["pipeline"]["id"]
        delete_pipeline(pid)
        # Pipeline still exists in store, just archived
        result = get_pipeline(pid)
        assert result["success"] is True
        assert result["pipeline"]["status"] == "archived"


# ---------------------------------------------------------------------------
# Agent-native: every error has a suggestion
# ---------------------------------------------------------------------------

class TestAgentNativeSuggestions:
    """Verify every error response includes a 'suggestion' field."""

    def test_create_error_has_suggestion(self):
        result = create_pipeline(
            org_id="org-1", name="", instrument_type="bad", steps=[],
        )
        assert "suggestion" in result

    def test_validate_error_has_suggestion(self):
        result = validate_pipeline("nonexistent")
        assert "suggestion" in result

    def test_estimate_error_has_suggestion(self):
        result = estimate_duration()
        assert "suggestion" in result

    def test_list_error_has_suggestion(self):
        result = list_pipelines(org_id="org-1", status="bad")
        assert "suggestion" in result

    def test_get_error_has_suggestion(self):
        result = get_pipeline("bad-id")
        assert "suggestion" in result

    def test_update_error_has_suggestion(self):
        result = update_pipeline(pipeline_id="bad-id", name="x")
        assert "suggestion" in result

    def test_delete_error_has_suggestion(self):
        result = delete_pipeline("bad-id")
        assert "suggestion" in result

    def test_success_responses_have_suggestion(self):
        """Even successful responses should include suggestions for next actions."""
        created = _create_default_pipeline()
        assert "suggestion" in created

        pid = created["pipeline"]["id"]
        assert "suggestion" in validate_pipeline(pid)
        assert "suggestion" in estimate_duration(pipeline_id=pid)
        assert "suggestion" in list_pipelines(org_id="org-1")
        assert "suggestion" in get_pipeline(pid)
        assert "suggestion" in update_pipeline(pipeline_id=pid, name="New")
        assert "suggestion" in delete_pipeline(pid)
