  Interview Summary: LabLink Backend Build

  What we're building: The complete Python backend for LabLink — an agent-native lab data integration platform.

  Scope decisions:
  1. Backend only — FastAPI app, models, schemas, services, parsers, tasks, MCP server
  2. SQLite + mocks — No Docker dependency for dev. Mock S3, ES, Redis.
  3. Own parsers — Custom CSV/XML parsers outputting canonical ASM-compatible model. No allotropy dep yet.
  4. Sync task fallback — Tasks run inline in dev mode. Celery config present but optional.
  5. Realistic fixtures — Instrument data files mimicking real NanoDrop, plate reader, HPLC, PCR, balance output.
  6. MCP server included — FastMCP with 25 curated tools across 4 toolsets + 2 discovery tools.

  Key files (~60+): All models, schemas, routers, services, parsers, tasks, MCP server, migrations, tests, fixtures, config files (pyproject.toml, docker-compose.yml,
  Makefile, CLAUDE.md).