/**
 * MSW request handlers for LabLink API.
 *
 * Every handler returns data wrapped in the Envelope[T] format:
 *   { data: T, meta: { request_id, timestamp, pagination? }, errors: [] }
 *
 * Handlers are registered for BOTH `/api/v1/...` (raw fetch in page
 * components) and `/...` (openapi-fetch apiClient with baseUrl: '/').
 */

import { http, HttpResponse } from "msw";
import {
  mockUpload,
  mockExperiment,
  mockAgent,
  mockUser,
  mockSearchResult,
  mockMeasurement,
  wrapEnvelope,
  wrapListEnvelope,
  wrapErrorEnvelope,
} from "./data";

// ---------------------------------------------------------------------------
// Default mock data
// ---------------------------------------------------------------------------

const defaultUser = mockUser();
const defaultUploads = [
  mockUpload({ filename: "nanodrop_sample_A.csv", status: "parsed" }),
  mockUpload({ filename: "plate_reader_run_07.xlsx", status: "parsing", instrument_type: "plate_reader" }),
  mockUpload({ filename: "hplc_batch_12.csv", status: "failed", instrument_type: "hplc", error_message: "Unsupported column layout" }),
];
const defaultExperiments = [
  mockExperiment({ name: "DNA Quantification Batch #42", status: "active" }),
  mockExperiment({ name: "Protein Assay Run #7", status: "draft" }),
  mockExperiment({ name: "PCR Validation #3", status: "completed" }),
];
const defaultAgents = [
  mockAgent({ name: "Lab-PC-01", status: "online" }),
  mockAgent({ name: "Lab-PC-02", status: "offline" }),
  mockAgent({ name: "Lab-PC-03", status: "online" }),
];
const defaultSearchResults = [
  mockSearchResult({ title: "nanodrop_sample_A.csv", entity_type: "upload" }),
  mockSearchResult({ title: "DNA Quantification Batch #42", entity_type: "experiment" }),
];

// ---------------------------------------------------------------------------
// Handler factories — called once per URL prefix to produce handler arrays
// ---------------------------------------------------------------------------

function createHandlers(prefix: string) {
  return [
    // ---- Auth ----

    http.post(`${prefix}/auth/login`, async ({ request }) => {
      const body = (await request.json()) as Record<string, string>;
      if (body.email === "bad@example.com") {
        return HttpResponse.json(
          wrapErrorEnvelope(
            "INVALID_CREDENTIALS",
            "Invalid email or password",
            "Check your email and password and try again",
          ),
          { status: 401 },
        );
      }
      return HttpResponse.json(
        wrapEnvelope({
          access_token: "mock-jwt-token-abc123",
          token_type: "bearer",
          expires_in: 3600,
        }),
      );
    }),

    http.post(`${prefix}/auth/register`, async ({ request }) => {
      const body = (await request.json()) as Record<string, string>;
      return HttpResponse.json(
        wrapEnvelope({
          user: {
            id: defaultUser.id,
            email: body.email ?? defaultUser.email,
            display_name: body.full_name ?? defaultUser.display_name,
            org_id: defaultUser.org_id,
            is_active: true,
          },
          token: {
            access_token: "mock-jwt-token-register",
            token_type: "bearer",
            expires_in: 3600,
          },
        }),
        { status: 201 },
      );
    }),

    http.post(`${prefix}/auth/refresh`, () => {
      return HttpResponse.json(
        wrapEnvelope({
          access_token: "mock-jwt-token-refreshed",
          token_type: "bearer",
          expires_in: 3600,
        }),
      );
    }),

    http.get(`${prefix}/auth/me`, () => {
      return HttpResponse.json(wrapEnvelope(defaultUser));
    }),

    // ---- Uploads ----

    http.get(`${prefix}/uploads`, ({ request }) => {
      const url = new URL(request.url);
      const status = url.searchParams.get("status");
      const instrumentType = url.searchParams.get("instrument_type");
      const page = Number(url.searchParams.get("page") ?? 1);
      const pageSize = Number(url.searchParams.get("page_size") ?? 20);

      let filtered = [...defaultUploads];
      if (status) {
        filtered = filtered.filter((u) => u.status === status);
      }
      if (instrumentType) {
        filtered = filtered.filter((u) => u.instrument_type === instrumentType);
      }

      return HttpResponse.json(
        wrapListEnvelope(filtered, {
          total_count: filtered.length,
          page,
          page_size: pageSize,
        }),
      );
    }),

    http.get(`${prefix}/uploads/:id`, ({ params }) => {
      const upload = defaultUploads.find((u) => u.id === params.id);
      if (!upload) {
        return HttpResponse.json(
          wrapErrorEnvelope("UPLOAD_NOT_FOUND", `No upload with ID '${params.id as string}'`),
          { status: 404 },
        );
      }
      return HttpResponse.json(
        wrapEnvelope({
          ...upload,
          parsed_data: {
            instrument_type: upload.instrument_type,
            sample_count: 12,
            measurements: [mockMeasurement(), mockMeasurement({ value: 2.1 })],
          },
        }),
      );
    }),

    http.post(`${prefix}/uploads`, async () => {
      const newUpload = mockUpload({
        filename: "new_upload.csv",
        status: "queued",
      });
      return HttpResponse.json(wrapEnvelope(newUpload), { status: 201 });
    }),

    // ---- Experiments ----

    http.get(`${prefix}/experiments`, ({ request }) => {
      const url = new URL(request.url);
      const status = url.searchParams.get("status");
      const page = Number(url.searchParams.get("page") ?? 1);
      const pageSize = Number(url.searchParams.get("page_size") ?? 20);

      let filtered = [...defaultExperiments];
      if (status) {
        filtered = filtered.filter((e) => e.status === status);
      }

      return HttpResponse.json(
        wrapListEnvelope(filtered, {
          total_count: filtered.length,
          page,
          page_size: pageSize,
        }),
      );
    }),

    http.post(`${prefix}/experiments`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const newExperiment = mockExperiment({
        name: (body.name as string) ?? "New Experiment",
        description: (body.description as string) ?? "",
        status: "draft",
      });
      return HttpResponse.json(wrapEnvelope(newExperiment), { status: 201 });
    }),

    http.post(`${prefix}/experiments/:id/transition`, async ({ params, request }) => {
      const body = (await request.json()) as { target_status?: string };
      const experiment = defaultExperiments.find((e) => e.id === params.id);
      if (!experiment) {
        return HttpResponse.json(
          wrapErrorEnvelope(
            "EXPERIMENT_NOT_FOUND",
            `No experiment with ID '${params.id as string}'`,
            "Use list_experiments to find valid IDs",
          ),
          { status: 404 },
        );
      }
      return HttpResponse.json(
        wrapEnvelope({
          ...experiment,
          status: body.target_status ?? "active",
          updated_at: new Date().toISOString(),
        }),
      );
    }),

    // Also handle PATCH for status transitions (openapi-fetch hooks use PATCH)
    http.patch(`${prefix}/experiments/:id`, async ({ params, request }) => {
      const body = (await request.json()) as { status?: string; name?: string };
      const experiment = defaultExperiments.find((e) => e.id === params.id);
      if (!experiment) {
        return HttpResponse.json(
          wrapErrorEnvelope(
            "EXPERIMENT_NOT_FOUND",
            `No experiment with ID '${params.id as string}'`,
            "Use list_experiments to find valid IDs",
          ),
          { status: 404 },
        );
      }
      return HttpResponse.json(
        wrapEnvelope({
          ...experiment,
          ...(body.status && { status: body.status }),
          ...(body.name && { name: body.name }),
          updated_at: new Date().toISOString(),
        }),
      );
    }),

    // ---- Search ----

    http.post(`${prefix}/search`, async ({ request }) => {
      const body = (await request.json()) as { query?: string; filters?: Record<string, unknown> };
      const query = body.query ?? "";

      if (!query.trim()) {
        return HttpResponse.json(
          wrapListEnvelope([], { total_count: 0 }),
        );
      }

      return HttpResponse.json(
        wrapListEnvelope(defaultSearchResults, {
          total_count: defaultSearchResults.length,
        }),
      );
    }),

    // ---- Agents ----

    http.get(`${prefix}/agents`, () => {
      return HttpResponse.json(
        wrapListEnvelope(defaultAgents, {
          total_count: defaultAgents.length,
        }),
      );
    }),

    // ---- Health ----

    http.get(`${prefix}/health`, () => {
      return HttpResponse.json(wrapEnvelope({ status: "ok" }));
    }),
  ];
}

// Register handlers for both URL patterns
export const handlers = [
  ...createHandlers("/api/v1"),
  ...createHandlers(""),
];

// ---------------------------------------------------------------------------
// Exports for test-specific overrides
// ---------------------------------------------------------------------------

export {
  defaultUser,
  defaultUploads,
  defaultExperiments,
  defaultAgents,
  defaultSearchResults,
};
