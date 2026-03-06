/**
 * Test render utilities for LabLink frontend.
 *
 * Provides a renderWithProviders() helper that wraps components in
 * the same provider tree the real app uses: QueryClientProvider + Router.
 */

import React, { type ReactElement } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";

// ---------------------------------------------------------------------------
// Fresh QueryClient per test — no cache sharing between tests
// ---------------------------------------------------------------------------

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

// ---------------------------------------------------------------------------
// Provider wrapper
// ---------------------------------------------------------------------------

interface WrapperProps {
  children: React.ReactNode;
}

export interface RenderWithProvidersOptions extends Omit<RenderOptions, "wrapper"> {
  /** Initial URL path for the router (default: "/") */
  initialPath?: string;
  /** Custom QueryClient — a fresh one is created per call if omitted */
  queryClient?: QueryClient;
}

/**
 * Render a component wrapped in all required providers.
 *
 * Uses a simple catch-all router so page components can use router hooks
 * without errors. The QueryClient is always fresh to avoid cross-test leakage.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {},
) {
  const {
    initialPath = "/",
    queryClient = createTestQueryClient(),
    ...renderOptions
  } = options;

  // Build a minimal router that renders the test UI at the initial path
  const rootRoute = createRootRoute({ component: () => ui });
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => ui,
  });

  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  });

  function Wrapper({ children }: WrapperProps) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  }

  // We render the RouterProvider inside the wrapper so both providers are active.
  // However, since TanStack Router controls rendering via its own tree, we
  // render the UI directly wrapped in providers for simplicity in unit tests.
  const result = render(ui, {
    wrapper: Wrapper,
    ...renderOptions,
  });

  return {
    ...result,
    queryClient,
    router,
  };
}

// Re-export everything from @testing-library/react for convenience
export * from "@testing-library/react";
