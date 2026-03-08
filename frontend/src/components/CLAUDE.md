# components Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `components` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Feature-based React components for the LabLink frontend. Components are organized by domain feature, with shared UI primitives in `ui/`. Pages in `pages/` compose these components — they don't contain their own complex logic.

## Architecture Within This Module

Feature directories (one per domain):
- `dashboard/` — Dashboard widgets and summary cards
- `experiments/` — Experiment list, detail view, state machine controls
- `uploads/` — Upload list, upload form, parse status indicators
- `search/` — Search interface, result cards, filters
- `charts/` — Plotly.js chart wrappers (structured for agent-readable output)
- `layout/` — App shell: sidebar, header, navigation
- `ui/` — Shared primitives: buttons, badges, modals, toasts, inputs

## Coding Conventions

- **Feature-first organization**: Related components live in the same feature directory. Don't flatten everything to `components/`.
- **TypeScript strict**: All props typed with interfaces. No `any` except as escape hatch with comment.
- **Tailwind utility classes**: No CSS modules, no styled-components. Class composition via `clsx` or `cn`.
- **Data fetching in hooks**: Components don't call `apiClient` directly. Use custom hooks from `@/api/hooks/`.
- **Zustand for cross-component state**: Use `@/store` hooks for auth, filters, toasts. Don't prop-drill.
- **One component per file**: Named export, matching filename. `ExperimentList.tsx` exports `ExperimentList`.
- **Charts return structured data**: Any chart component must also expose its data as a machine-readable JSON prop/callback for agent parity.

## Patterns

**Feature component** (consuming data via hook):
```tsx
// experiments/ExperimentList.tsx
import { useExperiments } from '@/api/hooks'
import { useFilterStore } from '@/store'

export function ExperimentList() {
  const { filters } = useFilterStore()
  const { data: experiments, isLoading } = useExperiments(filters)

  if (isLoading) return <LoadingSpinner />

  return (
    <div className="space-y-4">
      {experiments?.map(exp => (
        <ExperimentCard key={exp.id} experiment={exp} />
      ))}
    </div>
  )
}
```

**Shared UI primitive** (in `ui/`):
```tsx
// ui/Badge.tsx
interface BadgeProps {
  variant: 'success' | 'warning' | 'error' | 'info'
  children: React.ReactNode
}

export function Badge({ variant, children }: BadgeProps) {
  const classes = {
    success: 'bg-green-100 text-green-800',
    warning: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
    info: 'bg-blue-100 text-blue-800',
  }
  return <span className={`px-2 py-1 rounded text-sm ${classes[variant]}`}>{children}</span>
}
```

**Toast notifications** (via uiStore):
```tsx
import { useUIStore } from '@/store'
const { addToast } = useUIStore()
addToast({ message: 'Upload successful', variant: 'success' })
```

## Key Types and Interfaces

- `components` from `@/api/schema` — All backend schema types (via openapi-typescript)
- `Toast`, `ToastVariant` from `@/store` — Toast notification types
- `ExperimentFilters`, `UploadFilters` from `@/store` — Filter state types
- `UserProfile` from `@/store` — Authenticated user type

## What Belongs Here

- Presentational and container components organized by feature
- Shared UI primitives (buttons, badges, modals, toasts) in `ui/`
- Component-level state via `useState`/`useReducer` for UI-only state
- Event handlers that call hooks or store actions

## What Does Not Belong Here

- Direct `apiClient` calls (use hooks from `@/api/hooks/`)
- Business logic beyond UI orchestration
- Page-level routing (use `pages/`)
- Store definitions (use `store/`)

## Key Dependencies

- `react`, `react-dom` — Component framework
- `tailwindcss` — Styling
- `clsx` or `cn` — Class composition
- `@/store` — Zustand stores
- `@/api/hooks` — Data fetching hooks
- `plotly.js-dist-min` — Charts (lazy-loaded)

## Testing Approach

Component tests with Vitest + React Testing Library. Test files in `__tests__/` adjacent to feature directories. Render with `render()`, query with `screen`, interact with `userEvent`. Mock API hooks at the module level (`vi.mock('@/api/hooks')`). Don't test implementation details — test what users see and interact with.

## Common Gotchas

- **No direct `apiClient` calls in components**: Always go through hooks. This ensures loading/error states are handled consistently.
- **Charts must be agent-readable**: When adding a new chart, also expose the underlying data as a structured prop or ref. Agent parity principle.
- **`layout/` components render once**: The sidebar and header are rendered at the app shell level. Don't duplicate navigation logic in feature components.
- **Zustand selectors prevent re-renders**: Use selector functions (`useAuthStore(selectUser)`) instead of selecting the whole store object.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
