"""Tests for Planner toolset (7 tools): pipeline CRUD, validation, estimation.

Planner tools are sync functions called directly (not via FastMCP dispatch).
"""

from app.mcp_server.tools.planner import (
    create_pipeline,
    delete_pipeline,
    estimate_duration,
    get_pipeline,
    list_pipelines,
    update_pipeline,
    validate_pipeline,
)


class TestCreatePipeline:
    """Tests for create_pipeline tool."""

    def test_creates_pipeline_successfully(
        self, pipeline_store, sample_org_id, sample_pipeline_steps
    ):
        """Creating a pipeline with valid args returns success."""
        result = create_pipeline(
            org_id=sample_org_id,
            name="HPLC Daily QC",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        assert result["success"] is True
        assert "pipeline" in result
        assert result["pipeline"]["name"] == "HPLC Daily QC"
        assert result["pipeline"]["instrument_type"] == "hplc"
        assert result["pipeline"]["status"] == "draft"

    def test_pipeline_gets_uuid_id(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Created pipeline has a valid UUID-style ID."""
        result = create_pipeline(
            org_id=sample_org_id,
            name="Test",
            instrument_type="pcr",
            steps=sample_pipeline_steps,
        )
        assert len(result["pipeline"]["id"]) == 36  # UUID length

    def test_invalid_instrument_type_returns_error(
        self, pipeline_store, sample_org_id, sample_pipeline_steps
    ):
        """Unknown instrument type returns error with suggestion."""
        result = create_pipeline(
            org_id=sample_org_id,
            name="Bad Type",
            instrument_type="foobar",
            steps=sample_pipeline_steps,
        )
        assert result["success"] is False
        assert "suggestion" in result
        assert "Valid instrument types" in result["suggestion"]

    def test_empty_name_returns_error(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Empty name returns error."""
        result = create_pipeline(
            org_id=sample_org_id,
            name="",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        assert result["success"] is False
        assert "name" in result["error"].lower()

    def test_invalid_step_type_returns_error(self, pipeline_store, sample_org_id):
        """Invalid step_type returns error with valid options."""
        result = create_pipeline(
            org_id=sample_org_id,
            name="Test",
            instrument_type="hplc",
            steps=[{"step_type": "invalid_step"}],
        )
        assert result["success"] is False
        assert "details" in result

    def test_suggestion_field_present(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Success response includes suggestion for next action."""
        result = create_pipeline(
            org_id=sample_org_id,
            name="Test",
            instrument_type="spectrophotometer",
            steps=sample_pipeline_steps,
        )
        assert "suggestion" in result
        assert "validate_pipeline" in result["suggestion"]


class TestValidatePipeline:
    """Tests for validate_pipeline tool."""

    def test_valid_pipeline_passes(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """A well-formed pipeline validates successfully."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="Valid Pipeline",
            instrument_type="spectrophotometer",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = validate_pipeline(pipeline_id=pid)
        assert result["valid"] is True
        assert result["pipeline_name"] == "Valid Pipeline"

    def test_pipeline_without_parse_step_warns(self, pipeline_store, sample_org_id):
        """Pipeline not starting with 'parse' generates a warning."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="No Parse First",
            instrument_type="hplc",
            steps=[
                {"step_type": "validate"},
                {"step_type": "store"},
            ],
        )
        pid = create_result["pipeline"]["id"]
        result = validate_pipeline(pipeline_id=pid)
        assert result["valid"] is True  # warnings don't fail validation
        assert any("parse" in w.lower() for w in result["warnings"])

    def test_nonexistent_pipeline_returns_error(self, pipeline_store):
        """Validating a non-existent pipeline returns not found."""
        result = validate_pipeline(pipeline_id="fake-uuid")
        assert result["valid"] is False
        assert "not found" in result["error"].lower()
        assert "suggestion" in result

    def test_pipeline_without_store_step_warns(self, pipeline_store, sample_org_id):
        """Pipeline not ending with 'store' generates a warning."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="No Store End",
            instrument_type="hplc",
            steps=[
                {"step_type": "parse"},
                {"step_type": "validate"},
            ],
        )
        pid = create_result["pipeline"]["id"]
        result = validate_pipeline(pipeline_id=pid)
        assert any("store" in w.lower() for w in result["warnings"])


class TestEstimateDuration:
    """Tests for estimate_duration tool."""

    def test_estimates_for_existing_pipeline(
        self, pipeline_store, sample_org_id, sample_pipeline_steps
    ):
        """estimate_duration works with an existing pipeline ID."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="Duration Test",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = estimate_duration(pipeline_id=pid)
        assert result["success"] is True
        assert result["estimated_total_seconds"] > 0
        assert "steps" in result
        assert len(result["steps"]) == len(sample_pipeline_steps)

    def test_estimates_for_ad_hoc_steps(self, pipeline_store):
        """estimate_duration works with ad-hoc step list."""
        result = estimate_duration(
            steps=[{"step_type": "parse"}, {"step_type": "store"}],
        )
        assert result["success"] is True
        assert result["estimated_total_seconds"] > 0

    def test_scales_with_file_count(self, pipeline_store):
        """Duration estimate scales with file count."""
        result_1 = estimate_duration(
            steps=[{"step_type": "parse"}],
            file_count=1,
        )
        result_10 = estimate_duration(
            steps=[{"step_type": "parse"}],
            file_count=10,
        )
        assert result_10["estimated_total_seconds"] > result_1["estimated_total_seconds"]

    def test_no_args_returns_error(self, pipeline_store):
        """Must provide pipeline_id or steps."""
        result = estimate_duration()
        assert result["success"] is False
        assert "suggestion" in result

    def test_includes_suggestion(self, pipeline_store):
        """Result includes agent-friendly suggestion."""
        result = estimate_duration(steps=[{"step_type": "parse"}])
        assert "suggestion" in result


class TestListPipelines:
    """Tests for list_pipelines tool."""

    def test_empty_org_returns_empty_list(self, pipeline_store, sample_org_id):
        """Listing pipelines for an org with no pipelines returns empty list."""
        result = list_pipelines(org_id=sample_org_id)
        assert result["success"] is True
        assert result["pipelines"] == []
        assert result["total"] == 0

    def test_lists_created_pipelines(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """After creating pipelines, they appear in list."""
        create_pipeline(
            org_id=sample_org_id, name="P1", instrument_type="hplc", steps=sample_pipeline_steps
        )
        create_pipeline(
            org_id=sample_org_id, name="P2", instrument_type="pcr", steps=sample_pipeline_steps
        )
        result = list_pipelines(org_id=sample_org_id)
        assert result["total"] == 2

    def test_filter_by_status(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Status filter narrows results."""
        create_pipeline(
            org_id=sample_org_id, name="Draft", instrument_type="hplc", steps=sample_pipeline_steps
        )
        result = list_pipelines(org_id=sample_org_id, status="active")
        assert result["total"] == 0  # all are draft

    def test_invalid_status_filter(self, pipeline_store, sample_org_id):
        """Invalid status filter returns error."""
        result = list_pipelines(org_id=sample_org_id, status="invalid")
        assert result["success"] is False
        assert "suggestion" in result

    def test_includes_suggestion(self, pipeline_store, sample_org_id):
        """Result includes suggestion."""
        result = list_pipelines(org_id=sample_org_id)
        assert "suggestion" in result


class TestGetPipeline:
    """Tests for get_pipeline tool."""

    def test_gets_existing_pipeline(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Can retrieve a created pipeline by ID."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="Retrievable",
            instrument_type="balance",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = get_pipeline(pipeline_id=pid)
        assert result["success"] is True
        assert result["pipeline"]["name"] == "Retrievable"

    def test_nonexistent_pipeline_returns_error(self, pipeline_store):
        """Missing pipeline returns error with suggestion."""
        result = get_pipeline(pipeline_id="no-such-id")
        assert result["success"] is False
        assert "suggestion" in result


class TestUpdatePipeline:
    """Tests for update_pipeline tool."""

    def test_update_name(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Can update pipeline name."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="Old Name",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, name="New Name")
        assert result["success"] is True
        assert result["pipeline"]["name"] == "New Name"

    def test_activate_draft_pipeline(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Can transition draft -> active."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="To Activate",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, status="active")
        assert result["success"] is True
        assert result["pipeline"]["status"] == "active"

    def test_invalid_transition_returns_error(
        self, pipeline_store, sample_org_id, sample_pipeline_steps
    ):
        """Invalid state transition returns error with suggestion."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="Can't Pause Draft",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = update_pipeline(pipeline_id=pid, status="paused")
        assert result["success"] is False
        assert "suggestion" in result

    def test_cannot_update_archived(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Archived pipeline cannot be updated."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="To Archive",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        delete_pipeline(pipeline_id=pid)
        result = update_pipeline(pipeline_id=pid, name="Can't Update")
        assert result["success"] is False
        assert "archived" in result["error"].lower()


class TestDeletePipeline:
    """Tests for delete_pipeline tool."""

    def test_soft_deletes_pipeline(self, pipeline_store, sample_org_id, sample_pipeline_steps):
        """Deleting a pipeline archives it (soft delete)."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="To Delete",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        result = delete_pipeline(pipeline_id=pid)
        assert result["success"] is True
        assert result["current_status"] == "archived"
        assert result["previous_status"] == "draft"

    def test_already_archived_returns_error(
        self, pipeline_store, sample_org_id, sample_pipeline_steps
    ):
        """Double-archiving returns error."""
        create_result = create_pipeline(
            org_id=sample_org_id,
            name="Already Archived",
            instrument_type="hplc",
            steps=sample_pipeline_steps,
        )
        pid = create_result["pipeline"]["id"]
        delete_pipeline(pipeline_id=pid)
        result = delete_pipeline(pipeline_id=pid)
        assert result["success"] is False
        assert "already archived" in result["error"].lower()

    def test_nonexistent_pipeline_returns_error(self, pipeline_store):
        """Deleting non-existent pipeline returns error."""
        result = delete_pipeline(pipeline_id="fake")
        assert result["success"] is False
        assert "suggestion" in result
