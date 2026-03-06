/**
 * Typed real-time event definitions for the LabLink SSE stream.
 *
 * The backend emits *named* SSE events (i.e. `event: file_ingested\ndata: ...`)
 * which EventSource exposes via `addEventListener(type, handler)`.
 * Each event carries a JSON-encoded payload described by the types below.
 */

// ---------------------------------------------------------------------------
// Connection status
// ---------------------------------------------------------------------------

export type SSEConnectionStatus =
  | "idle"          // hook mounted but no URL provided
  | "connecting"    // EventSource constructor called, awaiting `open`
  | "connected"     // `open` event received
  | "reconnecting"  // error occurred; backoff timer is running
  | "error"         // error state (non-recoverable or max retries exceeded)
  | "closed";       // deliberately closed (component unmounted)

// ---------------------------------------------------------------------------
// Named event types
// ---------------------------------------------------------------------------

/** The set of named event types the backend may emit. */
export const SSE_EVENT_TYPES = [
  "file_ingested",
  "job_status",
  "alert_triggered",
  "connected",
  "heartbeat",
] as const;

export type SSEEventType = (typeof SSE_EVENT_TYPES)[number];

// ---------------------------------------------------------------------------
// Per-event payloads
// ---------------------------------------------------------------------------

/**
 * Emitted when a file has been fully parsed and stored in the database.
 * Maps to the backend `POST /uploads/{id}/parse` completion.
 */
export interface FileIngestedPayload {
  uploadId: string;
  filename: string;
  instrumentType: string;
  measurementCount: number;
  projectId?: string | null;
  /** Terminal parse status. */
  status: "success" | "failed";
  errorMessage?: string | null;
  /** ISO-8601 timestamp when ingest completed. */
  completedAt: string;
}

/**
 * Emitted during and after a Celery background job (e.g. re-parse, export).
 */
export interface JobStatusPayload {
  jobId: string;
  jobType: string;
  status: "pending" | "running" | "complete" | "failed";
  /** Completion percentage 0–100. Absent if indeterminate. */
  progress?: number | null;
  message?: string | null;
  /** ISO-8601 timestamp of the last status update. */
  updatedAt: string;
}

/**
 * Emitted when a configured threshold alert fires.
 */
export interface AlertTriggeredPayload {
  alertId: string;
  alertName: string;
  severity: "info" | "warning" | "critical";
  message: string;
  experimentId?: string | null;
  measurementId?: string | null;
  /** ISO-8601 timestamp when the alert was triggered. */
  triggeredAt: string;
}

/** Sent immediately after the SSE stream is established. */
export interface ConnectedPayload {
  serverId: string;
  protocolVersion: string;
}

/** Periodic keep-alive ping (no meaningful payload). */
export type HeartbeatPayload = Record<string, never>;

// ---------------------------------------------------------------------------
// Discriminated-union SSE event
// ---------------------------------------------------------------------------

/** Maps each event type to its payload type. */
export interface SSEPayloadMap {
  file_ingested: FileIngestedPayload;
  job_status: JobStatusPayload;
  alert_triggered: AlertTriggeredPayload;
  connected: ConnectedPayload;
  heartbeat: HeartbeatPayload;
}

/** A fully-typed, enriched SSE event stored in the event store. */
export interface SSEEvent<T extends SSEEventType = SSEEventType> {
  /** Unique client-side id for React keying. */
  id: string;
  type: T;
  payload: SSEPayloadMap[T];
  /** `Date.now()` at the time the client received the event. */
  receivedAt: number;
}

// Convenience type aliases
export type FileIngestedEvent = SSEEvent<"file_ingested">;
export type JobStatusEvent = SSEEvent<"job_status">;
export type AlertTriggeredEvent = SSEEvent<"alert_triggered">;
