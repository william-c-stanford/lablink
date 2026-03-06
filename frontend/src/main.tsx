import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import {
  RouterProvider,
  createRouter,
  createRootRoute,
  createRoute,
} from "@tanstack/react-router";
import { queryClient } from "@/lib/query-client";
import App from "@/App";
import "./app.css";

// ---------------------------------------------------------------------------
// Router setup — routes will be expanded as pages are built
// ---------------------------------------------------------------------------

const rootRoute = createRootRoute({ component: App });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => <div className="p-8 text-xl font-semibold">Dashboard</div>,
});

const uploadsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/uploads",
  component: () => <div className="p-8 text-xl font-semibold">Uploads</div>,
});

const experimentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/experiments",
  component: () => (
    <div className="p-8 text-xl font-semibold">Experiments</div>
  ),
});

const searchRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/search",
  component: () => <div className="p-8 text-xl font-semibold">Search</div>,
});

const instrumentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/instruments",
  component: () => (
    <div className="p-8 text-xl font-semibold">Instruments</div>
  ),
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: () => <div className="p-8 text-xl font-semibold">Settings</div>,
});

const adminRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/admin",
  component: () => <div className="p-8 text-xl font-semibold">Admin</div>,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  uploadsRoute,
  experimentsRoute,
  searchRoute,
  instrumentsRoute,
  settingsRoute,
  adminRoute,
]);

const router = createRouter({ routeTree });

// ---------------------------------------------------------------------------
// Mount
// ---------------------------------------------------------------------------

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Missing #root element");

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
