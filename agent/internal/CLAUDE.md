# internal Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the Go desktop agent internals.
> Keep this under 150 lines. Global patterns live in docs/DESIGN.md.

## Purpose

Go packages implementing the LabLink desktop agent — a lightweight background process that watches lab instrument output directories and uploads new files to the LabLink API. Packages: `watcher`, `uploader`, `queue`, `heartbeat`, `updater`, `config`.

## Directory Layout

```
internal/
  watcher/   # fsnotify-based file system watcher (detects new instrument files)
  uploader/  # HTTP client that POSTs files to the LabLink upload API
  queue/     # Persistent retry queue (BBolt) for uploads that fail
  heartbeat/ # Periodic health ping to the LabLink API (agent registration)
  updater/   # Self-update logic (checks for new agent versions)
  config/    # Agent configuration (watched dirs, API URL, org token)
```

## Patterns

- **Package per concern**: Each subdirectory is a single-responsibility package. No circular imports.
- **BBolt for persistence**: The `queue/` package uses BBolt for durable upload queuing — survives agent restarts.
- **fsnotify events**: `watcher/` filters events to `CREATE` and `WRITE` + debounce. Ignore temp files (`.tmp`, `~`).
- **Retry with backoff**: Failed uploads are queued and retried with exponential backoff in `queue/`.
- **Config from file + env**: `config/` reads from a TOML/JSON config file, with env var overrides (`LABLINK_*`).

## Coding Conventions

- Standard Go: `gofmt`, package names lowercase single word matching directory name.
- Errors returned, not panicked — agent must never crash on a bad file or failed upload.
- Each package has `_test.go` files. Use `httptest.NewServer` for uploader tests.
- Interfaces over concrete types for testability (e.g., `Uploader` interface, not just the struct).

## What Belongs Here

- File watching, upload, queue, heartbeat, updater, and config logic.
- All agent behavior that runs in the background process.

## What Doesn't Belong Here

- CLI flag parsing — that lives in `agent/cmd/` or `agent/main.go`.
- UI or interactive output — the agent is headless.
- API schema definitions — those are generated from the backend OpenAPI spec.

## Key Dependencies

- `github.com/fsnotify/fsnotify` — cross-platform file system events
- `go.etcd.io/bbolt` — embedded key-value store for the upload queue
- `net/http` stdlib — HTTP client for uploads and heartbeat
- `github.com/BurntSushi/toml` or similar — config file parsing

## Testing Approach

Unit tests per package with `_test.go` files. Use `httptest.NewServer` to mock the LabLink API for uploader and heartbeat tests. Watcher tests use temp directories. Run with `go test ./...` from the `agent/` directory.

## Related Docs

- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/DESIGN.md](../../docs/DESIGN.md)
