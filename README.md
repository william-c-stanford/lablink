# LabLink

Agent-native lab data integration platform. Connects instruments, parses data, and exposes everything to AI agents via MCP.

## Local Quickstart (no Docker, no AWS)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`
- Node.js 18+

### Setup

```bash
# 1. Clone and install
git clone https://github.com/william-c-stanford/lablink.git
cd lablink
uv sync --all-extras

# 2. Copy environment config (defaults work out of the box)
cp .env.example .env.local

# 3. Run database migrations
make migrate

# 4. Seed demo data (optional — creates demo@lablink.local / demodemo)
make seed

# 5. Start API + frontend together
make dev-local
```

Open [http://localhost:5173](http://localhost:5173) and log in with `demo@example.com` / `demodemo`.

> The app runs fully on SQLite + local filesystem storage — no Redis, Elasticsearch, or S3 needed.

## Commands

| Command | Description |
|---|---|
| `make dev-local` | Start API + frontend together (honcho) |
| `make dev` | Start API server only |
| `make test` | Run unit + integration tests |
| `make e2e` | Run end-to-end browser tests |
| `make lint` | Ruff + mypy |
| `make format` | Auto-format with ruff |
| `make migrate` | Run Alembic migrations |
| `make seed` | Load demo data |
| `make check-ports` | Verify ports 8000 / 5173 are free |

## Running E2E Tests

```bash
# First time: install Playwright browsers
uv run playwright install chromium

# Run all E2E tests
make e2e
```

Tests start the API and frontend automatically, seed the database, run all scenarios headlessly, and tear everything down.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full stack overview.

## Documentation

| Doc | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Stack, data flow, deployment |
| [docs/DESIGN.md](docs/DESIGN.md) | Design philosophy |
| [docs/SECURITY.md](docs/SECURITY.md) | Auth patterns, threat model |
| [docs/FRONTEND.md](docs/FRONTEND.md) | Frontend conventions |

## Stack

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic
- **Dev mode**: SQLite + local filesystem (no infra needed)
- **Prod mode**: PostgreSQL / Redis / Elasticsearch / S3
- **Frontend**: React 19 / TypeScript / TanStack Router + Query / Tailwind / Plotly.js
- **MCP Server**: FastMCP (25 tools across 4 toolsets)
- **E2E**: Playwright (Python)
