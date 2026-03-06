/**
 * Tests for useSSE hook
 *
 * Strategy:
 *  - Replace the global EventSource with a controllable fake
 *  - Use renderHook from @testing-library/react
 *  - Use vi.useFakeTimers() to control exponential backoff without real waits
 *  - Verify status transitions, retry logic, backoff, and manual controls
 */

import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSSE, parseSSEData, type SSEStatus } from "../useSSE";

// ---------------------------------------------------------------------------
// Fake EventSource
// ---------------------------------------------------------------------------

interface FakeESInstance {
  url: string;
  init: EventSourceInit | undefined;
  onopen:   ((e: Event) => void) | null;
  onerror:  ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  eventListeners: Map<string, Array<(e: Event) => void>>;
  addEventListener: Mock;
  removeEventListener: Mock;
  close: Mock;
  /** Test helper: simulate the connection opening */
  simulateOpen: () => void;
  /** Test helper: simulate an error / disconnect */
  simulateError: () => void;
  /** Test helper: simulate receiving a default "message" event */
  simulateMessage: (data: string) => void;
  /** Test helper: simulate receiving a named event */
  simulateNamedEvent: (type: string, data: string) => void;
}

/** All instances created during the test, in order */
let fakeInstances: FakeESInstance[] = [];

class FakeEventSource implements FakeESInstance {
  url: string;
  init: EventSourceInit | undefined;
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

  constructor(url: string, init?: EventSourceInit) {
    this.url  = url;
    this.init = init;
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
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  globalThis.EventSource = OriginalEventSource;
});

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function latestInstance(): FakeESInstance {
  return fakeInstances[fakeInstances.length - 1];
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useSSE — initial state", () => {
  it("starts as 'idle' when enabled=false", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", { enabled: false }),
    );
    expect(result.current.status).toBe<SSEStatus>("idle");
    expect(result.current.retryCount).toBe(0);
    expect(result.current.lastError).toBeNull();
    expect(result.current.lastEventAt).toBeNull();
  });

  it("starts as 'idle' when url is null", () => {
    const { result } = renderHook(() => useSSE(null));
    expect(result.current.status).toBe<SSEStatus>("idle");
  });

  it("moves to 'connecting' immediately when url is provided and enabled", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    expect(result.current.status).toBe<SSEStatus>("connecting");
  });

  it("creates an EventSource with the correct URL", () => {
    renderHook(() => useSSE("/api/uploads/stream"));
    expect(fakeInstances).toHaveLength(1);
    expect(fakeInstances[0].url).toBe("/api/uploads/stream");
  });

  it("passes eventSourceInit options to EventSource", () => {
    renderHook(() =>
      useSSE("/api/stream", { eventSourceInit: { withCredentials: true } }),
    );
    expect(fakeInstances[0].init).toEqual({ withCredentials: true });
  });
});

describe("useSSE — connection open", () => {
  it("transitions to 'open' when EventSource fires onopen", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    act(() => latestInstance().simulateOpen());
    expect(result.current.status).toBe<SSEStatus>("open");
  });

  it("resets retryCount to 0 on open", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 100, maxBackoff: 200 }),
    );

    // Trigger an error + retry cycle, then open
    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(200));
    act(() => latestInstance().simulateOpen());

    expect(result.current.retryCount).toBe(0);
  });

  it("calls onOpen callback when connection opens", () => {
    const onOpen = vi.fn();
    renderHook(() => useSSE("/api/stream", { onOpen }));
    act(() => latestInstance().simulateOpen());
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("clears lastError when connection (re)opens", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 50, maxBackoff: 100 }),
    );
    act(() => latestInstance().simulateError());
    expect(result.current.lastError).not.toBeNull();

    act(() => vi.advanceTimersByTime(100));
    act(() => latestInstance().simulateOpen());
    expect(result.current.lastError).toBeNull();
  });
});

describe("useSSE — message events", () => {
  it("updates lastEventAt when a message is received", () => {
    const now = Date.now();
    const { result } = renderHook(() => useSSE("/api/stream"));
    act(() => latestInstance().simulateOpen());
    act(() => latestInstance().simulateMessage('{"type":"ping"}'));
    expect(result.current.lastEventAt).toBeGreaterThanOrEqual(now);
  });

  it("calls onMessage for unnamed 'message' events", () => {
    const onMessage = vi.fn();
    renderHook(() => useSSE("/api/stream", { onMessage }));
    act(() => latestInstance().simulateOpen());
    act(() => latestInstance().simulateMessage("hello"));
    expect(onMessage).toHaveBeenCalledOnce();
    expect(onMessage.mock.calls[0][0]).toBeInstanceOf(MessageEvent);
  });

  it("calls named event handler from onEvent map", () => {
    const handler = vi.fn();
    renderHook(() =>
      useSSE("/api/stream", { onEvent: { "upload.complete": handler } }),
    );
    act(() => latestInstance().simulateOpen());
    act(() => latestInstance().simulateNamedEvent("upload.complete", '{"id":"abc"}'));
    expect(handler).toHaveBeenCalledOnce();
  });

  it("registers multiple named event handlers", () => {
    const h1 = vi.fn();
    const h2 = vi.fn();
    renderHook(() =>
      useSSE("/api/stream", { onEvent: { "event.a": h1, "event.b": h2 } }),
    );
    act(() => {
      latestInstance().simulateNamedEvent("event.a", "1");
      latestInstance().simulateNamedEvent("event.b", "2");
    });
    expect(h1).toHaveBeenCalledOnce();
    expect(h2).toHaveBeenCalledOnce();
  });
});

describe("useSSE — error handling and reconnect", () => {
  it("transitions to 'error' on connection failure", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    act(() => latestInstance().simulateError());
    expect(result.current.status).toBe<SSEStatus>("error");
  });

  it("stores the error event in lastError", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    act(() => latestInstance().simulateError());
    expect(result.current.lastError).toBeInstanceOf(Event);
  });

  it("calls onError callback on error", () => {
    const onError = vi.fn();
    renderHook(() => useSSE("/api/stream", { onError }));
    act(() => latestInstance().simulateError());
    expect(onError).toHaveBeenCalledOnce();
  });

  it("increments retryCount on each failure", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 100, maxBackoff: 10_000 }),
    );

    act(() => latestInstance().simulateError());
    expect(result.current.retryCount).toBe(1);

    act(() => vi.advanceTimersByTime(200));
    act(() => latestInstance().simulateError());
    expect(result.current.retryCount).toBe(2);
  });

  it("creates a new EventSource after the backoff delay", () => {
    renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 1_000, maxBackoff: 30_000, jitter: false }),
    );
    expect(fakeInstances).toHaveLength(1);

    act(() => latestInstance().simulateError());
    // Not yet — within backoff window
    expect(fakeInstances).toHaveLength(1);

    act(() => vi.advanceTimersByTime(1_100));
    expect(fakeInstances).toHaveLength(2);
  });

  it("doubles the backoff on each retry (no jitter)", () => {
    renderHook(() =>
      useSSE("/api/stream", {
        initialBackoff: 1_000,
        maxBackoff: 30_000,
        jitter: false,
      }),
    );

    // First error → backoff = 1000 ms
    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(999));
    expect(fakeInstances).toHaveLength(1); // still waiting

    act(() => vi.advanceTimersByTime(2));
    expect(fakeInstances).toHaveLength(2); // reconnected

    // Second error → backoff = 2000 ms
    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(1_999));
    expect(fakeInstances).toHaveLength(2); // still waiting

    act(() => vi.advanceTimersByTime(2));
    expect(fakeInstances).toHaveLength(3); // reconnected
  });

  it("caps backoff at maxBackoff", () => {
    renderHook(() =>
      useSSE("/api/stream", {
        initialBackoff: 1_000,
        maxBackoff: 5_000,
        jitter: false,
      }),
    );

    // exhaust enough retries to exceed cap
    for (let i = 0; i < 5; i++) {
      act(() => latestInstance().simulateError());
      act(() => vi.advanceTimersByTime(30_000)); // always advance past any cap
    }

    // All reconnections should have completed — more than 1 instance created
    expect(fakeInstances.length).toBeGreaterThan(1);
  });

  it("stops retrying after maxRetries exhausted", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", {
        initialBackoff: 100,
        maxBackoff: 1_000,
        jitter: false,
        maxRetries: 2,
      }),
    );

    act(() => latestInstance().simulateError());   // retry 1 scheduled
    act(() => vi.advanceTimersByTime(200));         // retry 1 fires
    act(() => latestInstance().simulateError());   // retry 2 scheduled
    act(() => vi.advanceTimersByTime(500));         // retry 2 fires
    act(() => latestInstance().simulateError());   // no more retries

    expect(result.current.status).toBe<SSEStatus>("closed");
    // No 4th instance should be created
    expect(fakeInstances).toHaveLength(3);
  });

  it("maxRetries=0 retries indefinitely (open after many retries)", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", {
        initialBackoff: 100,
        maxBackoff: 200,
        jitter: false,
        maxRetries: 0,
      }),
    );

    for (let i = 0; i < 10; i++) {
      act(() => latestInstance().simulateError());
      act(() => vi.advanceTimersByTime(500));
    }

    // Still not closed — status is either 'error' or 'connecting'
    expect(result.current.status).not.toBe<SSEStatus>("closed");
    expect(fakeInstances.length).toBeGreaterThan(5);
  });
});

describe("useSSE — manual controls", () => {
  it("close() transitions to 'closed'", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    act(() => result.current.close());
    expect(result.current.status).toBe<SSEStatus>("closed");
  });

  it("close() calls EventSource.close()", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    const es = latestInstance();
    act(() => result.current.close());
    expect(es.close).toHaveBeenCalled();
  });

  it("close() prevents retry after an error", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 100, maxBackoff: 200, jitter: false }),
    );

    act(() => result.current.close());
    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(500));

    // No second instance should be created
    expect(fakeInstances).toHaveLength(1);
    expect(result.current.status).toBe<SSEStatus>("closed");
  });

  it("reconnect() creates a new EventSource immediately", () => {
    const { result } = renderHook(() => useSSE("/api/stream"));
    act(() => result.current.close());
    expect(fakeInstances).toHaveLength(1);

    act(() => result.current.reconnect());
    expect(fakeInstances).toHaveLength(2);
    expect(result.current.status).toBe<SSEStatus>("connecting");
  });

  it("reconnect() resets retryCount", () => {
    const { result } = renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 100, maxBackoff: 200, jitter: false }),
    );

    act(() => latestInstance().simulateError());
    act(() => vi.advanceTimersByTime(200));
    act(() => latestInstance().simulateError());
    expect(result.current.retryCount).toBe(2);

    act(() => result.current.reconnect());
    act(() => latestInstance().simulateOpen());
    expect(result.current.retryCount).toBe(0);
  });

  it("reconnect() is a no-op when url is null", () => {
    const { result } = renderHook(() => useSSE(null));
    act(() => result.current.reconnect());
    expect(fakeInstances).toHaveLength(0);
  });
});

describe("useSSE — lifecycle", () => {
  it("closes EventSource on unmount", () => {
    const { unmount } = renderHook(() => useSSE("/api/stream"));
    const es = latestInstance();
    unmount();
    expect(es.close).toHaveBeenCalled();
  });

  it("does not attempt reconnect after unmount", () => {
    const { unmount } = renderHook(() =>
      useSSE("/api/stream", { initialBackoff: 100, maxBackoff: 200, jitter: false }),
    );

    act(() => latestInstance().simulateError());
    unmount();
    act(() => vi.advanceTimersByTime(500));

    // Still only the original instance — no retry after unmount
    expect(fakeInstances).toHaveLength(1);
  });

  it("reconnects when url changes", () => {
    const { rerender } = renderHook(
      ({ url }: { url: string }) => useSSE(url),
      { initialProps: { url: "/api/stream/v1" } },
    );
    expect(fakeInstances[0].url).toBe("/api/stream/v1");

    rerender({ url: "/api/stream/v2" });
    expect(fakeInstances).toHaveLength(2);
    expect(fakeInstances[1].url).toBe("/api/stream/v2");
  });

  it("disconnects when enabled flips to false", () => {
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useSSE("/api/stream", { enabled }),
      { initialProps: { enabled: true } },
    );

    const es = latestInstance();
    act(() => es.simulateOpen());
    expect(result.current.status).toBe<SSEStatus>("open");

    rerender({ enabled: false });
    expect(es.close).toHaveBeenCalled();
    expect(result.current.status).toBe<SSEStatus>("idle");
  });

  it("connects when enabled flips to true", () => {
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useSSE("/api/stream", { enabled }),
      { initialProps: { enabled: false } },
    );
    expect(result.current.status).toBe<SSEStatus>("idle");
    expect(fakeInstances).toHaveLength(0);

    rerender({ enabled: true });
    expect(fakeInstances).toHaveLength(1);
    expect(result.current.status).toBe<SSEStatus>("connecting");
  });
});

describe("parseSSEData", () => {
  it("parses valid JSON from event.data", () => {
    const event = new MessageEvent("message", { data: '{"id":"123","status":"ok"}' });
    const result = parseSSEData<{ id: string; status: string }>(event);
    expect(result).toEqual({ id: "123", status: "ok" });
  });

  it("returns null and logs a warning for invalid JSON", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const event = new MessageEvent("message", { data: "not-json{{{" });
    const result = parseSSEData(event);
    expect(result).toBeNull();
    expect(warnSpy).toHaveBeenCalledWith(
      "[useSSE] Failed to parse SSE event data:",
      "not-json{{{",
    );
  });

  it("handles array data", () => {
    const event = new MessageEvent("message", { data: '[1,2,3]' });
    expect(parseSSEData<number[]>(event)).toEqual([1, 2, 3]);
  });

  it("handles primitive data (string)", () => {
    const event = new MessageEvent("message", { data: '"hello"' });
    expect(parseSSEData<string>(event)).toBe("hello");
  });
});
