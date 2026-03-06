"""Shared fixtures for MCP tool tests."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

import pytest
from fastmcp import FastMCP

from app.mcp_server.context import MCPContext
from app.mcp_server.server import (
    _TOOL_HANDLERS,
    _TOOL_TOOLSET_MAP,
    TOOLSET_DESCRIPTIONS,
    create_mcp_server,
)


@pytest.fixture
def mcp_ctx() -> MCPContext:
    """Create a fresh MCPContext for testing."""
    return MCPContext()


@pytest.fixture
def mcp_server(mcp_ctx: MCPContext) -> FastMCP:
    """Create a fresh MCP FastMCP server with all 25 tools registered."""
    return create_mcp_server(mcp_ctx)


@pytest.fixture
def tool_handlers(mcp_server) -> dict:
    """Return the tool handler registry (populated after server creation)."""
    return dict(_TOOL_HANDLERS)


@pytest.fixture
def tool_toolset_map(mcp_server) -> dict:
    """Return the tool -> toolset mapping (populated after server creation)."""
    return dict(_TOOL_TOOLSET_MAP)


@pytest.fixture
def populated_ctx() -> MCPContext:
    """Create an MCPContext with sample data for explorer tests."""
    return MCPContext(
        uploads={
            "file-1": {
                "id": "file-1",
                "file_name": "hplc_run_001.csv",
                "file_hash": "abc123def456",
                "status": "parsed",
                "instrument_type": "hplc",
                "instrument_id": "inst-1",
                "created_at": "2026-03-01T10:00:00",
                "parse_result": {
                    "parser_name": "hplc",
                    "measurement_count": 42,
                    "sample_count": 5,
                    "is_valid": True,
                },
            },
            "file-2": {
                "id": "file-2",
                "file_name": "balance_reading.csv",
                "file_hash": "def456ghi789",
                "status": "uploaded",
                "instrument_type": "balance",
                "instrument_id": "inst-2",
                "created_at": "2026-03-02T12:00:00",
            },
            "file-3": {
                "id": "file-3",
                "file_name": "spectro_scan_42.csv",
                "file_hash": "ghi789jkl012",
                "status": "parsed",
                "instrument_type": "spectrophotometer",
                "instrument_id": "inst-3",
                "created_at": "2026-02-28T08:00:00",
                "experiment_id": "exp-1",
                "parse_result": {
                    "parser_name": "spectrophotometer",
                    "measurement_count": 8,
                    "sample_count": 2,
                    "is_valid": True,
                },
            },
        },
        experiments={
            "exp-1": {
                "id": "exp-1",
                "name": "Protein assay v2",
                "status": "running",
                "org_id": "org-1",
                "description": "Characterize protein samples",
                "created_at": "2026-03-01T09:00:00",
            },
            "exp-2": {
                "id": "exp-2",
                "name": "Buffer stability test",
                "status": "draft",
                "org_id": "org-1",
                "description": "Test buffer stability over time",
                "created_at": "2026-03-02T14:00:00",
            },
            "exp-3": {
                "id": "exp-3",
                "name": "HPLC Purity Check",
                "status": "completed",
                "org_id": "org-2",
                "description": "Verify compound purity",
                "created_at": "2026-02-20T10:00:00",
            },
        },
        instruments={
            "inst-1": {
                "id": "inst-1",
                "name": "HPLC-1",
                "instrument_type": "hplc",
                "lab_id": "lab-1",
                "manufacturer": "Agilent",
                "model_name": "1260 Infinity",
                "is_active": True,
            },
            "inst-2": {
                "id": "inst-2",
                "name": "Balance-A",
                "instrument_type": "balance",
                "lab_id": "lab-1",
                "manufacturer": "Mettler Toledo",
                "model_name": "XPR205",
                "is_active": True,
            },
            "inst-3": {
                "id": "inst-3",
                "name": "UV-Vis Spec",
                "instrument_type": "spectrophotometer",
                "lab_id": "lab-2",
                "manufacturer": "Agilent",
                "model_name": "Cary 60",
                "is_active": False,
            },
        },
        search_index=[
            {
                "type": "dataset",
                "id": "ds-1",
                "name": "HPLC Dataset Run 1",
                "instrument_type": "hplc",
                "parser_name": "hplc",
                "org_id": "org-1",
                "sample_count": 5,
                "measurement_count": 42,
                "warning_count": 1,
                "error_count": 0,
                "measurements": [
                    {"name": "peak_area", "value": 1234.5, "sample_id": "s1", "quality": "good"},
                    {"name": "peak_area", "value": 2345.6, "sample_id": "s2", "quality": "good"},
                    {"name": "retention_time", "value": 3.14, "sample_id": "s1", "quality": "suspect"},
                ],
                "created_at": "2026-03-01T11:00:00",
            },
            {
                "type": "dataset",
                "id": "ds-2",
                "name": "Spectro Scan Results",
                "instrument_type": "spectrophotometer",
                "parser_name": "spectrophotometer",
                "org_id": "org-1",
                "sample_count": 2,
                "measurement_count": 8,
                "warning_count": 0,
                "error_count": 0,
                "measurements": [
                    {"name": "absorbance", "value": 0.542, "sample_id": "s1", "quality": "good"},
                    {"name": "absorbance", "value": 0.321, "sample_id": "s2", "quality": "good"},
                ],
                "created_at": "2026-02-28T09:00:00",
            },
        ],
    )


@pytest.fixture
def pipeline_store():
    """Get the pipeline store and ensure it's clean for each test."""
    from app.mcp_server.tools.planner import get_pipeline_store
    store = get_pipeline_store()
    store.clear()
    yield store
    store.clear()


@pytest.fixture
def sample_org_id() -> str:
    """A consistent org ID for tests."""
    return "org-test-001"


@pytest.fixture
def sample_user_id() -> str:
    """A consistent user ID for tests."""
    return "user-test-001"


@pytest.fixture
def sample_spectro_csv() -> bytes:
    """Sample spectrophotometer CSV content for ingestion tests."""
    return (
        "Sample ID,Wavelength (nm),Absorbance (AU)\n"
        "SAMPLE-001,260,0.542\n"
        "SAMPLE-001,280,0.321\n"
        "SAMPLE-002,260,0.876\n"
        "SAMPLE-002,280,0.432\n"
    ).encode("utf-8")


@pytest.fixture
def sample_spectro_csv_b64(sample_spectro_csv: bytes) -> str:
    """Base64-encoded spectrophotometer CSV."""
    return base64.b64encode(sample_spectro_csv).decode("ascii")


@pytest.fixture
def sample_balance_csv() -> bytes:
    """Sample balance CSV content."""
    return (
        "Sample ID,Mass (g),Unit,Timestamp\n"
        "BAL-001,12.345,g,2025-01-15T10:30:00\n"
        "BAL-002,0.987,g,2025-01-15T10:31:00\n"
    ).encode("utf-8")


@pytest.fixture
def sample_pipeline_steps() -> list[dict]:
    """Sample pipeline step definitions."""
    return [
        {"step_type": "parse", "config": {"parser": "spectrophotometer"}, "description": "Parse raw data"},
        {"step_type": "validate", "config": {}, "description": "Validate measurements"},
        {"step_type": "store", "config": {"format": "json"}, "description": "Persist to storage"},
    ]


@pytest.fixture
def sample_audit_entries() -> list[dict]:
    """Sample audit log entries for admin tool tests."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "action": "CREATE",
            "resource_type": "experiment",
            "resource_id": str(uuid.uuid4()),
            "actor_id": "user-test-001",
            "summary": "Created experiment 'UV-Vis Test'",
            "timestamp": now,
        },
        {
            "action": "UPLOAD",
            "resource_type": "file",
            "resource_id": str(uuid.uuid4()),
            "actor_id": "agent-auto",
            "summary": "Auto-ingested spectrophotometer file",
            "timestamp": now,
        },
        {
            "action": "STATE_CHANGE",
            "resource_type": "experiment",
            "resource_id": str(uuid.uuid4()),
            "actor_id": "user-test-002",
            "summary": "Experiment transitioned draft -> running",
            "timestamp": now,
        },
    ]
