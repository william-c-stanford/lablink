/**
 * Event Store — shared Zustand store for real-time SSE events
 *
 * The `useSSE` hook writes incoming events here so any component can
 * subscribe to the live feed without prop-drilling or Context overhead.
 *
 * Design decisions:
 *  - Capped at MAX_EVENTS (newest first) to avoid unbounded memory growth
 *  - Typed selectors for the three primary event categories
 *  - Connection status is co-located so components can show connection UI
 */

import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type {
  SSEEvent,
  SSEEventType,
  SSEConnectionStatus,
  FileIngestedEvent,
  JobStatusEvent,
  AlertTriggeredEvent,
} from "@/types/sse";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Maximum number of events retained in memory. */
export const MAX_EVENTS = 100;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EventState {
  /** Ordered list of received events, newest first. Capped at MAX_EVENTS. */
  events: SSEEvent[];
  /** Current SSE connection status (managed by useSSE). */
  connectionStatus: SSEConnectionStatus;
  /** Timestamp (Date.now()) of the last received event, or null if none. */
  lastEventAt: number | null;
  /** Running total of events received in this session. */
  totalReceived: number;
}

export interface EventActions {
  /** Add a new event to the top of the list; evicts oldest if over cap. */
  addEvent: (event: SSEEvent) => void;
  /** Remove all stored events. */
  clearEvents: () => void;
  /** Update the connection status (called by useSSE). */
  setConnectionStatus: (status: SSEConnectionStatus) => void;
  /** Reset to initial state (useful in tests). */
  reset: () => void;
}

export type EventStore = EventState & EventActions;

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

const initialState: EventState = {
  events: [],
  connectionStatus: "idle",
  lastEventAt: null,
  totalReceived: 0,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useEventStore = create<EventStore>()(
  devtools(
    (set) => ({
      ...initialState,

      addEvent: (event) =>
        set(
          (s) => {
            const updated = [event, ...s.events];
            return {
              events: updated.length > MAX_EVENTS ? updated.slice(0, MAX_EVENTS) : updated,
              lastEventAt: event.receivedAt,
              totalReceived: s.totalReceived + 1,
            };
          },
          false,
          "event/addEvent",
        ),

      clearEvents: () =>
        set(
          { events: [], lastEventAt: null },
          false,
          "event/clearEvents",
        ),

      setConnectionStatus: (status) =>
        set({ connectionStatus: status }, false, "event/setConnectionStatus"),

      reset: () => set({ ...initialState }, false, "event/reset"),
    }),
    { name: "EventStore" },
  ),
);

// ---------------------------------------------------------------------------
// Selectors — stable references for component subscriptions
// ---------------------------------------------------------------------------

export const selectEvents = (s: EventStore) => s.events;
export const selectConnectionStatus = (s: EventStore) => s.connectionStatus;
export const selectLastEventAt = (s: EventStore) => s.lastEventAt;
export const selectTotalReceived = (s: EventStore) => s.totalReceived;
export const selectIsConnected = (s: EventStore) => s.connectionStatus === "connected";

/** All `file_ingested` events, newest first. */
export const selectFileIngestedEvents = (s: EventStore): FileIngestedEvent[] =>
  s.events.filter((e): e is FileIngestedEvent => e.type === "file_ingested");

/** All `job_status` events, newest first. */
export const selectJobStatusEvents = (s: EventStore): JobStatusEvent[] =>
  s.events.filter((e): e is JobStatusEvent => e.type === "job_status");

/** All `alert_triggered` events, newest first. */
export const selectAlertEvents = (s: EventStore): AlertTriggeredEvent[] =>
  s.events.filter((e): e is AlertTriggeredEvent => e.type === "alert_triggered");

/**
 * Returns the most recent event of a given type, or null if none received.
 */
export const selectLatestByType =
  <T extends SSEEventType>(type: T) =>
  (s: EventStore): SSEEvent<T> | null =>
    (s.events.find((e) => e.type === type) as SSEEvent<T> | undefined) ?? null;
