---
status: pending
priority: p2
issue_id: "002"
tags: [code-review, security, e2e, subprocess]
dependencies: []
---

# E2E conftest Passes Full `os.environ` to API Subprocess

## Problem Statement

In `tests/e2e/conftest.py`, the API server subprocess is started with `env = {**os.environ, "LABLINK_DATABASE_URL": ...}` which inherits every environment variable from the developer's shell — including any real `LABLINK_SECRET_KEY`, `AWS_*` credentials, database passwords, or API keys in their environment. This means:

1. Tests run against a non-isolated configuration (developer's real secret key, real Redis URL, etc.)
2. If the developer has real cloud credentials, the test API server could make real external calls
3. On CI, any secrets in the environment are forwarded to the subprocess unnecessarily

## Findings

```python
# tests/e2e/conftest.py (current)
env = {**os.environ, "LABLINK_DATABASE_URL": f"sqlite+aiosqlite:///{DB_PATH}"}
api_proc = subprocess.Popen(
    ["uv", "run", "uvicorn", "lablink.main:app", ...],
    env=env,  # ← inherits everything from shell
    ...
)
```

The seed script has a similar issue:
```python
subprocess.run(["uv", "run", "python", "-m", "lablink.scripts.seed"],
               env=env, ...)
```

## Proposed Solutions

### Option 1: Explicit minimal env dict (Recommended)

Pass only what the process needs, derived from a known-safe baseline:

```python
import sys

MINIMAL_ENV = {
    # System paths — needed for subprocess to find executables
    "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "USER": os.environ.get("USER", ""),
    # Python/uv context
    "UV_PROJECT_ENVIRONMENT": os.environ.get("UV_PROJECT_ENVIRONMENT", ""),
    "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
    # LabLink config — safe defaults for E2E
    "LABLINK_DATABASE_URL": f"sqlite+aiosqlite:///{DB_PATH}",
    "LABLINK_SECRET_KEY": "e2e-test-secret-not-for-production",
    "LABLINK_CORS_ORIGINS": '["http://localhost:5173"]',
    "LABLINK_TASK_BACKEND": "sync",
    "LABLINK_STORAGE_BACKEND": "local",
    "LABLINK_SEARCH_BACKEND": "memory",
    "LABLINK_ENVIRONMENT": "test",
}
```

**Pros:** Fully isolated, reproducible, no accidental cloud calls
**Effort:** Small
**Risk:** Medium — may miss an env var the app needs; test carefully

### Option 2: Allowlist approach — filter `os.environ`

Pass `os.environ` but remove known-sensitive prefixes:

```python
BLOCKED_PREFIXES = ("AWS_", "LABLINK_SECRET", "DATABASE_URL", "REDIS_URL", "ELASTICSEARCH_")
env = {
    k: v for k, v in os.environ.items()
    if not any(k.startswith(p) for p in BLOCKED_PREFIXES)
}
env["LABLINK_DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
env["LABLINK_SECRET_KEY"] = "e2e-test-secret"
```

**Pros:** Less likely to miss needed env vars
**Cons:** Allowlisting is error-prone; new secrets won't be blocked
**Effort:** Small
**Risk:** Medium

### Option 3: Keep as-is with documentation

Add a comment explaining the inheritance. Acceptable for dev-only E2E tests that already require local services.

**Pros:** Zero effort
**Cons:** Security hygiene issue; non-reproducible test behavior

## Recommended Action

Option 1 for CI hardening. The config defaults in `lablink.config` already default to SQLite/local/sync, so passing `LABLINK_DATABASE_URL` + `LABLINK_SECRET_KEY` + PATH should be sufficient. Test locally first to confirm no missing env vars.

## Technical Details

- Affected file: `tests/e2e/conftest.py` lines ~85-110
- No frontend changes needed
- Verify the app starts cleanly with minimal env by running `make e2e` after change

## Acceptance Criteria

- [ ] API subprocess does not inherit real cloud credentials from shell
- [ ] E2E suite still passes with explicit env dict
- [ ] CI E2E job passes

## Work Log

- 2026-03-09: Created during code review of feat/week7-docs-and-infrastructure
