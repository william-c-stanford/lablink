# LabLink Framework Documentation Research

**Date**: March 5, 2026
**Purpose**: Comprehensive documentation and best practices for all frameworks/libraries used in the LabLink project.

---

## 1. FastAPI

### Version Information
- **Latest Stable**: 0.115.x (0.115.13 confirmed on PyPI); 0.128.0 also available
- **Python Requirement**: 3.9+ (Python 3.8 support removed)
- **Starlette Dependency**: >=0.46.0

### Key Imports
```python
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated
```

### Breaking Changes (2025-2026)
1. **Strict Content-Type checking** is now ON by default. JSON requests must have a valid `Content-Type: application/json` header. Disable with `strict_content_type=False` on the app if clients do not send proper headers.
2. **fastapi-slim removed** -- use `fastapi[standard]` or plain `fastapi`.
3. **Pydantic v1 deprecation warnings** added -- must use Pydantic v2.
4. **Starlette >=0.46.0** required for proper exception group unwrapping.

### Best Practices for Large Applications

**Project Structure** (Router-based):
```
app/
  main.py           # FastAPI() instance, middleware, startup/shutdown
  core/
    config.py       # Settings via Pydantic BaseSettings
    deps.py         # Shared dependencies (get_db, get_current_user)
  api/
    v1/
      router.py     # APIRouter aggregating all endpoint modules
      endpoints/
        experiments.py
        samples.py
        instruments.py
  models/           # SQLAlchemy models
  schemas/          # Pydantic request/response schemas
  services/         # Business logic layer
  tasks/            # Celery tasks
```

**Dependency Injection Pattern**:
```python
from typing import Annotated
from fastapi import Depends

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

DbDep = Annotated[AsyncSession, Depends(get_db)]

@router.get("/experiments/{id}")
async def get_experiment(id: int, db: DbDep):
    ...
```

**Background Tasks vs Celery**:
- Use `BackgroundTasks` for lightweight, fire-and-forget work (logging, simple notifications) that completes in <30s and does not need retries.
- Use **Celery** for: long-running tasks, tasks needing retry/failure handling, periodic/scheduled tasks, tasks requiring distributed execution across workers, anything requiring result tracking.

### Gotchas
- `async def` endpoints run on the main event loop; `def` (sync) endpoints run in a threadpool. Do not mix blocking I/O in `async def` endpoints.
- `BackgroundTasks` run after response is sent but still within the same process/request lifecycle -- if the process dies, the task is lost.
- Use `Annotated[type, Depends(dep)]` syntax (not the older `= Depends(dep)` parameter default).

---

## 2. Pydantic v2

### Version Information
- **Latest Stable**: 2.12.x (2.13.0b2 in beta as of Feb 2026)
- **Python Requirement**: 3.9+
- **Core**: Written in Rust (pydantic-core) for performance

### Key Imports
```python
from pydantic import BaseModel, Field, ConfigDict, model_validator
from pydantic import TypeAdapter
from typing import Generic, TypeVar
```

### Model Configuration (v2 style)
```python
from pydantic import BaseModel, ConfigDict

class Experiment(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,        # replaces orm_mode=True
        populate_by_name=True,       # replaces allow_population_by_field_name
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"name": "PCR Run"}]},
        strict=False,                # coerce types by default
    )
    name: str
    status: str = "pending"
```

### JSON Schema Generation
```python
import json
schema = Experiment.model_json_schema()
# Supports mode='validation' or mode='serialization'
schema = Experiment.model_json_schema(mode='serialization')
print(json.dumps(schema, indent=2))
```

### Generic Models for Response Envelopes
```python
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel

T = TypeVar("T")

class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int

# Usage in FastAPI:
@router.get("/experiments", response_model=PaginatedResponse[ExperimentOut])
async def list_experiments(...):
    ...

@router.get("/experiments/{id}", response_model=ResponseEnvelope[ExperimentOut])
async def get_experiment(...):
    ...
```

### Gotchas
- `model_config = ConfigDict(...)` replaces the inner `class Config:` (the old style still works but is discouraged).
- `from_attributes=True` replaces `orm_mode = True`.
- `model_dump()` replaces `.dict()`, `model_dump_json()` replaces `.json()`.
- `model_validate()` replaces `.parse_obj()`.
- Generic models generate proper OpenAPI schemas in FastAPI automatically.
- `TypeAdapter` is the v2 way to validate non-BaseModel types (e.g., `TypeAdapter(list[int]).validate_python([1,2,3])`).

---

## 3. Celery with Redis Broker

### Version Information
- **Latest Stable**: 5.6.2 (released January 4, 2026)
- **Python Requirement**: 3.9 - 3.13
- **Key Fixes in 5.6**: Memory leak fixes (especially Python 3.11+), security fixes for broker credentials in logs

### Key Imports
```python
from celery import Celery, shared_task
from celery.schedules import crontab
from celery.utils.log import get_task_logger
```

### Basic Setup with Redis
```python
# celery_app.py
from celery import Celery

app = Celery(
    "lablink",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                    # ack after task completes
    worker_prefetch_multiplier=1,           # fair scheduling
    broker_connection_retry_on_startup=True,
    result_expires=3600,                    # 1 hour
)
```

### Task Definition Pattern
```python
from celery import shared_task

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_experiment_data(self, experiment_id: int):
    try:
        # ... processing logic
        pass
    except TransientError as exc:
        raise self.retry(exc=exc)
```

### Periodic Tasks (Celery Beat)
```python
app.conf.beat_schedule = {
    "sync-instruments-every-hour": {
        "task": "lablink.tasks.sync_instruments",
        "schedule": crontab(minute=0),  # every hour
    },
    "cleanup-stale-sessions": {
        "task": "lablink.tasks.cleanup_sessions",
        "schedule": crontab(hour=2, minute=0),  # daily at 2 AM
    },
}
```

### Error Handling Pattern
```python
@shared_task(bind=True, autoretry_for=(ConnectionError, TimeoutError),
             retry_backoff=True, retry_backoff_max=600, max_retries=5)
def resilient_task(self, data):
    ...
```

### FastAPI Integration
```python
# In your FastAPI endpoint:
@router.post("/experiments/{id}/analyze")
async def trigger_analysis(id: int):
    task = process_experiment_data.delay(id)
    return {"task_id": task.id, "status": "queued"}

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    result = AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "result": result.result}
```

### Gotchas
- Use separate Redis databases for broker (db 0) and backend (db 1) to isolate concerns.
- `task_acks_late=True` + `worker_prefetch_multiplier=1` for reliable task processing.
- Redis is susceptible to data loss on abrupt termination -- for critical tasks, consider RabbitMQ.
- Start with `--concurrency=4` for general tasks; increase to 8-12 for I/O-bound; match CPU cores for CPU-bound.
- Large messages congest Redis -- keep payloads small, pass IDs not data blobs.

---

## 4. SQLAlchemy 2.0+ with Async Support

### Version Information
- **Latest Stable**: 2.0.44 (October 2025)
- **Beta**: 2.1.0b1 (January 21, 2026)
- **Python Requirement**: 2.0.x supports 3.7+; 2.1.x requires 3.10+

### Key Imports
```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncAttrs,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import select, func
```

### Async Engine and Session Setup (FastAPI Pattern)
```python
# database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/lablink",
    echo=False,
    pool_size=20,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    expire_on_commit=False,  # CRITICAL for async -- prevents lazy loads after commit
)
```

### FastAPI Dependency
```python
from typing import AsyncGenerator, Annotated
from fastapi import Depends

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

DbDep = Annotated[AsyncSession, Depends(get_db)]
```

### Model Definition (2.0 Mapped Style)
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    samples: Mapped[list["Sample"]] = relationship(back_populates="experiment", lazy="selectin")

class Sample(Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    experiment: Mapped["Experiment"] = relationship(back_populates="samples")
```

### 2.1 Changes to Watch
- **greenlet no longer auto-installs**: Use `pip install sqlalchemy[asyncio]` to get the asyncio dependency.
- **Python 3.10+ required** in 2.1.
- **Free-threaded Python** support added.
- Per-session execution options now supported in constructors.

### Gotchas
- **Always use `expire_on_commit=False`** with async sessions to avoid `MissingGreenlet` errors when accessing attributes after commit.
- Use `lazy="selectin"` or `lazy="joined"` for relationships in async -- `lazy="select"` (default) triggers implicit I/O which fails in async context.
- Use `select()` style queries (not the legacy `session.query()`) for 2.0 compatibility.
- For `relationship()` in async, use `await session.execute(select(...).options(selectinload(Model.relation)))` or set `lazy="selectin"` on the relationship.

---

## 5. Elasticsearch Python Client

### Version Information
- **Latest Stable**: 9.2.1 (December 23, 2025); 9.0.5 also available on the 9.0.x line
- **Requires**: Elasticsearch 9.x server (will NOT work with ES 8.x)
- **Async Support**: Built-in via `AsyncElasticsearch` (requires `aiohttp`)

### Key Imports
```python
from elasticsearch import Elasticsearch, AsyncElasticsearch
from elasticsearch.helpers import bulk, async_bulk, async_scan
```

### Installation
```bash
pip install elasticsearch[async]  # includes aiohttp for async support
```

### Async Client Pattern
```python
from elasticsearch import AsyncElasticsearch

es = AsyncElasticsearch(
    hosts=["https://localhost:9200"],
    api_key="your-api-key",
    verify_certs=True,
)

# Index a document
await es.index(index="experiments", id="1", document={"name": "PCR Run", "status": "complete"})

# Search
resp = await es.search(index="experiments", query={"match": {"name": "PCR"}})

# Always close when done
await es.close()
```

### Index Management Pattern
```python
async def ensure_index(es: AsyncElasticsearch, index_name: str, mappings: dict):
    if not await es.indices.exists(index=index_name):
        await es.indices.create(
            index=index_name,
            mappings=mappings,
            settings={
                "number_of_shards": 1,
                "number_of_replicas": 1,
            },
        )

# Example mappings for lab data
experiment_mappings = {
    "properties": {
        "name": {"type": "text", "analyzer": "standard"},
        "status": {"type": "keyword"},
        "created_at": {"type": "date"},
        "parameters": {"type": "nested"},
        "results_vector": {"type": "dense_vector", "dims": 768},
    }
}
```

### Bulk Indexing
```python
from elasticsearch.helpers import async_bulk

async def index_experiments(es, experiments):
    actions = [
        {
            "_index": "experiments",
            "_id": exp.id,
            "_source": exp.to_dict(),
        }
        for exp in experiments
    ]
    success, errors = await async_bulk(es, actions)
    return success, errors
```

### Breaking Changes in 9.x
- Removed deprecated `timeout`, `randomize_hosts`, `host_info_callback`, `sniffer_timeout`, `sniff_on_connection_fail`, `maxsize` from `Elasticsearch.__init__()`.
- DSL module in 9.2.0 includes `exclude_vectors` option in all search requests (requires ES 9.1.0+).
- Must upgrade ES server to 9.x before using client 9.x.

### Gotchas
- The old `elasticsearch-async` package is deprecated -- use the built-in `AsyncElasticsearch` from the main `elasticsearch` package.
- Always close the client connection (use context manager or explicit `await es.close()`).
- For FastAPI, create the client in a lifespan handler and close on shutdown.

---

## 6. FastMCP

### Version Information
- **Latest Stable**: 3.1.0 (released March 3, 2026)
- **Python Requirement**: 3.10+
- **Architecture**: Provider-based (components, providers, transforms)

### Key Imports
```python
from fastmcp import FastMCP
from fastmcp.server import Context
```

### Basic MCP Server with Tool Definition
```python
from fastmcp import FastMCP

mcp = FastMCP("LabLink MCP Server")

@mcp.tool
def search_experiments(query: str, limit: int = 10) -> list[dict]:
    """Search for experiments by name or parameters."""
    # Implementation here
    return results

@mcp.tool
def get_experiment_status(experiment_id: int) -> dict:
    """Get the current status of an experiment."""
    return {"id": experiment_id, "status": "running"}

@mcp.resource("experiment://{experiment_id}")
def get_experiment_resource(experiment_id: int) -> str:
    """Retrieve full experiment data as a resource."""
    return json.dumps(experiment_data)

if __name__ == "__main__":
    mcp.run()
```

### FastAPI Integration (Key Pattern)
```python
from fastapi import FastAPI
from fastmcp import FastMCP

# Option 1: Generate MCP server from existing FastAPI app
fastapi_app = FastAPI()

@fastapi_app.get("/experiments")
async def list_experiments():
    return [...]

@fastapi_app.post("/experiments")
async def create_experiment(data: ExperimentCreate):
    return {...}

# Convert FastAPI routes to MCP tools
mcp = FastMCP.from_fastapi(app=fastapi_app)

# Option 2: Serve both FastAPI and MCP from same app
mcp_asgi = mcp.http_app()
combined = FastAPI()
combined.mount("/mcp", mcp_asgi)
combined.mount("/", fastapi_app)
```

### FastMCP 3.0 Architecture (Providers, Transforms)
```python
from fastmcp import FastMCP
from fastmcp.server import Context

mcp = FastMCP("LabLink")

# Tool with context for logging/progress
@mcp.tool
async def analyze_data(ctx: Context, experiment_id: int) -> dict:
    """Run analysis on experiment data."""
    await ctx.report_progress(0, 100)
    # ... processing ...
    await ctx.report_progress(100, 100)
    return {"result": "complete"}

# Versioned tools
@mcp.tool(version="2.0")
def search_experiments_v2(query: str, filters: dict = {}) -> list:
    """Enhanced search with filters (v2)."""
    ...
```

### FastMCP 3.1 Code Mode
- Servers can find and execute code on behalf of agents without clients knowing what tools exist.
- CLI tools: `fastmcp list` and `fastmcp call` for querying and invoking tools from terminal.

### Gotchas
- FastMCP 3.0 is a significant architectural change from 2.x -- the provider/transform model is new.
- `FastMCP.from_fastapi()` converts all routes to tools by default; use `RouteMap` to customize which endpoints become tools vs resources.
- Tool functions must have type hints and docstrings -- these are used to generate the MCP schema.
- The `Context` parameter is injected automatically; do not include it in the tool's schema.

---

## 7. Plotly.js with React

### Version Information
- **Plotly.js Latest**: 3.4.0 (February 2026)
- **react-plotly.js**: Wrapper component for React
- **Built on**: d3.js and stack.gl

### Installation
```bash
npm install react-plotly.js plotly.js
# Or for smaller bundle:
npm install react-plotly.js plotly.js-basic-dist
```

### Key Imports
```javascript
import Plot from 'react-plotly.js';
// Or for custom bundle:
import Plotly from 'plotly.js-basic-dist';
import createPlotlyComponent from 'react-plotly.js/factory';
const Plot = createPlotlyComponent(Plotly);
```

### Basic Usage Pattern (Scientific Data)
```jsx
function ExperimentPlot({ data }) {
  return (
    <Plot
      data={[
        {
          x: data.wavelengths,
          y: data.absorbance,
          type: 'scatter',
          mode: 'lines+markers',
          name: 'Absorbance',
          marker: { color: '#1f77b4' },
        },
        {
          x: data.wavelengths,
          y: data.fluorescence,
          type: 'scatter',
          mode: 'lines',
          name: 'Fluorescence',
          yaxis: 'y2',
          marker: { color: '#ff7f0e' },
        },
      ]}
      layout={{
        title: 'Spectral Analysis',
        xaxis: { title: 'Wavelength (nm)' },
        yaxis: { title: 'Absorbance (AU)' },
        yaxis2: {
          title: 'Fluorescence (RFU)',
          overlaying: 'y',
          side: 'right',
        },
        autosize: true,
      }}
      config={{
        responsive: true,
        displayModeBar: true,
        toImageButtonOptions: {
          format: 'svg',
          filename: 'experiment_plot',
        },
      }}
      useResizeHandler={true}
      style={{ width: '100%', height: '100%' }}
    />
  );
}
```

### Scientific Chart Types Available
- **scatter / scattergl**: XY plots with WebGL acceleration for large datasets
- **heatmap / heatmapgl**: For plate reader data, correlation matrices
- **scatter3d / surface**: 3D parameter space visualization
- **histogram / histogram2d**: Distribution analysis
- **contour**: Contour plots for response surfaces
- **box / violin**: Statistical distributions

### Performance Pattern for Large Datasets
```jsx
// Use scattergl for >10k points
<Plot
  data={[{
    x: largeArray,
    y: largeArray2,
    type: 'scattergl',  // WebGL-accelerated
    mode: 'markers',
  }]}
/>
```

### Recent Updates (2025-2026)
- Extended SI formatting for tick exponents (femto, pico, atto prefixes) -- useful for scientific data.
- Plotly.js 3.x is the current major version.

### Gotchas
- Default bundle is large (~3MB). Use partial bundles (`plotly.js-basic-dist`, `plotly.js-cartesian-dist`) for smaller builds.
- Use `useResizeHandler={true}` + `style={{ width: '100%', height: '100%' }}` for responsive charts.
- `scattergl` is significantly faster than `scatter` for large datasets but has fewer styling options.
- Wrap `Plot` in `React.memo` or use `revision` prop to control re-renders.

---

## 8. Go fsnotify

### Version Information
- **Latest Stable**: v1.9.0 (released April 4, 2025)
- **Go Requirement**: Go 1.17+
- **No v2 release** -- still on v1.x line

### Key Imports
```go
import "github.com/fsnotify/fsnotify"
```

### Basic File Watching Pattern
```go
package main

import (
    "log"
    "github.com/fsnotify/fsnotify"
)

func main() {
    watcher, err := fsnotify.NewWatcher()
    if err != nil {
        log.Fatal(err)
    }
    defer watcher.Close()

    go func() {
        for {
            select {
            case event, ok := <-watcher.Events:
                if !ok {
                    return
                }
                if event.Has(fsnotify.Write) {
                    log.Println("Modified file:", event.Name)
                }
                if event.Has(fsnotify.Create) {
                    log.Println("Created file:", event.Name)
                }
            case err, ok := <-watcher.Errors:
                if !ok {
                    return
                }
                log.Println("Error:", err)
            }
        }
    }()

    // Watch a directory (NOT recursive)
    err = watcher.Add("/path/to/lab/data")
    if err != nil {
        log.Fatal(err)
    }

    // Block main goroutine
    <-make(chan struct{})
}
```

### Cross-Platform Desktop Agent Pattern
```go
// Recursive directory watching (manual implementation)
func watchRecursive(watcher *fsnotify.Watcher, root string) error {
    return filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
        if err != nil {
            return err
        }
        if info.IsDir() {
            return watcher.Add(path)
        }
        return nil
    })
}

// Handle new directories being created
case event := <-watcher.Events:
    if event.Has(fsnotify.Create) {
        info, err := os.Stat(event.Name)
        if err == nil && info.IsDir() {
            watcher.Add(event.Name)  // Watch new subdirectories
        }
    }
```

### Event Types
- `fsnotify.Create` -- file/directory created
- `fsnotify.Write` -- file modified
- `fsnotify.Remove` -- file/directory removed
- `fsnotify.Rename` -- file/directory renamed
- `fsnotify.Chmod` -- file attributes changed

### Gotchas
- **Not recursive** -- you must manually walk directories and add watches for each subdirectory.
- **NFS/SMB not supported** -- network filesystems do not provide file-level notifications.
- `/proc` and `/sys` virtual filesystems are not supported.
- **Watch parent directories**, not individual files. Filter by `event.Name` for specific files.
- On macOS, rename events may fire differently than on Linux. Test cross-platform behavior.
- Debounce rapid events (editors often create temp files and rename) -- use a timer to batch events.

---

## 9. Terraform for AWS ECS/Fargate

### Version Information
- **Terraform**: 1.x (use >=1.5 for latest features)
- **AWS Provider**: Use `hashicorp/aws` >= 5.x

### Core Resource Pattern
```hcl
# ecs.tf
resource "aws_ecs_cluster" "lablink" {
  name = "lablink-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "lablink-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = "${aws_ecr_repository.api.repository_url}:latest"
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "lablink-api"
  cluster         = aws_ecs_cluster.lablink.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnets
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
}
```

### ALB Configuration
```hcl
resource "aws_lb" "main" {
  name               = "lablink-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnets
}

resource "aws_lb_target_group" "api" {
  name        = "lablink-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}
```

### Fargate Spot for Cost Savings
```hcl
resource "aws_ecs_service" "worker" {
  # ... other config ...

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 70
  }
  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 30
    base              = 1  # at least 1 on-demand task
  }
}
```

### Best Practices (2025-2026)
- Use **separate task definitions** for API server and Celery workers.
- Use **Fargate Spot** (up to 70% savings) for Celery workers; keep API on regular Fargate.
- Build Docker images for `linux/amd64` on Apple Silicon: `docker buildx build --platform linux/amd64`.
- Use **ECR** for container images with lifecycle policies to prune old images.
- Use **AWS Secrets Manager** or **SSM Parameter Store** for secrets, not environment variables.
- Enable **Container Insights** for monitoring.

### Gotchas
- Fargate tasks in private subnets need a NAT Gateway for outbound internet (ECR pulls, etc.).
- Health check path must return 200 quickly -- use a dedicated `/health` endpoint.
- Task CPU/memory must use specific Fargate-compatible combinations (e.g., 512 CPU / 1024 memory).
- ECS service updates are rolling by default -- set `deployment_minimum_healthy_percent` and `deployment_maximum_percent` appropriately.

---

## 10. pytest (Testing FastAPI Applications)

### Version Information
- **pytest**: 8.x (latest stable)
- **pytest-asyncio**: 1.0.0+ (released May 25, 2025 -- major breaking changes)
- **httpx**: Used for `AsyncClient` in async tests

### Key Imports
```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
```

### Installation
```bash
pip install pytest pytest-asyncio httpx
```

### pytest-asyncio 1.0 Breaking Changes
1. **`event_loop` fixture removed** -- no longer manually manage the event loop.
2. **Use `loop_scope` on marker** instead: `@pytest.mark.asyncio(loop_scope="session")`.
3. **Scoped event loops** are created only once per scope (performance improvement).
4. Python 3.14 preliminary support added.

### Configuration (pyproject.toml)
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # auto-detect async tests, no need for @pytest.mark.asyncio

[tool.pytest-asyncio]
# Optional: set default loop scope
loop_scope = "function"
```

### Async FastAPI Test Pattern (Current Best Practice)
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

async def test_list_experiments(client: AsyncClient):
    response = await client.get("/api/v1/experiments")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
```

### Database Test Fixture Pattern
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest.fixture(scope="function")
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()

@pytest.fixture
async def client(db_session):
    def override_get_db():
        return db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

### Concurrent Request Testing
```python
import asyncio

async def test_concurrent_requests(client: AsyncClient):
    tasks = [client.get(f"/api/v1/experiments/{i}") for i in range(10)]
    responses = await asyncio.gather(*tasks)
    assert all(r.status_code in (200, 404) for r in responses)
```

### Mocking Async Dependencies
```python
from unittest.mock import AsyncMock

async def test_with_mocked_service(client: AsyncClient):
    mock_service = AsyncMock(return_value={"id": 1, "name": "Test"})
    app.dependency_overrides[get_experiment_service] = lambda: mock_service
    response = await client.get("/api/v1/experiments/1")
    assert response.status_code == 200
    app.dependency_overrides.clear()
```

### Gotchas
- **pytest-asyncio 1.0** removed the `event_loop` fixture. If old code uses it, refactor to use `loop_scope` on the marker.
- Use `asyncio_mode = "auto"` in config to avoid decorating every test with `@pytest.mark.asyncio`.
- `httpx.AsyncClient` with `ASGITransport` is the current standard; the older `TestClient` (sync) from Starlette still works for sync tests.
- Async fixtures must use `async def` and are supported natively in pytest-asyncio 1.0+.
- Scope async fixtures carefully -- `scope="session"` async fixtures share one event loop for the session.

---

## Quick Reference: Version Summary

| Framework/Library       | Latest Stable Version | Python/Go Req |
|------------------------|-----------------------|---------------|
| FastAPI                | 0.115.x               | Python 3.9+   |
| Pydantic               | 2.12.x (2.13 beta)    | Python 3.9+   |
| Celery                 | 5.6.2                  | Python 3.9-3.13 |
| SQLAlchemy             | 2.0.44 (2.1.0 beta)   | Python 3.7+ (2.1: 3.10+) |
| elasticsearch-py       | 9.2.1                  | Python 3.9+   |
| FastMCP                | 3.1.0                  | Python 3.10+  |
| Plotly.js              | 3.4.0                  | N/A (JS)      |
| react-plotly.js        | latest (wraps plotly.js)| React 16+     |
| Go fsnotify            | v1.9.0                 | Go 1.17+      |
| Terraform AWS Provider | >= 5.x                 | Terraform 1.5+ |
| pytest                 | 8.x                    | Python 3.9+   |
| pytest-asyncio         | 1.0.0+                 | Python 3.9+   |

---

## Sources

### FastAPI
- [FastAPI Releases](https://github.com/fastapi/fastapi/releases)
- [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes/)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [FastAPI Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/)

### Pydantic
- [Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic Releases](https://github.com/pydantic/pydantic/releases)
- [Advanced Pydantic: Generic Models](https://dev.to/mechcloud_academy/advanced-pydantic-generic-models-custom-types-and-performance-tricks-4opf)

### Celery
- [Celery Redis Broker Docs](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- [Celery PyPI](https://pypi.org/project/celery/)
- [Celery Complete Guide 2026](https://devtoolbox.dedyn.io/blog/celery-complete-guide)

### SQLAlchemy
- [SQLAlchemy Async Extension](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy 2.1.0b1 Release](https://www.sqlalchemy.org/blog/2026/01/21/sqlalchemy-2.1.0b1-released/)
- [SQLAlchemy 2.0.44 Release](https://www.sqlalchemy.org/blog/2025/10/10/sqlalchemy-2.0.44-released/)

### Elasticsearch
- [Elasticsearch Python Async Docs](https://www.elastic.co/docs/reference/elasticsearch/clients/python/async)
- [Elasticsearch Python Client](https://www.elastic.co/docs/reference/elasticsearch/clients/python)
- [Elasticsearch-py Release Notes](https://www.elastic.co/docs/release-notes/elasticsearch/clients/python)

### FastMCP
- [FastMCP Updates](https://gofastmcp.com/updates)
- [FastMCP PyPI](https://pypi.org/project/fastmcp/)
- [FastMCP 3.0 Announcement](https://www.jlowin.dev/blog/fastmcp-3)
- [FastMCP FastAPI Integration](https://gofastmcp.com/integrations/fastapi)
- [FastMCP GitHub](https://github.com/jlowin/fastmcp)

### Plotly.js / React
- [Plotly.js React](https://plotly.com/javascript/react/)
- [react-plotly.js GitHub](https://github.com/plotly/react-plotly.js)
- [Plotly.js Releases](https://github.com/plotly/plotly.js/releases)

### Go fsnotify
- [fsnotify GitHub](https://github.com/fsnotify/fsnotify)
- [fsnotify pkg.go.dev](https://pkg.go.dev/github.com/fsnotify/fsnotify)
- [fsnotify v1.9.0 Release](https://github.com/fsnotify/fsnotify/releases/tag/v1.9.0)

### Terraform / AWS ECS
- [FastAPI on ECS Starter](https://github.com/tomsharp/fastapi-on-ecs)
- [Create ECS Cluster with Fargate in Terraform](https://oneuptime.com/blog/post/2026-02-23-create-ecs-cluster-with-fargate-in-terraform/view)
- [Deploying FastAPI to AWS Fargate](https://dev.to/ntanwir10/deploying-fastapi-to-aws-part-2-containerizing-with-ecs-fargate-5hlh)

### pytest
- [pytest-asyncio PyPI](https://pypi.org/project/pytest-asyncio/)
- [pytest-asyncio 1.0 Migration](https://thinhdanggroup.github.io/pytest-asyncio-v1-migrate/)
- [FastAPI Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/)
- [Async Testing with FastAPI and pytest](https://weirdsheeplabs.com/blog/fast-and-furious-async-testing-with-fastapi-and-pytest)
