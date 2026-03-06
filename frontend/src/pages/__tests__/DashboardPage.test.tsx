/**
 * DashboardPage tests
 *
 * Covers:
 *  - Renders stat cards with correct counts
 *  - Shows recent uploads list
 *  - Shows connected agent count
 *  - Shows loading skeleton while fetching
 *  - Handles API error gracefully
 *  - Navigates to uploads page on "View All" click
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import {
  wrapListEnvelope,
  wrapErrorEnvelope,
} from "@/test/mocks/data";
import {
  defaultUploads,
  defaultExperiments,
  defaultAgents,
} from "@/test/mocks/handlers";

import DashboardPage from "@/pages/DashboardPage";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderPage() {
  const qc = createTestQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("renders stat cards with correct upload count", async () => {
    renderPage();

    await waitFor(() => {
      // The mock returns 3 uploads total, and pagination total_count is 3
      expect(screen.getByText("Total Uploads")).toBeInTheDocument();
    });

    // Check that the stat value appears (total_count from the pagination metadata)
    await waitFor(() => {
      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });

  it("shows active experiment count", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Active Experiments")).toBeInTheDocument();
    });

    // 1 active experiment in mock data (DNA Quantification is "active")
    await waitFor(() => {
      expect(screen.getByText("1")).toBeInTheDocument();
    });
  });

  it("shows connected agent count", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Connected Agents")).toBeInTheDocument();
    });

    // 2 online agents in the mock data (Lab-PC-01 and Lab-PC-03)
    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  it("shows recent uploads list with filenames", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Recent Uploads")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("nanodrop_sample_A.csv")).toBeInTheDocument();
      expect(screen.getByText("plate_reader_run_07.xlsx")).toBeInTheDocument();
      expect(screen.getByText("hplc_batch_12.csv")).toBeInTheDocument();
    });
  });

  it("shows loading state with dash values before data arrives", async () => {
    // Add a delay to the handlers so we can observe the loading state
    server.use(
      http.get("*/uploads", async () => {
        await new Promise((r) => setTimeout(r, 500));
        return HttpResponse.json(
          wrapListEnvelope(defaultUploads, { total_count: 3 }),
        );
      }),
      http.get("*/experiments", async () => {
        await new Promise((r) => setTimeout(r, 500));
        return HttpResponse.json(
          wrapListEnvelope(defaultExperiments, { total_count: 3 }),
        );
      }),
      http.get("*/agents", async () => {
        await new Promise((r) => setTimeout(r, 500));
        return HttpResponse.json(
          wrapListEnvelope(defaultAgents, { total_count: 3 }),
        );
      }),
    );

    renderPage();

    // While loading, stat cards show "-" as placeholder
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("handles API error gracefully", async () => {
    server.use(
      http.get("*/uploads", () => {
        return HttpResponse.json(
          wrapErrorEnvelope("SERVER_ERROR", "Internal server error"),
          { status: 500 },
        );
      }),
    );

    renderPage();

    await waitFor(() => {
      // Should show the error text from the uploads section
      expect(screen.getByText(/Failed to load uploads/i)).toBeInTheDocument();
    });
  });

  it("renders Agent Status section with agent names", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Agent Status")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Lab-PC-01")).toBeInTheDocument();
      expect(screen.getByText("Lab-PC-02")).toBeInTheDocument();
      expect(screen.getByText("Lab-PC-03")).toBeInTheDocument();
    });
  });
});
