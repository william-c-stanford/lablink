# Frontend

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-09 -->

> Frontend conventions, component patterns, and styling approach.

## Stack

React 18 + TypeScript + Tailwind CSS + Vite + Zustand + openapi-fetch + Plotly.js

## Component Conventions

Components live under `frontend/src/components/` organized by feature: `dashboard/`, `experiments/`, `uploads/`, `search/`, `charts/`, `layout/`, `ui/`.

- Feature components in feature dirs: `experiments/ExperimentList.tsx`
- Shared UI primitives in `ui/`: buttons, modals, badges, etc.
- Page-level components in `pages/`: one per route (`DashboardPage.tsx`, `ExperimentsPage.tsx`, etc.)
- Pages compose feature components, not business logic

## Styling Approach

Tailwind CSS utility classes. No CSS modules or styled-components. Component-level className composition via `clsx`/`cn` utilities.

## State Management

Zustand stores in `frontend/src/store/`:
- `authStore` — JWT tokens (in-memory, never localStorage), user profile, refresh logic
- `uiStore` — toasts, modals, sidebar state
- `filterStore` — upload/experiment/search filter state
- `eventStore` — SSE events from server-sent events stream

Import from the barrel: `import { useAuthStore } from '@/store'`

Do NOT store auth tokens in localStorage. The `authStore` keeps them in memory only.

## Data Fetching

`openapi-fetch` typed client in `frontend/src/api/client.ts`. Types auto-generated from the backend OpenAPI spec into `schema.d.ts`.

```ts
import { apiClient } from '@/api'
const { data, error } = await apiClient.GET('/experiments')
```

The client injects Bearer tokens automatically via `authMiddleware`. On 401, it auto-refreshes (deduplicated with a shared promise).

Custom React Query hooks live in `frontend/src/api/hooks/` (or `hooks.ts`) — wrap `apiClient` calls, handle loading/error states.

## Testing

Component tests with Vitest + React Testing Library. Test files in `__tests__/` directories adjacent to the components they test. API client mocked at the `fetch` level.

E2E tests in `tests/e2e/` use Playwright to drive the full stack (API + Vite dev server). Run via `make e2e`. E2E tests are excluded from `make test`.

## Dev Server Configuration

Vite proxies `/api/*` requests to the backend. The proxy target defaults to `http://localhost:8000` but can be overridden via the `VITE_API_BASE_URL` environment variable (used by `make e2e` to point at the E2E API port). Set in `vite.config.ts`: `target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000"`.

## Performance Guidelines

- Code-split at the page level (React.lazy + Suspense)
- Charts rendered with Plotly.js — lazy-load the Plotly bundle
- SSE connection managed in `eventStore` — one connection per session
