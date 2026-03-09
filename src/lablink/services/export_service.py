"""Export service — data export in multiple formats with async job management.

Supports exporting parsed instrument data as CSV, JSON, XLSX, and PDF.
Exports are tracked as jobs with status lifecycle (pending → processing →
completed / failed) and produce download URLs (S3 presigned or local
filesystem paths).

Usage::

    from lablink.services.export_service import ExportService

    svc = ExportService(storage_backend="local", local_storage_path="./storage")
    job = await svc.create_export(db, org_id=..., format="csv", upload_ids=[...])
    job = await svc.get_export(db, job.id)
    # job.download_url is set once status == "completed"
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lablink.models import ParsedData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Pydantic schemas (service-level, not HTTP-level)
# ---------------------------------------------------------------------------


class ExportFormat(str, Enum):
    """Supported export formats."""

    csv = "csv"
    json = "json"
    xlsx = "xlsx"
    pdf = "pdf"


class ExportStatus(str, Enum):
    """Export job lifecycle states."""

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ExportJob(BaseModel):
    """In-memory representation of an export job.

    In a production deployment this would be persisted to the database.
    For the MVP (sync task fallback), jobs are executed inline and this
    schema tracks the result.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: str
    format: ExportFormat
    status: ExportStatus = ExportStatus.pending
    upload_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    filename: str | None = None
    download_url: str | None = None
    file_size_bytes: int | None = None
    record_count: int = 0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class ExportRequest(BaseModel):
    """Parameters for creating a new export."""

    format: ExportFormat
    upload_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    # filters may contain: instrument_type, project_id, date_from, date_to, etc.


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class ExportService:
    """Stateless service for creating and managing data exports.

    Parameters
    ----------
    storage_backend:
        ``"local"`` for filesystem (dev/test) or ``"s3"`` for S3.
    local_storage_path:
        Root directory for local exports.  Ignored when backend is ``"s3"``.
    s3_bucket:
        S3 bucket name.  Required when backend is ``"s3"``.
    """

    def __init__(
        self,
        storage_backend: str = "local",
        local_storage_path: str = "./storage",
        s3_bucket: str = "",
    ) -> None:
        self.storage_backend = storage_backend
        self.local_storage_path = local_storage_path
        self.s3_bucket = s3_bucket
        # In-memory job store (MVP sync fallback; production would use DB)
        self._jobs: dict[str, ExportJob] = {}

    @classmethod
    def from_settings(cls) -> ExportService:
        """Create an ExportService from application settings."""
        from lablink.config import get_settings

        settings = get_settings()
        return cls(
            storage_backend=settings.storage_backend,
            local_storage_path=settings.local_storage_path,
            s3_bucket=settings.s3_bucket,
        )

    # ── Job management ────────────────────────────────────────────────

    async def create_export(
        self,
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        request: ExportRequest,
    ) -> ExportJob:
        """Create and execute an export job (sync inline for MVP).

        Parameters
        ----------
        db:
            Async database session.
        organization_id:
            Owning organization UUID.
        request:
            Export parameters.

        Returns
        -------
        ExportJob
            The completed (or failed) job with download_url if successful.

        Raises
        ------
        ValueError
            If no upload IDs or filters are provided, or format is unsupported.
        """
        if not request.upload_ids and not request.filters:
            raise ValueError("Either upload_ids or filters must be provided for export")

        job = ExportJob(
            organization_id=str(organization_id),
            format=request.format,
            upload_ids=request.upload_ids,
            filters=request.filters,
        )
        self._jobs[job.id] = job

        # Execute inline (sync fallback — Celery would dispatch here)
        try:
            job.status = ExportStatus.processing
            await self._execute_export(db, job)
        except Exception as exc:
            logger.error("Export job %s failed: %s", job.id, exc)
            job.status = ExportStatus.failed
            job.error_message = str(exc)

        return job

    async def get_export(self, job_id: str) -> ExportJob | None:
        """Retrieve an export job by ID."""
        return self._jobs.get(job_id)

    async def list_exports(
        self,
        *,
        organization_id: uuid.UUID,
        status: ExportStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ExportJob], int]:
        """List export jobs for an organization.

        Returns
        -------
        tuple[list[ExportJob], int]
            (jobs, total_count)
        """
        org_str = str(organization_id)
        all_jobs = [
            j
            for j in self._jobs.values()
            if j.organization_id == org_str and (status is None or j.status == status)
        ]
        # Sort newest first
        all_jobs.sort(key=lambda j: j.created_at, reverse=True)
        total = len(all_jobs)
        start = (page - 1) * page_size
        return all_jobs[start : start + page_size], total

    # ── Export execution ──────────────────────────────────────────────

    async def _execute_export(self, db: AsyncSession, job: ExportJob) -> None:
        """Fetch data and write to the target format."""
        # Fetch parsed data
        records = await self._fetch_data(db, job)
        job.record_count = len(records)

        if not records:
            job.status = ExportStatus.completed
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = "No data matched the export criteria"
            return

        # Generate file content
        content, filename = await self._render(job.format, records, job.id)

        # Store the file
        download_url, file_size = await self._store_file(
            content, filename, str(job.organization_id)
        )

        job.filename = filename
        job.download_url = download_url
        job.file_size_bytes = file_size
        job.status = ExportStatus.completed
        job.completed_at = datetime.now(timezone.utc)

    async def _fetch_data(self, db: AsyncSession, job: ExportJob) -> list[dict[str, Any]]:
        """Query ParsedData records based on job parameters."""
        stmt = select(ParsedData).where(
            ParsedData.organization_id == uuid.UUID(job.organization_id)
        )

        if job.upload_ids:
            upload_uuids = [uuid.UUID(uid) for uid in job.upload_ids]
            stmt = stmt.where(ParsedData.upload_id.in_(upload_uuids))

        # Apply filters
        filters = job.filters
        if filters.get("instrument_type"):
            stmt = stmt.where(ParsedData.instrument_type == filters["instrument_type"])

        if filters.get("measurement_type"):
            stmt = stmt.where(ParsedData.measurement_type == filters["measurement_type"])

        result = await db.execute(stmt)
        parsed_rows = result.scalars().all()

        # Flatten to dicts
        records: list[dict[str, Any]] = []
        for row in parsed_rows:
            base = {
                "parsed_data_id": str(row.id),
                "upload_id": str(row.upload_id),
                "instrument_type": row.instrument_type,
                "parser_version": row.parser_version,
                "measurement_type": row.measurement_type,
                "sample_count": row.sample_count,
            }
            # Expand measurements into individual records
            for i, measurement in enumerate(row.measurements or []):
                record = {**base, "measurement_index": i}
                if isinstance(measurement, dict):
                    record.update(measurement)
                records.append(record)

        return records

    async def _render(
        self,
        fmt: ExportFormat,
        records: list[dict[str, Any]],
        job_id: str,
    ) -> tuple[bytes, str]:
        """Render records into the requested format.

        Returns
        -------
        tuple[bytes, str]
            (file_content, filename)
        """
        if fmt == ExportFormat.csv:
            return self._render_csv(records, job_id)
        elif fmt == ExportFormat.json:
            return self._render_json(records, job_id)
        elif fmt == ExportFormat.xlsx:
            return self._render_xlsx(records, job_id)
        elif fmt == ExportFormat.pdf:
            return self._render_pdf(records, job_id)
        else:
            raise ValueError(f"Unsupported export format: {fmt}")

    def _render_csv(self, records: list[dict[str, Any]], job_id: str) -> tuple[bytes, str]:
        """Render records as CSV."""
        if not records:
            return b"", f"export-{job_id}.csv"

        # Collect all keys across all records for consistent columns
        all_keys: list[str] = []
        seen: set[str] = set()
        for rec in records:
            for k in rec:
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            # Stringify nested objects for CSV
            flat = {}
            for k, v in rec.items():
                if isinstance(v, (dict, list)):
                    flat[k] = json.dumps(v, default=str)
                else:
                    flat[k] = v
            writer.writerow(flat)

        content = buf.getvalue().encode("utf-8")
        return content, f"export-{job_id}.csv"

    def _render_json(self, records: list[dict[str, Any]], job_id: str) -> tuple[bytes, str]:
        """Render records as JSON."""
        output = {
            "export_id": job_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(records),
            "records": records,
        }
        content = json.dumps(output, indent=2, default=str).encode("utf-8")
        return content, f"export-{job_id}.json"

    def _render_xlsx(self, records: list[dict[str, Any]], job_id: str) -> tuple[bytes, str]:
        """Render records as XLSX.

        Falls back to CSV if openpyxl is not installed.
        """
        try:
            import openpyxl

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Export"

            if not records:
                return b"", f"export-{job_id}.xlsx"

            # Headers
            all_keys = list(dict.fromkeys(k for rec in records for k in rec))
            ws.append(all_keys)

            # Data rows
            for rec in records:
                row = []
                for k in all_keys:
                    v = rec.get(k, "")
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v, default=str)
                    row.append(v)
                ws.append(row)

            buf = io.BytesIO()
            wb.save(buf)
            content = buf.getvalue()
            return content, f"export-{job_id}.xlsx"

        except ImportError:
            logger.warning("openpyxl not installed; falling back to CSV for XLSX export")
            content, _ = self._render_csv(records, job_id)
            return content, f"export-{job_id}.csv"

    def _render_pdf(self, records: list[dict[str, Any]], job_id: str) -> tuple[bytes, str]:
        """Render records as PDF.

        Falls back to JSON if no PDF library is available.
        PDF generation is best-effort for MVP.
        """
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter)

            if not records:
                doc.build([])
                return buf.getvalue(), f"export-{job_id}.pdf"

            all_keys = list(dict.fromkeys(k for rec in records for k in rec))
            table_data = [all_keys]
            for rec in records:
                row = [str(rec.get(k, ""))[:50] for k in all_keys]
                table_data.append(row)

            table = Table(table_data)
            doc.build([table])
            return buf.getvalue(), f"export-{job_id}.pdf"

        except ImportError:
            logger.warning("reportlab not installed; falling back to JSON for PDF export")
            return self._render_json(records, job_id)

    # ── Storage ───────────────────────────────────────────────────────

    async def _store_file(
        self,
        content: bytes,
        filename: str,
        organization_id: str,
    ) -> tuple[str, int]:
        """Store the export file and return (download_url, file_size).

        Uses local filesystem for dev/test, S3 for production.
        """
        file_size = len(content)

        if self.storage_backend == "s3":
            return await self._store_s3(content, filename, organization_id), file_size
        else:
            return await self._store_local(content, filename, organization_id), file_size

    async def _store_local(
        self,
        content: bytes,
        filename: str,
        organization_id: str,
    ) -> str:
        """Store file to local filesystem and return a file:// URL."""
        export_dir = Path(self.local_storage_path) / "exports" / organization_id
        export_dir.mkdir(parents=True, exist_ok=True)

        file_path = export_dir / filename
        file_path.write_bytes(content)

        return f"file://{file_path.resolve()}"

    async def _store_s3(
        self,
        content: bytes,
        filename: str,
        organization_id: str,
    ) -> str:
        """Store file to S3 and return a presigned download URL.

        Falls back to a mock S3 URL if boto3 is not available.
        """
        s3_key = f"exports/{organization_id}/{filename}"

        try:
            import boto3

            s3_client = boto3.client("s3")
            s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=content,
                ContentType=self._content_type_for(filename),
            )
            # Generate presigned URL (1 hour expiry)
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.s3_bucket, "Key": s3_key},
                ExpiresIn=3600,
            )
            return url

        except ImportError:
            logger.warning("boto3 not installed; returning mock S3 URL")
            return f"https://{self.s3_bucket}.s3.amazonaws.com/{s3_key}"

    @staticmethod
    def _content_type_for(filename: str) -> str:
        """Return MIME type based on file extension."""
        if filename.endswith(".csv"):
            return "text/csv"
        elif filename.endswith(".json"):
            return "application/json"
        elif filename.endswith(".xlsx"):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif filename.endswith(".pdf"):
            return "application/pdf"
        return "application/octet-stream"
