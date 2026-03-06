"""Explorer toolset — 8 tools for browsing and discovering lab data.

All tools operate on in-memory stores (MCPContext) for dev/test mode,
making them runnable without Docker or external databases.

Tools:
  1. search_files — Full-text search across file records
  2. list_experiments — List experiments with filtering
  3. get_file_metadata — Get detailed metadata for a file
  4. get_experiment_detail — Get full experiment details
  5. list_datasets — List parsed datasets with filtering
  6. get_parse_result — Get parse result for a file
  7. list_instruments — List registered instruments
  8. get_dataset_summary — Get summary statistics for a dataset
"""

from __future__ import annotations

from typing import Any

from app.mcp_server.context import MCPContext


def _match(text: str | None, query: str) -> bool:
    """Case-insensitive substring match."""
    if text is None:
        return False
    return query.lower() in text.lower()


# ---------------------------------------------------------------------------
# 1. search_files
# ---------------------------------------------------------------------------
def search_files(
    ctx: MCPContext,
    query: str = "",
    instrument_type: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search file records by name, hash, or instrument type.

    Args:
        ctx: MCP execution context with in-memory stores.
        query: Search term to match against file names and hashes.
        instrument_type: Filter by instrument type (e.g. 'hplc', 'pcr').
        status: Filter by file status (uploaded, queued, parsing, parsed, failed, stored).
        limit: Max results to return (default 20, max 100).
        offset: Number of results to skip for pagination.

    Returns:
        Dict with 'files' list and 'total' count.
    """
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    files = list(ctx.uploads.values())

    # Apply filters
    if query:
        files = [
            f for f in files
            if _match(f.get("file_name"), query)
            or _match(f.get("file_hash"), query)
        ]

    if instrument_type:
        files = [
            f for f in files
            if f.get("instrument_type") == instrument_type
        ]

    if status:
        files = [f for f in files if f.get("status") == status]

    # Sort by created_at descending (newest first)
    files.sort(key=lambda f: f.get("created_at", ""), reverse=True)

    total = len(files)
    page = files[offset: offset + limit]

    return {
        "files": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "suggestion": (
            "Use get_file_metadata with a file ID for full details."
            if page
            else "No files found. Try broadening your search query."
        ),
    }


# ---------------------------------------------------------------------------
# 2. list_experiments
# ---------------------------------------------------------------------------
def list_experiments(
    ctx: MCPContext,
    org_id: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List experiments with optional filtering and pagination.

    Args:
        ctx: MCP execution context with in-memory stores.
        org_id: Filter by organization ID.
        status: Filter by experiment status (draft, running, completed, failed, cancelled).
        page: Page number, 1-indexed.
        page_size: Items per page (default 20, max 100).

    Returns:
        Dict with 'experiments' list, 'total' count, and pagination info.
    """
    page_size = min(max(page_size, 1), 100)
    page = max(page, 1)

    experiments = list(ctx.experiments.values())

    if org_id:
        experiments = [e for e in experiments if e.get("org_id") == org_id]

    if status:
        experiments = [e for e in experiments if e.get("status") == status]

    # Sort by created_at descending
    experiments.sort(key=lambda e: e.get("created_at", ""), reverse=True)

    total = len(experiments)
    start = (page - 1) * page_size
    page_items = experiments[start: start + page_size]

    return {
        "experiments": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "suggestion": (
            "Use get_experiment_detail with an experiment ID for full details."
            if page_items
            else "No experiments found. Try different filters or create one via the API."
        ),
    }


# ---------------------------------------------------------------------------
# 3. get_file_metadata
# ---------------------------------------------------------------------------
def get_file_metadata(ctx: MCPContext, file_id: str) -> dict[str, Any]:
    """Get detailed metadata for a specific file record.

    Args:
        ctx: MCP execution context with in-memory stores.
        file_id: UUID of the file record.

    Returns:
        Full file metadata including instrument info and parse status.
    """
    f = ctx.uploads.get(file_id)
    if f is None:
        return {
            "error": "not_found",
            "message": f"File record '{file_id}' not found.",
            "suggestion": "Check the file ID. Use search_files to find valid file IDs.",
        }

    # Enrich with instrument info if available
    instrument_id = f.get("instrument_id")
    instrument_info = None
    if instrument_id:
        instrument_info = ctx.instruments.get(instrument_id)

    result = {**f, "instrument": instrument_info}
    result["suggestion"] = "Use get_parse_result to view full parsed data for this file."
    return result


# ---------------------------------------------------------------------------
# 4. get_experiment_detail
# ---------------------------------------------------------------------------
def get_experiment_detail(ctx: MCPContext, experiment_id: str) -> dict[str, Any]:
    """Get full details for a specific experiment.

    Args:
        ctx: MCP execution context with in-memory stores.
        experiment_id: UUID of the experiment.

    Returns:
        Complete experiment details including linked files and state machine info.
    """
    exp = ctx.experiments.get(experiment_id)
    if exp is None:
        return {
            "error": "not_found",
            "message": f"Experiment '{experiment_id}' not found.",
            "suggestion": "Check the experiment ID. Use list_experiments to discover valid IDs.",
        }

    # Compute valid transitions from the state machine
    from app.models.experiment import EXPERIMENT_TRANSITIONS, ExperimentStatus

    current_status_str = exp.get("status", "draft")
    try:
        current_status = ExperimentStatus(current_status_str)
        valid_next = EXPERIMENT_TRANSITIONS.get(current_status, set())
        valid_transitions = sorted(s.value for s in valid_next)
    except ValueError:
        valid_transitions = []

    # Find linked files
    linked_files = [
        f for f in ctx.uploads.values()
        if f.get("experiment_id") == experiment_id
    ]

    result = {
        **exp,
        "valid_transitions": valid_transitions,
        "linked_files": linked_files,
    }
    result["suggestion"] = (
        f"Valid next states: {', '.join(valid_transitions)}."
        if valid_transitions
        else "This experiment is in a terminal state."
    )
    return result


# ---------------------------------------------------------------------------
# 5. list_datasets
# ---------------------------------------------------------------------------
def list_datasets(
    ctx: MCPContext,
    org_id: str | None = None,
    instrument_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List parsed datasets with optional filtering.

    Args:
        ctx: MCP execution context with in-memory stores.
        org_id: Filter by organization ID.
        instrument_type: Filter by instrument type (spectrophotometer, plate_reader, hplc, pcr, balance).
        limit: Max results to return (default 20, max 100).
        offset: Number of results to skip for pagination.

    Returns:
        Dict with 'datasets' list and 'total' count.
    """
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    # Datasets stored in search_index with type="dataset"
    datasets: list[dict[str, Any]] = [
        entry for entry in ctx.search_index
        if entry.get("type") == "dataset"
    ]

    if org_id:
        datasets = [d for d in datasets if d.get("org_id") == org_id]

    if instrument_type:
        datasets = [d for d in datasets if d.get("instrument_type") == instrument_type]

    datasets.sort(key=lambda d: d.get("created_at", ""), reverse=True)

    total = len(datasets)
    page = datasets[offset: offset + limit]

    return {
        "datasets": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "suggestion": (
            "Use get_dataset_summary with a dataset ID for detailed statistics."
            if page
            else "No datasets found. Ingest instrument files to create datasets."
        ),
    }


# ---------------------------------------------------------------------------
# 6. get_parse_result
# ---------------------------------------------------------------------------
def get_parse_result(ctx: MCPContext, file_id: str) -> dict[str, Any]:
    """Get the parsed result for a specific file.

    Args:
        ctx: MCP execution context with in-memory stores.
        file_id: UUID of the file record to get parse results for.

    Returns:
        Parse result data including measurements and quality info.
    """
    f = ctx.uploads.get(file_id)
    if f is None:
        return {
            "error": "not_found",
            "message": f"No file record found for '{file_id}'.",
            "suggestion": "Check the file ID. Use search_files to find valid file IDs.",
        }

    parse_result = f.get("parse_result")
    if parse_result is None:
        return {
            "error": "not_parsed",
            "message": f"File '{file_id}' has not been parsed yet.",
            "suggestion": (
                "The file may still be in the processing queue. "
                "Check file status with get_file_metadata."
            ),
        }

    result = {
        "file_id": file_id,
        "file_name": f.get("file_name"),
        **parse_result,
    }
    result["suggestion"] = "Use list_datasets to find the canonical dataset derived from this parse."
    return result


# ---------------------------------------------------------------------------
# 7. list_instruments
# ---------------------------------------------------------------------------
def list_instruments(
    ctx: MCPContext,
    lab_id: str | None = None,
    instrument_type: str | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    """List registered instruments with optional filtering.

    Args:
        ctx: MCP execution context with in-memory stores.
        lab_id: Filter by lab ID.
        instrument_type: Filter by instrument type.
        active_only: If True (default), only return active instruments.

    Returns:
        Dict with 'instruments' list.
    """
    instruments = list(ctx.instruments.values())

    if active_only:
        instruments = [
            i for i in instruments
            if i.get("is_active", True)
        ]

    if lab_id:
        instruments = [i for i in instruments if i.get("lab_id") == lab_id]

    if instrument_type:
        instruments = [i for i in instruments if i.get("instrument_type") == instrument_type]

    instruments.sort(key=lambda i: i.get("name", ""))

    return {
        "instruments": instruments,
        "total": len(instruments),
        "suggestion": "Use search_files with an instrument_type to find files from a specific instrument type.",
    }


# ---------------------------------------------------------------------------
# 8. get_dataset_summary
# ---------------------------------------------------------------------------
def get_dataset_summary(ctx: MCPContext, dataset_id: str) -> dict[str, Any]:
    """Get summary statistics for a specific dataset.

    Args:
        ctx: MCP execution context with in-memory stores.
        dataset_id: UUID of the dataset.

    Returns:
        Dataset summary including measurement stats, quality info, and sample breakdown.
    """
    dataset = None
    for entry in ctx.search_index:
        if entry.get("type") == "dataset" and entry.get("id") == dataset_id:
            dataset = entry
            break

    if dataset is None:
        return {
            "error": "not_found",
            "message": f"Dataset '{dataset_id}' not found.",
            "suggestion": "Check the dataset ID. Use list_datasets to discover valid IDs.",
        }

    # Compute summary stats from measurements if available
    measurements = dataset.get("measurements", [])
    values = [m.get("value") for m in measurements if m.get("value") is not None]
    samples = {m.get("sample_id") for m in measurements if m.get("sample_id")}
    measurement_names = {m.get("name") for m in measurements if m.get("name")}

    quality_breakdown: dict[str, int] = {}
    for m in measurements:
        q = m.get("quality", "good")
        quality_breakdown[q] = quality_breakdown.get(q, 0) + 1

    statistics = {
        "data_point_count": len(measurements),
        "average_value": sum(values) / len(values) if values else None,
        "min_value": min(values) if values else None,
        "max_value": max(values) if values else None,
        "unique_samples": len(samples),
        "unique_measurement_types": len(measurement_names),
    }

    return {
        "id": dataset.get("id"),
        "name": dataset.get("name"),
        "instrument_type": dataset.get("instrument_type"),
        "parser_name": dataset.get("parser_name"),
        "sample_count": dataset.get("sample_count", len(samples)),
        "measurement_count": dataset.get("measurement_count", len(measurements)),
        "statistics": statistics,
        "quality_breakdown": quality_breakdown,
        "warning_count": dataset.get("warning_count", 0),
        "error_count": dataset.get("error_count", 0),
        "instrument_settings": dataset.get("instrument_settings"),
        "org_id": dataset.get("org_id"),
        "created_at": dataset.get("created_at"),
        "suggestion": "Use search_files to find the source file, or list_experiments to find linked experiments.",
    }


# ---------------------------------------------------------------------------
# Tool registry for explorer toolset
# ---------------------------------------------------------------------------
EXPLORER_TOOLS = {
    "search_files": search_files,
    "list_experiments": list_experiments,
    "get_file_metadata": get_file_metadata,
    "get_experiment_detail": get_experiment_detail,
    "list_datasets": list_datasets,
    "get_parse_result": get_parse_result,
    "list_instruments": list_instruments,
    "get_dataset_summary": get_dataset_summary,
}
