# pages Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `pages` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Page-level React components — one per application route. Pages are the top-level containers that compose feature components from `components/`. Each page corresponds to a URL route registered in the React Router config.

## Architecture Within This Module

Current pages:
- `DashboardPage.tsx` — Overview: recent uploads, experiment summary, system stats
- `ExperimentsPage.tsx` — Experiment list, creation, filtering
- `UploadsPage.tsx` — Upload list, file upload form, parse status
- `SearchPage.tsx` — Full-text search across instruments and data
- `AgentsPage.tsx` — MCP agent status and tool listing
- `LoginPage.tsx` — Auth form (unauthenticated route)
- `RegisterPage.tsx` — Registration form (unauthenticated route)

## Coding Conventions

- **Pages are thin**: One page = one route. Pages orchestrate components, not implement them. If a page grows beyond ~100 lines of JSX, extract components.
- **Named exports**: `export function DashboardPage() {...}`. Match filename exactly.
- **Route-level code splitting**: Pages should be wrapped with `React.lazy()` at the router level to enable automatic code splitting.
- **Auth guard at route level**: Protected pages don't implement their own auth checks — the router handles redirecting unauthenticated users.
- **Page-level document title**: Each page should set a descriptive `document.title` (or via a `useTitle` hook).

## Patterns

**Standard page structure**:
```tsx
// pages/ExperimentsPage.tsx
import { ExperimentList } from '@/components/experiments/ExperimentList'
import { ExperimentFiltersPanel } from '@/components/experiments/ExperimentFiltersPanel'
import { PageHeader } from '@/components/layout/PageHeader'

export function ExperimentsPage() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader title="Experiments" />
      <ExperimentFiltersPanel />
      <ExperimentList />
    </div>
  )
}
```

**Auth pages** (no auth guard, different layout):
```tsx
export function LoginPage() {
  // Uses unauthenticated layout (no sidebar/header)
  return (
    <div className="min-h-screen flex items-center justify-center">
      <LoginForm />
    </div>
  )
}
```

## Key Types and Interfaces

- None specific to this module — pages compose typed components from `components/`

## What Belongs Here

- Route-level component definitions
- Top-level layout composition for each page
- Page-specific SEO/title setting

## What Does Not Belong Here

- Feature component logic (use `components/`)
- Data fetching (use hooks in components or via `@/api/hooks`)
- State management (use `store/`)
- Navigation/routing config (use the router config file in `src/`)

## Key Dependencies

- `react-router-dom` — `useParams`, `useNavigate` if needed
- `@/components/*` — Feature components composed in each page
- `@/components/layout` — App shell layout components

## Testing Approach

Page-level tests are integration tests — render the full page with router and store providers, verify that the right feature components appear. Mock API hooks at the module level. Page tests should be sparse — rely on component-level tests for detailed coverage.

Test files in `__tests__/` adjacent to the pages directory.

## Common Gotchas

- **Don't fetch data in pages**: Pages compose components; data fetching belongs in the components or their hooks.
- **Auth check is router-level**: Don't add `if (!user) return <Navigate to="/login" />` inside pages — this is handled by the route guard wrapper.
- **File naming**: Page files must end in `Page.tsx` and export a function with the same name. This is a convention the router config depends on.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
