/**
 * TanStack Router configuration for LabLink.
 *
 * Routes:
 *   /             — Dashboard (auth required)
 *   /uploads      — Uploads management (auth required)
 *   /search       — Full-text search (auth required)
 *   /experiments  — Experiment management (auth required)
 *   /login        — Login page (public)
 *   /register     — Registration page (public)
 *
 * Auth guard: protected routes redirect to /login when no token is present.
 */

import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { AppShell } from '@/components/layout'
import { getToken } from '@/lib/auth'

import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import DashboardPage from '@/pages/DashboardPage'
import UploadsPage from '@/pages/UploadsPage'
import SearchPage from '@/pages/SearchPage'
import ExperimentsPage from '@/pages/ExperimentsPage'
import { AgentsPage } from '@/pages/AgentsPage'

// ---------------------------------------------------------------------------
// Root route — wraps all children with the AppShell layout
// ---------------------------------------------------------------------------

const rootRoute = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return <Outlet />
}

// ---------------------------------------------------------------------------
// Layout wrapper — authenticated pages get AppShell
// ---------------------------------------------------------------------------

const authenticatedLayout = createRoute({
  getParentRoute: () => rootRoute,
  id: 'authenticated',
  beforeLoad: () => {
    if (!getToken()) {
      throw redirect({ to: '/login' })
    }
  },
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})

// ---------------------------------------------------------------------------
// Public routes (no auth required, no AppShell)
// ---------------------------------------------------------------------------

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  component: LoginPage,
})

const registerRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/register',
  component: RegisterPage,
})

// ---------------------------------------------------------------------------
// Protected routes (require auth, wrapped in AppShell)
// ---------------------------------------------------------------------------

const dashboardRoute = createRoute({
  getParentRoute: () => authenticatedLayout,
  path: '/',
  component: DashboardPage,
})

const uploadsRoute = createRoute({
  getParentRoute: () => authenticatedLayout,
  path: '/uploads',
  component: UploadsPage,
})

const searchRoute = createRoute({
  getParentRoute: () => authenticatedLayout,
  path: '/search',
  component: SearchPage,
})

const experimentsRoute = createRoute({
  getParentRoute: () => authenticatedLayout,
  path: '/experiments',
  component: ExperimentsPage,
})

const agentsRoute = createRoute({
  getParentRoute: () => authenticatedLayout,
  path: '/agents',
  component: AgentsPage,
})

// ---------------------------------------------------------------------------
// Route tree + router
// ---------------------------------------------------------------------------

const routeTree = rootRoute.addChildren([
  loginRoute,
  registerRoute,
  authenticatedLayout.addChildren([
    dashboardRoute,
    uploadsRoute,
    searchRoute,
    experimentsRoute,
    agentsRoute,
  ]),
])

export const router = createRouter({ routeTree })

// ---------------------------------------------------------------------------
// Type-safe router declaration (for useNavigate, Link, etc.)
// ---------------------------------------------------------------------------

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
