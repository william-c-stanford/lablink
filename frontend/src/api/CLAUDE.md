# api Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the frontend API client layer.
> Keep this under 150 lines. Global patterns live in docs/FRONTEND.md.

## Purpose

Type-safe API client for the LabLink backend REST API. Built on `openapi-fetch` using TypeScript types auto-generated from the backend OpenAPI spec (`openapi.json` → `schema.d.ts`). Also exposes typed React hooks and SSE connection helpers.

## Patterns

- **Single import point**: All consumers import from `@/api` (the barrel `index.ts`) — never import `client.ts` directly.
- **openapi-fetch**: `apiClient.GET('/path')`, `apiClient.POST('/path', { body })` — fully typed against `schema.d.ts`. Never use raw `fetch`.
- **Envelope unwrapping**: Use `unwrapResponse(result)` to extract `data` and surface `errors` — every backend response is `{ data, meta, errors }`.
- **Token management**: Tokens are in-memory only (`setAccessToken` / `getAccessToken`). Never store in `localStorage`.
- **SSE**: Use `openSSEConnection(path)` for server-sent event streams — don't construct `EventSource` directly.

## Coding Conventions

- Re-export everything through `index.ts`. Add new exports there when adding client utilities.
- `schema.d.ts` is auto-generated — do not edit manually. Regenerate via `npm run generate-types` after backend schema changes.
- Hooks live in `hooks/` and `hooks.ts` — one hook per domain (e.g., `useExperiments`, `useUploads`).
- Hook tests live in `__tests__/` — use `msw` for API mocking, not `vi.spyOn(apiClient, ...)`.

## What Belongs Here

- The `apiClient` instance and auth token management.
- `unwrapResponse` and other response helpers.
- `openSSEConnection` and streaming utilities.
- Domain-specific React hooks that fetch/mutate via `apiClient`.
- The generated `schema.d.ts` type definitions.

## What Doesn't Belong Here

- UI components — those live in `components/`.
- Page-level data fetching logic — use hooks from this module in `pages/`.
- Business logic or data transformation — keep hooks thin; transform in components if needed.

## Key Dependencies

- `openapi-fetch` — typed fetch client
- `react` (for hooks)
- Backend OpenAPI spec at `frontend/openapi.json`

## Testing Approach

Hook tests in `__tests__/`. Mock the API layer with `msw` (Mock Service Worker). Test loading, success, and error states for each hook.

## Related Docs

- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
