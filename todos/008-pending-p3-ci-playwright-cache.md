---
status: pending
priority: p3
issue_id: "008"
tags: [code-review, ci, performance]
dependencies: []
---

# Playwright Chromium Binary Not Cached in CI — 60-120s per Run

## Problem Statement

The CI E2E job runs `playwright install chromium --with-deps` on every run, downloading ~130MB of Chrome + system dependencies. No `actions/cache` step wraps `~/.cache/ms-playwright`. This adds 60-120 seconds to every E2E CI run unnecessarily.

## Proposed Solution

Add a cache step in `.github/workflows/ci.yml` before the Playwright install:

```yaml
      - name: Cache Playwright browsers
        uses: actions/cache@v4
        id: playwright-cache
        with:
          path: ~/.cache/ms-playwright
          key: playwright-chromium-${{ hashFiles('pyproject.toml') }}

      - name: Install Playwright browsers
        run: playwright install chromium --with-deps
        if: steps.playwright-cache.outputs.cache-hit != 'true'
```

**Effort:** Tiny — 8 lines of YAML
**Expected savings:** 60-120s per CI E2E run

## Acceptance Criteria

- [ ] Playwright browsers cached between CI runs
- [ ] Cache key invalidates when `pyproject.toml` changes (Playwright version change)
- [ ] E2E CI job still passes

## Work Log

- 2026-03-09: Created during code review — performance reviewer surfaced this optimization
