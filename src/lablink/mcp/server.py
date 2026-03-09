"""LabLink MCP server — 25 tools + 2 discovery tools across 4 toolsets.

Toolsets:
    explorer  (8 tools) — read-only data exploration and search
    planner   (7 tools) — experiment and campaign management
    ingestor  (4 tools) — file upload, parsing, and reparse
    admin     (4 tools) — usage stats, agents, webhooks, audit

All tools follow the verb_noun naming convention and return structured
dicts that map to the LabLink { data, meta, errors } envelope.

Run standalone::

    python -m lablink.mcp.server
"""

import uuid
from typing import Any, Optional

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    "LabLink",
    instructions=(
        "LabLink is a lab data integration platform. Use the discovery tools "
        "(list_toolsets, get_toolset) to learn what tools are available, then "
        "call specific tools to explore data, plan experiments, ingest files, "
        "or administer the system. All IDs are UUIDs. Dates use ISO-8601."
    ),
)


# ---------------------------------------------------------------------------
# Toolset metadata (used by discovery tools)
# ---------------------------------------------------------------------------

_TOOLSETS: dict[str, dict[str, str]] = {
    "explorer": {
        "list_experiments": "List experiment summaries with optional filters. Returns paginated experiment list.",
        "get_experiment": "Retrieve full details for a single experiment by ID. Returns experiment with parameters, status, and linked uploads.",
        "get_instrument_data": "Retrieve parsed measurement data for an upload. Returns measurements, instrument settings, and sample metadata.",
        "search_catalog": "Search the data catalog by free-text query. Returns ranked results with highlights and facets.",
        "list_instruments": "List all registered instruments with their status and type. Returns instrument summaries.",
        "list_uploads": "List uploaded files with optional status and instrument filters. Returns paginated upload list.",
        "get_chart_data": "Retrieve Plotly-compatible chart configuration and raw JSON data for an upload. Returns chart config and data arrays.",
        "create_export": "Create a data export in the specified format (csv, json, xlsx, pdf). Returns export job with download URL.",
    },
    "planner": {
        "create_experiment": "Create a new experiment with intent and optional parameters. Returns the created experiment.",
        "update_experiment": "Update mutable fields on an experiment (intent, parameters, constraints). Returns the updated experiment.",
        "record_outcome": "Record the outcome of a completed experiment. Returns the updated experiment with outcome data.",
        "link_upload_to_experiment": "Associate an upload with an experiment for data linkage. Returns the created link.",
        "create_campaign": "Create a new optimization campaign grouping related experiments. Returns the created campaign.",
        "get_campaign_progress": "Retrieve progress metrics for a campaign. Returns counts by experiment status and completion rate.",
        "list_campaigns": "List campaigns with optional status filter. Returns paginated campaign list.",
    },
    "ingestor": {
        "create_upload": "Upload a file for parsing by specifying its storage path. Returns upload record with status.",
        "list_parsers": "List all available parsers with their supported formats and instrument types. Returns parser metadata.",
        "get_upload": "Retrieve upload details including parse status and linked data. Returns full upload record.",
        "reparse_upload": "Trigger a re-parse of a previously uploaded file. Returns updated upload status.",
    },
    "admin": {
        "get_usage_stats": "Retrieve storage usage, instrument count, and user counts. Returns usage metrics vs plan limits.",
        "list_agents": "List all desktop agents with their connection status and last heartbeat. Returns agent summaries.",
        "create_webhook": "Register a new webhook subscription for event notifications. Returns the webhook with generated secret.",
        "list_audit_events": "Query the immutable audit trail with filters. Returns paginated audit events.",
    },
}


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  DISCOVERY TOOLS (always loaded)                                       ║
# ╚═════════════════════════════════════════════════════════════════════════╝


def list_toolsets() -> dict[str, Any]:
    """List available toolset categories and their tool counts.

    Returns a dict mapping each toolset name (explorer, planner, ingestor,
    admin) to its description and number of tools. Use get_toolset to see
    individual tool names and descriptions within a category.
    """
    result = {}
    for name, tools in _TOOLSETS.items():
        result[name] = {
            "tool_count": len(tools),
            "description": {
                "explorer": "Read-only data exploration, search, and export",
                "planner": "Experiment and campaign lifecycle management",
                "ingestor": "File upload, parsing, and reparse operations",
                "admin": "Usage stats, agent management, webhooks, and audit trail",
            }[name],
            "tools": list(tools.keys()),
        }
    return {"data": result, "meta": {"total_toolsets": len(result)}}


mcp.tool()(list_toolsets)


def get_toolset(name: str) -> dict[str, Any]:
    """Retrieve tool names and descriptions for a named toolset.

    Pass one of: explorer, planner, ingestor, admin. Returns a list of
    tool entries with name and description for each tool in the set.

    Parameters
    ----------
    name:
        Toolset name. One of: explorer, planner, ingestor, admin.
    """
    toolset = _TOOLSETS.get(name)
    if toolset is None:
        return {
            "data": None,
            "errors": [
                {
                    "code": "not_found",
                    "message": f"Toolset '{name}' not found.",
                    "suggestion": f"Valid toolsets: {', '.join(_TOOLSETS.keys())}",
                }
            ],
        }
    tools = [{"name": k, "description": v} for k, v in toolset.items()]
    return {"data": {"toolset": name, "tools": tools}, "meta": {"tool_count": len(tools)}}


mcp.tool()(get_toolset)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  EXPLORER TOOLSET (8 tools)                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝


@mcp.tool()
async def list_experiments(
    status: Optional[str] = None,
    campaign_id: Optional[str] = None,
    created_after: Optional[str] = None,
    instrument_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List experiment summaries with optional filters.

    Returns a paginated list of experiments. Filter by status (planned,
    running, completed, failed, cancelled), campaign_id (UUID), or
    created_after (ISO-8601 date). Results are ordered newest first.

    Parameters
    ----------
    status:
        Filter by experiment status. One of: planned, running, completed, failed, cancelled.
    campaign_id:
        Filter by campaign UUID string.
    created_after:
        ISO-8601 datetime string. Only return experiments created after this date.
    instrument_type:
        Filter by linked instrument type (e.g. hplc, pcr, spectrophotometer).
    page:
        Page number, 1-indexed. Default 1.
    page_size:
        Results per page, 1-100. Default 20.
    """
    from lablink.database import async_session_factory
    from lablink.models.experiment import ExperimentStatus
    from lablink.services.experiment_service import list_experiments as svc_list

    async with async_session_factory() as session:
        exp_status = ExperimentStatus(status) if status else None
        camp_id = uuid.UUID(campaign_id) if campaign_id else None

        experiments, total = await svc_list(
            session,
            status=exp_status,
            campaign_id=camp_id,
            page=page,
            page_size=page_size,
        )

        items = []
        for exp in experiments:
            items.append(
                {
                    "id": str(exp.id),
                    "intent": exp.intent,
                    "status": exp.status,
                    "campaign_id": str(exp.campaign_id) if exp.campaign_id else None,
                    "created_at": exp.created_at.isoformat() if exp.created_at else None,
                }
            )

        return {
            "data": items,
            "meta": {"total": total, "page": page, "page_size": page_size},
        }


@mcp.tool()
async def get_experiment(experiment_id: str) -> dict[str, Any]:
    """Retrieve full details for a single experiment by its UUID.

    Returns the experiment record including intent, hypothesis, parameters,
    constraints, status, outcome, and linked upload IDs.

    Parameters
    ----------
    experiment_id:
        UUID string of the experiment.
    """
    from lablink.database import async_session_factory
    from lablink.services.experiment_service import get_experiment as svc_get

    async with async_session_factory() as session:
        try:
            exp = await svc_get(session, uuid.UUID(experiment_id))
        except Exception as exc:
            return {"data": None, "errors": [{"code": "not_found", "message": str(exc)}]}

        return {
            "data": {
                "id": str(exp.id),
                "intent": exp.intent,
                "hypothesis": getattr(exp, "hypothesis", None),
                "parameters": getattr(exp, "parameters", {}),
                "constraints": getattr(exp, "constraints", {}),
                "status": exp.status,
                "outcome": getattr(exp, "outcome", None),
                "design_method": getattr(exp, "design_method", None),
                "campaign_id": str(exp.campaign_id) if exp.campaign_id else None,
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
                "completed_at": (
                    exp.completed_at.isoformat() if getattr(exp, "completed_at", None) else None
                ),
            },
        }


@mcp.tool()
async def get_instrument_data(upload_id: str) -> dict[str, Any]:
    """Retrieve parsed measurement data for an upload by its UUID.

    Returns the canonical parsed result including measurements array,
    instrument settings, sample count, and parser metadata.

    Parameters
    ----------
    upload_id:
        UUID string of the upload.
    """
    from sqlalchemy import select

    from lablink.database import async_session_factory
    from lablink.models.data_pipeline import ParsedData

    uid = uuid.UUID(upload_id)

    async with async_session_factory() as session:
        stmt = select(ParsedData).where(ParsedData.upload_id == uid)
        result = await session.execute(stmt)
        parsed_records = result.scalars().all()

        if not parsed_records:
            return {
                "data": None,
                "errors": [
                    {
                        "code": "not_found",
                        "message": f"No parsed data found for upload {upload_id}.",
                        "suggestion": "Check upload status with get_upload. The file may not be parsed yet.",
                    }
                ],
            }

        items = []
        for pd in parsed_records:
            items.append(
                {
                    "id": str(pd.id),
                    "upload_id": str(pd.upload_id),
                    "instrument_type": pd.instrument_type,
                    "measurement_type": pd.measurement_type,
                    "parser_version": pd.parser_version,
                    "sample_count": pd.sample_count,
                    "measurements": pd.measurements,
                    "instrument_settings": pd.instrument_settings,
                    "data_summary": pd.data_summary,
                    "metadata": pd.metadata_,
                }
            )

        return {"data": items, "meta": {"record_count": len(items)}}


@mcp.tool()
async def search_catalog(
    query: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search the data catalog by free-text query across all indexed data.

    Returns ranked results with relevance scores, highlights, and faceted
    counts by instrument type and measurement type.

    Parameters
    ----------
    query:
        Free-text search query (e.g. "absorbance > 0.5", "HPLC peak area").
    max_results:
        Maximum number of results to return, 1-100. Default 20.
    """
    from lablink.services.search_service import get_search_service

    search_svc = get_search_service()

    # Search across all orgs in dev mode (no org scoping for MCP)
    result = await search_svc.search(
        org_id="*",
        query=query,
        page_size=min(max(max_results, 1), 100),
    )

    return {
        "data": {
            "hits": result["hits"],
            "facets": result.get("facets", {}),
        },
        "meta": {
            "total": result["total"],
            "query_time_ms": result["query_time_ms"],
        },
    }


@mcp.tool()
async def list_instruments() -> dict[str, Any]:
    """List all registered instruments with their status, type, and agent link.

    Returns instrument summaries including name, instrument_type, manufacturer,
    model, location, and linked agent ID.
    """
    from sqlalchemy import select

    from lablink.database import async_session_factory
    from lablink.models.instrument import Instrument

    async with async_session_factory() as session:
        stmt = select(Instrument).order_by(Instrument.created_at.desc())
        result = await session.execute(stmt)
        instruments = result.scalars().all()

        items = []
        for inst in instruments:
            items.append(
                {
                    "id": str(inst.id),
                    "name": inst.name,
                    "instrument_type": inst.instrument_type,
                    "manufacturer": inst.manufacturer,
                    "model": inst.model,
                    "serial_number": inst.serial_number,
                    "location": inst.location,
                    "agent_id": str(inst.agent_id) if inst.agent_id else None,
                }
            )

        return {"data": items, "meta": {"total": len(items)}}


@mcp.tool()
async def list_uploads(
    status: Optional[str] = None,
    instrument_id: Optional[str] = None,
    created_after: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List uploaded files with optional status and instrument filters.

    Returns a paginated list of uploads ordered newest first. Each entry
    includes filename, status, file size, parser used, and timestamps.

    Parameters
    ----------
    status:
        Filter by upload status. One of: uploaded, parsing, parsed, parse_failed, indexed.
    instrument_id:
        Filter by instrument UUID string.
    created_after:
        ISO-8601 datetime string. Only return uploads created after this date.
    page:
        Page number, 1-indexed. Default 1.
    page_size:
        Results per page, 1-100. Default 20.
    """
    from sqlalchemy import select, func

    from lablink.database import async_session_factory
    from lablink.models.data_pipeline import Upload, UploadStatus

    async with async_session_factory() as session:
        base = select(Upload)

        if status:
            base = base.where(Upload.status == UploadStatus(status))
        if instrument_id:
            base = base.where(Upload.instrument_id == uuid.UUID(instrument_id))

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        # Paginate
        offset = (max(page, 1) - 1) * min(max(page_size, 1), 100)
        stmt = base.order_by(Upload.created_at.desc()).offset(offset).limit(page_size)
        result = await session.execute(stmt)
        uploads = result.scalars().all()

        items = []
        for u in uploads:
            items.append(
                {
                    "id": str(u.id),
                    "filename": u.filename,
                    "status": u.status.value if hasattr(u.status, "value") else u.status,
                    "file_size_bytes": u.file_size_bytes,
                    "mime_type": u.mime_type,
                    "instrument_type_detected": u.instrument_type_detected,
                    "parser_used": u.parser_used,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "parsed_at": u.parsed_at.isoformat() if u.parsed_at else None,
                    "indexed_at": u.indexed_at.isoformat() if u.indexed_at else None,
                }
            )

        return {
            "data": items,
            "meta": {"total": total, "page": page, "page_size": page_size},
        }


@mcp.tool()
async def get_chart_data(upload_id: str) -> dict[str, Any]:
    """Retrieve Plotly-compatible chart configuration and raw JSON data for an upload.

    Returns a Plotly trace config suitable for rendering, plus the raw
    measurement values as arrays. Useful for visualization agents.

    Parameters
    ----------
    upload_id:
        UUID string of the upload to chart.
    """
    from sqlalchemy import select

    from lablink.database import async_session_factory
    from lablink.models.data_pipeline import ParsedData

    uid = uuid.UUID(upload_id)

    async with async_session_factory() as session:
        stmt = select(ParsedData).where(ParsedData.upload_id == uid)
        result = await session.execute(stmt)
        parsed = result.scalar_one_or_none()

        if parsed is None:
            return {
                "data": None,
                "errors": [
                    {
                        "code": "not_found",
                        "message": f"No parsed data for upload {upload_id}.",
                        "suggestion": "Ensure the upload has been parsed. Use get_upload to check status.",
                    }
                ],
            }

        # Build Plotly-compatible trace
        measurements = parsed.measurements or []
        values = [m.get("value") for m in measurements if isinstance(m, dict)]
        labels = [
            m.get("sample_id") or m.get("sample_name") or f"sample_{i}"
            for i, m in enumerate(measurements)
            if isinstance(m, dict)
        ]
        units = [m.get("unit", "") for m in measurements if isinstance(m, dict)]

        plotly_config = {
            "data": [
                {
                    "type": "bar",
                    "x": labels,
                    "y": values,
                    "name": parsed.measurement_type or parsed.instrument_type,
                }
            ],
            "layout": {
                "title": f"{parsed.instrument_type} — {parsed.measurement_type or 'measurements'}",
                "xaxis": {"title": "Sample"},
                "yaxis": {"title": units[0] if units else "value"},
            },
        }

        return {
            "data": {
                "plotly_config": plotly_config,
                "raw_values": values,
                "labels": labels,
                "units": units,
                "measurement_count": len(values),
            },
        }


@mcp.tool()
async def create_export(
    format: str,
    filters: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create a data export in the specified format and return a download URL.

    Supported formats: csv, json, xlsx, pdf. Provide filters to scope the
    export (e.g. instrument_type, upload_ids, date_from, date_to).

    Parameters
    ----------
    format:
        Export format. One of: csv, json, xlsx, pdf.
    filters:
        Optional dict of filters: { instrument_type?, upload_ids?, date_from?, date_to? }.
    """
    from lablink.services.export_service import ExportFormat, ExportRequest, ExportService

    try:
        fmt = ExportFormat(format)
    except ValueError:
        return {
            "data": None,
            "errors": [
                {
                    "code": "validation_error",
                    "message": f"Unsupported format '{format}'.",
                    "suggestion": "Use one of: csv, json, xlsx, pdf.",
                }
            ],
        }

    export_svc = ExportService.from_settings()
    request = ExportRequest(
        format=fmt,
        filters=filters or {},
        upload_ids=filters.get("upload_ids", []) if filters else [],
    )

    # Use a placeholder org for MCP context
    from lablink.database import async_session_factory

    async with async_session_factory() as session:
        job = await export_svc.create_export(
            session,
            organization_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            request=request,
        )

    return {
        "data": {
            "export_id": job.id,
            "format": job.format.value,
            "status": job.status.value,
            "download_url": job.download_url,
            "record_count": job.record_count,
            "file_size_bytes": job.file_size_bytes,
        },
    }


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  PLANNER TOOLSET (7 tools)                                             ║
# ╚═════════════════════════════════════════════════════════════════════════╝


@mcp.tool()
async def create_experiment(
    intent: str,
    parameters: Optional[dict[str, Any]] = None,
    campaign_id: Optional[str] = None,
    predecessor_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Create a new experiment in PLANNED status with the given intent.

    Returns the created experiment record. Optionally link to a campaign
    and/or predecessor experiments to form an experiment DAG.

    Parameters
    ----------
    intent:
        What this experiment aims to achieve. Required.
    parameters:
        Experimental conditions as a JSON dict (e.g. { "temperature_c": 37.0 }).
    campaign_id:
        UUID string of the campaign to associate with.
    predecessor_ids:
        List of UUID strings for predecessor experiments in the DAG.
    """
    from lablink.database import async_session_factory
    from lablink.services.experiment_service import (
        add_predecessor,
        create_experiment as svc_create,
    )

    async with async_session_factory() as session:
        async with session.begin():
            camp_id = uuid.UUID(campaign_id) if campaign_id else None
            # Use placeholder org for MCP context
            org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

            exp = await svc_create(
                session,
                organization_id=org_id,
                intent=intent,
                parameters=parameters,
                campaign_id=camp_id,
            )

            # Link predecessors
            if predecessor_ids:
                for pred_id in predecessor_ids:
                    try:
                        await add_predecessor(session, exp.id, uuid.UUID(pred_id))
                    except Exception as exc:
                        return {
                            "data": None,
                            "errors": [
                                {
                                    "code": "validation_error",
                                    "message": f"Failed to link predecessor {pred_id}: {exc}",
                                }
                            ],
                        }

            return {
                "data": {
                    "id": str(exp.id),
                    "intent": exp.intent,
                    "status": exp.status,
                    "parameters": getattr(exp, "parameters", {}),
                    "campaign_id": str(exp.campaign_id) if exp.campaign_id else None,
                    "created_at": exp.created_at.isoformat() if exp.created_at else None,
                },
            }


@mcp.tool()
async def update_experiment(
    experiment_id: str,
    status: Optional[str] = None,
    outcome: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Update mutable fields or transition the status of an experiment.

    Pass status to trigger a state transition (planned -> running ->
    completed|failed, planned -> cancelled). Pass outcome when completing
    or failing an experiment.

    Parameters
    ----------
    experiment_id:
        UUID string of the experiment to update.
    status:
        New status. One of: planned, running, completed, failed, cancelled.
    outcome:
        Outcome data dict, only applicable when status is completed or failed.
    """
    from lablink.database import async_session_factory
    from lablink.models.experiment import ExperimentStatus
    from lablink.services.experiment_service import transition_experiment

    async with async_session_factory() as session:
        async with session.begin():
            try:
                if status:
                    exp = await transition_experiment(
                        session,
                        uuid.UUID(experiment_id),
                        ExperimentStatus(status),
                        outcome=outcome,
                    )
                else:
                    from lablink.services.experiment_service import get_experiment as svc_get

                    exp = await svc_get(session, uuid.UUID(experiment_id))
            except Exception as exc:
                return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

            return {
                "data": {
                    "id": str(exp.id),
                    "intent": exp.intent,
                    "status": exp.status,
                    "outcome": getattr(exp, "outcome", None),
                    "completed_at": (
                        exp.completed_at.isoformat() if getattr(exp, "completed_at", None) else None
                    ),
                },
            }


@mcp.tool()
async def record_outcome(
    experiment_id: str,
    results: dict[str, Any],
    success: bool,
) -> dict[str, Any]:
    """Record the outcome of a completed experiment and transition its status.

    Marks the experiment as completed (if success=True) or failed
    (if success=False) and stores the results dict as the outcome.

    Parameters
    ----------
    experiment_id:
        UUID string of the experiment.
    results:
        Outcome data dict with measured values, observations, etc.
    success:
        True to mark as completed, False to mark as failed.
    """
    from lablink.database import async_session_factory
    from lablink.models.experiment import ExperimentStatus
    from lablink.services.experiment_service import transition_experiment

    target_status = ExperimentStatus.COMPLETED if success else ExperimentStatus.FAILED

    async with async_session_factory() as session:
        async with session.begin():
            try:
                exp = await transition_experiment(
                    session,
                    uuid.UUID(experiment_id),
                    target_status,
                    outcome=results,
                )
            except Exception as exc:
                return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

            return {
                "data": {
                    "id": str(exp.id),
                    "status": exp.status,
                    "outcome": getattr(exp, "outcome", None),
                    "completed_at": (
                        exp.completed_at.isoformat() if getattr(exp, "completed_at", None) else None
                    ),
                },
            }


@mcp.tool()
async def link_upload_to_experiment(
    experiment_id: str,
    upload_id: str,
) -> dict[str, Any]:
    """Associate an upload with an experiment for data linkage.

    Creates a link between the upload (instrument data file) and the
    experiment record. Returns the link metadata.

    Parameters
    ----------
    experiment_id:
        UUID string of the experiment.
    upload_id:
        UUID string of the upload to link.
    """
    from lablink.database import async_session_factory
    from lablink.services.experiment_service import link_upload

    async with async_session_factory() as session:
        async with session.begin():
            try:
                link = await link_upload(
                    session,
                    uuid.UUID(experiment_id),
                    uuid.UUID(upload_id),
                )
            except Exception as exc:
                return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

            return {
                "data": {
                    "experiment_id": str(link.experiment_id),
                    "upload_id": str(link.upload_id),
                    "linked_at": link.created_at.isoformat()
                    if hasattr(link, "created_at") and link.created_at
                    else None,
                },
            }


@mcp.tool()
async def create_campaign(
    name: str,
    objective: str,
    optimization_method: Optional[str] = None,
) -> dict[str, Any]:
    """Create a new optimization campaign grouping related experiments.

    Returns the created campaign record in ACTIVE status. Use
    get_campaign_progress to track experiment completion within the campaign.

    Parameters
    ----------
    name:
        Campaign name. Required.
    objective:
        What this campaign aims to achieve. Required.
    optimization_method:
        Optimization strategy: manual, bayesian, grid_search, etc. Optional.
    """
    from lablink.database import async_session_factory
    from lablink.services.campaign_service import create_campaign as svc_create

    async with async_session_factory() as session:
        async with session.begin():
            org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            campaign = await svc_create(
                session,
                organization_id=org_id,
                name=name,
                objective=objective,
                optimization_method=optimization_method,
            )

            return {
                "data": {
                    "id": str(campaign.id),
                    "name": campaign.name,
                    "objective": campaign.objective,
                    "status": campaign.status,
                    "optimization_method": campaign.optimization_method,
                    "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
                },
            }


@mcp.tool()
async def get_campaign_progress(campaign_id: str) -> dict[str, Any]:
    """Retrieve progress metrics for a campaign by its UUID.

    Returns counts of experiments by status (planned, running, completed,
    failed, cancelled) and an overall completion rate (0.0-1.0).

    Parameters
    ----------
    campaign_id:
        UUID string of the campaign.
    """
    from lablink.database import async_session_factory
    from lablink.services.campaign_service import get_campaign_progress as svc_progress

    async with async_session_factory() as session:
        try:
            progress = await svc_progress(session, uuid.UUID(campaign_id))
        except Exception as exc:
            return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

        return {"data": dict(progress)}


@mcp.tool()
async def list_campaigns(
    status: Optional[str] = None,
) -> dict[str, Any]:
    """List campaigns with optional status filter.

    Returns a paginated list of campaigns ordered newest first. Filter
    by status (active, paused, completed).

    Parameters
    ----------
    status:
        Filter by campaign status. One of: active, paused, completed.
    """
    from lablink.database import async_session_factory
    from lablink.models.experiment import CampaignStatus
    from lablink.services.campaign_service import list_campaigns as svc_list

    async with async_session_factory() as session:
        camp_status = CampaignStatus(status) if status else None
        campaigns, total = await svc_list(session, status=camp_status)

        items = []
        for c in campaigns:
            items.append(
                {
                    "id": str(c.id),
                    "name": c.name,
                    "objective": c.objective,
                    "status": c.status,
                    "optimization_method": c.optimization_method,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
            )

        return {"data": items, "meta": {"total": total}}


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  INGESTOR TOOLSET (4 tools)                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝


@mcp.tool()
async def create_upload(
    file_path: str,
    instrument_type: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    """Upload a file for parsing by specifying its local storage path.

    Reads the file from the given path, stores it in LabLink storage,
    and kicks off the parsing pipeline. Returns the upload record.

    Parameters
    ----------
    file_path:
        Absolute path to the file on the local filesystem.
    instrument_type:
        Hint for parser selection (e.g. hplc, pcr, spectrophotometer, plate_reader, balance).
    project_id:
        UUID string of the project to associate the upload with.
    """
    from pathlib import Path

    from lablink.database import async_session_factory
    from lablink.services.upload_service import UploadService

    path = Path(file_path)
    if not path.exists():
        return {
            "data": None,
            "errors": [
                {
                    "code": "not_found",
                    "message": f"File not found: {file_path}",
                    "suggestion": "Provide an absolute path to an existing file.",
                }
            ],
        }

    file_bytes = path.read_bytes()
    filename = path.name

    async with async_session_factory() as session:
        async with session.begin():
            org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            proj_id = uuid.UUID(project_id) if project_id else None

            upload_svc = UploadService(db=session)
            try:
                upload = await upload_svc.upload_file(
                    file_bytes=file_bytes,
                    filename=filename,
                    organization_id=org_id,
                    project_id=proj_id,
                )
            except Exception as exc:
                return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

            result = {
                "data": {
                    "id": str(upload.id),
                    "filename": upload.filename,
                    "status": upload.status.value,
                    "file_size_bytes": upload.file_size_bytes,
                    "content_hash": upload.content_hash,
                },
            }

    # Dispatch parse task (outside the DB session)
    from lablink.tasks import dispatch_task
    from lablink.tasks.parse_task import parse_upload_file

    dispatch_task(parse_upload_file, str(upload.id))

    return result


@mcp.tool()
def list_parsers() -> dict[str, Any]:
    """List all available parsers with their supported formats and instrument types.

    Returns parser metadata including name, version, instrument_type, and
    supported file extensions. Use this to determine which file formats
    are supported before uploading.
    """
    from lablink.services.parser_service import ParserService

    parsers = ParserService.list_parsers()
    return {"data": parsers, "meta": {"parser_count": len(parsers)}}


@mcp.tool()
async def get_upload(upload_id: str) -> dict[str, Any]:
    """Retrieve full upload details including parse status and linked data.

    Returns the upload record with filename, status, file size, parser used,
    error message (if failed), and timestamps.

    Parameters
    ----------
    upload_id:
        UUID string of the upload.
    """
    from lablink.database import async_session_factory
    from lablink.models.data_pipeline import Upload

    async with async_session_factory() as session:
        upload = await session.get(Upload, uuid.UUID(upload_id))
        if upload is None:
            return {
                "data": None,
                "errors": [
                    {
                        "code": "not_found",
                        "message": f"Upload {upload_id} not found.",
                        "suggestion": "Use list_uploads to find valid upload IDs.",
                    }
                ],
            }

        return {
            "data": {
                "id": str(upload.id),
                "filename": upload.filename,
                "status": upload.status.value if hasattr(upload.status, "value") else upload.status,
                "file_size_bytes": upload.file_size_bytes,
                "mime_type": upload.mime_type,
                "content_hash": upload.content_hash,
                "instrument_type_detected": upload.instrument_type_detected,
                "parser_used": upload.parser_used,
                "error_message": upload.error_message,
                "created_at": upload.created_at.isoformat() if upload.created_at else None,
                "parsed_at": upload.parsed_at.isoformat() if upload.parsed_at else None,
                "indexed_at": upload.indexed_at.isoformat() if upload.indexed_at else None,
            },
        }


@mcp.tool()
async def reparse_upload(upload_id: str) -> dict[str, Any]:
    """Trigger a re-parse of a previously uploaded file.

    Resets the upload status and dispatches a new parse task. Useful when
    parsers have been updated or the initial parse failed.

    Parameters
    ----------
    upload_id:
        UUID string of the upload to reparse.
    """
    from lablink.database import async_session_factory
    from lablink.models.data_pipeline import Upload, UploadStatus

    async with async_session_factory() as session:
        async with session.begin():
            upload = await session.get(Upload, uuid.UUID(upload_id))
            if upload is None:
                return {
                    "data": None,
                    "errors": [
                        {
                            "code": "not_found",
                            "message": f"Upload {upload_id} not found.",
                            "suggestion": "Use list_uploads to find valid upload IDs.",
                        }
                    ],
                }

            # Reset status to uploaded so the parse task picks it up
            upload.status = UploadStatus.uploaded
            upload.error_message = None
            upload.parser_used = None
            upload.parsed_at = None
            upload.indexed_at = None

    # Dispatch parse task
    from lablink.tasks import dispatch_task
    from lablink.tasks.parse_task import parse_upload_file

    dispatch_task(parse_upload_file, upload_id)

    return {
        "data": {
            "upload_id": upload_id,
            "status": "reparse_queued",
            "message": "Parse task has been dispatched.",
        },
    }


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  ADMIN TOOLSET (4 tools)                                               ║
# ╚═════════════════════════════════════════════════════════════════════════╝


@mcp.tool()
async def get_usage_stats() -> dict[str, Any]:
    """Retrieve storage usage, instrument count, and user counts vs plan limits.

    Returns current usage metrics including total uploads, storage bytes,
    instrument count, user count, and agent count. Useful for capacity
    planning and billing checks.
    """
    from sqlalchemy import func, select

    from lablink.database import async_session_factory
    from lablink.models.data_pipeline import Upload

    async with async_session_factory() as session:
        # Upload stats
        upload_stats = await session.execute(
            select(
                func.count(Upload.id).label("total_uploads"),
                func.coalesce(func.sum(Upload.file_size_bytes), 0).label("total_storage_bytes"),
            )
        )
        row = upload_stats.one()

        # Try to count instruments and agents
        instrument_count = 0
        agent_count = 0
        user_count = 0

        try:
            from lablink.models.instrument import Instrument

            result = await session.execute(select(func.count(Instrument.id)))
            instrument_count = result.scalar_one()
        except Exception:
            pass

        try:
            from lablink.models.agent import Agent

            result = await session.execute(select(func.count(Agent.id)))
            agent_count = result.scalar_one()
        except Exception:
            pass

        try:
            from lablink.models.user import User

            result = await session.execute(select(func.count(User.id)))
            user_count = result.scalar_one()
        except Exception:
            pass

        return {
            "data": {
                "total_uploads": row.total_uploads,
                "total_storage_bytes": row.total_storage_bytes,
                "total_storage_mb": round(row.total_storage_bytes / (1024 * 1024), 2),
                "instrument_count": instrument_count,
                "agent_count": agent_count,
                "user_count": user_count,
            },
        }


@mcp.tool()
async def list_agents() -> dict[str, Any]:
    """List all desktop agents with their connection status and last heartbeat.

    Returns agent summaries including name, platform, version, status
    (active/inactive/offline), and last heartbeat timestamp.
    """
    from sqlalchemy import select

    from lablink.database import async_session_factory
    from lablink.models.agent import Agent

    async with async_session_factory() as session:
        stmt = select(Agent).order_by(Agent.created_at.desc())
        result = await session.execute(stmt)
        agents = result.scalars().all()

        items = []
        for a in agents:
            items.append(
                {
                    "id": str(a.id),
                    "name": a.name,
                    "platform": a.platform,
                    "version": a.version,
                    "status": a.status,
                    "last_heartbeat_at": (
                        a.last_heartbeat_at.isoformat() if a.last_heartbeat_at else None
                    ),
                    "instrument_count": len(a.instruments) if a.instruments else 0,
                }
            )

        return {"data": items, "meta": {"total": len(items)}}


@mcp.tool()
async def create_webhook(
    url: str,
    events: list[str],
    secret: Optional[str] = None,
) -> dict[str, Any]:
    """Register a new webhook subscription for event notifications.

    Returns the created webhook with its auto-generated secret (if not
    provided). Events are strings like upload.parsed, upload.parse_failed,
    experiment.completed, etc.

    Parameters
    ----------
    url:
        HTTPS callback URL to receive POST requests.
    events:
        List of event type strings to subscribe to (e.g. ["upload.parsed", "experiment.completed"]).
    secret:
        Optional shared secret for HMAC signing. Auto-generated if omitted.
    """
    from lablink.database import async_session_factory
    from lablink.services.webhook_service import WebhookService

    async with async_session_factory() as session:
        async with session.begin():
            org_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
            webhook_svc = WebhookService()

            try:
                webhook = await webhook_svc.create(
                    session,
                    organization_id=org_id,
                    url=url,
                    events=events,
                    created_by=user_id,
                    secret=secret,
                )
            except Exception as exc:
                return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

            return {
                "data": {
                    "id": str(webhook.id),
                    "url": webhook.url,
                    "events": webhook.events,
                    "is_active": webhook.is_active,
                    "secret": webhook.secret,
                    "created_at": (
                        webhook.created_at.isoformat()
                        if hasattr(webhook, "created_at") and webhook.created_at
                        else None
                    ),
                },
            }


@mcp.tool()
async def list_audit_events(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    created_after: Optional[str] = None,
    page: int = 1,
) -> dict[str, Any]:
    """Query the immutable audit trail with optional filters.

    Returns paginated audit events ordered newest first. Filter by
    resource_type (experiment, upload, webhook, etc.) and/or resource_id.

    Parameters
    ----------
    resource_type:
        Filter by resource type (e.g. experiment, upload, campaign, webhook).
    resource_id:
        Filter by specific resource UUID string.
    created_after:
        ISO-8601 datetime string. Only return events after this date.
    page:
        Page number, 1-indexed. Default 1.
    """
    from lablink.database import async_session_factory
    from lablink.services.audit_service import list_audit_events as svc_list

    async with async_session_factory() as session:
        try:
            events, total = await svc_list(
                session,
                resource_type=resource_type,
                resource_id=resource_id,
                page=page,
            )
        except Exception as exc:
            return {"data": None, "errors": [{"code": "error", "message": str(exc)}]}

        items = [e.model_dump(mode="json") for e in events]

        return {"data": items, "meta": {"total": total, "page": page}}


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  Standalone entry point                                                 ║
# ╚═════════════════════════════════════════════════════════════════════════╝


def main() -> None:
    """Run the MCP server standalone via stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
