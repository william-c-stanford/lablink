/**
 * Mock data factories for LabLink frontend tests.
 *
 * Each factory returns a realistic object with sensible defaults
 * that can be overridden via the optional `overrides` parameter.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _idCounter = 0;

function nextId(): string {
  _idCounter += 1;
  return `00000000-0000-4000-a000-${String(_idCounter).padStart(12, "0")}`;
}

function isoNow(): string {
  return new Date().toISOString();
}

// ---------------------------------------------------------------------------
// Envelope helpers
// ---------------------------------------------------------------------------

export interface EnvelopeMeta {
  request_id: string;
  timestamp: string;
  pagination?: {
    total_count: number;
    page: number;
    page_size: number;
    has_more: boolean;
  } | null;
}

export interface EnvelopeError {
  code: string;
  message: string;
  field?: string | null;
  suggestion?: string | null;
  retry?: boolean;
  retry_after?: number | null;
}

export interface Envelope<T> {
  data: T | null;
  meta: EnvelopeMeta;
  errors: EnvelopeError[];
}

export function wrapEnvelope<T>(
  data: T,
  meta?: Partial<EnvelopeMeta>,
): Envelope<T> {
  return {
    data,
    meta: {
      request_id: nextId(),
      timestamp: isoNow(),
      pagination: null,
      ...meta,
    },
    errors: [],
  };
}

export function wrapListEnvelope<T>(
  data: T[],
  pagination?: {
    total_count?: number;
    page?: number;
    page_size?: number;
    has_more?: boolean;
  },
): Envelope<T[]> {
  const total = pagination?.total_count ?? data.length;
  const page = pagination?.page ?? 1;
  const pageSize = pagination?.page_size ?? 20;
  return {
    data,
    meta: {
      request_id: nextId(),
      timestamp: isoNow(),
      pagination: {
        total_count: total,
        page,
        page_size: pageSize,
        has_more: pagination?.has_more ?? total > page * pageSize,
      },
    },
    errors: [],
  };
}

export function wrapErrorEnvelope(
  code: string,
  message: string,
  suggestion?: string,
): Envelope<null> {
  return {
    data: null,
    meta: {
      request_id: nextId(),
      timestamp: isoNow(),
    },
    errors: [
      {
        code,
        message,
        suggestion: suggestion ?? null,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Mock user
// ---------------------------------------------------------------------------

export interface MockUser {
  id: string;
  email: string;
  display_name: string;
  org_id: string;
  is_active: boolean;
  role: string;
}

export function mockUser(overrides?: Partial<MockUser>): MockUser {
  return {
    id: nextId(),
    email: "alice@acmelab.com",
    display_name: "Alice Chen",
    org_id: nextId(),
    is_active: true,
    role: "admin",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Mock upload
// ---------------------------------------------------------------------------

export type UploadStatus =
  | "pending"
  | "uploading"
  | "parsing"
  | "parsed"
  | "failed"
  | "queued";

export interface MockUpload {
  id: string;
  filename: string;
  instrument_type: string;
  status: UploadStatus;
  file_size: number;
  file_hash: string;
  s3_key: string;
  org_id: string;
  uploaded_by: string;
  project_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  parsed_data?: MockParsedData | null;
}

export interface MockParsedData {
  instrument_type: string;
  sample_count: number;
  measurements: MockMeasurement[];
}

export function mockUpload(overrides?: Partial<MockUpload>): MockUpload {
  return {
    id: nextId(),
    filename: "nanodrop_2024-03-05.csv",
    instrument_type: "spectrophotometer",
    status: "parsed",
    file_size: 14520,
    file_hash: "sha256:abc123def456",
    s3_key: "uploads/org-1/nanodrop_2024-03-05.csv",
    org_id: "org-001",
    uploaded_by: "user-001",
    project_id: null,
    error_message: null,
    created_at: "2026-03-05T10:00:00Z",
    updated_at: "2026-03-05T10:01:00Z",
    parsed_data: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Mock experiment
// ---------------------------------------------------------------------------

export type ExperimentStatus =
  | "draft"
  | "active"
  | "completed"
  | "archived"
  | "cancelled";

export interface MockExperiment {
  id: string;
  name: string;
  description: string;
  status: ExperimentStatus;
  campaign_id: string | null;
  org_id: string;
  created_by: string;
  upload_ids: string[];
  parameters: Record<string, unknown>;
  outcome: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export function mockExperiment(
  overrides?: Partial<MockExperiment>,
): MockExperiment {
  return {
    id: nextId(),
    name: "DNA Quantification Batch #42",
    description: "Measure concentrations of extracted gDNA samples",
    status: "active",
    campaign_id: null,
    org_id: "org-001",
    created_by: "user-001",
    upload_ids: [],
    parameters: { target_concentration: "50ng/uL" },
    outcome: null,
    created_at: "2026-03-04T09:00:00Z",
    updated_at: "2026-03-04T09:30:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Mock agent
// ---------------------------------------------------------------------------

export type AgentStatus = "online" | "offline" | "degraded";

export interface MockAgent {
  id: string;
  name: string;
  hostname: string;
  status: AgentStatus;
  version: string;
  os: string;
  watch_paths: string[];
  last_heartbeat: string;
  org_id: string;
  created_at: string;
}

export function mockAgent(overrides?: Partial<MockAgent>): MockAgent {
  return {
    id: nextId(),
    name: "Lab Desktop Agent",
    hostname: "LAB-PC-01",
    status: "online",
    version: "0.1.0",
    os: "windows",
    watch_paths: ["C:\\LabData\\NanoDrop", "C:\\LabData\\PlateReader"],
    last_heartbeat: isoNow(),
    org_id: "org-001",
    created_at: "2026-03-01T08:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Mock measurement
// ---------------------------------------------------------------------------

export interface MockMeasurement {
  id: string;
  sample_id: string;
  measurement_type: string;
  value: number;
  unit: string;
  wavelength_nm?: number | null;
  well_position?: string | null;
}

export function mockMeasurement(
  overrides?: Partial<MockMeasurement>,
): MockMeasurement {
  return {
    id: nextId(),
    sample_id: "sample-001",
    measurement_type: "absorbance",
    value: 1.823,
    unit: "AU",
    wavelength_nm: 260,
    well_position: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Mock search result
// ---------------------------------------------------------------------------

export interface MockSearchResult {
  id: string;
  entity_type: "upload" | "experiment" | "measurement";
  title: string;
  snippet: string;
  score: number;
  highlights: string[];
  created_at: string;
}

export function mockSearchResult(
  overrides?: Partial<MockSearchResult>,
): MockSearchResult {
  return {
    id: nextId(),
    entity_type: "upload",
    title: "nanodrop_2024-03-05.csv",
    snippet: "Absorbance measurements at 260nm/280nm for gDNA samples",
    score: 0.95,
    highlights: ["<em>absorbance</em> measurements at <em>260nm</em>"],
    created_at: "2026-03-05T10:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Reset ID counter (for test isolation)
// ---------------------------------------------------------------------------

export function resetIdCounter(): void {
  _idCounter = 0;
}
