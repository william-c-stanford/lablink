/**
 * Tests for the eventStore Zustand slice
 *
 * Covers:
 *  - addEvent / clearEvents CRUD
 *  - MAX_EVENTS cap (oldest events evicted)
 *  - totalReceived counter
 *  - lastEventAt tracking
 *  - setConnectionStatus
 *  - All typed selectors (selectFileIngestedEvents, selectJobStatusEvents, etc.)
 *  - selectLatestByType helper
 *  - reset()
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  useEventStore,
  MAX_EVENTS,
  selectFileIngestedEvents,
  selectJobStatusEvents,
  selectAlertEvents,
  selectLatestByType,
  selectIsConnected,
  selectTotalReceived,
  selectLastEventAt,
} from "../eventStore";
import type { SSEEvent } from "@/types/sse";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _counter = 0;
function makeEvent<T extends SSEEvent["type"]>(
  type: T,
  payload: SSEEvent<T>["payload"],
  receivedAt = Date.now(),
): SSEEvent<T> {
  _counter += 1;
  return { id: `test-${_counter}`, type, payload, receivedAt } as SSEEvent<T>;
}

function makeFileIngested(partial: Partial<SSEEvent<"file_ingested">["payload"]> = {}): SSEEvent<"file_ingested"> {
  return makeEvent("file_ingested", {
    uploadId: "u1",
    filename: "data.csv",
    instrumentType: "spectrophotometer",
    measurementCount: 10,
    status: "success",
    completedAt: "2026-03-06T12:00:00Z",
    ...partial,
  });
}

function makeJobStatus(partial: Partial<SSEEvent<"job_status">["payload"]> = {}): SSEEvent<"job_status"> {
  return makeEvent("job_status", {
    jobId: "j1",
    jobType: "export",
    status: "running",
    updatedAt: "2026-03-06T12:00:00Z",
    ...partial,
  });
}

function makeAlertTriggered(partial: Partial<SSEEvent<"alert_triggered">["payload"]> = {}): SSEEvent<"alert_triggered"> {
  return makeEvent("alert_triggered", {
    alertId: "a1",
    alertName: "High OD",
    severity: "warning",
    message: "OD600 exceeded threshold",
    triggeredAt: "2026-03-06T12:00:00Z",
    ...partial,
  });
}

// Reset store state before every test
beforeEach(() => {
  useEventStore.getState().reset();
});

// ---------------------------------------------------------------------------
// addEvent
// ---------------------------------------------------------------------------

describe("eventStore — addEvent", () => {
  it("starts with an empty events list", () => {
    expect(useEventStore.getState().events).toHaveLength(0);
  });

  it("adds an event and returns it as the first element (newest first)", () => {
    const evt = makeFileIngested();
    useEventStore.getState().addEvent(evt);
    const events = useEventStore.getState().events;
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual(evt);
  });

  it("prepends events so the list is newest-first", () => {
    const e1 = makeFileIngested({ uploadId: "first" });
    const e2 = makeFileIngested({ uploadId: "second" });
    useEventStore.getState().addEvent(e1);
    useEventStore.getState().addEvent(e2);
    const events = useEventStore.getState().events as FileIngestedEvent[];
    expect(events[0].payload.uploadId).toBe("second");
    expect(events[1].payload.uploadId).toBe("first");
  });

  it("handles events of different types in the same list", () => {
    useEventStore.getState().addEvent(makeFileIngested());
    useEventStore.getState().addEvent(makeJobStatus());
    useEventStore.getState().addEvent(makeAlertTriggered());
    expect(useEventStore.getState().events).toHaveLength(3);
  });

  it("increments totalReceived on each addEvent", () => {
    useEventStore.getState().addEvent(makeFileIngested());
    useEventStore.getState().addEvent(makeJobStatus());
    expect(useEventStore.getState().totalReceived).toBe(2);
  });

  it("updates lastEventAt to the event's receivedAt", () => {
    const ts = 1_700_000_000_000;
    useEventStore.getState().addEvent(makeEvent("heartbeat", {}, ts));
    expect(useEventStore.getState().lastEventAt).toBe(ts);
  });

  it("retains lastEventAt from the most recently added event", () => {
    useEventStore.getState().addEvent(makeEvent("heartbeat", {}, 1000));
    useEventStore.getState().addEvent(makeEvent("heartbeat", {}, 2000));
    expect(useEventStore.getState().lastEventAt).toBe(2000);
  });
});

// ---------------------------------------------------------------------------
// MAX_EVENTS cap
// ---------------------------------------------------------------------------

describe("eventStore — MAX_EVENTS cap", () => {
  it("does not evict events when below the cap", () => {
    for (let i = 0; i < MAX_EVENTS - 1; i++) {
      useEventStore.getState().addEvent(makeFileIngested());
    }
    expect(useEventStore.getState().events).toHaveLength(MAX_EVENTS - 1);
  });

  it("evicts the oldest event when the cap is exceeded", () => {
    const first = makeFileIngested({ uploadId: "oldest" });
    useEventStore.getState().addEvent(first);

    for (let i = 0; i < MAX_EVENTS; i++) {
      useEventStore.getState().addEvent(makeFileIngested({ uploadId: `fill-${i}` }));
    }

    const events = useEventStore.getState().events as FileIngestedEvent[];
    expect(events).toHaveLength(MAX_EVENTS);
    // The "oldest" event should have been evicted (it's no longer in the list)
    expect(events.some((e) => e.payload.uploadId === "oldest")).toBe(false);
  });

  it("keeps exactly MAX_EVENTS entries after many additions", () => {
    for (let i = 0; i < MAX_EVENTS * 3; i++) {
      useEventStore.getState().addEvent(makeFileIngested());
    }
    expect(useEventStore.getState().events).toHaveLength(MAX_EVENTS);
  });

  it("totalReceived is not capped — counts every event even after eviction", () => {
    for (let i = 0; i < MAX_EVENTS + 10; i++) {
      useEventStore.getState().addEvent(makeFileIngested());
    }
    expect(useEventStore.getState().totalReceived).toBe(MAX_EVENTS + 10);
  });
});

// ---------------------------------------------------------------------------
// clearEvents
// ---------------------------------------------------------------------------

describe("eventStore — clearEvents", () => {
  it("empties the events list", () => {
    useEventStore.getState().addEvent(makeFileIngested());
    useEventStore.getState().addEvent(makeJobStatus());
    useEventStore.getState().clearEvents();
    expect(useEventStore.getState().events).toHaveLength(0);
  });

  it("resets lastEventAt to null", () => {
    useEventStore.getState().addEvent(makeFileIngested());
    useEventStore.getState().clearEvents();
    expect(useEventStore.getState().lastEventAt).toBeNull();
  });

  it("does not reset totalReceived (historical count preserved)", () => {
    useEventStore.getState().addEvent(makeFileIngested());
    useEventStore.getState().addEvent(makeJobStatus());
    useEventStore.getState().clearEvents();
    // totalReceived is a session counter; clearEvents only empties the visible list
    expect(useEventStore.getState().totalReceived).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// setConnectionStatus
// ---------------------------------------------------------------------------

describe("eventStore — setConnectionStatus", () => {
  it("starts as 'idle'", () => {
    expect(useEventStore.getState().connectionStatus).toBe("idle");
  });

  it("updates to the given status", () => {
    useEventStore.getState().setConnectionStatus("connected");
    expect(useEventStore.getState().connectionStatus).toBe("connected");
  });

  it("transitions through the full lifecycle", () => {
    const store = useEventStore.getState();
    store.setConnectionStatus("connecting");
    expect(useEventStore.getState().connectionStatus).toBe("connecting");
    store.setConnectionStatus("connected");
    expect(useEventStore.getState().connectionStatus).toBe("connected");
    store.setConnectionStatus("error");
    expect(useEventStore.getState().connectionStatus).toBe("error");
    store.setConnectionStatus("closed");
    expect(useEventStore.getState().connectionStatus).toBe("closed");
  });
});

// ---------------------------------------------------------------------------
// Selectors
// ---------------------------------------------------------------------------

describe("eventStore — selectIsConnected", () => {
  it("returns false when status is idle", () => {
    expect(selectIsConnected(useEventStore.getState())).toBe(false);
  });

  it("returns true only when status is 'connected'", () => {
    useEventStore.getState().setConnectionStatus("connected");
    expect(selectIsConnected(useEventStore.getState())).toBe(true);
  });

  it("returns false when status is 'connecting'", () => {
    useEventStore.getState().setConnectionStatus("connecting");
    expect(selectIsConnected(useEventStore.getState())).toBe(false);
  });
});

describe("eventStore — selectTotalReceived / selectLastEventAt", () => {
  it("selectTotalReceived returns 0 initially", () => {
    expect(selectTotalReceived(useEventStore.getState())).toBe(0);
  });

  it("selectLastEventAt returns null initially", () => {
    expect(selectLastEventAt(useEventStore.getState())).toBeNull();
  });

  it("selectLastEventAt reflects the most recent receivedAt", () => {
    useEventStore.getState().addEvent(makeEvent("heartbeat", {}, 9_999));
    expect(selectLastEventAt(useEventStore.getState())).toBe(9_999);
  });
});

describe("eventStore — selectFileIngestedEvents", () => {
  it("returns only file_ingested events", () => {
    useEventStore.getState().addEvent(makeFileIngested());
    useEventStore.getState().addEvent(makeJobStatus());
    useEventStore.getState().addEvent(makeAlertTriggered());
    const events = selectFileIngestedEvents(useEventStore.getState());
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("file_ingested");
  });

  it("returns empty array when no file_ingested events exist", () => {
    useEventStore.getState().addEvent(makeJobStatus());
    expect(selectFileIngestedEvents(useEventStore.getState())).toHaveLength(0);
  });

  it("returns multiple file_ingested events, newest first", () => {
    const e1 = makeFileIngested({ uploadId: "u-old" });
    const e2 = makeFileIngested({ uploadId: "u-new" });
    useEventStore.getState().addEvent(e1);
    useEventStore.getState().addEvent(e2);
    const events = selectFileIngestedEvents(useEventStore.getState());
    expect(events[0].payload.uploadId).toBe("u-new");
    expect(events[1].payload.uploadId).toBe("u-old");
  });
});

describe("eventStore — selectJobStatusEvents", () => {
  it("returns only job_status events", () => {
    useEventStore.getState().addEvent(makeJobStatus());
    useEventStore.getState().addEvent(makeFileIngested());
    const events = selectJobStatusEvents(useEventStore.getState());
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("job_status");
  });

  it("filters by status field in payload", () => {
    useEventStore.getState().addEvent(makeJobStatus({ status: "complete" }));
    useEventStore.getState().addEvent(makeJobStatus({ status: "failed" }));
    const events = selectJobStatusEvents(useEventStore.getState());
    expect(events).toHaveLength(2);
    const statuses = events.map((e) => e.payload.status);
    expect(statuses).toContain("complete");
    expect(statuses).toContain("failed");
  });
});

describe("eventStore — selectAlertEvents", () => {
  it("returns only alert_triggered events", () => {
    useEventStore.getState().addEvent(makeAlertTriggered({ severity: "critical" }));
    useEventStore.getState().addEvent(makeFileIngested());
    const events = selectAlertEvents(useEventStore.getState());
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("alert_triggered");
    expect(events[0].payload.severity).toBe("critical");
  });
});

describe("eventStore — selectLatestByType", () => {
  it("returns null when no event of that type exists", () => {
    useEventStore.getState().addEvent(makeJobStatus());
    const latest = selectLatestByType("file_ingested")(useEventStore.getState());
    expect(latest).toBeNull();
  });

  it("returns the most recently added event of the given type", () => {
    useEventStore.getState().addEvent(makeFileIngested({ uploadId: "old" }));
    useEventStore.getState().addEvent(makeFileIngested({ uploadId: "new" }));
    const latest = selectLatestByType("file_ingested")(useEventStore.getState());
    expect(latest?.payload.uploadId).toBe("new");
  });

  it("is unaffected by events of other types", () => {
    useEventStore.getState().addEvent(makeFileIngested({ uploadId: "target" }));
    useEventStore.getState().addEvent(makeJobStatus());
    useEventStore.getState().addEvent(makeAlertTriggered());
    const latest = selectLatestByType("file_ingested")(useEventStore.getState());
    expect(latest?.payload.uploadId).toBe("target");
  });
});

// ---------------------------------------------------------------------------
// reset()
// ---------------------------------------------------------------------------

describe("eventStore — reset", () => {
  it("restores initial state completely", () => {
    const store = useEventStore.getState();
    store.addEvent(makeFileIngested());
    store.addEvent(makeJobStatus());
    store.setConnectionStatus("connected");
    store.reset();
    const s = useEventStore.getState();
    expect(s.events).toHaveLength(0);
    expect(s.connectionStatus).toBe("idle");
    expect(s.lastEventAt).toBeNull();
    expect(s.totalReceived).toBe(0);
  });
});
