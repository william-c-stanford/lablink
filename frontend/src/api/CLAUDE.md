# api Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `api` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Type-safe API client for the LabLink frontend. Provides a single entry point for all backend HTTP communication, built on `openapi-fetch` with types auto-generated from the backend's OpenAPI spec. Also manages JWT tokens (in-memory) and Server-Sent Events (SSE) connections.

## Architecture Within This Module

- `client.ts` — Core API client, token management, auth middleware, `uploadFile()` helper, `openSSEConnection()`
- `schema.d.ts` — Auto-generated TypeScript types from `openapi.json` (do NOT edit manually)
- `index.ts` — Barrel export: `apiClient`, `uploadFile`, `openSSEConnection`, token helpers, `unwrapResponse`
- `hooks/` — React Query hooks that wrap `apiClient` calls
- `hooks.ts` — Alternative/additional hooks file

## Coding Conventions

- **Import from `@/api`**: Always import from the barrel (`import { apiClient } from '@/api'`), not from `./client` directly.
- **Never use `localStorage` for tokens**: The auth token is stored in the module-level variable in `client.ts`. Never persist to localStorage — security risk.
- **Type-safe paths**: Use `apiClient.GET('/experiments')` with the exact OpenAPI path string. TypeScript will enforce correct parameters and response shapes.
- **`unwrapResponse()`**: Use this helper to safely extract data from the `Envelope[T]` wrapper and throw on errors.
- **Auto-generated types**: `schema.d.ts` is generated from the backend OpenAPI spec. To update it, re-run the generator — never hand-edit.

## Patterns

**Standard API call**:
```ts
import { apiClient, unwrapResponse } from '@/api'

// Type-safe GET
const { data, error } = await apiClient.GET('/experiments/{experiment_id}', {
  params: { path: { experiment_id: id } }
})

// Or with unwrapResponse for automatic error throwing
const experiment = await unwrapResponse(
  apiClient.GET('/experiments/{experiment_id}', { params: { path: { experiment_id: id } } })
)
```

**File upload** (multipart):
```ts
import { uploadFile } from '@/api'
const upload = await uploadFile({ file, organizationId, projectId })
```

**SSE connection** (for real-time events):
```ts
import { openSSEConnection } from '@/api'
const close = openSSEConnection('/events', {
  onMessage: (event) => eventStore.addEvent(event),
  onError: () => eventStore.setDisconnected(),
})
```

**React Query hook** (in `hooks/`):
```ts
export function useExperiments(filters: ExperimentFilters) {
  return useQuery({
    queryKey: ['experiments', filters],
    queryFn: () => unwrapResponse(apiClient.GET('/experiments', { params: { query: filters } }))
  })
}
```

**Token management**:
```ts
import { setAccessToken, clearAccessToken, getAccessToken } from '@/api'
setAccessToken(token)  // After login/refresh
clearAccessToken()     // On logout
```

## Key Types and Interfaces

- `paths` (`schema.d.ts`) — All API path types, parameters, and responses (auto-generated)
- `components` (`schema.d.ts`) — All schema component types (auto-generated)
- `ApiResponse<T>` (`client.ts`) — `{ data?: T, error?: ErrorDetail[] }`
- `UploadFileOptions` (`client.ts`) — Options for `uploadFile()`
- `SSEOptions` (`client.ts`) — Options for `openSSEConnection()`

## What Belongs Here

- API client configuration and middleware
- Token management functions
- `uploadFile()` helper for multipart uploads
- `openSSEConnection()` helper for SSE
- React Query hooks that wrap API calls
- `schema.d.ts` (auto-generated, never hand-edited)

## What Does Not Belong Here

- Business logic or state management (use `store/`)
- UI components (use `components/`)
- Direct `fetch()` calls bypassing `apiClient`
- Auth flow logic beyond token storage (use `store/authStore.ts`)

## Key Dependencies

- `openapi-fetch` — Type-safe fetch client (`createClient<paths>()`)
- Generated `paths` type from `schema.d.ts`
- `@tanstack/react-query` — for hooks in `hooks/`

## Testing Approach

Mock at the fetch level using `vi.mock` or MSW (Mock Service Worker). Test that `authMiddleware` injects `Authorization` headers correctly. Test that `unwrapResponse` throws on error envelopes. Test hooks using `renderHook` from React Testing Library.

## Common Gotchas

- **`schema.d.ts` is auto-generated**: Any manual change will be overwritten next time `npm run generate-types` runs. Change the backend OpenAPI spec instead, then regenerate.
- **Concurrent 401 refresh**: The `authMiddleware` deduplicates concurrent 401 responses via `refreshPromise`. Don't add additional refresh logic in hooks.
- **SSE requires explicit close**: `openSSEConnection()` returns a cleanup function. Call it in `useEffect` cleanup or the connection will leak.
- **Token in-memory only**: If the user refreshes the page, the token is gone. The `authStore` handles silent re-authentication on mount.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
