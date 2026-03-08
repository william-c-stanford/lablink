# store Module Guide

<!-- garden-managed: auto -->
<!-- last-reviewed: 2026-03-08 -->

> Local style guide for the `store` module.
> Claude Code automatically loads this file when it reads files in this directory.

## Purpose

Zustand stores for LabLink frontend global state. Manages: authentication tokens and user profile, UI state (toasts, modals, sidebar), filter state for lists (uploads, experiments, search), and real-time events from the SSE stream.

## Architecture Within This Module

Four stores, each in its own file:
- `authStore.ts` — JWT access token (in-memory), user profile, login/logout/refresh actions, initialization flag
- `uiStore.ts` — Toasts, modal visibility, sidebar open/closed, loading states
- `filterStore.ts` — Upload filters, experiment filters, search filters, date ranges
- `eventStore.ts` — SSE events from server, connection status, event selectors

`index.ts` — barrel re-export for all stores, types, and selectors.

## Coding Conventions

- **Import from `@/store`**: Always use the barrel export. Never import from individual store files.
- **Typed store interfaces**: Each store is typed with `Store = State & Actions` interfaces. Export them for use in tests.
- **Selector functions**: Export pre-built selectors (e.g., `selectIsAuthenticated`, `selectEvents`) for common derived state. Use these to prevent unnecessary re-renders.
- **In-memory tokens only**: Auth tokens are stored as a module-level variable in `authStore.ts`. Never use `localStorage` or `sessionStorage`.
- **Store slices for large stores**: If a store grows large, split into state and actions slices but keep them in one `create()` call.

## Patterns

**Zustand store definition**:
```ts
// authStore.ts
interface AuthState {
  accessToken: string | null
  user: UserProfile | null
  isInitialized: boolean
  isRefreshing: boolean
}

interface AuthActions {
  setAccessToken: (token: string | null) => void
  setUser: (user: UserProfile | null) => void
  logout: () => void
}

export type AuthStore = AuthState & AuthActions

export const useAuthStore = create<AuthStore>((set, get) => ({
  accessToken: null,
  user: null,
  isInitialized: false,
  isRefreshing: false,

  setAccessToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),
  logout: () => set({ accessToken: null, user: null }),
}))
```

**Selector function**:
```ts
export const selectIsAuthenticated = (state: AuthStore): boolean =>
  state.accessToken !== null && state.user !== null

// Usage in component:
const isAuthenticated = useAuthStore(selectIsAuthenticated)
```

**Toast usage** (in any component):
```ts
import { useUIStore } from '@/store'
const { addToast } = useUIStore()
addToast({ message: 'Upload complete', variant: 'success', duration: 3000 })
```

**Event store** (SSE events):
```ts
import { useEventStore, selectFileIngestedEvents } from '@/store'
const fileEvents = useEventStore(selectFileIngestedEvents)
const { connectionStatus } = useEventStore(selectConnectionStatus)
```

## Key Types and Interfaces

- `AuthStore`, `AuthState`, `AuthActions` (`authStore.ts`) — auth state and actions
- `UIStore`, `UIState`, `Toast`, `ToastVariant` (`uiStore.ts`) — UI state
- `FilterStore`, `UploadFilters`, `ExperimentFilters`, `SearchFilters` (`filterStore.ts`) — filter state
- `EventStore`, `EventState` (`eventStore.ts`) — SSE event state
- `UserProfile` (`authStore.ts`) — authenticated user data shape

## What Belongs Here

- Global client-side state shared across components
- Authentication token management (in-memory only)
- UI state that multiple components need (toasts, modals, sidebar)
- Filter state for list pages
- Real-time event stream state

## What Does Not Belong Here

- Server state (use React Query hooks in `@/api/hooks/`)
- Component-local state (use `useState` in the component)
- Business logic beyond state updates (keep actions simple)
- Direct API calls (use `@/api/client.ts` → actions can call `apiClient` for side effects, but that's the boundary)

## Key Dependencies

- `zustand` — `create()` from zustand
- No other runtime dependencies — stores are pure state

## Testing Approach

Test store actions by calling them directly on a fresh store instance. Use `create()` with the same factory function, reset between tests with `useStore.setState(initialState)`. Test selectors with plain objects.

```ts
const store = useAuthStore.getState()
store.setAccessToken('test-token')
expect(selectIsAuthenticated(useAuthStore.getState())).toBe(true)
```

## Common Gotchas

- **Never `localStorage` for tokens**: The whole reason for in-memory storage is XSS resistance. One slip to localStorage breaks this.
- **`MAX_EVENTS` cap in eventStore**: The event store keeps a rolling buffer of `MAX_EVENTS` (exported constant). Old events are dropped when the buffer is full. Don't rely on events being available indefinitely.
- **Selector stability**: Pass a selector function to `useStore(selector)` — never `useStore()` which subscribes to all changes and causes re-renders on any state change.
- **Store initialization**: The `authStore` has an `isInitialized` flag that's set after the first token refresh attempt on app mount. Components that need auth should wait for `isInitialized` before rendering or redirecting.

## Related Docs

- [ARCHITECTURE.md](../../../ARCHITECTURE.md)
- [docs/FRONTEND.md](../../../docs/FRONTEND.md)
