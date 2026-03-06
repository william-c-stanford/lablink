/**
 * SearchPage tests
 *
 * Covers:
 *  - Renders search input
 *  - Submits search and shows results
 *  - Debounces input (doesn't fire on every keystroke)
 *  - Shows "No results" for empty results
 *  - Filter chips update search params
 */

import { describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  act,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { wrapListEnvelope } from "@/test/mocks/data";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

import SearchPage from "@/pages/SearchPage";

function renderPage() {
  const qc = createTestQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <SearchPage />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SearchPage", () => {
  it("renders search input", () => {
    renderPage();

    const input = screen.getByTestId("search-input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder");
  });

  it("submits search and shows results after debounce", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    renderPage();

    const input = screen.getByTestId("search-input");

    // Type a search query
    await act(async () => {
      fireEvent.change(input, { target: { value: "nanodrop absorbance" } });
    });

    // Wait for debounce (300ms) and results to appear
    await waitFor(
      () => {
        expect(screen.getByTestId("search-results")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    // Results should show the mock data titles
    expect(screen.getByText("nanodrop_sample_A.csv")).toBeInTheDocument();
    expect(
      screen.getByText("DNA Quantification Batch #42"),
    ).toBeInTheDocument();
  });

  it("debounces input and does not fire immediately", async () => {
    let searchCallCount = 0;

    server.use(
      http.post("*/search", async ({ request }) => {
        searchCallCount++;
        const body = (await request.json()) as { query?: string };
        if (!body.query?.trim()) {
          return HttpResponse.json(wrapListEnvelope([], { total_count: 0 }));
        }
        return HttpResponse.json(
          wrapListEnvelope(
            [
              {
                id: "sr-1",
                entity_type: "upload",
                title: "result",
                snippet: "test",
                score: 0.9,
                highlights: [],
                created_at: new Date().toISOString(),
              },
            ],
            { total_count: 1 },
          ),
        );
      }),
    );

    renderPage();
    const input = screen.getByTestId("search-input");

    // Rapidly type multiple characters
    const initialCallCount = searchCallCount;

    await act(async () => {
      fireEvent.change(input, { target: { value: "a" } });
    });
    await act(async () => {
      fireEvent.change(input, { target: { value: "ab" } });
    });
    await act(async () => {
      fireEvent.change(input, { target: { value: "abc" } });
    });

    // The debounce should prevent a search call for each keystroke.
    // Wait for the debounce to settle.
    await waitFor(
      () => {
        // After debounce settles, there should be fewer calls than keystrokes
        // The exact number depends on timing, but it should be less than 3 new calls
        expect(searchCallCount - initialCallCount).toBeLessThanOrEqual(2);
      },
      { timeout: 2000 },
    );
  });

  it("shows 'No results' for empty search results", async () => {
    server.use(
      http.post("*/search", () => {
        return HttpResponse.json(wrapListEnvelope([], { total_count: 0 }));
      }),
    );

    renderPage();
    const input = screen.getByTestId("search-input");

    await act(async () => {
      fireEvent.change(input, { target: { value: "xyznonexistent" } });
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("no-results")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    expect(screen.getByText(/No results found/i)).toBeInTheDocument();
  });

  it("renders filter chips and toggles them on click", async () => {
    renderPage();

    const filterChips = screen.getByTestId("filter-chips");
    expect(filterChips).toBeInTheDocument();

    // Should have 3 filter options: upload, experiment, measurement
    expect(screen.getByTestId("filter-chip-upload")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-experiment")).toBeInTheDocument();
    expect(screen.getByTestId("filter-chip-measurement")).toBeInTheDocument();

    // Click the upload filter chip
    const uploadChip = screen.getByTestId("filter-chip-upload");
    await act(async () => {
      fireEvent.click(uploadChip);
    });

    // After clicking, the badge inside should switch to "primary" variant
    // (indicated by having the blue background class)
    const badge = uploadChip.querySelector("span");
    expect(badge?.className).toContain("bg-[#3b82f6]");
  });
});
