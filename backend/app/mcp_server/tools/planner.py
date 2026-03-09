"""Planner toolset — 7 MCP tools for pipeline planning and management.

Tools:
1. create_pipeline    — Create a new ingestion pipeline definition
2. validate_pipeline  — Validate a pipeline definition without executing
3. estimate_duration  — Estimate processing time for a pipeline
4. list_pipelines     — List all pipelines for an organization
5. get_pipeline       — Get details of a specific pipeline
6. update_pipeline    — Update a pipeline's configuration
7. delete_pipeline    — Soft-delete a pipeline

All tools return structured dicts suitable for MCP tool responses with
suggestion fields for agent-native error recovery.
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.parsers import PARSER_REGISTRY

# ---------------------------------------------------------------------------
# Pipeline domain types
# ---------------------------------------------------------------------------

class PipelineStatus(str, Enum):
    """Pipeline lifecycle states."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class PipelineStepType(str, Enum):
    """Types of steps available in a pipeline."""
    PARSE = "parse"
    VALIDATE = "validate"
    TRANSFORM = "transform"
    STORE = "store"
    NOTIFY = "notify"


# Estimated seconds per step type (used for duration estimation)
_STEP_DURATION_ESTIMATES: dict[str, float] = {
    PipelineStepType.PARSE: 2.5,
    PipelineStepType.VALIDATE: 0.5,
    PipelineStepType.TRANSFORM: 1.5,
    PipelineStepType.STORE: 1.0,
    PipelineStepType.NOTIFY: 0.3,
}

# Valid parser/instrument types for pipeline definitions
VALID_INSTRUMENT_TYPES = set(PARSER_REGISTRY.keys())


class PipelineStep(BaseModel):
    """A single step in a pipeline definition."""
    step_type: PipelineStepType
    config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class PipelineDefinition(BaseModel):
    """Full pipeline definition stored in-memory."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    name: str
    description: str | None = None
    instrument_type: str
    steps: list[PipelineStep] = Field(default_factory=list)
    status: PipelineStatus = PipelineStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str | None = None


# ---------------------------------------------------------------------------
# In-memory pipeline store (replaced by DB in production)
# ---------------------------------------------------------------------------

class PipelineStore:
    """In-memory pipeline store for dev/MCP usage.

    Thread-safe enough for single-process dev mode. Production
    would use the database via the service layer.
    """

    def __init__(self) -> None:
        self._pipelines: dict[str, PipelineDefinition] = {}

    def add(self, pipeline: PipelineDefinition) -> PipelineDefinition:
        self._pipelines[pipeline.id] = pipeline
        return pipeline

    def get(self, pipeline_id: str) -> PipelineDefinition | None:
        return self._pipelines.get(pipeline_id)

    def list_for_org(
        self,
        org_id: str,
        *,
        status: PipelineStatus | None = None,
        include_archived: bool = False,
    ) -> list[PipelineDefinition]:
        results = []
        for p in self._pipelines.values():
            if p.org_id != org_id:
                continue
            if not include_archived and p.status == PipelineStatus.ARCHIVED:
                continue
            if status is not None and p.status != status:
                continue
            results.append(p)
        return sorted(results, key=lambda p: p.created_at, reverse=True)

    def update(self, pipeline_id: str, **fields: Any) -> PipelineDefinition | None:
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            return None
        for key, value in fields.items():
            if hasattr(pipeline, key) and value is not None:
                setattr(pipeline, key, value)
        pipeline.updated_at = datetime.now(UTC)
        return pipeline

    def delete(self, pipeline_id: str) -> PipelineDefinition | None:
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            return None
        pipeline.status = PipelineStatus.ARCHIVED
        pipeline.updated_at = datetime.now(UTC)
        return pipeline

    def clear(self) -> None:
        """Clear all pipelines (useful for testing)."""
        self._pipelines.clear()


# Module-level store instance
_store = PipelineStore()


def get_pipeline_store() -> PipelineStore:
    """Get the module-level pipeline store."""
    return _store


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_steps(steps: list[dict[str, Any]]) -> tuple[list[PipelineStep], list[str]]:
    """Validate and parse pipeline steps.

    Returns:
        Tuple of (parsed steps, validation errors).
    """
    parsed: list[PipelineStep] = []
    errors: list[str] = []

    if not steps:
        errors.append("Pipeline must have at least one step.")
        return parsed, errors

    valid_step_types = {e.value for e in PipelineStepType}

    for i, step_dict in enumerate(steps):
        step_type = step_dict.get("step_type", "")
        if step_type not in valid_step_types:
            errors.append(
                f"Step {i}: invalid step_type '{step_type}'. "
                f"Valid types: {', '.join(sorted(valid_step_types))}."
            )
            continue

        config = step_dict.get("config", {})
        description = step_dict.get("description")

        # Validate parse step has instrument_type in config if needed
        if step_type == PipelineStepType.PARSE:
            parser_name = config.get("parser")
            if parser_name and parser_name not in VALID_INSTRUMENT_TYPES:
                errors.append(
                    f"Step {i}: unknown parser '{parser_name}'. "
                    f"Valid parsers: {', '.join(sorted(VALID_INSTRUMENT_TYPES))}."
                )
                continue

        parsed.append(PipelineStep(
            step_type=PipelineStepType(step_type),
            config=config,
            description=description,
        ))

    return parsed, errors


def _pipeline_to_dict(pipeline: PipelineDefinition) -> dict[str, Any]:
    """Serialize a pipeline to a dict for MCP responses."""
    return {
        "id": pipeline.id,
        "org_id": pipeline.org_id,
        "name": pipeline.name,
        "description": pipeline.description,
        "instrument_type": pipeline.instrument_type,
        "steps": [
            {
                "step_type": s.step_type.value,
                "config": s.config,
                "description": s.description,
            }
            for s in pipeline.steps
        ],
        "status": pipeline.status.value,
        "created_at": pipeline.created_at.isoformat(),
        "updated_at": pipeline.updated_at.isoformat(),
        "created_by": pipeline.created_by,
        "step_count": len(pipeline.steps),
    }


# ---------------------------------------------------------------------------
# MCP Tool functions (7 tools)
# ---------------------------------------------------------------------------

def create_pipeline(
    org_id: str,
    name: str,
    instrument_type: str,
    steps: list[dict[str, Any]],
    description: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """Create a new ingestion pipeline definition.

    A pipeline defines the sequence of processing steps applied to
    instrument files after upload: parse -> validate -> transform -> store.

    Args:
        org_id: Organization ID that owns this pipeline.
        name: Human-readable pipeline name.
        instrument_type: Target instrument type (spectrophotometer, plate_reader, hplc, pcr, balance).
        steps: List of step definitions, each with step_type, config, and optional description.
        description: Optional pipeline description.
        created_by: Optional user ID of creator.

    Returns:
        Dict with created pipeline data or error details.
    """
    # Validate instrument type
    if instrument_type not in VALID_INSTRUMENT_TYPES:
        return {
            "success": False,
            "error": f"Unknown instrument_type '{instrument_type}'.",
            "suggestion": f"Valid instrument types: {', '.join(sorted(VALID_INSTRUMENT_TYPES))}.",
        }

    # Validate name
    if not name or not name.strip():
        return {
            "success": False,
            "error": "Pipeline name is required.",
            "suggestion": "Provide a descriptive name like 'HPLC Daily QC Pipeline'.",
        }

    # Validate steps
    parsed_steps, step_errors = _validate_steps(steps)
    if step_errors:
        return {
            "success": False,
            "error": "Invalid pipeline steps.",
            "details": step_errors,
            "suggestion": "Fix the step definitions and retry. Each step needs a valid step_type.",
        }

    pipeline = PipelineDefinition(
        org_id=org_id,
        name=name.strip(),
        instrument_type=instrument_type,
        steps=parsed_steps,
        description=description,
        created_by=created_by,
    )

    store = get_pipeline_store()
    store.add(pipeline)

    return {
        "success": True,
        "pipeline": _pipeline_to_dict(pipeline),
        "suggestion": f"Pipeline created. Use validate_pipeline('{pipeline.id}') to check it before activating.",
    }


def validate_pipeline(
    pipeline_id: str,
) -> dict[str, Any]:
    """Validate a pipeline definition without executing it.

    Checks that all steps are properly configured, parsers exist,
    and the step sequence is logically valid.

    Args:
        pipeline_id: UUID of the pipeline to validate.

    Returns:
        Dict with validation results including any warnings or errors.
    """
    store = get_pipeline_store()
    pipeline = store.get(pipeline_id)

    if pipeline is None:
        return {
            "valid": False,
            "error": f"Pipeline '{pipeline_id}' not found.",
            "suggestion": "Use list_pipelines to find available pipeline IDs.",
        }

    warnings: list[str] = []
    errors: list[str] = []

    # Check instrument type
    if pipeline.instrument_type not in VALID_INSTRUMENT_TYPES:
        errors.append(
            f"Unknown instrument_type '{pipeline.instrument_type}'. "
            f"Valid: {', '.join(sorted(VALID_INSTRUMENT_TYPES))}."
        )

    # Check steps
    if not pipeline.steps:
        errors.append("Pipeline has no steps defined.")
    else:
        step_types = [s.step_type for s in pipeline.steps]

        # Recommend starting with parse
        if step_types and step_types[0] != PipelineStepType.PARSE:
            warnings.append(
                "Pipeline does not start with a 'parse' step. "
                "Most pipelines should begin with parsing the raw instrument file."
            )

        # Recommend ending with store
        if step_types and step_types[-1] != PipelineStepType.STORE:
            warnings.append(
                "Pipeline does not end with a 'store' step. "
                "Data will not be persisted unless you add a store step."
            )

        # Check for duplicate consecutive step types
        for i in range(1, len(step_types)):
            if step_types[i] == step_types[i - 1]:
                warnings.append(
                    f"Steps {i - 1} and {i} are both '{step_types[i].value}'. "
                    f"This may be intentional but is unusual."
                )

        # Validate parse step config
        for i, step in enumerate(pipeline.steps):
            if step.step_type == PipelineStepType.PARSE:
                parser_name = step.config.get("parser")
                if parser_name and parser_name not in VALID_INSTRUMENT_TYPES:
                    errors.append(
                        f"Step {i}: parser '{parser_name}' not found in registry."
                    )

    is_valid = len(errors) == 0

    return {
        "valid": is_valid,
        "pipeline_id": pipeline_id,
        "pipeline_name": pipeline.name,
        "errors": errors,
        "warnings": warnings,
        "step_count": len(pipeline.steps),
        "suggestion": (
            "Pipeline is valid and ready to activate."
            if is_valid
            else "Fix the errors above and re-validate."
        ),
    }


def estimate_duration(
    pipeline_id: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    file_count: int = 1,
    avg_file_size_mb: float = 1.0,
) -> dict[str, Any]:
    """Estimate processing time for a pipeline or ad-hoc step list.

    Provide either pipeline_id (to estimate an existing pipeline) or
    steps (to estimate an ad-hoc sequence). The estimate scales with
    file count and average file size.

    Args:
        pipeline_id: UUID of an existing pipeline (optional).
        steps: List of step dicts for ad-hoc estimation (optional).
        file_count: Number of files to process (default 1).
        avg_file_size_mb: Average file size in MB (default 1.0).

    Returns:
        Dict with estimated duration breakdown per step and total.
    """
    store = get_pipeline_store()
    resolved_steps: list[PipelineStep] = []

    if pipeline_id is not None:
        pipeline = store.get(pipeline_id)
        if pipeline is None:
            return {
                "success": False,
                "error": f"Pipeline '{pipeline_id}' not found.",
                "suggestion": "Use list_pipelines to find available pipeline IDs, or pass steps directly.",
            }
        resolved_steps = pipeline.steps
    elif steps is not None:
        parsed, errors = _validate_steps(steps)
        if errors:
            return {
                "success": False,
                "error": "Invalid steps for estimation.",
                "details": errors,
                "suggestion": "Fix step definitions. Valid step_types: parse, validate, transform, store, notify.",
            }
        resolved_steps = parsed
    else:
        return {
            "success": False,
            "error": "Provide either pipeline_id or steps for estimation.",
            "suggestion": "Pass pipeline_id='<uuid>' for an existing pipeline, or steps=[...] for ad-hoc estimation.",
        }

    if file_count < 1:
        return {
            "success": False,
            "error": "file_count must be at least 1.",
            "suggestion": "Set file_count to the number of files you plan to process.",
        }

    # Size scaling factor: base estimate is for 1MB files
    size_factor = max(0.1, avg_file_size_mb)

    step_estimates: list[dict[str, Any]] = []
    total_per_file = 0.0

    for i, step in enumerate(resolved_steps):
        base_seconds = _STEP_DURATION_ESTIMATES.get(step.step_type, 1.0)
        # Parse and transform scale with file size; others are roughly constant
        if step.step_type in (PipelineStepType.PARSE, PipelineStepType.TRANSFORM):
            estimated = base_seconds * size_factor
        else:
            estimated = base_seconds

        total_per_file += estimated
        step_estimates.append({
            "step_index": i,
            "step_type": step.step_type.value,
            "estimated_seconds_per_file": round(estimated, 2),
        })

    total_seconds = total_per_file * file_count

    return {
        "success": True,
        "pipeline_id": pipeline_id,
        "file_count": file_count,
        "avg_file_size_mb": avg_file_size_mb,
        "steps": step_estimates,
        "estimated_seconds_per_file": round(total_per_file, 2),
        "estimated_total_seconds": round(total_seconds, 2),
        "estimated_total_minutes": round(total_seconds / 60, 2),
        "suggestion": (
            f"Estimated {round(total_seconds, 1)}s for {file_count} file(s). "
            "Actual time depends on system load and file complexity."
        ),
    }


def list_pipelines(
    org_id: str,
    status: str | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    """List all pipelines for an organization.

    Args:
        org_id: Organization ID to list pipelines for.
        status: Optional filter by status (draft, active, paused, archived).
        include_archived: Whether to include archived pipelines.

    Returns:
        Dict with list of pipeline summaries.
    """
    store = get_pipeline_store()

    # Validate status filter
    status_filter: PipelineStatus | None = None
    if status is not None:
        try:
            status_filter = PipelineStatus(status)
        except ValueError:
            valid = [s.value for s in PipelineStatus]
            return {
                "success": False,
                "error": f"Invalid status filter '{status}'.",
                "suggestion": f"Valid statuses: {', '.join(valid)}.",
            }

    pipelines = store.list_for_org(
        org_id,
        status=status_filter,
        include_archived=include_archived,
    )

    return {
        "success": True,
        "org_id": org_id,
        "pipelines": [_pipeline_to_dict(p) for p in pipelines],
        "total": len(pipelines),
        "suggestion": (
            "No pipelines found. Use create_pipeline to define one."
            if not pipelines
            else f"Found {len(pipelines)} pipeline(s). Use get_pipeline('<id>') for details."
        ),
    }


def get_pipeline(
    pipeline_id: str,
) -> dict[str, Any]:
    """Get full details of a specific pipeline.

    Args:
        pipeline_id: UUID of the pipeline.

    Returns:
        Dict with complete pipeline definition or error.
    """
    store = get_pipeline_store()
    pipeline = store.get(pipeline_id)

    if pipeline is None:
        return {
            "success": False,
            "error": f"Pipeline '{pipeline_id}' not found.",
            "suggestion": "Use list_pipelines to find available pipeline IDs.",
        }

    return {
        "success": True,
        "pipeline": _pipeline_to_dict(pipeline),
        "suggestion": (
            f"Pipeline '{pipeline.name}' is {pipeline.status.value}. "
            + (
                "Use validate_pipeline to check it before activating."
                if pipeline.status == PipelineStatus.DRAFT
                else "Use update_pipeline to modify its configuration."
            )
        ),
    }


def update_pipeline(
    pipeline_id: str,
    name: str | None = None,
    description: str | None = None,
    steps: list[dict[str, Any]] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Update a pipeline's configuration.

    Only draft and paused pipelines can have their steps modified.
    Active pipelines can only be paused or have metadata updated.

    Args:
        pipeline_id: UUID of the pipeline to update.
        name: New pipeline name (optional).
        description: New description (optional).
        steps: New step definitions (optional, only for draft/paused).
        status: New status (optional). Valid transitions:
            draft -> active, active -> paused, paused -> active, * -> archived.

    Returns:
        Dict with updated pipeline or error details.
    """
    store = get_pipeline_store()
    pipeline = store.get(pipeline_id)

    if pipeline is None:
        return {
            "success": False,
            "error": f"Pipeline '{pipeline_id}' not found.",
            "suggestion": "Use list_pipelines to find available pipeline IDs.",
        }

    if pipeline.status == PipelineStatus.ARCHIVED:
        return {
            "success": False,
            "error": "Cannot update an archived pipeline.",
            "suggestion": "Create a new pipeline instead. Archived pipelines are read-only.",
        }

    update_fields: dict[str, Any] = {}

    # Validate and apply name
    if name is not None:
        if not name.strip():
            return {
                "success": False,
                "error": "Pipeline name cannot be empty.",
                "suggestion": "Provide a descriptive name.",
            }
        update_fields["name"] = name.strip()

    # Apply description
    if description is not None:
        update_fields["description"] = description

    # Validate and apply steps (only for draft/paused)
    if steps is not None:
        if pipeline.status not in (PipelineStatus.DRAFT, PipelineStatus.PAUSED):
            return {
                "success": False,
                "error": f"Cannot modify steps of a '{pipeline.status.value}' pipeline.",
                "suggestion": "Pause the pipeline first with update_pipeline(status='paused'), then update steps.",
            }
        parsed_steps, step_errors = _validate_steps(steps)
        if step_errors:
            return {
                "success": False,
                "error": "Invalid pipeline steps.",
                "details": step_errors,
                "suggestion": "Fix the step definitions and retry.",
            }
        update_fields["steps"] = parsed_steps

    # Validate and apply status transition
    if status is not None:
        try:
            new_status = PipelineStatus(status)
        except ValueError:
            valid = [s.value for s in PipelineStatus]
            return {
                "success": False,
                "error": f"Invalid status '{status}'.",
                "suggestion": f"Valid statuses: {', '.join(valid)}.",
            }

        # Define valid transitions
        valid_transitions: dict[PipelineStatus, set[PipelineStatus]] = {
            PipelineStatus.DRAFT: {PipelineStatus.ACTIVE, PipelineStatus.ARCHIVED},
            PipelineStatus.ACTIVE: {PipelineStatus.PAUSED, PipelineStatus.ARCHIVED},
            PipelineStatus.PAUSED: {PipelineStatus.ACTIVE, PipelineStatus.ARCHIVED},
            PipelineStatus.ARCHIVED: set(),
        }

        allowed = valid_transitions.get(pipeline.status, set())
        if new_status not in allowed:
            allowed_str = ", ".join(s.value for s in sorted(allowed, key=lambda s: s.value))
            return {
                "success": False,
                "error": f"Cannot transition from '{pipeline.status.value}' to '{new_status.value}'.",
                "suggestion": (
                    f"Valid transitions from '{pipeline.status.value}': {allowed_str}."
                    if allowed_str
                    else "Archived pipelines cannot be transitioned. Create a new one."
                ),
            }

        update_fields["status"] = new_status

    if not update_fields:
        return {
            "success": False,
            "error": "No fields provided for update.",
            "suggestion": "Pass at least one of: name, description, steps, status.",
        }

    updated = store.update(pipeline_id, **update_fields)

    return {
        "success": True,
        "pipeline": _pipeline_to_dict(updated),
        "suggestion": f"Pipeline updated successfully. Current status: {updated.status.value}.",
    }


def delete_pipeline(
    pipeline_id: str,
) -> dict[str, Any]:
    """Soft-delete (archive) a pipeline.

    Archived pipelines remain queryable but cannot be executed or modified.
    This is a non-destructive operation.

    Args:
        pipeline_id: UUID of the pipeline to archive.

    Returns:
        Dict confirming deletion or error details.
    """
    store = get_pipeline_store()
    pipeline = store.get(pipeline_id)

    if pipeline is None:
        return {
            "success": False,
            "error": f"Pipeline '{pipeline_id}' not found.",
            "suggestion": "Use list_pipelines to find available pipeline IDs.",
        }

    if pipeline.status == PipelineStatus.ARCHIVED:
        return {
            "success": False,
            "error": f"Pipeline '{pipeline_id}' is already archived.",
            "suggestion": "No action needed. The pipeline is already soft-deleted.",
        }

    previous_status = pipeline.status.value
    deleted = store.delete(pipeline_id)

    return {
        "success": True,
        "pipeline_id": deleted.id,
        "pipeline_name": deleted.name,
        "previous_status": previous_status,
        "current_status": deleted.status.value,
        "suggestion": "Pipeline archived. It can still be queried with include_archived=True.",
    }


# ---------------------------------------------------------------------------
# Tool registration helper
# ---------------------------------------------------------------------------

PLANNER_TOOLS = {
    "create_pipeline": create_pipeline,
    "validate_pipeline": validate_pipeline,
    "estimate_duration": estimate_duration,
    "list_pipelines": list_pipelines,
    "get_pipeline": get_pipeline,
    "update_pipeline": update_pipeline,
    "delete_pipeline": delete_pipeline,
}
"""All 7 planner tools for MCP registration."""
