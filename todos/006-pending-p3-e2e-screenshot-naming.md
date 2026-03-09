---
status: pending
priority: p3
issue_id: "006"
tags: [code-review, quality, e2e, ci]
dependencies: []
---

# E2E Screenshot on Failure Uses Fixed Path — Multiple Failures Overwrite Each Other

## Problem Statement

The `auth_page` fixture saves a screenshot on failure to a fixed path `/tmp/e2e-auth-failure.png`. If multiple tests fail, each overwrites the previous screenshot. The CI artifact upload glob `e2e-failure-*.png` matches `helpers.py`'s pattern but not the conftest fixture's path.

## Findings

`tests/e2e/conftest.py` (auth_page fixture):
```python
page.screenshot(path="/tmp/e2e-auth-failure.png")
```

`tests/e2e/helpers.py` (screenshot_on_failure helper):
```python
path = f"/tmp/e2e-failure-{name}.png"
```

CI upload glob:
```yaml
path: /tmp/e2e-failure-*.png
```

The `auth_page` screenshot uses `e2e-auth-failure.png` which does NOT match the CI glob `e2e-failure-*.png`. The artifact upload will miss it.

## Proposed Solutions

### Option 1: Use consistent naming + test identity in path

```python
# In auth_page fixture:
import time
page.screenshot(path=f"/tmp/e2e-failure-auth-{int(time.time())}.png")
```

This matches the CI glob and includes a timestamp to prevent overwrites.

### Option 2: Pass test name via pytest request fixture

```python
@pytest.fixture()
def auth_page(page: Page, request: pytest.FixtureRequest) -> Page:
    ...
    except Exception:
        test_name = request.node.name.replace("/", "_")
        page.screenshot(path=f"/tmp/e2e-failure-{test_name}.png")
        raise
```

**Pros:** Named after the failing test for easy identification
**Effort:** Tiny
**Risk:** None

## Recommended Action

Option 2 — use `request.node.name` for the screenshot path. Also update the `auth_page` fixture signature to accept `request`.

## Acceptance Criteria

- [ ] Screenshot path matches CI artifact glob `e2e-failure-*.png`
- [ ] Multiple test failures produce separate screenshots
- [ ] Screenshot filename identifies which test failed

## Work Log

- 2026-03-09: Created during code review of feat/week7-docs-and-infrastructure
