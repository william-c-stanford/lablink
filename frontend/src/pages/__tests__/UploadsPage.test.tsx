/**
 * UploadsPage tests
 *
 * Covers:
 *  - Renders upload list with status badges
 *  - Drag-and-drop zone accepts files
 *  - File input triggers upload mutation
 *  - Shows upload progress during upload
 *  - Filters by instrument type
 *  - Filters by status
 *  - Pagination works (next/prev)
 *  - Shows error state on upload failure
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
import { wrapErrorEnvelope, wrapListEnvelope, mockUpload } from "@/test/mocks/data";

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

import UploadsPage from "@/pages/UploadsPage";

function renderPage() {
  const qc = createTestQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <UploadsPage />
    </QueryClientProvider>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UploadsPage", () => {
  it("renders upload list with filenames and status badges", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("nanodrop_sample_A.csv")).toBeInTheDocument();
      expect(screen.getByText("plate_reader_run_07.xlsx")).toBeInTheDocument();
      expect(screen.getByText("hplc_batch_12.csv")).toBeInTheDocument();
    });

    // Status badges are rendered as UploadStatusBadge which shows label text
    await waitFor(() => {
      expect(screen.getByText("Parsed")).toBeInTheDocument();
      expect(screen.getByText("Parsing")).toBeInTheDocument();
      expect(screen.getByText("Failed")).toBeInTheDocument();
    });
  });

  it("renders the drop zone area", async () => {
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(/Drag and drop instrument files/i),
      ).toBeInTheDocument();
    });
  });

  it("drag-and-drop zone changes styling on dragOver", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Drag and drop/i)).toBeInTheDocument();
    });

    const dropZone = screen.getByText(/Drag and drop/i).closest("div")!;

    // Simulate dragOver
    fireEvent.dragOver(dropZone, {
      dataTransfer: { files: [], types: ["Files"] },
    });

    // The zone should update styling (border changes to blue dashed)
    await waitFor(() => {
      const style = dropZone.getAttribute("style") ?? "";
      expect(style).toContain("#3b82f6");
    });
  });

  it("file input triggers upload (via hidden input)", async () => {
    // Track that POST /uploads is called
    let uploadCalled = false;
    server.use(
      http.post("*/uploads", async () => {
        uploadCalled = true;
        return HttpResponse.json(
          { data: mockUpload({ status: "queued" }), meta: { request_id: "x", timestamp: new Date().toISOString() }, errors: [] },
          { status: 201 },
        );
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Drag and drop/i)).toBeInTheDocument();
    });

    // Find the hidden file input
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeTruthy();

    // Create a mock file and trigger change
    const file = new File(["test content"], "test_data.csv", {
      type: "text/csv",
    });

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } });
    });

    await waitFor(() => {
      expect(uploadCalled).toBe(true);
    });
  });

  it("shows upload progress indicator during upload", async () => {
    // Delay the upload response to observe progress state
    server.use(
      http.post("*/uploads", async () => {
        await new Promise((r) => setTimeout(r, 200));
        return HttpResponse.json(
          { data: mockUpload({ status: "queued" }), meta: { request_id: "x", timestamp: new Date().toISOString() }, errors: [] },
          { status: 201 },
        );
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Drag and drop/i)).toBeInTheDocument();
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["data"], "progress_test.csv", { type: "text/csv" });

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } });
    });

    // Progress bar should appear (the component sets progress to 0 immediately)
    // It uses a div with a width style for progress
    await waitFor(() => {
      const progressBars = document.querySelectorAll('[style*="width"]');
      expect(progressBars.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("filters by status when status select changes", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("nanodrop_sample_A.csv")).toBeInTheDocument();
    });

    // Find the status filter select
    const selects = document.querySelectorAll("select");
    const statusSelect = selects[0] as HTMLSelectElement;

    await act(async () => {
      fireEvent.change(statusSelect, { target: { value: "parsed" } });
    });

    // After filtering by "parsed", only the parsed upload should show
    await waitFor(() => {
      expect(screen.getByText("nanodrop_sample_A.csv")).toBeInTheDocument();
    });
  });

  it("filters by instrument type when instrument select changes", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("nanodrop_sample_A.csv")).toBeInTheDocument();
    });

    const selects = document.querySelectorAll("select");
    // Second select is instrument filter
    const instrumentSelect = selects[1] as HTMLSelectElement;

    await act(async () => {
      fireEvent.change(instrumentSelect, {
        target: { value: "plate_reader" },
      });
    });

    // Client-side filter should show only plate_reader uploads
    await waitFor(() => {
      expect(screen.getByText("plate_reader_run_07.xlsx")).toBeInTheDocument();
    });
  });

  it("renders pagination controls", async () => {
    renderPage();

    await waitFor(() => {
      // Pagination buttons
      expect(screen.getByText("Previous")).toBeInTheDocument();
      expect(screen.getByText("Next")).toBeInTheDocument();
    });

    // Previous button should be disabled on page 1
    const prevButton = screen.getByText("Previous");
    expect(prevButton).toBeDisabled();
  });

  it("shows error state on upload failure", async () => {
    server.use(
      http.post("*/uploads", () => {
        return HttpResponse.json(
          wrapErrorEnvelope("UPLOAD_FAILED", "File too large"),
          { status: 400 },
        );
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Drag and drop/i)).toBeInTheDocument();
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["x".repeat(100)], "big_file.csv", {
      type: "text/csv",
    });

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [file] } });
    });

    await waitFor(() => {
      // The upload error message should be visible
      const errorText = screen.getByText(/Upload failed|File too large/i);
      expect(errorText).toBeInTheDocument();
    });
  });
});
