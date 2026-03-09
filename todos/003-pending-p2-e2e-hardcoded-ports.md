---
status: pending
priority: p2
issue_id: "003"
tags: [code-review, e2e, reliability, infrastructure]
dependencies: []
---

# E2E Tests Use Hardcoded Ports 8000/5173 — Conflicts with Running Dev Server

## Problem Statement

The E2E conftest hardcodes ports 8000 (API) and 5173 (Vite). If a developer is already running `make dev-local` or `uvicorn` in another terminal, the E2E session-start code kills those processes via:

```python
for port in (8000, 5173):
    _sub.run(f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true", shell=True)
```

This silently kills the developer's running dev server whenever they run `make e2e`. Additionally, any other service on these common ports fails the E2E session startup.

## Findings

`tests/e2e/conftest.py`:
```python
API_BASE_URL = "http://localhost:8000"
E2E_BASE_URL = "http://localhost:5173"

for port in (8000, 5173):
    _sub.run(f"lsof -ti:{port} | xargs kill -9 2>/dev/null || true", shell=True)
```

Also hardcoded in:
- `tests/e2e/test_auth.py` — imports `E2E_BASE_URL` from conftest
- `Makefile` — `make e2e` doesn't set alternative ports
- CI workflow — relies on default ports

## Proposed Solutions

### Option 1: Use different ports for E2E (Recommended — minimal change)

Use non-conflicting ports that are unlikely to be in use:
```python
API_BASE_URL = os.environ.get("E2E_API_URL", "http://localhost:8765")
E2E_BASE_URL = os.environ.get("E2E_FE_URL", "http://localhost:5174")
```

Update the Makefile `e2e` target to export these, and update the frontend Vite port in the subprocess call. No `kill -9` needed if using ports that aren't used by `make dev-local`.

**Pros:** Dev server coexists with E2E; no destructive `kill -9`
**Effort:** Small
**Risk:** Low — just port numbers

### Option 2: Dynamic port allocation

Use `socket.bind(("", 0))` to get OS-assigned free ports, pass them to subprocesses as env vars:

```python
import socket

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]

API_PORT = _free_port()
FE_PORT = _free_port()
API_BASE_URL = f"http://localhost:{API_PORT}"
```

**Pros:** Guaranteed no conflict
**Cons:** More complex; ports can't be configured via env
**Effort:** Medium
**Risk:** Low

### Option 3: Keep as-is

The `kill -9` is documented behavior; developers know to stop their dev server before running E2E.

**Pros:** Zero effort
**Cons:** Destroys developer's running session silently; bad DX

## Recommended Action

Option 1 — use ports 8765/5174 for E2E, remove the `kill -9` loop, add a check that the ports are free and emit a clear error if not.

## Technical Details

- Affected: `tests/e2e/conftest.py`, `Makefile`, CI workflow
- The `kill -9` loop (line ~73-76 in conftest) should become a "port-in-use" error or simply be removed if using non-conflicting ports

## Acceptance Criteria

- [ ] `make dev-local` and `make e2e` can run simultaneously without killing each other
- [ ] E2E suite passes on non-conflicting ports
- [ ] Error message is clear if E2E ports are already in use

## Work Log

- 2026-03-09: Created during code review of feat/week7-docs-and-infrastructure
