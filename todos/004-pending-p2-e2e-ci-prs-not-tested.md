---
status: pending
priority: p2
issue_id: "004"
tags: [code-review, ci, e2e, devops]
dependencies: []
---

# E2E Tests Only Run on Main Branch Push — Not on PRs

## Problem Statement

The CI E2E job is configured to run only on `push` to `main`:

```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

This means E2E failures are discovered only after merging to main, not during PR review. This is backwards — CI catches bugs before merge, not after.

## Findings

`.github/workflows/ci.yml`:
```yaml
  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

The PR comment in the commit message says: "CI job on main merges only" — this was intentional (E2E tests require browser infrastructure and take longer). However, this creates a window where E2E regressions are invisible during PR review.

## Proposed Solutions

### Option 1: Run E2E on all PRs (Recommended long-term)

Remove the `if:` condition and let E2E run on all pushes:

```yaml
  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    # No if: condition — runs on all pushes and PRs
```

**Pros:** Catches regressions before merge
**Cons:** Adds ~3-5 minutes to every PR; requires GitHub Actions minutes budget
**Effort:** Trivial
**Risk:** Low

### Option 2: Run on PRs but allow failure

Run E2E on PRs but mark as non-blocking:

```yaml
  e2e:
    name: E2E Tests (non-blocking on PRs)
    runs-on: ubuntu-latest
    continue-on-error: ${{ github.event_name == 'pull_request' }}
```

**Pros:** Shows E2E status on PRs without blocking; E2E must pass on main
**Cons:** Developers may ignore non-blocking failures
**Effort:** Trivial
**Risk:** Low

### Option 3: Run E2E on PRs labeled `[e2e]`

Opt-in E2E on PRs when the PR title contains `[e2e]` or has a specific label:

```yaml
if: |
  (github.event_name == 'push' && github.ref == 'refs/heads/main') ||
  (github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'run-e2e'))
```

**Pros:** Opt-in for E2E-touching PRs; saves CI minutes
**Cons:** Requires discipline to add label; can miss regressions
**Effort:** Small
**Risk:** Low

### Option 4: Keep as-is

Main-only E2E is acceptable for an MVP project. The 1,423 unit tests catch most regressions.

## Recommended Action

Option 2 or Option 3. Option 3 is a good pragmatic middle ground: E2E always runs on main, and PR authors can opt into it with a label. Add to branch protection rules: E2E must pass on main before any new merge.

## Technical Details

- Affected file: `.github/workflows/ci.yml`
- Current E2E run time: ~3-5 minutes per run
- GitHub-hosted runners: ubuntu-latest includes Chrome

## Acceptance Criteria

- [ ] E2E failures are visible before (or at) merge time, not only after
- [ ] PR authors can determine E2E pass/fail status before requesting review

## Work Log

- 2026-03-09: Created during code review of feat/week7-docs-and-infrastructure
