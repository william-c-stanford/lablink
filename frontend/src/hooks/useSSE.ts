/**
 * useSSE — Custom React hook for Server-Sent Events (SSE)
 *
 * Features:
 *  - Establishes an EventSource connection to a backend SSE endpoint
 *  - Tracks connection status: idle | connecting | open | error | closed
 *  - Exponential backoff reconnection with optional jitter
 *  - Configurable max retries (0 = infinite)
 *  - Supports named custom event types via onEvent map
 *  - Exposes manual close() and reconnect() controls
 *  - Cleans up gracefully on unmount
 *  - Optionally dispatches typed LabLink events (file_ingested, job_status,
 *    alert_triggered, connected, heartbeat) into the shared eventStore so any
 *    component can reactively consume the live feed without prop-drilling.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useEventStore } from "@/store/eventStore";
import { SSE_EVENT_TYPES } from "@/types/sse";
import type { SSEEvent, SSEEventType, SSEConnectionStatus } from "@/types/sse";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * Connection lifecycle states.
 *
 * idle       — hook is disabled (enabled=false) or not yet mounted
 * connecting — EventSource created, waiting for `open` event
 * open       — connection established, receiving events
 * error      — last attempt failed; will retry if retries remain
 * closed     — manually closed or max retries exhausted
 */
export type SSEStatus = "idle" | "connecting" | "open" | "error" | "closed";

/** Named-event handler map: { "upload.complete": handler, ... } */
export type SSEEventHandlers = Record<string, (event: MessageEvent) => void>;

export interface SSEOptions {
  /**
   * Handler for the default "message" event type (unnamed server messages).
   * Called for every `data:` line without an `event:` field.
   */
  onMessage?: (event: MessageEvent) => void;

  /**
   * Map of named event handlers.
   * Keys are the SSE `event:` field values.
   *
   * @example
   * onEvent={{
   *   "upload.complete": (e) => console.log(JSON.parse(e.data)),
   *   "agent.status":    (e) => console.log(JSON.parse(e.data)),
   * }}
   */
  onEvent?: SSEEventHandlers;

  /** Called once when the connection successfully opens. */
  onOpen?: () => void;

  /**
   * Called on every connection error.
   * Note: the browser may emit an error just before an automatic re-connect;
   * use `status` to determine if the connection is still alive.
   */
  onError?: (event: Event) => void;

  /**
   * Initial reconnect delay in milliseconds.
   * @default 1_000
   */
  initialBackoff?: number;

  /**
   * Maximum reconnect delay in milliseconds (cap for exponential growth).
   * @default 30_000
   */
  maxBackoff?: number;

  /**
   * Add ±20 % random jitter to each backoff interval.
   * Prevents thundering-herd reconnects when many clients drop simultaneously.
   * @default true
   */
  jitter?: boolean;

  /**
   * Maximum number of reconnect attempts.
   * 0 means retry indefinitely.
   * @default 0
   */
  maxRetries?: number;

  /**
   * Set to false to disable the connection (useful for conditional subscriptions).
   * When flipped to true the hook will connect immediately.
   * @default true
   */
  enabled?: boolean;

  /** Options forwarded to the EventSource constructor. */
  eventSourceInit?: EventSourceInit;

  /**
   * When `true` (the default), the hook automatically registers listeners for
   * every well-known LabLink SSE event type (`file_ingested`, `job_status`,
   * `alert_triggered`, `connected`, `heartbeat`) and dispatches each parsed
   * event into the shared `eventStore`.
   *
   * Set to `false` if you only want the raw `onEvent` callback API and do not
   * want the global store to be populated.
   *
   * @default true
   */
  dispatchToStore?: boolean;
}

export interface SSEState {
  /** Current connection lifecycle status. */
  status: SSEStatus;
  /** How many reconnect attempts have been made in this session. */
  retryCount: number;
  /** The most recent error event, or null if no error occurred yet. */
  lastError: Event | null;
  /** Timestamp of the most recently received event, or null if none yet. */
  lastEventAt: number | null;
}

export interface SSEControls {
  /** Permanently close the EventSource (will not reconnect). */
  close: () => void;
  /** Tear down the current EventSource and establish a fresh connection immediately. */
  reconnect: () => void;
}

export type UseSSEReturn = SSEState & SSEControls;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Monotonically increasing counter used to give each SSE event a unique id. */
let _sseEventCounter = 0;
function generateSSEEventId(): string {
  _sseEventCounter += 1;
  return `sse-${Date.now()}-${_sseEventCounter}`;
}

/**
 * Maps the hook's SSEStatus to the event-store's SSEConnectionStatus.
 * The only difference is that the hook calls the open state "open" while
 * the store uses the more self-descriptive "connected".
 */
function toStoreStatus(status: SSEStatus): SSEConnectionStatus {
  if (status === "open") return "connected";
  // "idle" | "connecting" | "error" | "closed" are identical in both types
  return status as SSEConnectionStatus;
}

/** Returns base * 2^attempt, capped at maxBackoff, with optional ±20% jitter. */
function calcBackoff(
  attempt: number,
  initialBackoff: number,
  maxBackoff: number,
  jitter: boolean,
): number {
  const base = Math.min(initialBackoff * Math.pow(2, attempt), maxBackoff);
  if (!jitter) return base;
  // ±20 % random jitter
  const jitterFactor = 0.8 + Math.random() * 0.4; // [0.8, 1.2)
  return Math.floor(base * jitterFactor);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useSSE — subscribe to a Server-Sent Events stream.
 *
 * @param url  The SSE endpoint URL (e.g. "/api/uploads/stream").
 *             Pass null or undefined to disable without setting enabled=false.
 * @param options  Configuration and event handlers.
 *
 * @example
 * const { status, retryCount } = useSSE("/api/uploads/stream", {
 *   onMessage: (e) => dispatch(JSON.parse(e.data)),
 *   onEvent: {
 *     "upload.complete": (e) => toast.success("Upload complete"),
 *     "agent.heartbeat": (e) => updateAgent(JSON.parse(e.data)),
 *   },
 *   maxRetries: 10,
 * });
 */
export function useSSE(
  url: string | null | undefined,
  options: SSEOptions = {},
): UseSSEReturn {
  const {
    onMessage,
    onEvent,
    onOpen,
    onError,
    initialBackoff = 1_000,
    maxBackoff = 30_000,
    jitter = true,
    maxRetries = 0,
    enabled = true,
    eventSourceInit,
    dispatchToStore = true,
  } = options;

  // Store actions — these are stable references; won't cause re-renders.
  const addStoreEvent = useEventStore((s) => s.addEvent);
  const setStoreStatus = useEventStore((s) => s.setConnectionStatus);

  const [state, setState] = useState<SSEState>({
    status: "idle",
    retryCount: 0,
    lastError: null,
    lastEventAt: null,
  });

  // ---------------------------------------------------------------------------
  // Stable refs — avoids stale closures in EventSource callbacks without
  // tearing down and recreating the connection on every render.
  // ---------------------------------------------------------------------------
  const onMessageRef = useRef(onMessage);
  const onEventRef   = useRef(onEvent);
  const onOpenRef    = useRef(onOpen);
  const onErrorRef   = useRef(onError);
  // Keep dispatchToStore in a ref so connect() always sees the latest value
  const dispatchToStoreRef = useRef(dispatchToStore);
  // Keep store-action refs stable across re-renders
  const addStoreEventRef   = useRef(addStoreEvent);
  const setStoreStatusRef  = useRef(setStoreStatus);

  useEffect(() => { onMessageRef.current      = onMessage;       }, [onMessage]);
  useEffect(() => { onEventRef.current        = onEvent;         }, [onEvent]);
  useEffect(() => { onOpenRef.current         = onOpen;          }, [onOpen]);
  useEffect(() => { onErrorRef.current        = onError;         }, [onError]);
  useEffect(() => { dispatchToStoreRef.current = dispatchToStore; }, [dispatchToStore]);
  useEffect(() => { addStoreEventRef.current   = addStoreEvent;   }, [addStoreEvent]);
  useEffect(() => { setStoreStatusRef.current  = setStoreStatus;  }, [setStoreStatus]);

  // Refs for EventSource instance and retry timer
  const esRef          = useRef<EventSource | null>(null);
  const retryTimerRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef  = useRef(0);
  // Set to true when user calls close() — prevents auto-reconnect
  const closedByUserRef = useRef(false);

  // ---------------------------------------------------------------------------
  // clearTimer helper
  // ---------------------------------------------------------------------------
  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  // ---------------------------------------------------------------------------
  // destroySource — close the EventSource cleanly, remove all listeners
  // ---------------------------------------------------------------------------
  const destroySource = useCallback(() => {
    const es = esRef.current;
    if (!es) return;
    es.onopen    = null;
    es.onerror   = null;
    es.onmessage = null;
    es.close();
    esRef.current = null;
  }, []);

  // ---------------------------------------------------------------------------
  // connect — create a new EventSource and wire up event handlers
  // ---------------------------------------------------------------------------
  const connect = useCallback((targetUrl: string) => {
    destroySource();

    setState((prev) => ({ ...prev, status: "connecting" }));
    setStoreStatusRef.current(toStoreStatus("connecting"));

    const es = new EventSource(targetUrl, eventSourceInit);
    esRef.current = es;

    es.onopen = () => {
      // Reset retry counter on a successful open
      retryCountRef.current = 0;
      setState((prev) => ({
        ...prev,
        status: "open",
        retryCount: 0,
        lastError: null,
      }));
      setStoreStatusRef.current(toStoreStatus("open"));
      onOpenRef.current?.();
    };

    es.onmessage = (event: MessageEvent) => {
      setState((prev) => ({ ...prev, lastEventAt: Date.now() }));
      onMessageRef.current?.(event);
    };

    es.onerror = (event: Event) => {
      setState((prev) => ({ ...prev, status: "error", lastError: event }));
      setStoreStatusRef.current(toStoreStatus("error"));
      onErrorRef.current?.(event);

      // The browser closes the EventSource internally on a network error;
      // destroy our reference and schedule a retry if appropriate.
      destroySource();

      if (closedByUserRef.current) return;

      const attempt = retryCountRef.current;
      if (maxRetries > 0 && attempt >= maxRetries) {
        setState((prev) => ({ ...prev, status: "closed" }));
        setStoreStatusRef.current(toStoreStatus("closed"));
        return;
      }

      const delay = calcBackoff(attempt, initialBackoff, maxBackoff, jitter);
      retryCountRef.current = attempt + 1;
      setState((prev) => ({ ...prev, retryCount: retryCountRef.current }));

      retryTimerRef.current = setTimeout(() => {
        if (!closedByUserRef.current) {
          connect(targetUrl);
        }
      }, delay);
    };

    // Register named event handlers from the caller's onEvent map
    const handlers = onEventRef.current ?? {};
    for (const [eventType, handler] of Object.entries(handlers)) {
      es.addEventListener(eventType, (event) => {
        setState((prev) => ({ ...prev, lastEventAt: Date.now() }));
        handler(event as MessageEvent);
      });
    }

    // -------------------------------------------------------------------------
    // Typed store dispatch — parse well-known LabLink SSE event types and push
    // each received event into the shared eventStore so any component can
    // reactively consume the live feed without prop-drilling or Context.
    // Opt out by passing dispatchToStore=false.
    // -------------------------------------------------------------------------
    if (dispatchToStoreRef.current) {
      for (const type of SSE_EVENT_TYPES) {
        es.addEventListener(type, (rawEvent: Event) => {
          const messageEvent = rawEvent as MessageEvent;
          try {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const payload = JSON.parse(messageEvent.data) as any;
            const sseEvent: SSEEvent = {
              id: generateSSEEventId(),
              type: type as SSEEventType,
              payload,
              receivedAt: Date.now(),
            };
            addStoreEventRef.current(sseEvent);
            // Keep local lastEventAt in sync with store events too
            setState((prev) => ({ ...prev, lastEventAt: sseEvent.receivedAt }));
          } catch {
            console.warn("[useSSE] Failed to parse typed event payload", {
              type,
              data: messageEvent.data,
            });
          }
        });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destroySource, initialBackoff, maxBackoff, jitter, maxRetries, eventSourceInit]);

  // ---------------------------------------------------------------------------
  // Public controls
  // ---------------------------------------------------------------------------
  const close = useCallback(() => {
    closedByUserRef.current = true;
    clearRetryTimer();
    destroySource();
    setState((prev) => ({ ...prev, status: "closed" }));
    setStoreStatusRef.current(toStoreStatus("closed"));
  }, [clearRetryTimer, destroySource]);

  const reconnect = useCallback(() => {
    if (!url) return;
    closedByUserRef.current = false;
    retryCountRef.current = 0;
    clearRetryTimer();
    connect(url);
  }, [url, clearRetryTimer, connect]);

  // ---------------------------------------------------------------------------
  // Effect — open / close connection based on url + enabled
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!enabled || !url) {
      // Disabled or no URL: ensure we're clean
      destroySource();
      clearRetryTimer();
      setState((prev) => ({ ...prev, status: "idle" }));
      setStoreStatusRef.current(toStoreStatus("idle"));
      return;
    }

    // Reset closed-by-user flag when the effect runs fresh
    closedByUserRef.current = false;
    retryCountRef.current   = 0;
    connect(url);

    return () => {
      // On cleanup (unmount or url/enabled change): close without scheduling retry
      closedByUserRef.current = true;
      clearRetryTimer();
      destroySource();
      // Mirror "closed" into the shared event store so subscribers know the
      // connection is gone (safe to call Zustand actions after unmount).
      setStoreStatusRef.current(toStoreStatus("closed"));
    };
    // connect is stable (only recreated if backoff/maxRetries change);
    // url and enabled changes intentionally restart the connection.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, enabled]);

  return {
    ...state,
    close,
    reconnect,
  };
}

// ---------------------------------------------------------------------------
// Typed variant helpers — narrow the event data generically
// ---------------------------------------------------------------------------

/**
 * Parse the JSON data payload from an SSE MessageEvent.
 * Returns null if parsing fails (logs a warning).
 */
export function parseSSEData<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    console.warn("[useSSE] Failed to parse SSE event data:", event.data);
    return null;
  }
}
