# pages Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the frontend page components.
> Keep this under 150 lines. Global patterns live in docs/FRONTEND.md.

## Purpose

Top-level page components, one per route. Pages own data fetching (via `@/api` hooks), orchestrate layout, and compose domain components. Current pages: Dashboard, Experiments, Uploads, Search, Agents, Login, Register.

## Patterns

- **Pages own data fetching**: Call `@/api` hooks here, pass data down to components as props.
- **One file per route**: `DashboardPage.tsx` → `/dashboard`, `ExperimentsPage.tsx` → `/experiments`, etc.
- **Use layout components**: Wrap page content in the appropriate layout from `components/layout/`.
- **Loading + error states**: Every page must handle loading and error states from its hooks — don't render partial data without a loading indicator.

## Coding Conventions

- Filenames: `{Name}Page.tsx` convention — always suffix with `Page`.
- Named exports, not default exports.
- Keep pages thin: minimal logic, mostly composition of components and hooks.
- Route definitions live outside this directory (in the router config) — pages do not know their own URLs.

## What Belongs Here

- One page component per application route.
- Data fetching via hooks from `@/api`.
- Top-level state (e.g., selected item, open modal) that spans multiple child components on the page.
- Page-level error boundaries if needed.

## What Doesn't Belong Here

- Reusable UI components — those live in `components/`.
- API client logic — that lives in `@/api`.
- Routing configuration — that lives in the router setup (e.g., `main.tsx` or a routes file).

## Key Dependencies

- `react`
- `@/api` hooks for data fetching
- `components/layout/` for page shell
- Domain components from `components/`

## Testing Approach

Integration tests with Vitest + Testing Library. Render the full page with a mocked router context and mocked `@/api` hooks. Test that loading, success, and error states render correctly. Tests live in `__tests__/` inside this directory.

## Related Docs

- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
