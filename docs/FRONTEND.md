# Frontend

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-07 -->

> Frontend conventions, component patterns, and styling approach.

## Stack

- **Framework**: React 18 + TypeScript
- **Build**: Vite
- **Styling**: Tailwind CSS
- **Charts**: Plotly.js
- **Testing**: Vitest
- **Location**: `frontend/src/`

## Component Conventions

- Components live in `frontend/src/` and use PascalCase filenames.
- Prefer functional components with hooks over class components.
- Props typed with TypeScript interfaces, not `any`.

## Styling Approach

Tailwind CSS utility classes. Avoid custom CSS unless Tailwind cannot express the style.

## State Management

Local React state (`useState`, `useReducer`) for component-level state.
Global state via React Context or lightweight hooks — avoid Redux unless complexity demands it.

## Data Fetching

Fetch from the LabLink REST API. All responses follow the `Envelope[T]` shape:
`{ data, meta, errors }`. Always check `errors` before using `data`.

## Testing

Vitest for unit and component tests (`vitest.config.ts`).
API integration tests use the Python pytest suite — see `tests/`.

## Performance Guidelines

- Lazy-load route-level components with `React.lazy`.
- Use Plotly.js `react-plotly.js` wrapper for charts.
- Keep bundle size in check: run `vite build --report` to inspect.
