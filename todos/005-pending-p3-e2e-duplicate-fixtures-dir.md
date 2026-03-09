---
status: pending
priority: p3
issue_id: "005"
tags: [code-review, quality, e2e]
dependencies: []
---

# Duplicate `FIXTURES_DIR` Path in test_uploads.py vs conftest.py

## Problem Statement

`tests/e2e/test_uploads.py` defines its own `FIXTURES_DIR` path constant that duplicates path construction logic from `tests/e2e/conftest.py`. If the fixtures directory moves, both places need updating.

## Findings

`tests/e2e/test_uploads.py`:
```python
FIXTURES_DIR = (
    Path(__file__).parent.parent.parent / "tests" / "fixtures"
)
```

`tests/e2e/conftest.py`:
- Uses `PROJECT_ROOT` which is `Path(__file__).parent.parent.parent`
- The same path is implied but not exposed as a constant

Note: The path in `test_uploads.py` also has an extra `"tests/"` segment since `__file__` is already inside `tests/e2e/`, making the resolved path `tests/tests/fixtures/` — this is likely a bug that happens to work because Playwright doesn't validate the path until `upload_file()` is called.

Wait, let me re-check: `Path(__file__).parent.parent.parent` from `tests/e2e/test_uploads.py` would be:
- `__file__` = `tests/e2e/test_uploads.py`
- `.parent` = `tests/e2e/`
- `.parent` = `tests/`
- `.parent` = project root `/`
- `/ "tests" / "fixtures"` = `tests/fixtures/` ✓ — actually correct

But it's still duplicated from what could be a shared constant.

## Proposed Solutions

### Option 1: Export `FIXTURES_DIR` from conftest (Recommended)

In `tests/e2e/conftest.py`:
```python
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
```

In `tests/e2e/test_uploads.py`:
```python
from tests.e2e.conftest import FIXTURES_DIR
```

**Effort:** Tiny
**Risk:** None

### Option 2: Use a shared `tests/conftest.py` constant

The main `tests/conftest.py` likely already defines fixture paths. Add `FIXTURES_DIR` there.

**Effort:** Tiny
**Risk:** None

### Option 3: Keep as-is (acceptable for P3)

Two lines of path construction — trivial duplication, not worth the import dependency.

## Recommended Action

Option 1 — one line change. Easy cleanup when touching this area.

## Acceptance Criteria

- [ ] `FIXTURES_DIR` defined once and imported where needed
- [ ] E2E uploads tests still pass

## Work Log

- 2026-03-09: Created during code review of feat/week7-docs-and-infrastructure
