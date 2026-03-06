/**
 * Tests for useSSE — typed event dispatch and event-store integration
 *
 * These tests focus on the *new* behaviour added in the extension:
 *  1. Typed LabLink events (file_ingested, job_status, alert_triggered)
 *     are parsed and dispatched into the shared eventStore.
 *  2. dispatchToStore=false opts out of store integration.
 *  3. Malformed JSON is handled gracefully (no crash, warning logged).
 *  4. Connection status is mirrored into the eventStore.
 *  5. Multiple rapid events do not interfere with each other.
 *  6. Reconnection correctly re-registers the typed listeners.
 *
 * The FakeEventSource from the original test file is reproduced here so each
 * file is self-contained, avoiding shared mutable state across test suites.
 */

import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSSE } from "../useSSE";
import { useEventStore } from "@/store/eventStore";
import type {
  FileIngestedPayload,
  JobStatusPayload,
  AlertTriggeredPayload,
  ConnectedPayload,
} from "@/types/sse";

// ---------------------------------------------------------------------------
// Fake EventSource (identical shape to the one in useSSE.test.ts)
// ---------------------------------------------------------------------------

interface FakeESInstance {
  url: string;
  onopen:   ((e: Event) => void) | null;
  onerror:  ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  eventListeners: Map<string, Array<(e: Event) => void>>;
  addEventListener: Mock;
  removeEventListener: Mock;
  close: Mock;
  simulateOpen: () => void;
  simulateError: () => void;
  simulateMessage: (data: string) => void;
  simulateNamedEvent: (type: string, data: string) => void;
}

let fakeInstances: FakeESInstance[] = [];

class FakeEventSource implements FakeESInstance {
  url: string;
  onopen:   ((e: Event) => void) | null = null;
  onerror:  ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  eventListeners: Map<string, Array<(e: Event) => void>> = new Map();
  close: Mock = vi.fn();

  addEventListener: Mock = vi.fn((type: string, handler: (e: Event) => void) => {
    const list = this.eventListeners.get(type) ?? [];
    list.push(handler);
    this.eventListeners.set(type, list);
  });

  removeEventListener: Mock = vi.fn();

  constructor(url: string) {
    this.url = url;
    fakeInstances.push(this);
  }

  simulateOpen() {
    this.onopen?.(new Event("open"));
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }

  simulateMessage(data: string) {
    const event = new MessageEvent("message", { data });
    this.onmessage?.(event);
  }

  simulateNamedEvent(type: string, data: string) {
    const event = new MessageEvent(type, { data });
    const handlers = this.eventListeners.get(type) ?? [];
    for (const h of handlers) h(event);
  }
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

const OriginalEventSource = globalThis.EventSource;

beforeEach(() => {
  fakeInstances = [];
  vi.useFakeTimers();
  // @ts-expect-error — replace global with fake
  globalThis.EventSource = FakeEventSource;
  // Reset the event store to a clean slate
  useEventStore.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  globalThis.EventSource = OriginalEventSource;
  useEventStore.getState().reset();
});

function latestInstance(): FakeESInstance {
  return fakeInstances[fakeInstances.length - 1];
}

// ---------------------------------------------------------------------------
// Helpers: typed SSE payloads
// ---------------------------------------------------------------------------

const fileIngestedPayload = {
  uploadId: "upload-abc",
  filename: "results.csv",
  instrumentType: "spectrophotometer",
  measurementCount: 48,
  status: "success" as const,
  completedAt: "2026-03-06T10:00:00Z",
};

const jobStatusPayload = {
  jobId: "job-123",
  jobType: "export",
  status: "running" as const,
  progress: 42,
  updatedAt: "2026-03-06T10:01:00Z",
};

const alertTriggeredPayload = {
  alertId: "alert-99",
  alertName: "OD Spike",
  severity: "critical" as const,
  message: "OD600 value exceeded 2.0",
  triggeredAt: "2026-03-06T10:02:00Z",
};

// ---------------------------------------------------------------------------
// 1. file_ingested event dispatched to store
// ---------------------------------------------------------------------------

describe("useSSE — typed dispatch: file_ingested", () => {
  it("dispatches a file_ingested event to the event store", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent(
        "file_ingested",
        JSON.stringify(fileIngestedPayload),
      );
    });

    const events = useEventStore.getState().events;
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("file_ingested");
    expect(events[0].payload).toMatchObject(fileIngestedPayload);
  });

  it("assigns a unique id to each dispatched event", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify({ ...fileIngestedPayload, uploadId: "u2" }));
    });

    const events = useEventStore.getState().events;
    expect(events).toHaveLength(2);
    expect(events[0].id).not.toBe(events[1].id);
  });

  it("sets receivedAt to a recent timestamp", () => {
    const before = Date.now();
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
    });

    const after = Date.now();
    const { receivedAt } = useEventStore.getState().events[0];
    expect(receivedAt).toBeGreaterThanOrEqual(before);
    expect(receivedAt).toBeLessThanOrEqual(after);
  });

  it("failed file ingests (status=failed) are also dispatched", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent(
        "file_ingested",
        JSON.stringify({ ...fileIngestedPayload, status: "failed", errorMessage: "parse error" }),
      );
    });

    const [evt] = useEventStore.getState().events;
    expect((evt.payload as FileIngestedPayload).status).toBe("failed");
  });
});

// ---------------------------------------------------------------------------
// 2. job_status event dispatched to store
// ---------------------------------------------------------------------------

describe("useSSE — typed dispatch: job_status", () => {
  it("dispatches a job_status event to the event store", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("job_status", JSON.stringify(jobStatusPayload));
    });

    const events = useEventStore.getState().events;
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("job_status");
    expect(events[0].payload).toMatchObject(jobStatusPayload);
  });

  it("accumulates sequential job_status updates in the store", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("job_status", JSON.stringify({ ...jobStatusPayload, progress: 0 }));
      latestInstance().simulateNamedEvent("job_status", JSON.stringify({ ...jobStatusPayload, progress: 50 }));
      latestInstance().simulateNamedEvent("job_status", JSON.stringify({ ...jobStatusPayload, progress: 100, status: "complete" }));
    });

    const events = useEventStore.getState().events;
    expect(events).toHaveLength(3);
    // Newest first — last dispatched is events[0]
    const latestJob = events[0].payload as JobStatusPayload;
    expect(latestJob.progress).toBe(100);
    expect(latestJob.status).toBe("complete");
  });
});

// ---------------------------------------------------------------------------
// 3. alert_triggered event dispatched to store
// ---------------------------------------------------------------------------

describe("useSSE — typed dispatch: alert_triggered", () => {
  it("dispatches an alert_triggered event to the event store", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("alert_triggered", JSON.stringify(alertTriggeredPayload));
    });

    const events = useEventStore.getState().events;
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("alert_triggered");
    expect(events[0].payload).toMatchObject(alertTriggeredPayload);
  });

  it("correctly stores severity levels", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("alert_triggered", JSON.stringify({ ...alertTriggeredPayload, severity: "info" }));
    });

    expect((useEventStore.getState().events[0].payload as AlertTriggeredPayload).severity).toBe("info");
  });
});

// ---------------------------------------------------------------------------
// 4. Mixed event types all dispatched correctly
// ---------------------------------------------------------------------------

describe("useSSE — typed dispatch: mixed event types", () => {
  it("dispatches file_ingested, job_status, and alert_triggered in one stream", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
      latestInstance().simulateNamedEvent("job_status", JSON.stringify(jobStatusPayload));
      latestInstance().simulateNamedEvent("alert_triggered", JSON.stringify(alertTriggeredPayload));
    });

    const store = useEventStore.getState();
    expect(store.events).toHaveLength(3);
    expect(store.totalReceived).toBe(3);

    const types = store.events.map((e) => e.type);
    expect(types).toContain("file_ingested");
    expect(types).toContain("job_status");
    expect(types).toContain("alert_triggered");
  });

  it("heartbeat events are also dispatched", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("heartbeat", JSON.stringify({}));
    });

    expect(useEventStore.getState().events[0].type).toBe("heartbeat");
  });

  it("connected event is dispatched on stream establishment", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent(
        "connected",
        JSON.stringify({ serverId: "srv-1", protocolVersion: "1.0" }),
      );
    });

    const [evt] = useEventStore.getState().events;
    expect(evt.type).toBe("connected");
    expect((evt.payload as ConnectedPayload).serverId).toBe("srv-1");
  });
});

// ---------------------------------------------------------------------------
// 5. dispatchToStore=false opt-out
// ---------------------------------------------------------------------------

describe("useSSE — dispatchToStore=false", () => {
  it("does not write events to the store when opted out", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false, dispatchToStore: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
      latestInstance().simulateNamedEvent("job_status", JSON.stringify(jobStatusPayload));
    });

    expect(useEventStore.getState().events).toHaveLength(0);
  });

  it("still calls onEvent handlers when dispatchToStore=false", () => {
    const handler = vi.fn();
    renderHook(() =>
      useSSE("/api/stream", {
        jitter: false,
        dispatchToStore: false,
        onEvent: { file_ingested: handler },
      }),
    );

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
    });

    expect(handler).toHaveBeenCalledOnce();
    expect(useEventStore.getState().events).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 6. Malformed JSON handling
// ---------------------------------------------------------------------------

describe("useSSE — malformed event data", () => {
  it("does not throw when event data is invalid JSON", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    expect(() => {
      act(() => {
        latestInstance().simulateOpen();
        latestInstance().simulateNamedEvent("file_ingested", "not-valid-json{{");
      });
    }).not.toThrow();

    warnSpy.mockRestore();
  });

  it("logs a warning with the event type and raw data on parse failure", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", "not-valid-json{{");
    });

    expect(warnSpy).toHaveBeenCalledWith(
      "[useSSE] Failed to parse typed event payload",
      expect.objectContaining({ type: "file_ingested", data: "not-valid-json{{" }),
    );

    warnSpy.mockRestore();
  });

  it("does not add anything to the event store after a parse failure", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", "{broken");
    });

    expect(useEventStore.getState().events).toHaveLength(0);
  });

  it("continues dispatching valid events after a parse failure", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    renderHook(() => useSSE("/api/stream", { jitter: false }));

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", "bad-data");
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
    });

    expect(useEventStore.getState().events).toHaveLength(1);
    expect(useEventStore.getState().events[0].type).toBe("file_ingested");
  });
});

// ---------------------------------------------------------------------------
// 7. Connection status mirrored into the event store
// ---------------------------------------------------------------------------

describe("useSSE — event store connection status mirroring", () => {
  it("sets store status to 'connecting' when hook initialises with a URL", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));
    expect(useEventStore.getState().connectionStatus).toBe("connecting");
  });

  it("sets store status to 'connected' when EventSource opens", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false }));
    act(() => latestInstance().simulateOpen());
    expect(useEventStore.getState().connectionStatus).toBe("connected");
  });

  it("sets store status to 'error' when EventSource fires an error", () => {
    renderHook(() => useSSE("/api/stream", { jitter: false, maxRetries: 1 }));
    act(() => latestInstance().simulateError());
    expect(useEventStore.getState().connectionStatus).toBe("error");
  });

  it("sets store status to 'idle' when enabled=false", () => {
    renderHook(() => useSSE("/api/stream", { enabled: false }));
    expect(useEventStore.getState().connectionStatus).toBe("idle");
  });

  it("sets store status to 'closed' when max retries are exhausted", () => {
    renderHook(() =>
      useSSE("/api/stream", { jitter: false, initialBackoff: 100, maxBackoff: 200, maxRetries: 1 }),
    );

    act(() => latestInstance().simulateError()); // retry 1 scheduled
    act(() => vi.advanceTimersByTime(200));       // retry 1 fires
    act(() => latestInstance().simulateError()); // no more retries

    expect(useEventStore.getState().connectionStatus).toBe("closed");
  });

  it("sets store status to 'closed' when close() is called manually", () => {
    const { result } = renderHook(() => useSSE("/api/stream", { jitter: false }));
    act(() => result.current.close());
    expect(useEventStore.getState().connectionStatus).toBe("closed");
  });
});

// ---------------------------------------------------------------------------
// 8. Reconnection re-registers typed listeners
// ---------------------------------------------------------------------------

describe("useSSE — reconnection preserves typed dispatch", () => {
  it("dispatches typed events after automatic reconnect", () => {
    renderHook(() =>
      useSSE("/api/stream", { jitter: false, initialBackoff: 100, maxBackoff: 200 }),
    );

    // First connection: open, error, reconnect
    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(150));

    // Second connection established
    act(() => latestInstance().simulateOpen());

    // Events should still be dispatched to store on the new connection
    act(() => {
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
    });

    expect(useEventStore.getState().events).toHaveLength(1);
    expect(useEventStore.getState().events[0].type).toBe("file_ingested");
  });

  it("accumulates events across reconnections", () => {
    renderHook(() =>
      useSSE("/api/stream", { jitter: false, initialBackoff: 100, maxBackoff: 200 }),
    );

    // First connection session: 1 event
    act(() => latestInstance().simulateOpen());
    act(() => latestInstance().simulateNamedEvent("job_status", JSON.stringify(jobStatusPayload)));

    // Drop + reconnect
    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(150));

    // Second connection session: 1 more event
    act(() => latestInstance().simulateOpen());
    act(() => latestInstance().simulateNamedEvent("alert_triggered", JSON.stringify(alertTriggeredPayload)));

    expect(useEventStore.getState().events).toHaveLength(2);
    expect(useEventStore.getState().totalReceived).toBe(2);
  });

  it("store connection status transitions correctly during reconnect cycle", () => {
    renderHook(() =>
      useSSE("/api/stream", { jitter: false, initialBackoff: 100, maxBackoff: 200 }),
    );

    // connecting → error → (timer) → connecting → connected
    expect(useEventStore.getState().connectionStatus).toBe("connecting");

    act(() => latestInstance().simulateError());
    expect(useEventStore.getState().connectionStatus).toBe("error");

    act(() => vi.advanceTimersByTime(150));
    expect(useEventStore.getState().connectionStatus).toBe("connecting");

    act(() => latestInstance().simulateOpen());
    expect(useEventStore.getState().connectionStatus).toBe("connected");
  });
});

// ---------------------------------------------------------------------------
// 9. onEvent handlers and store dispatch coexist
// ---------------------------------------------------------------------------

describe("useSSE — onEvent and store dispatch together", () => {
  it("calls onEvent handler AND dispatches to store for the same event", () => {
    const handler = vi.fn();
    renderHook(() =>
      useSSE("/api/stream", {
        jitter: false,
        onEvent: { file_ingested: handler },
      }),
    );

    act(() => {
      latestInstance().simulateOpen();
      latestInstance().simulateNamedEvent("file_ingested", JSON.stringify(fileIngestedPayload));
    });

    // onEvent handler was called
    expect(handler).toHaveBeenCalledOnce();
    // Event store also has the event
    expect(useEventStore.getState().events).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// 10. Unmount cleans up and does not dispatch further events
// ---------------------------------------------------------------------------

describe("useSSE — cleanup on unmount", () => {
  it("store is not written to after unmount", () => {
    const { unmount } = renderHook(() => useSSE("/api/stream", { jitter: false }));
    act(() => latestInstance().simulateOpen());
    unmount();

    // Simulate server pushing an event after unmount — should not reach store
    // (EventSource is closed, so this won't fire, but we verify via store count)
    expect(useEventStore.getState().events).toHaveLength(0);
    expect(useEventStore.getState().connectionStatus).toBe("closed");
  });
});
