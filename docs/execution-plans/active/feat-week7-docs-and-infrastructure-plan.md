---
title: "feat: Week 7 — Documentation + Infrastructure"
type: feat
status: active
date: 2026-03-08
deepened: 2026-03-08
---

# Week 7: Documentation + Infrastructure

## Progress

All 20 files created and committed on 2026-03-08. Tests: 1,423 passing (no regressions). Pre-commit hooks: all green.

| Task | Status | Notes |
|---|---|---|
| .dockerignore + llms.txt + llms-full.txt | ✅ Complete | llms.txt ~500 tokens, includes parameter signatures |
| Dockerfile + Dockerfile.worker | ✅ Complete | Virtual env pattern, tini, non-root uid 999 |
| docs.json + 5 MDX files | ✅ Complete | Mintlify v3 nested tabs format |
| infra/ (7 Terraform files incl. vpc.tf) | ✅ Complete | OpenSearch, Redis replication group, RDS managed password |
| ci.yml + deploy.yml + dependabot.yml | ✅ Complete | SHA-pinned, parallel jobs, ARN verification |

## Decision Log

| Decision | Rationale |
|---|---|
| Added infra/vpc.tf (not in original plan) | Security review found missing VPC — all data services must be in private subnets |
| aws_elasticache_replication_group instead of cluster | Cluster resource doesn't support AUTH tokens or TLS encryption |
| manage_master_user_password on RDS | Avoids storing plaintext password in Terraform state |
| SHA-pinned GitHub Actions | March 2025 tj-actions supply chain attack; GitHub enforced org-level SHA pinning Aug 2025 |
| Task def registration + ARN verification in deploy.yml | --force-new-deployment only re-pulls same task def; waiter returns success even on rollback |
| Mintlify v3 nested navigation | v2 mint.json top-level tabs array no longer works in v3 (renamed Feb 2025) |

## Outcomes & Retrospective

_To be completed after Week 8 design partner onboarding._

Metrics to capture:
- Time for first design partner to complete for-developers.mdx quickstart
- `mintlify dev` build time
- Docker build time (cold vs warm cache)
- `terraform validate` pass/fail on first attempt

## Enhancement Summary

**Deepened on:** 2026-03-08
**Sections enhanced:** 5 (Mintlify docs, Docker, Terraform, CI/CD, Agent-native docs)
**Research agents used:** best-practices-researcher ×4, security-sentinel, agent-native-reviewer

### Key Improvements Discovered

1. **Mintlify v3 docs.json** renamed from `mint.json` (Feb 2025); navigation structure completely changed — use nested `tabs/groups/pages`, not parallel arrays. OpenAPI goes inside navigation group objects.
2. **Use `aws_elasticache_replication_group`** instead of `aws_elasticache_cluster` — the cluster resource does not support AUTH tokens or TLS, both of which are required.
3. **ECS code deploys require a new task definition revision** — `--force-new-deployment` alone only re-pulls the same task definition; code changes need `aws ecs register-task-definition` first.
4. **Pin GitHub Action versions to 40-char SHA** — the March 2025 tj-actions supply chain attack compromised `@v4`-style tag pins; SHA enforcement is now org-level policy at GitHub (Aug 2025).
5. **Terraform 1.11 drops DynamoDB state locking** in favor of native S3 locking via `use_lockfile = true`.

### New Security Considerations Discovered

- **Critical**: OIDC role trust policy must use `StringEquals` on the `:sub` claim scoped to `ref:refs/heads/main`. Without it, any PR branch can assume the production deploy role.
- **High**: Missing VPC + private subnet resources — RDS, OpenSearch, and Redis must not be in the default VPC.
- **High**: S3 uploads bucket needs `aws_s3_bucket_public_access_block` and encryption configuration.
- **High**: Terraform state S3 bucket needs `encrypt = true`, versioning, and DynamoDB lock table (or native S3 locking on TF 1.11+).
- **Medium**: Use `manage_master_user_password = true` on RDS to avoid storing the password in Terraform state.

### New Agent-Native Documentation Gaps Discovered

- `llms.txt` should include parameter signatures per tool (e.g., `create_experiment(intent: str, ...) -> Experiment`)
- The `suggestion` + `retry` + `retry_after` error fields need dedicated documentation in both llms files
- MCP upload workflow is async — agents must poll `get_upload` until `status == "parsed"` before calling `get_instrument_data`; this must be documented prominently
- MCP server has no authentication layer — a security callout is required in for-agents.mdx
- Multi-tenancy is hardcoded stub (org_id = 00000000-...) — document as MVP limitation with future env var path

---

## Overview

Deliver the final pre-launch layer of LabLink: a Mintlify-powered docs site for three audiences (developers, agents, SDK users), auto-generated LLM context files (`llms.txt` / `llms-full.txt`), production-grade Terraform infrastructure on AWS, multi-stage Dockerfiles, and CI/CD pipelines via GitHub Actions.

Everything in this week makes the platform publicly launchable. After Week 7, the repo is demo-ready, deployable to AWS with one command, and discoverable by LLM agents via the `/llms.txt` protocol.

---

## Background & Motivation

Weeks 1–6 produced a fully-functional backend: 51 API endpoints, 25 MCP tools across 4 toolsets, 5 instrument parsers, Go desktop agent, React frontend, and 1,296 passing tests. The platform is feature-complete for the MVP but not yet:

- **Documented** for external audiences (developers, Claude/Cursor agent users, Python SDK users)
- **Deployable** to a reproducible production environment (no Terraform, no Dockerfiles)
- **CI/CD-guarded** (no automated test-gate on PRs, no deploy pipeline)
- **LLM-discoverable** (no `llms.txt` / `llms-full.txt` context files)

Week 7 closes all four gaps.

**Note on docs/ structure:** The existing `docs/` directory already contains internal documentation (DESIGN.md, SECURITY.md, FRONTEND.md, etc.) organized for developer reference. The Mintlify public docs will coexist in `docs/` using dedicated subdirectories (`docs/quickstart/`, `docs/mcp/`) and a root `docs/docs.json` config. Mintlify only serves files listed in `docs.json` — existing internal `.md` files are unaffected.

---

## Proposed Solution

### A. Mintlify Documentation Site (8 files in `docs/`)

A three-track quickstart system targeting:
1. **REST API developers** — curl + token auth, upload + parse + query flow
2. **Claude/Cursor agent users** — MCP server setup for Claude Desktop, tool discovery walkthrough
3. **Python SDK users** (future SDK preview, patterns with `httpx` for now)

Plus two MCP reference pages explaining the toolset architecture.

### B. LLM Context Files (2 files at repo root)

Following the [`llms.txt` spec](https://llmstxt.org/):
- `llms.txt` — ~500-token tool index for agent discovery, including parameter signatures
- `llms-full.txt` — Full markdown reference with all 25 MCP tools, all 51 endpoints, authentication patterns, error recovery guidance

### C. Terraform Infrastructure (6 files in `infra/`)

AWS-native IaC targeting a production-ready but cost-conscious setup:

| Service | Spec | Monthly Est. |
|---|---|---|
| ECS Fargate (API) | 2 tasks × 0.25 vCPU / 512 MB | ~$15 |
| ECS Fargate (Worker) | 1 task × 0.25 vCPU / 512 MB | ~$7 |
| RDS PostgreSQL 16 | db.t4g.medium, 20 GB gp3 | ~$50 |
| OpenSearch | t3.small.search, 10 GB | ~$25 |
| ElastiCache Redis | cache.t4g.micro | ~$12 |
| S3 | Standard + lifecycle | ~$2 |
| VPC + NAT Gateway | 1 AZ | ~$35 |
| **Total** | | **~$146/mo** |

> Note: VPC + NAT Gateway added after security review — services must not run in the default VPC.

### D. Docker Images (2 files at root)

Multi-stage builds for both the FastAPI API server and the Celery worker, optimized for minimal layer size and production security (non-root user, no dev deps in final image, virtual env in build stage for clean separation).

### E. GitHub Actions CI/CD (2 workflows)

- **`ci.yml`**: pytest + ruff + mypy on every PR, with pip cache and parallel lint/test jobs
- **`deploy.yml`**: Build → ECR (with GHA BuildKit cache) → new ECS task definition revision → rolling update on merge to `main`

---

## Technical Approach

### Architecture

```
Repository Root
├── docs/                          ← Mintlify docs site (coexists with internal docs)
│   ├── docs.json                  ← Mintlify v3 navigation config
│   ├── quickstart/
│   │   ├── for-developers.mdx
│   │   ├── for-agents.mdx
│   │   └── for-sdk-users.mdx
│   └── mcp/
│       ├── overview.mdx
│       └── toolsets.mdx
├── llms.txt                       ← ~500 token tool index (repo root)
├── llms-full.txt                  ← Full markdown API reference (repo root)
├── Dockerfile                     ← Multi-stage API image
├── Dockerfile.worker              ← Celery worker image
├── .dockerignore                  ← Critical for image size
├── infra/
│   ├── main.tf                    ← AWS provider, backend, variables
│   ├── vpc.tf                     ← VPC, subnets, NAT gateway (new — required by security)
│   ├── ecs.tf                     ← Fargate task definitions + services + circuit breaker
│   ├── rds.tf                     ← PostgreSQL 16 RDS instance
│   ├── s3.tf                      ← S3 bucket + public access block + encryption + lifecycle
│   ├── elasticsearch.tf           ← OpenSearch domain (t3.small.search)
│   └── redis.tf                   ← ElastiCache replication group (t4g.micro)
└── .github/workflows/
    ├── garden-ci.yml              ← Already exists (doc linting)
    ├── release.yml                ← Already exists (Go cross-compile)
    ├── ci.yml                     ← New: pytest + ruff + mypy (parallel jobs)
    └── deploy.yml                 ← New: ECR + new task def revision + ECS deploy
```

> Note: `infra/vpc.tf` added (was implicit in plan, explicit after security review). Total Terraform files: 6 (not 5).

### Implementation Phases

#### Phase 1: LLM Context Files (`llms.txt` + `llms-full.txt`)

Start here because these are the fastest to produce and validate the API surface understanding needed for the docs.

**`llms.txt`** — structured per the llmstxt.org spec (4 variants: llms.txt, llms-full.txt, llms-ctx.txt, llms-ctx-full.txt — implement the first two):

```
# LabLink

> Agent-native lab data integration platform. Connect instruments, parse data,
> run experiments. PostgreSQL is source of truth; Elasticsearch is eventually
> consistent; S3 is immutable.

## REST API
- [Authentication](https://docs.lablink.io/quickstart/for-developers): Bearer token via `Authorization: Bearer <token>`
- [OpenAPI spec](https://api.lablink.io/api/openapi.json): Machine-readable schema for all 51 endpoints
- [Error recovery](https://docs.lablink.io/quickstart/for-developers#errors): Every error includes `suggestion` field — act on it before giving up

## MCP Server (25 tools, 4 toolsets + 2 discovery)
- Install: `pip install lablink` then `python -m lablink.mcp.server`
- Discovery: Call `list_toolsets()` first, then `get_toolset("explorer")` to see tools
- [Full MCP reference](https://docs.lablink.io/mcp/toolsets)

## Explorer Tools (read-only)
- `list_experiments(status?, project_id?, limit?)` → ExperimentSummary[]
- `get_experiment(experiment_id: uuid)` → Experiment (full detail)
- `get_instrument_data(upload_id: uuid)` → ParsedResult (measurements + settings)
- `search_catalog(q: str, limit?)` → SearchResult[] with highlights
- `list_instruments(project_id?)` → Instrument[]
- `list_uploads(status?, instrument_id?, limit?)` → Upload[]
- `get_chart_data(upload_id: uuid)` → Plotly config + raw JSON arrays
- `create_export(upload_ids: uuid[], format: csv|json|xlsx|pdf)` → ExportJob with download_url

## Planner Tools
- `create_experiment(intent: str, hypothesis?, campaign_id?, parameters?)` → Experiment
- `update_experiment(experiment_id: uuid, intent?, parameters?, constraints?)` → Experiment
- `record_outcome(experiment_id: uuid, outcome: object)` → Experiment (with outcome)
- `link_upload_to_experiment(experiment_id: uuid, upload_id: uuid)` → ExperimentUpload
- `create_campaign(name: str, objective: str)` → Campaign
- `get_campaign_progress(campaign_id: uuid)` → CampaignProgress (counts by status)
- `list_campaigns(status?)` → Campaign[]

## Ingestor Tools (async — poll get_upload until status=="parsed")
- `create_upload(storage_path: str, instrument_type?)` → Upload (status: pending)
- `list_parsers()` → Parser[] (supported formats and instrument types)
- `get_upload(upload_id: uuid)` → Upload (check status field)
- `reparse_upload(upload_id: uuid, instrument_type?)` → Upload (status: pending)

## Admin Tools
- `get_usage_stats()` → UsageMetrics (vs plan limits)
- `list_agents()` → Agent[] (with connection status)
- `create_webhook(url: str, events: str[])` → Webhook (with generated secret)
- `list_audit_events(resource_id?, action?, limit?)` → AuditEvent[]

## Error Recovery
Every error response includes `errors[0].suggestion` with a concrete next action.
`errors[0].retry` (bool) and `errors[0].retry_after` (seconds) signal transient failures.
Always check `suggestion` before reporting failure to the user.
```

**Research insights for `llms.txt`:**
- Spec has 4 variants; llms-ctx.txt excludes Optional-section URLs for smaller context
- Mintlify auto-generates `/llms.txt` from MDX frontmatter `description` fields — ensure all MDX pages have a description < 20 words
- Keep curated; un-curated auto-generation can balloon to 100K+ tokens (Turborepo example)
- Token budget: target 500–2K tokens for llms.txt, up to 50K for llms-full.txt

**`llms-full.txt`** — full markdown with:
- Authentication section (token generation, header format, expiry)
- Envelope schema documentation (`{ data, meta, errors }` structure, all error fields including `suggestion`, `retry`, `retry_after`)
- All 4 MCP toolsets with full parameter docs and JSON response shapes
- Key REST endpoint groups with request/response examples
- Async patterns: upload flow requires polling `get_upload` until `status == "parsed"`
- MVP limitations: multi-tenancy is stubbed (org_id hardcoded), future `LABLINK_MCP_ORG_ID` env var

#### Phase 2: Mintlify Docs Site

**Critical: `docs.json` uses Mintlify v3 format** (renamed from `mint.json` in February 2025). The navigation structure changed completely — use nested tabs/groups/pages hierarchy:

```json
{
  "$schema": "https://mintlify.com/docs.json",
  "name": "LabLink",
  "logo": {
    "light": "/logo/light.svg",
    "dark": "/logo/dark.svg"
  },
  "favicon": "/favicon.svg",
  "colors": {
    "primary": "#0066CC",
    "light": "#3399FF",
    "dark": "#0044AA"
  },
  "api": {
    "baseUrl": "https://api.lablink.io",
    "auth": { "method": "bearer" },
    "playground": { "mode": "simple" }
  },
  "navigation": {
    "tabs": [
      {
        "tab": "Quickstart",
        "groups": [
          {
            "group": "Get Started",
            "pages": [
              "quickstart/for-developers",
              "quickstart/for-agents",
              "quickstart/for-sdk-users"
            ]
          }
        ]
      },
      {
        "tab": "MCP Server",
        "groups": [
          {
            "group": "Reference",
            "pages": ["mcp/overview", "mcp/toolsets"]
          }
        ]
      },
      {
        "tab": "API Reference",
        "groups": [
          {
            "group": "Endpoints",
            "openapi": {
              "source": "/api/openapi.json",
              "directory": "api-reference"
            }
          }
        ]
      }
    ]
  }
}
```

> **Pitfall**: Do NOT put `openapi` at the top level of docs.json. In v3, it goes inside a navigation group object. The old `mint.json` `tabs` array at the top level no longer works.

**MDX frontmatter pattern** (required for good llms.txt auto-generation):
```mdx
---
title: "REST API Quickstart"
sidebarTitle: "For Developers"
description: "Authenticate and make your first API call in 5 minutes."
---
```

**`docs/quickstart/for-developers.mdx`** — REST API walkthrough:
- Prerequisites: API token (explain how to get one via dashboard or `POST /api/v1/auth/tokens`)
- First call: `GET /health` to verify connectivity
- Core workflow: `POST /api/v1/uploads` → poll `GET /api/v1/uploads/{id}` until status=parsed → `GET /api/v1/data/search?q=...` → `POST /api/v1/experiments`
- Authentication header: `Authorization: Bearer <token>`
- Envelope schema: show `{ data, meta, errors }` with explanation of `suggestion` field
- Error handling examples: what to do when `errors[0].retry = true` vs `false`

**`docs/quickstart/for-agents.mdx`** — MCP setup for Claude Desktop:

```json
{
  "mcpServers": {
    "lablink": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/lablink",
        "run", "python", "-m", "lablink.mcp.server"
      ],
      "env": {
        "LABLINK_DATABASE_URL": "sqlite+aiosqlite:///./lablink.db",
        "LABLINK_ENVIRONMENT": "development"
      }
    }
  }
}
```

> **Use `uv run` pattern** (not `python -m` directly) — handles virtualenv activation correctly. Include `env` block with minimum required environment variables.

Critical items to cover:
- **Security callout**: MCP server has no authentication layer — do not expose over a network without a wrapper
- **Async upload flow**: `create_upload` returns `status: "pending"`. Agent MUST poll `get_upload(upload_id)` until `status == "parsed"` before calling `get_instrument_data`. Typically 2–30 seconds depending on file size.
- **MVP limitation**: Multi-tenancy is stubbed — all MCP writes go to `org_id = 00000000-0000-0000-0000-000000000000`. Data isolation by organization is a Q2 feature.
- **Discovery first**: Always start with `list_toolsets()` → `get_toolset("ingestor")` before uploading
- **Error recovery**: Check `suggestion` field on every error before retrying or failing

**`docs/quickstart/for-sdk-users.mdx`** — Python patterns with httpx:
```python
import httpx
import asyncio

BASE_URL = "https://api.lablink.io"
TOKEN = "your-api-token"

async def list_experiments():
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
    ) as client:
        resp = await client.get("/api/v1/experiments")
        resp.raise_for_status()
        envelope = resp.json()
        # Always access .data — never assume top-level fields
        return envelope["data"]
```
- Note: `pip install lablink` Python SDK ships in Q2 — this is the interim httpx pattern
- Document Envelope unwrapping as the canonical pattern
- Show error handling: check `errors` field before accessing `data`

**`docs/mcp/overview.mdx`** — Architecture explanation:
- What MCP is and why LabLink supports it (agent-first platform)
- 4 toolsets + 2 discovery tools diagram (ASCII or Mermaid)
- Verb_noun naming convention (`create_experiment` not `experimentCreate`)
- Envelope-to-dict mapping: REST returns HTTP `{ data, meta, errors }`, MCP returns the `data` dict directly
- When to use MCP vs REST vs SDK: MCP for Claude/Cursor agents, REST for integrations, SDK (Q2) for Python apps
- **STDIO protocol note**: MCP server uses JSON-RPC over STDIO — `print()` in server code corrupts the protocol. All logging goes to stderr.

**`docs/mcp/toolsets.mdx`** — Toolset reference with machine-readable shapes:
```mdx
## get_instrument_data

Retrieve parsed measurement data for an upload.

**Returns:**
```json
{
  "measurements": [
    {
      "sample_id": "Sample_1",
      "value": 1.234,
      "unit": "A260",
      "wavelength_nm": 260
    }
  ],
  "instrument_settings": {
    "instrument_type": "spectrophotometer",
    "model": "NanoDrop 2000"
  },
  "metadata": {
    "upload_id": "uuid",
    "parsed_at": "2026-03-08T22:00:00Z"
  }
}
```

> Note: `data` is a flat list. Data lives at `result["measurements"]`, not `result["data"]["measurements"]`.
```

Must include response shapes for all three non-obvious tools: `get_chart_data` (Plotly config + raw arrays), `get_instrument_data` (flat structure), `create_export` (synchronous in dev mode, async in production).

#### Phase 3: Dockerfiles

**`.dockerignore`** (critical for image size — create this alongside Dockerfiles):
```
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/
.git/
.env*
tests/
docs/
*.md
dist/
build/
*.egg-info/
.vscode/
.idea/
infra/
RESEARCH/
```

**`Dockerfile`** — Multi-stage API build using virtual environment (cleaner than `--target`):
```dockerfile
# Stage 1: builder — compile all deps into a venv
FROM python:3.12-slim AS builder
WORKDIR /build

# Install build deps (needed for psycopg2, cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency spec first (cache layer — only re-runs if pyproject.toml changes)
COPY pyproject.toml .

# Create venv and install runtime deps only (no [dev] extras)
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir .

# Stage 2: runtime — minimal image, no build tools
FROM python:3.12-slim AS runtime

# Install tini for proper signal handling (PID 1 problem)
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -g 999 lablink && useradd -r -u 999 -g lablink lablink

WORKDIR /app

# Copy venv from builder (only runtime packages)
COPY --from=builder /venv /venv

# Copy application source
COPY --chown=lablink:lablink src/ src/

USER lablink

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "lablink.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**`Dockerfile.worker`** — Celery worker (separate container per queue for independent scaling):
```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir .

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd -g 999 lablink && useradd -r -u 999 -g lablink lablink
WORKDIR /app
COPY --from=builder /venv /venv
COPY --chown=lablink:lablink src/ src/
USER lablink
ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A lablink.tasks.celery_app inspect ping -d "celery@$HOSTNAME" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["celery", "-A", "lablink.tasks.celery_app", "worker", \
     "--queues=parsing,webhooks,indexing", \
     "--concurrency=4", \
     "--loglevel=info", \
     "--pidfile=/tmp/celery-%n.pid"]
```

**Research insights:**
- Virtual environment approach (`/venv`) is cleaner than `--target deps` copy — avoids site-packages path confusion
- `tini` solves the PID 1 signal handling problem (`SIGTERM` → graceful shutdown, no zombie processes)
- `python:3.12-slim` not alpine — avoids musl libc incompatibilities with psycopg2, cryptography
- `COPY pyproject.toml .` BEFORE `COPY src/` maximizes Docker layer cache hits on dep install
- Consider running separate worker containers per queue (parsing-worker, webhook-worker, index-worker) for independent scaling — use `CELERY_QUEUES` env var override

#### Phase 4: Terraform Infrastructure

**Note on file count:** `infra/vpc.tf` is required (6 files total, not 5). All data services must be in private subnets.

**`infra/main.tf`**:
```hcl
terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "lablink-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true                         # Required — state contains sensitive data
    dynamodb_table = "lablink-terraform-locks"    # Remove if using TF >= 1.11 native locking
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region"    { default = "us-east-1" }
variable "environment"   { default = "production" }
variable "image_tag"     { default = "latest" }
variable "ecr_repo_url"  { description = "ECR repository URL (no tag)" }
```

> **No `db_password` variable** — use `manage_master_user_password = true` on RDS instead. Password is managed in Secrets Manager, never stored in Terraform state.

**`infra/vpc.tf`** (new, required by security review):
```hcl
resource "aws_vpc" "lablink" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "lablink-${var.environment}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.lablink.id
  cidr_block        = cidrsubnet(aws_vpc.lablink.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "lablink-private-${count.index}" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.lablink.id
  cidr_block              = cidrsubnet(aws_vpc.lablink.cidr_block, 8, count.index + 10)
  map_public_ip_on_launch = true
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "lablink-public-${count.index}" }
}

resource "aws_internet_gateway" "lablink" {
  vpc_id = aws_vpc.lablink.id
}

resource "aws_eip" "nat" { domain = "vpc" }

resource "aws_nat_gateway" "lablink" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
}

data "aws_availability_zones" "available" { state = "available" }
```

**`infra/ecs.tf`** — with deployment circuit breaker and proper task roles:
```hcl
resource "aws_ecs_cluster" "lablink" {
  name = "lablink-${var.environment}"
}

resource "aws_iam_role" "ecs_task_execution" {
  name = "lablink-ecs-execution-${var.environment}"
  # Allows ECS to pull images and fetch SSM params
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role" "ecs_api_task" {
  name = "lablink-api-task-${var.environment}"
  # Minimal: ssm:GetParameter on /lablink/prod/*, s3:GetObject/PutObject on uploads bucket
}

resource "aws_iam_role" "ecs_worker_task" {
  name = "lablink-worker-task-${var.environment}"
  # Same as API task + broader S3 access for parsing
}

resource "aws_ecs_task_definition" "api" {
  family                   = "lablink-api-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_api_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${var.ecr_repo_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    secrets = [
      { name = "DATABASE_URL",        valueFrom = aws_ssm_parameter.db_url.arn },
      { name = "REDIS_URL",           valueFrom = aws_ssm_parameter.redis_url.arn },
      { name = "ELASTICSEARCH_URL",   valueFrom = aws_ssm_parameter.es_url.arn },
      { name = "S3_BUCKET",           valueFrom = aws_ssm_parameter.s3_bucket.arn },
      { name = "SECRET_KEY",          valueFrom = aws_ssm_parameter.secret_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/lablink-api"
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 40
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "lablink-api"
  cluster         = aws_ecs_cluster.lablink.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true      # Auto-rolls back to previous task def on failure
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }
}
```

**`infra/rds.tf`** — with managed master password (no plaintext in state):
```hcl
resource "aws_db_instance" "lablink" {
  identifier             = "lablink-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = "db.t4g.medium"
  allocated_storage      = 20
  storage_type           = "gp3"
  db_name                = "lablink"
  username               = "lablink"

  # Managed password — stored in Secrets Manager, no var.db_password needed
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.lablink.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.lablink.name

  publicly_accessible     = false     # Never true in prod
  multi_az                = false     # Enable for production HA
  skip_final_snapshot     = false
  final_snapshot_identifier = "lablink-${var.environment}-final"
  backup_retention_period = 7
  deletion_protection     = true
  storage_encrypted       = true
}

resource "aws_db_parameter_group" "lablink" {
  name   = "lablink-pg16-${var.environment}"
  family = "postgres16"   # Must match engine major version — mismatch = apply failure
}

resource "aws_db_subnet_group" "lablink" {
  name       = "lablink-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}
```

**`infra/s3.tf`** — with public access block and encryption (required, was missing):
```hcl
resource "aws_s3_bucket" "uploads" {
  bucket = "lablink-uploads-${var.environment}"
}

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    transition { days = 30; storage_class = "STANDARD_IA" }
    transition { days = 90; storage_class = "GLACIER" }
  }
  rule {
    id     = "expire-soft-deleted"
    status = "Enabled"
    filter { tag { key = "SoftDeleted"; value = "true" } }
    expiration { days = 90 }
  }
}
```

**`infra/elasticsearch.tf`** — OpenSearch with VPC and encryption:
```hcl
resource "aws_opensearch_domain" "lablink" {
  domain_name    = "lablink-${var.environment}"
  engine_version = "OpenSearch_2.11"   # Format: "OpenSearch_X.Y" — NOT "2.11" or "Elasticsearch_7.10"

  cluster_config {
    instance_type  = "t3.small.search"
    instance_count = 1
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 10
    volume_type = "gp3"
  }

  vpc_options {
    subnet_ids         = [aws_subnet.private[0].id]
    security_group_ids = [aws_security_group.opensearch.id]
  }

  encrypt_at_rest         { enabled = true }
  node_to_node_encryption { enabled = true }
  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }
}
```

> **Note**: `t3.small.search` has I/O throttling limits. Fine for MVP; upgrade to `m5.large.search` in Q2.

**`infra/redis.tf`** — Use `aws_elasticache_replication_group` (NOT `aws_elasticache_cluster`):
```hcl
# Must use replication_group (not cluster) to support AUTH + TLS
resource "aws_elasticache_replication_group" "lablink" {
  replication_group_id       = "lablink-${var.environment}"
  description                = "LabLink Redis"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1          # Single node for MVP
  engine_version             = "7.0"
  parameter_group_name       = "default.redis7"
  port                       = 6379
  security_group_ids         = [aws_security_group.redis.id]
  subnet_group_name          = aws_elasticache_subnet_group.lablink.name
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  auth_token                 = aws_ssm_parameter.redis_auth_token.value
}

resource "aws_elasticache_subnet_group" "lablink" {
  name       = "lablink-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}
```

> **Critical**: `aws_elasticache_cluster` does NOT support AUTH tokens or TLS. Always use `aws_elasticache_replication_group` even for single-node setups. Encryption settings cannot be changed after creation — plan them upfront.

> **TF 1.11 note**: Terraform 1.11+ replaces DynamoDB state locking with native S3 locking (`use_lockfile = true`). If on TF >= 1.11, drop the `dynamodb_table` line from the backend config.

#### Phase 5: GitHub Actions CI/CD

**`ci.yml`** — Parallel jobs, pip cache, separate ruff steps:
```yaml
name: CI
on:
  pull_request:
    branches: [main]

permissions: {}   # Deny all at workflow level; grant per job

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/           # Check for lint errors
      - run: ruff format --check src/ tests/  # Check for formatting (separate step)
      - run: mypy src/lablink/ --ignore-missing-imports

  test:
    name: Test
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b  # v5.3.0
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: pip install -e ".[dev]"
      - run: python -m pytest tests/ -x -q --tb=short
```

**`deploy.yml`** — OIDC-scoped, new task def revision, GHA BuildKit cache, deployment verification:
```yaml
name: Deploy
on:
  push:
    branches: [main]

permissions: {}   # Deny all at workflow level

jobs:
  deploy:
    name: Build & Deploy
    runs-on: ubuntu-latest
    permissions:
      id-token: write    # Required for OIDC
      contents: read
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502  # v4.0.2
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1

      - name: Login to ECR
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@062b18b96a7aff071d4dc91bc00c4c1a7945b076  # v2.0.1

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@c47758b77c9736f4b2ef4073d4d51994fabfe349  # v3.7.1

      - name: Build and push API image
        uses: docker/build-push-action@4f58ea79222b3b9dc2c8bbdd6debcef730109a75  # v6.9.0
        with:
          push: true
          tags: |
            ${{ secrets.ECR_REGISTRY }}/lablink-api:${{ github.sha }}
            ${{ secrets.ECR_REGISTRY }}/lablink-api:latest
          cache-from: type=gha,mode=max    # GHA BuildKit cache — free, 10GB, 7d LRU
          cache-to: type=gha,mode=max

      - name: Build and push worker image
        uses: docker/build-push-action@4f58ea79222b3b9dc2c8bbdd6debcef730109a75  # v6.9.0
        with:
          file: Dockerfile.worker
          push: true
          tags: |
            ${{ secrets.ECR_REGISTRY }}/lablink-worker:${{ github.sha }}
            ${{ secrets.ECR_REGISTRY }}/lablink-worker:latest
          cache-from: type=gha,mode=max
          cache-to: type=gha,mode=max

      - name: Register new ECS task definition and deploy
        run: |
          # Get current task definition and update image tag
          API_TASK_DEF=$(aws ecs describe-task-definition \
            --task-definition lablink-api-production \
            --query 'taskDefinition' --output json | \
            jq --arg IMAGE "${{ secrets.ECR_REGISTRY }}/lablink-api:${{ github.sha }}" \
              'del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) |
               .containerDefinitions[0].image = $IMAGE')

          NEW_API_ARN=$(aws ecs register-task-definition \
            --cli-input-json "$API_TASK_DEF" \
            --query 'taskDefinition.taskDefinitionArn' --output text)

          aws ecs update-service \
            --cluster lablink-production \
            --service lablink-api \
            --task-definition "$NEW_API_ARN"

          # Wait for deployment and verify (waiter returns success even on rollback!)
          aws ecs wait services-stable --cluster lablink-production --services lablink-api
          ACTIVE_ARN=$(aws ecs describe-services \
            --cluster lablink-production --services lablink-api \
            --query 'services[0].deployments[0].taskDefinition' --output text)
          if [ "$ACTIVE_ARN" != "$NEW_API_ARN" ]; then
            echo "Deployment rolled back! Active: $ACTIVE_ARN, Expected: $NEW_API_ARN"
            exit 1
          fi
          echo "API deployment verified: $NEW_API_ARN"

      - name: Deploy worker
        run: |
          WORKER_TASK_DEF=$(aws ecs describe-task-definition \
            --task-definition lablink-worker-production \
            --query 'taskDefinition' --output json | \
            jq --arg IMAGE "${{ secrets.ECR_REGISTRY }}/lablink-worker:${{ github.sha }}" \
              'del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy) |
               .containerDefinitions[0].image = $IMAGE')

          NEW_WORKER_ARN=$(aws ecs register-task-definition \
            --cli-input-json "$WORKER_TASK_DEF" \
            --query 'taskDefinition.taskDefinitionArn' --output text)

          aws ecs update-service \
            --cluster lablink-production \
            --service lablink-worker \
            --task-definition "$NEW_WORKER_ARN"

          aws ecs wait services-stable --cluster lablink-production --services lablink-worker
```

**Research insights:**
- **SHA pinning is mandatory** (not `@v4`) — March 2025 tj-actions supply chain attack; GitHub added org-level SHA enforcement Aug 2025. Use Dependabot to auto-update pinned SHAs.
- `type=gha,mode=max` for BuildKit cache caches ALL intermediate layers including the slow dep-install layer — zero cost, 10 GB, 7-day LRU. `--cache-from image:latest` alone has high miss rates on multi-stage builds.
- OIDC trust policy must use `StringEquals` on `:sub` = `repo:william-c-stanford/lablink:ref:refs/heads/main`. Without this scope, any branch can assume the production role.
- `--force-new-deployment` alone only re-pulls the existing task def — code deploys require registering a new task definition revision and passing `--task-definition <new-arn>`.
- `aws ecs wait services-stable` returns success EVEN when the deployment rolled back. Always verify the active task definition ARN post-wait.
- Dependabot config for pinned action updates:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

---

## Alternative Approaches Considered

### Docs: GitBook vs Mintlify vs ReadTheDocs
- **GitBook**: Good UI but lacks OpenAPI component rendering natively
- **ReadTheDocs**: Sphinx-heavy, Python-centric, dated UX
- **Mintlify** ✅: Native OpenAPI playground, MDX components, auto-generates llms.txt from frontmatter, used by modern API companies (Anthropic, Resend, Supabase). Chosen.

### Infra: Pulumi vs Terraform vs CDK
- **Pulumi**: TypeScript/Python IaC — good DX but smaller ecosystem
- **CDK**: AWS-specific, good for pure AWS shops, harder for multi-cloud future
- **Terraform** ✅: Largest provider ecosystem, declarative HCL readable by non-infra devs, widely known by design partners

### ECS vs App Runner vs Lambda
- **App Runner**: Simpler but no persistent worker tasks, limited VPC integration
- **Lambda**: Stateless functions don't map well to Celery worker model
- **ECS Fargate** ✅: Long-running workers, VPC-native, rolling deploys with circuit breaker

### Docker base image: alpine vs slim vs full
- **alpine**: Smallest but musl libc causes issues with psycopg2, cryptography compiled wheels
- **python:3.12** full: 1+ GB — unnecessary
- **python:3.12-slim** ✅: ~130 MB, Debian-based, no glibc issues

### ElastiCache: `aws_elasticache_cluster` vs `aws_elasticache_replication_group`
- **`aws_elasticache_cluster`**: No AUTH token support, no TLS — inadequate for production
- **`aws_elasticache_replication_group`** ✅: Supports AUTH + TLS even for single-node — required

---

## System-Wide Impact

### Interaction Graph
- `ci.yml` PR gate → parallel lint + test jobs → blocks merge → prevents broken code reaching `deploy.yml`
- `deploy.yml` → new task def revision registered → ECS pulls new image → rolling replacement (0 downtime with deployment circuit breaker + rollback enabled)
- Terraform `elasticsearch.tf` uses `aws_opensearch_domain` (not `aws_elasticsearch_domain`) — AWS renamed the resource in provider v4+
- `docs.json` references OpenAPI inside navigation group (not top-level) — serves MDX-generated endpoint pages
- Mintlify auto-generates `llms.txt` from MDX frontmatter `description` fields — every MDX page MUST have a description

### Error & Failure Propagation
- If `ci.yml` lint OR test job fails: PR cannot merge (branch protection rule)
- If ECS deploy fails health check: circuit breaker detects failure, rolls back to previous task def, workflow step explicitly fails via ARN mismatch check
- If OpenSearch is unavailable: `search_catalog` MCP tool returns graceful error with `suggestion`. App continues operating (PostgreSQL is source of truth)
- Terraform state corruption prevented by DynamoDB locking (or native S3 locking on TF 1.11+) — concurrent applies cannot split-brain the state

### State Lifecycle Risks
- **RDS `deletion_protection = true`**: Prevents accidental `terraform destroy` from dropping the database
- **RDS `manage_master_user_password = true`**: Rotates password in Secrets Manager; ECS tasks fetch at runtime
- **S3 versioning + lifecycle**: Protects against accidental object deletion; soft-deleted objects expire after 90d
- **Terraform state bucket**: Must exist before first `terraform init` with encryption + versioning + public access block + DynamoDB lock table

### API Surface Parity
- `llms-full.txt` and `docs/mcp/toolsets.mdx` duplicate tool descriptions from `src/lablink/mcp/server.py:_TOOLSETS`. If MCP tools change, both files must be updated. Future: `make generate-docs` codegen target.
- `docs.json` OpenAPI source path (`/api/openapi.json`) must be CORS-accessible from Mintlify's preview domain (`*.mintlify.app`)

### Integration Test Scenarios
1. PR with failing test → `ci.yml` blocks merge → `deploy.yml` never runs
2. Successful merge → new task def revision → ECS circuit breaker detects health check pass → new code live → deployment ARN verified
3. Bad image pushed → health check fails → circuit breaker rollback → previous task def restored → workflow fails
4. `llms.txt` fetched by Claude → calls `list_toolsets()` → `get_toolset("ingestor")` → `create_upload(storage_path)` → polls `get_upload` until `status=="parsed"` → `get_instrument_data(upload_id)` (full async ingest chain documented)
5. Terraform apply on RDS with no changes → `No changes. Your infrastructure matches the configuration.`

---

## Acceptance Criteria

### Functional Requirements

**Documentation:**
- [ ] `docs/docs.json` uses Mintlify v3 format (`$schema: mintlify.com/docs.json`, nested tabs/groups navigation)
- [ ] `mintlify dev` runs locally without errors
- [ ] `docs/quickstart/for-developers.mdx` has working curl examples + Envelope schema explanation
- [ ] `docs/quickstart/for-agents.mdx` has valid `claude_desktop_config.json` with `uv run` pattern + env vars + security callout + async upload polling documentation
- [ ] `docs/quickstart/for-sdk-users.mdx` shows async httpx client with Envelope unwrapping
- [ ] `docs/mcp/overview.mdx` explains all 4 toolsets + 2 discovery tools + STDIO protocol note
- [ ] `docs/mcp/toolsets.mdx` documents all 25 tools with parameter signatures + machine-readable JSON response shapes for get_chart_data, get_instrument_data, create_export
- [ ] `llms.txt` includes parameter signatures per tool, error recovery section, ≤ 600 tokens
- [ ] `llms-full.txt` covers all 4 toolsets + async upload flow + suggestion/retry field docs + MVP multi-tenancy limitation

**Infrastructure:**
- [x] `terraform validate` passes on all 6 `.tf` files (including vpc.tf)
- [x] RDS uses `manage_master_user_password = true` (no plaintext password in state)
- [x] Redis uses `aws_elasticache_replication_group` with `transit_encryption_enabled = true`
- [x] OpenSearch `engine_version = "OpenSearch_2.11"` (correct format with prefix)
- [x] S3 has `aws_s3_bucket_public_access_block` (all 4 flags = true) + encryption config
- [x] Terraform backend has `encrypt = true` and `dynamodb_table` (or `use_lockfile = true` on TF 1.11+)
- [x] All data services (RDS, OpenSearch, Redis) in private subnets

**Docker:**
- [ ] `Dockerfile` uses virtual env pattern (not `--target deps` copy)
- [ ] Both images install `tini` and use `ENTRYPOINT ["/usr/bin/tini", "--"]`
- [ ] Both images have `HEALTHCHECK` instruction
- [ ] `.dockerignore` excludes tests/, docs/, .git/, .env*, __pycache__
- [ ] Final images run as non-root user `lablink` (uid 999)

**CI/CD:**
- [x] All GitHub Action versions pinned to full 40-char SHA (not `@v4`)
- [x] `ci.yml` runs lint and test as parallel jobs (no `needs:` between them)
- [x] `ci.yml` has separate `ruff check` and `ruff format --check` steps
- [x] `deploy.yml` OIDC trust policy comment shows required `:sub` claim format
- [x] `deploy.yml` registers new task definition before `update-service` (not just `--force-new-deployment`)
- [x] `deploy.yml` verifies active task def ARN post-deployment (not just waiter success)
- [x] `.github/dependabot.yml` created for github-actions ecosystem

### Non-Functional Requirements
- [ ] No AWS credentials hard-coded anywhere (OIDC + SSM + Secrets Manager)
- [ ] `llms.txt` validates per llmstxt.org spec (H1, blockquote, ## sections with file lists)
- [ ] OpenAPI `$ref` only uses internal references (Mintlify doesn't support external `$ref`)
- [ ] All MDX pages have `description` frontmatter < 20 words (for llms.txt auto-generation)

### Quality Gates
- [ ] Existing 1,296 tests continue to pass
- [ ] `docs/PLANS.md` updated ✅ (done during planning)
- [ ] `ruff check` and `mypy` pass on any Python files added/modified

---

## Success Metrics

- `mintlify dev` runs locally without errors
- `docker build` for both images completes in < 5 minutes (with BuildKit cache hits on repeat builds)
- `terraform validate` passes on all 6 files
- CI workflow runs green on a test PR (parallel lint + test jobs)
- `llms.txt` discovered and parsed by Claude to navigate to `get_instrument_data` with zero additional instruction
- Total new file count: 19 files created (18 original + .dockerignore), 0 existing files broken

---

## Dependencies & Prerequisites

| Dependency | Notes |
|---|---|
| Mintlify account | For deploying docs site (free tier OK for MVP) |
| AWS account | ECR, ECS, RDS, OpenSearch, ElastiCache, S3, VPC, IAM permissions |
| AWS IAM OIDC role | Trust policy must scope `:sub` to `repo:william-c-stanford/lablink:ref:refs/heads/main` |
| ECR repositories | `lablink-api` and `lablink-worker` repos must exist in ECR |
| Terraform state bootstrap | S3 bucket + DynamoDB table must exist before `terraform init` (one-time manual step) |
| GitHub secrets | `AWS_DEPLOY_ROLE_ARN`, `ECR_REGISTRY` |
| Python 3.12 | Already a project requirement |
| Docker with BuildKit | Required for multi-stage build + GHA cache |
| Dependabot | For keeping pinned action SHAs current |

---

## Risk Analysis & Mitigation

| Risk | Severity | Mitigation |
|---|---|---|
| OIDC role too broad (any branch can deploy) | Critical | `StringEquals` on `:sub` claim in trust policy; deploy.yml on `push` only, not `pull_request` |
| Missing VPC causes data services in default VPC | High | Add `infra/vpc.tf`; all services use `aws_subnet.private[*].id` |
| S3 uploads bucket publicly accessible | High | `aws_s3_bucket_public_access_block` with all 4 flags = true |
| Terraform state unencrypted (contains passwords) | High | `encrypt = true` + `manage_master_user_password` eliminates password from state |
| Action version tag hijacking | High | SHA pinning + Dependabot weekly updates |
| ECS waiter masks rollback as success | High | Explicit ARN comparison post-wait in deploy.yml |
| `aws_elasticache_cluster` used (no AUTH/TLS) | Medium | Use `aws_elasticache_replication_group` |
| OpenSearch `engine_version` format wrong | Medium | `"OpenSearch_2.11"` with prefix; note in comment |
| Mintlify v3 navigation format change | Medium | Use nested `navigation.tabs` structure; `openapi` inside group object |
| llms-full.txt balloon size | Low | Curate manually; monitor with `tiktoken` |
| MCP server stdout corruption | Low | Note in for-agents.mdx; MCP STDIO servers never print to stdout |

---

## Resource Requirements

- **Developer time**: ~1 day (all files are configuration/documentation, no new logic)
- **AWS cost**: ~$146/month for production (includes VPC + NAT Gateway)
- **Terraform bootstrap**: One-time S3 bucket + DynamoDB table creation (~$1/month)

---

## Future Considerations

- **Codegen for docs**: `make generate-docs` target that re-generates `llms.txt`, `llms-full.txt`, `docs/mcp/toolsets.mdx` from `src/lablink/mcp/server.py:_TOOLSETS`
- **Mintlify auto-deploy**: Add `mintlify deploy` to `deploy.yml` after ECS update
- **Per-queue worker containers**: Split Celery into parsing-worker, webhook-worker, index-worker for independent scaling
- **Multi-AZ**: RDS `multi_az = true`, ECS across 2 AZs for Q2 production HA
- **Docker image scanning**: Trivy or ECR native scanning in `deploy.yml`
- **MCP authentication wrapper**: Q2 — add token auth layer before network-exposing the MCP server
- **Multi-tenancy in MCP**: `LABLINK_MCP_ORG_ID` env var; remove hardcoded `00000000-...` org
- **TF 1.11 migration**: Replace DynamoDB locking with `use_lockfile = true` in backend config

---

## Implementation Order

1. `.dockerignore` (prerequisite for Dockerfiles)
2. `llms.txt` + `llms-full.txt` (fastest, validate API surface understanding)
3. `Dockerfile` + `Dockerfile.worker` (self-contained, testable locally)
4. `docs/docs.json` + all 5 MDX files (reference `llms-full.txt` while writing)
5. `infra/main.tf` → `infra/vpc.tf` → `infra/s3.tf` → `infra/rds.tf` → `infra/redis.tf` → `infra/elasticsearch.tf` → `infra/ecs.tf`
6. `.github/dependabot.yml`
7. `.github/workflows/ci.yml` → `.github/workflows/deploy.yml`

---

## Sources & References

### Internal References
- MCP server toolsets: `src/lablink/mcp/server.py:34-70` — `_TOOLSETS` dict with all 25 tools
- FastAPI app factory: `src/lablink/main.py` — entry point, health check path `/health`
- Error schema: `src/lablink/schemas/envelope.py` — `ErrorDetail` with `suggestion`, `retry`, `retry_after`
- Product roadmap Week 7: `docs/product-specs/lablink-product-roadmap.md:1043-1062`
- Existing GitHub workflows: `.github/workflows/release.yml`, `.github/workflows/garden-ci.yml`

### External References
- Mintlify v3 docs.json schema: https://mintlify.com/docs/settings/global
- Mintlify upgrade guide: https://mintlify.com/docs/migration/v3
- llmstxt.org spec: https://llmstxt.org/
- Terraform AWS ECS: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service
- Terraform AWS OpenSearch: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/opensearch_domain
- Terraform AWS ElastiCache Replication Group: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/elasticache_replication_group
- GitHub OIDC with AWS: https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services
- GHA action pinning (supply chain): https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions
- Docker BuildKit GHA cache: https://docs.docker.com/build/cache/backends/gha/

### Related Work
- Completed: `docs/execution-plans/completed/feat-complete-weeks-5-6-tests-and-ci.md`
- Roadmap: `docs/product-specs/lablink-product-roadmap.md`
