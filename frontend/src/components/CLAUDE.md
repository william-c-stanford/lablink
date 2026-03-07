# components Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Local coding conventions for the frontend component library.
> Keep this under 150 lines. Global patterns live in docs/FRONTEND.md.

## Purpose

Shared React components organized by domain. Includes a `ui/` primitives layer (buttons, cards, inputs, badges, data tables) and domain-specific components for charts, dashboard, experiments, uploads, search, and layout.

## Directory Layout

```
components/
  ui/          # Primitive UI components (no domain logic)
  charts/      # Plotly.js chart wrappers
  dashboard/   # Dashboard widgets and summary cards
  experiments/ # Experiment list, detail, and form components
  uploads/     # Upload dropzone, status, and list components
  search/      # Search bar and result components
  layout/      # App shell, nav, sidebar, header
```

## Patterns

- **ui/ primitives first**: Build domain components from `ui/` primitives (Button, Card, Input, etc.). Do not add domain logic to `ui/` components.
- **Co-located tests**: Component tests live in `__tests__/` within each subdirectory. Use Vitest + Testing Library.
- **Props over state**: Prefer controlled components (props + callbacks) over internal state for testability.
- **No API calls in components**: Data fetching belongs in `pages/` or hooks from `@/api`. Components receive data as props.

## Coding Conventions

- Filenames: PascalCase (`ExperimentCard.tsx`, `UploadDropzone.tsx`).
- Export components as named exports, not default exports.
- Each `ui/` component has a barrel export in `ui/index.ts`.
- Tailwind utility classes for all styling. No inline `style` props unless for dynamic values Tailwind can't express.

## What Belongs Here

- Presentational and interactive React components.
- Domain-grouped subdirectories for components with shared context.
- The `ui/` primitives layer: Button, Card, Input, Badge, Dialog, DataTable, etc.
- Plotly.js chart wrappers in `charts/`.

## What Doesn't Belong Here

- API calls or data fetching — use hooks from `@/api`.
- Page-level routing logic — that lives in `pages/`.
- Global state management — use React Context or pass via props.

## Key Dependencies

- `react`, `react-dom`
- `tailwindcss`
- `plotly.js` / `react-plotly.js` (charts only)

## Testing Approach

Vitest + `@testing-library/react`. Test rendering, user interactions, and prop variations. Use `__tests__/` inside each subdirectory. Mock `@/api` hooks with `vi.mock`.

## Related Docs

- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
