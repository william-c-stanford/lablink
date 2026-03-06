/**
 * ExperimentsPage tests
 *
 * Covers:
 *  - Renders experiment list
 *  - Create experiment modal opens
 *  - Creates experiment via form submission
 *  - Shows status badges correctly
 *  - Transition button changes experiment state
 *  - Handles error on failed transition
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
import { wrapErrorEnvelope } from "@/test/mocks/data";
import { defaultExperiments } from "@/test/mocks/handlers";

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

import ExperimentsPage from "@/pages/ExperimentsPage";

function renderPage() {
  const qc = createTestQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ExperimentsPage />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ExperimentsPage", () => {
  it("renders experiment list with names", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("experiment-list")).toBeInTheDocument();
    });

    expect(
      screen.getByText("DNA Quantification Batch #42"),
    ).toBeInTheDocument();
    expect(screen.getByText("Protein Assay Run #7")).toBeInTheDocument();
    expect(screen.getByText("PCR Validation #3")).toBeInTheDocument();
  });

  it("shows status badges correctly", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("Draft")).toBeInTheDocument();
      expect(screen.getByText("Completed")).toBeInTheDocument();
    });
  });

  it("opens create experiment modal on button click", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("create-experiment-btn")).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId("create-experiment-btn"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("create-experiment-modal")).toBeInTheDocument();
      expect(screen.getByText("Create Experiment")).toBeInTheDocument();
    });
  });

  it("creates experiment via form submission", async () => {
    let createCalled = false;

    server.use(
      http.post("*/experiments", async ({ request }) => {
        const body = (await request.json()) as Record<string, string>;
        createCalled = true;
        return HttpResponse.json(
          {
            data: {
              id: "exp-new-1",
              name: body.name,
              description: body.description,
              status: "draft",
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
            meta: {
              request_id: "req-1",
              timestamp: new Date().toISOString(),
            },
            errors: [],
          },
          { status: 201 },
        );
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("create-experiment-btn")).toBeInTheDocument();
    });

    // Open the modal
    await act(async () => {
      fireEvent.click(screen.getByTestId("create-experiment-btn"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("experiment-name-input")).toBeInTheDocument();
    });

    // Fill in the form
    const nameInput = screen.getByTestId("experiment-name-input");
    const descInput = screen.getByTestId("experiment-desc-input");

    await act(async () => {
      fireEvent.change(nameInput, {
        target: { value: "New HPLC Characterization" },
      });
      fireEvent.change(descInput, {
        target: { value: "Testing new column setup" },
      });
    });

    // Submit
    await act(async () => {
      fireEvent.click(screen.getByTestId("submit-experiment-btn"));
    });

    await waitFor(() => {
      expect(createCalled).toBe(true);
    });
  });

  it("shows transition buttons for draft and active experiments", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("experiment-list")).toBeInTheDocument();
    });

    // Draft experiment should have a "Start" button
    expect(screen.getByText("Start")).toBeInTheDocument();

    // Active experiment should have a "Complete" button
    expect(screen.getByText("Complete")).toBeInTheDocument();

    // Completed experiment (PCR Validation) should have NO transition button
    // (it's the last in the list and has no next status)
  });

  it("transition button triggers status change API call", async () => {
    let transitionCalled = false;
    const activeExperiment = defaultExperiments[0]; // "active" status

    server.use(
      http.post(`*/experiments/${activeExperiment.id}/transition`, async () => {
        transitionCalled = true;
        return HttpResponse.json({
          data: { ...activeExperiment, status: "completed" },
          meta: {
            request_id: "req-t",
            timestamp: new Date().toISOString(),
          },
          errors: [],
        });
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Complete")).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText("Complete"));
    });

    await waitFor(() => {
      expect(transitionCalled).toBe(true);
    });
  });

  it("handles error on failed transition", async () => {
    server.use(
      http.post("*/experiments/*/transition", () => {
        return HttpResponse.json(
          wrapErrorEnvelope(
            "INVALID_TRANSITION",
            "Cannot transition from completed to active",
          ),
          { status: 400 },
        );
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Complete")).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText("Complete"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("transition-error")).toBeInTheDocument();
    });
  });
});
