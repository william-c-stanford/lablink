"""Search service — Elasticsearch query building, faceted search, and filters.

Provides an abstraction over Elasticsearch for indexed instrument data.
When ``use_elasticsearch`` is False (default in dev/test), uses an
in-memory mock index so the app works without Docker.

Key features:
- Full-text search across parsed instrument data
- Faceted search with aggregations (by instrument type, project, date)
- Filters by date range, instrument type, project, organization
- Index management (create, delete, reindex)
- Bulk indexing from ParsedData records

Usage::

    from lablink.services.search_service import SearchService

    search_svc = SearchService(settings)
    results = await search_svc.search(
        org_id=org_id,
        query="absorbance > 0.5",
        instrument_type="spectrophotometer",
    )
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypedDict

from lablink.config import Settings, get_settings

logger = logging.getLogger("lablink.search")

# Index name template
INDEX_NAME = "lablink-data-{org_id}"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class SearchHit(TypedDict):
    """A single search result."""

    id: str
    upload_id: str
    instrument_type: str
    measurement_type: str | None
    filename: str
    score: float
    highlights: dict[str, list[str]]
    metadata: dict[str, Any]
    created_at: str


class FacetBucket(TypedDict):
    """A facet aggregation bucket."""

    key: str
    doc_count: int


class SearchFacets(TypedDict, total=False):
    """Faceted aggregation results."""

    instrument_types: list[FacetBucket]
    measurement_types: list[FacetBucket]
    date_histogram: list[FacetBucket]


class SearchResult(TypedDict):
    """Complete search response."""

    hits: list[SearchHit]
    total: int
    facets: SearchFacets
    query_time_ms: float


# ---------------------------------------------------------------------------
# In-memory mock index (for dev/test without Elasticsearch)
# ---------------------------------------------------------------------------


@dataclass
class _InMemoryIndex:
    """Simple in-memory search index for dev/test.

    Supports basic substring matching and facet counting.
    Not intended for production use.
    """

    documents: dict[str, dict[str, Any]] = field(default_factory=dict)

    def index_document(self, doc_id: str, document: dict[str, Any]) -> None:
        """Add or update a document in the index."""
        self.documents[doc_id] = {
            **document,
            "_indexed_at": datetime.now(timezone.utc).isoformat(),
        }

    def delete_document(self, doc_id: str) -> bool:
        """Remove a document from the index. Returns True if found."""
        return self.documents.pop(doc_id, None) is not None

    def search(
        self,
        *,
        org_id: str | None = None,
        query: str | None = None,
        instrument_type: str | None = None,
        measurement_type: str | None = None,
        project_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search the in-memory index with basic filtering.

        Returns:
            Tuple of (matched documents, total count).
        """
        results = []

        for doc_id, doc in self.documents.items():
            # Org filter
            if org_id and doc.get("organization_id") != org_id:
                continue

            # Instrument type filter
            if instrument_type and doc.get("instrument_type") != instrument_type:
                continue

            # Measurement type filter
            if measurement_type and doc.get("measurement_type") != measurement_type:
                continue

            # Project filter
            if project_id and doc.get("project_id") != project_id:
                continue

            # Date range filter
            doc_date = doc.get("created_at")
            if doc_date and isinstance(doc_date, str):
                try:
                    dt = datetime.fromisoformat(doc_date)
                    if date_from and dt < date_from:
                        continue
                    if date_to and dt > date_to:
                        continue
                except (ValueError, TypeError):
                    pass

            # Full-text query (simple substring matching)
            if query:
                query_lower = query.lower()
                searchable = " ".join(
                    str(v) for v in doc.values() if isinstance(v, (str, int, float))
                ).lower()
                if query_lower not in searchable:
                    continue

            results.append({"_id": doc_id, "_score": 1.0, **doc})

        total = len(results)
        page = results[offset : offset + limit]
        return page, total

    def get_facets(
        self,
        *,
        org_id: str | None = None,
    ) -> SearchFacets:
        """Compute facets for the indexed documents."""
        type_counts: dict[str, int] = {}
        measurement_counts: dict[str, int] = {}

        for doc in self.documents.values():
            if org_id and doc.get("organization_id") != org_id:
                continue

            itype = doc.get("instrument_type", "unknown")
            type_counts[itype] = type_counts.get(itype, 0) + 1

            mtype = doc.get("measurement_type")
            if mtype:
                measurement_counts[mtype] = measurement_counts.get(mtype, 0) + 1

        return SearchFacets(
            instrument_types=[
                FacetBucket(key=k, doc_count=v)
                for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
            ],
            measurement_types=[
                FacetBucket(key=k, doc_count=v)
                for k, v in sorted(measurement_counts.items(), key=lambda x: -x[1])
            ],
        )

    def clear(self) -> None:
        """Remove all documents from the index."""
        self.documents.clear()

    @property
    def count(self) -> int:
        """Number of documents in the index."""
        return len(self.documents)


# Singleton mock index for dev/test
_mock_index: _InMemoryIndex | None = None


def _get_mock_index() -> _InMemoryIndex:
    """Get or create the singleton mock index."""
    global _mock_index
    if _mock_index is None:
        _mock_index = _InMemoryIndex()
    return _mock_index


def reset_mock_index() -> None:
    """Reset the mock index (for testing)."""
    global _mock_index
    _mock_index = None


# ---------------------------------------------------------------------------
# Elasticsearch query builders
# ---------------------------------------------------------------------------


def build_search_query(
    *,
    org_id: str,
    query: str | None = None,
    instrument_type: str | None = None,
    measurement_type: str | None = None,
    project_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Build an Elasticsearch query DSL dict.

    Constructs a bool query with:
    - must: multi_match on query text (if provided)
    - filter: term/range filters for scoping

    Returns:
        Elasticsearch query body dict.
    """
    filters: list[dict[str, Any]] = [
        {"term": {"organization_id": org_id}},
    ]

    if instrument_type:
        filters.append({"term": {"instrument_type": instrument_type}})

    if measurement_type:
        filters.append({"term": {"measurement_type": measurement_type}})

    if project_id:
        filters.append({"term": {"project_id": project_id}})

    if date_from or date_to:
        date_range: dict[str, str] = {}
        if date_from:
            date_range["gte"] = date_from.isoformat()
        if date_to:
            date_range["lte"] = date_to.isoformat()
        filters.append({"range": {"created_at": date_range}})

    # Build bool query
    bool_query: dict[str, Any] = {"filter": filters}

    if query:
        bool_query["must"] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "filename^3",
                        "instrument_type^2",
                        "measurement_type^2",
                        "metadata.*",
                        "data_summary.*",
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]
    else:
        bool_query["must"] = [{"match_all": {}}]

    return {
        "query": {"bool": bool_query},
        "highlight": {
            "fields": {
                "filename": {},
                "instrument_type": {},
                "metadata.*": {},
            }
        },
        "aggs": {
            "instrument_types": {
                "terms": {"field": "instrument_type", "size": 20}
            },
            "measurement_types": {
                "terms": {"field": "measurement_type", "size": 20}
            },
            "uploads_over_time": {
                "date_histogram": {
                    "field": "created_at",
                    "calendar_interval": "day",
                }
            },
        },
    }


def build_index_mapping() -> dict[str, Any]:
    """Return the Elasticsearch index mapping for parsed data.

    Defines field types, analyzers, and keyword sub-fields.
    """
    return {
        "mappings": {
            "properties": {
                "organization_id": {"type": "keyword"},
                "upload_id": {"type": "keyword"},
                "project_id": {"type": "keyword"},
                "instrument_type": {"type": "keyword"},
                "measurement_type": {"type": "keyword"},
                "parser_version": {"type": "keyword"},
                "filename": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "sample_count": {"type": "integer"},
                "data_summary": {"type": "object", "enabled": True},
                "measurements": {"type": "nested", "enabled": False},
                "metadata": {"type": "object", "enabled": True},
                "created_at": {"type": "date"},
                "indexed_at": {"type": "date"},
            }
        },
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
    }


# ---------------------------------------------------------------------------
# SearchService
# ---------------------------------------------------------------------------


class SearchService:
    """High-level search service abstracting Elasticsearch operations.

    When ``use_elasticsearch`` is False (dev/test), falls back to an
    in-memory mock index.  In production, uses the real Elasticsearch
    cluster.

    Usage::

        svc = SearchService()  # uses get_settings()
        await svc.index_parsed_data(parsed_data_dict)
        results = await svc.search(org_id=..., query="absorbance")
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._use_es = self._settings.use_elasticsearch
        self._es_url = self._settings.elasticsearch_url
        self._es_client: Any | None = None  # Lazy-init ES client

    @property
    def _mock(self) -> _InMemoryIndex:
        """Access the in-memory mock index."""
        return _get_mock_index()

    async def _get_es_client(self) -> Any:
        """Lazily create the Elasticsearch async client.

        Only called when ``use_elasticsearch`` is True.
        """
        if self._es_client is None:
            try:
                from elasticsearch import AsyncElasticsearch

                self._es_client = AsyncElasticsearch(
                    [self._es_url],
                    request_timeout=30,
                )
            except ImportError:
                logger.warning(
                    "elasticsearch-py not installed, falling back to mock index"
                )
                self._use_es = False
        return self._es_client

    def _index_name(self, org_id: str | uuid.UUID) -> str:
        """Return the index name for an organization."""
        return INDEX_NAME.format(org_id=str(org_id))

    # --- Index management ---

    async def ensure_index(self, org_id: str | uuid.UUID) -> None:
        """Create the index for an organization if it doesn't exist."""
        if not self._use_es:
            return  # Mock index needs no setup

        client = await self._get_es_client()
        if client is None:
            return

        index_name = self._index_name(org_id)
        try:
            exists = await client.indices.exists(index=index_name)
            if not exists:
                mapping = build_index_mapping()
                await client.indices.create(
                    index=index_name,
                    body=mapping,
                )
                logger.info("Created index: %s", index_name)
        except Exception:
            logger.exception("Failed to create index: %s", index_name)

    async def delete_index(self, org_id: str | uuid.UUID) -> None:
        """Delete the index for an organization."""
        if not self._use_es:
            self._mock.clear()
            return

        client = await self._get_es_client()
        if client is None:
            return

        index_name = self._index_name(org_id)
        try:
            await client.indices.delete(index=index_name, ignore=[404])
            logger.info("Deleted index: %s", index_name)
        except Exception:
            logger.exception("Failed to delete index: %s", index_name)

    # --- Document operations ---

    async def index_document(
        self,
        *,
        org_id: str | uuid.UUID,
        doc_id: str,
        document: dict[str, Any],
    ) -> None:
        """Index a single document (parsed data record).

        Args:
            org_id: Organization UUID for index routing.
            doc_id: Unique document ID (typically ParsedData.id).
            document: The document body to index.
        """
        if not self._use_es:
            self._mock.index_document(doc_id, {
                **document,
                "organization_id": str(org_id),
            })
            return

        client = await self._get_es_client()
        if client is None:
            return

        index_name = self._index_name(org_id)
        try:
            await client.index(
                index=index_name,
                id=doc_id,
                body=document,
                refresh="wait_for",
            )
        except Exception:
            logger.exception("Failed to index document %s", doc_id)

    async def delete_document(
        self,
        *,
        org_id: str | uuid.UUID,
        doc_id: str,
    ) -> None:
        """Delete a single document from the index."""
        if not self._use_es:
            self._mock.delete_document(doc_id)
            return

        client = await self._get_es_client()
        if client is None:
            return

        index_name = self._index_name(org_id)
        try:
            await client.delete(
                index=index_name,
                id=doc_id,
                ignore=[404],
            )
        except Exception:
            logger.exception("Failed to delete document %s", doc_id)

    async def bulk_index(
        self,
        *,
        org_id: str | uuid.UUID,
        documents: list[tuple[str, dict[str, Any]]],
    ) -> int:
        """Bulk index multiple documents.

        Args:
            org_id: Organization UUID.
            documents: List of (doc_id, document_body) tuples.

        Returns:
            Number of successfully indexed documents.
        """
        if not documents:
            return 0

        if not self._use_es:
            for doc_id, doc in documents:
                self._mock.index_document(doc_id, {
                    **doc,
                    "organization_id": str(org_id),
                })
            return len(documents)

        client = await self._get_es_client()
        if client is None:
            return 0

        index_name = self._index_name(org_id)
        actions = []
        for doc_id, doc in documents:
            actions.append({"index": {"_index": index_name, "_id": doc_id}})
            actions.append(doc)

        try:
            resp = await client.bulk(body=actions, refresh="wait_for")
            errors = resp.get("errors", False)
            if errors:
                error_count = sum(
                    1 for item in resp["items"] if "error" in item.get("index", {})
                )
                logger.warning("Bulk index had %d errors", error_count)
                return len(documents) - error_count
            return len(documents)
        except Exception:
            logger.exception("Bulk index failed for %s", index_name)
            return 0

    # --- Search ---

    async def search(
        self,
        *,
        org_id: str | uuid.UUID,
        query: str | None = None,
        instrument_type: str | None = None,
        measurement_type: str | None = None,
        project_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResult:
        """Execute a search query against the index.

        Args:
            org_id: Organization UUID (required for scoping).
            query: Free-text search query.
            instrument_type: Filter by instrument type.
            measurement_type: Filter by measurement type.
            project_id: Filter by project.
            date_from: Start of date range filter.
            date_to: End of date range filter.
            page: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            SearchResult with hits, total count, facets, and query time.
        """
        import time

        start = time.perf_counter()
        page_size = min(max(page_size, 1), 100)
        page = max(page, 1)
        offset = (page - 1) * page_size
        org_str = str(org_id)

        if not self._use_es:
            docs, total = self._mock.search(
                org_id=org_str,
                query=query,
                instrument_type=instrument_type,
                measurement_type=measurement_type,
                project_id=project_id,
                date_from=date_from,
                date_to=date_to,
                offset=offset,
                limit=page_size,
            )
            facets = self._mock.get_facets(org_id=org_str)
            elapsed = (time.perf_counter() - start) * 1000

            hits: list[SearchHit] = []
            for doc in docs:
                hits.append(
                    SearchHit(
                        id=doc.get("_id", ""),
                        upload_id=doc.get("upload_id", ""),
                        instrument_type=doc.get("instrument_type", ""),
                        measurement_type=doc.get("measurement_type"),
                        filename=doc.get("filename", ""),
                        score=doc.get("_score", 1.0),
                        highlights={},
                        metadata=doc.get("metadata", {}),
                        created_at=doc.get("created_at", ""),
                    )
                )

            return SearchResult(
                hits=hits,
                total=total,
                facets=facets,
                query_time_ms=round(elapsed, 2),
            )

        # Real Elasticsearch query
        client = await self._get_es_client()
        if client is None:
            elapsed = (time.perf_counter() - start) * 1000
            return SearchResult(
                hits=[], total=0, facets=SearchFacets(), query_time_ms=round(elapsed, 2)
            )

        index_name = self._index_name(org_id)
        query_body = build_search_query(
            org_id=org_str,
            query=query,
            instrument_type=instrument_type,
            measurement_type=measurement_type,
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
        )
        query_body["from"] = offset
        query_body["size"] = page_size

        try:
            resp = await client.search(index=index_name, body=query_body)
            elapsed = (time.perf_counter() - start) * 1000

            hits = []
            for hit in resp["hits"]["hits"]:
                source = hit["_source"]
                highlights = hit.get("highlight", {})
                hits.append(
                    SearchHit(
                        id=hit["_id"],
                        upload_id=source.get("upload_id", ""),
                        instrument_type=source.get("instrument_type", ""),
                        measurement_type=source.get("measurement_type"),
                        filename=source.get("filename", ""),
                        score=hit.get("_score", 0.0),
                        highlights=highlights,
                        metadata=source.get("metadata", {}),
                        created_at=source.get("created_at", ""),
                    )
                )

            # Parse aggregations
            aggs = resp.get("aggregations", {})
            facets = SearchFacets(
                instrument_types=[
                    FacetBucket(key=b["key"], doc_count=b["doc_count"])
                    for b in aggs.get("instrument_types", {}).get("buckets", [])
                ],
                measurement_types=[
                    FacetBucket(key=b["key"], doc_count=b["doc_count"])
                    for b in aggs.get("measurement_types", {}).get("buckets", [])
                ],
                date_histogram=[
                    FacetBucket(key=b["key_as_string"], doc_count=b["doc_count"])
                    for b in aggs.get("uploads_over_time", {}).get("buckets", [])
                    if b["doc_count"] > 0
                ],
            )

            total = resp["hits"]["total"]
            if isinstance(total, dict):
                total = total.get("value", 0)

            return SearchResult(
                hits=hits,
                total=total,
                facets=facets,
                query_time_ms=round(elapsed, 2),
            )
        except Exception:
            logger.exception("Search failed on index %s", index_name)
            elapsed = (time.perf_counter() - start) * 1000
            return SearchResult(
                hits=[], total=0, facets=SearchFacets(), query_time_ms=round(elapsed, 2)
            )

    # --- Facets only ---

    async def get_facets(
        self,
        *,
        org_id: str | uuid.UUID,
    ) -> SearchFacets:
        """Get facet aggregations without a search query.

        Useful for populating filter dropdowns in the UI.
        """
        if not self._use_es:
            return self._mock.get_facets(org_id=str(org_id))

        # For real ES, use a size=0 search with just aggregations
        result = await self.search(
            org_id=org_id,
            page_size=1,  # Don't need actual results
        )
        return result["facets"]

    # --- Cleanup ---

    async def close(self) -> None:
        """Close the Elasticsearch client connection."""
        if self._es_client is not None:
            await self._es_client.close()
            self._es_client = None


# ---------------------------------------------------------------------------
# Module-level convenience (singleton-ish)
# ---------------------------------------------------------------------------

_search_service: SearchService | None = None


def get_search_service(settings: Settings | None = None) -> SearchService:
    """Get or create a singleton SearchService instance."""
    global _search_service
    if _search_service is None:
        _search_service = SearchService(settings)
    return _search_service


def reset_search_service() -> None:
    """Reset the singleton (for testing)."""
    global _search_service
    _search_service = None
    reset_mock_index()
