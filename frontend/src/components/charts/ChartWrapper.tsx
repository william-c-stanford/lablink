/**
 * ChartWrapper — Shared neuromorphic container for all LabLink chart components.
 *
 * Provides:
 *   - Neuromorphic outset card with title bar
 *   - Loading skeleton state
 *   - Error state with retry button
 *   - Export button (triggers onExport callback)
 *   - Consistent padding and styling matching the LabLink design system
 */

import * as React from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ChartWrapperProps {
  /** Chart title displayed in the header bar */
  title: string;
  /** Chart content (typically a <Plot /> component) */
  children: React.ReactNode;
  /** Show loading skeleton instead of children */
  loading?: boolean;
  /** Error message to display — replaces chart with error state */
  error?: string;
  /** Callback when the export button is clicked */
  onExport?: () => void;
  /** Callback when the retry button is clicked in error state */
  onRetry?: () => void;
  /** Additional CSS class names for the outer container */
  className?: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4 p-6">
      {/* Chart area skeleton */}
      <div
        className="w-full h-64 rounded-2xl"
        style={{
          backgroundColor: "#f5f7fa",
          boxShadow:
            "inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)",
        }}
      />
      {/* Legend skeleton */}
      <div className="flex gap-4">
        <div
          className="h-3 w-20 rounded-full"
          style={{ backgroundColor: "#e2e8f0" }}
        />
        <div
          className="h-3 w-16 rounded-full"
          style={{ backgroundColor: "#e2e8f0" }}
        />
        <div
          className="h-3 w-24 rounded-full"
          style={{ backgroundColor: "#e2e8f0" }}
        />
      </div>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center gap-4">
      {/* Error icon */}
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center"
        style={{
          backgroundColor: "#f5f7fa",
          boxShadow:
            "inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)",
          color: "#ef4444",
        }}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <p
        className="text-sm font-semibold max-w-xs"
        style={{ color: "#64748b" }}
      >
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-sm font-bold px-5 py-2 rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
          style={{
            backgroundColor: "#f5f7fa",
            boxShadow:
              "4px 4px 8px rgba(174,185,201,0.4), -4px -4px 8px rgba(255,255,255,0.9)",
            color: "#3b82f6",
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChartWrapper
// ---------------------------------------------------------------------------

export function ChartWrapper({
  title,
  children,
  loading = false,
  error,
  onExport,
  onRetry,
  className,
}: ChartWrapperProps) {
  return (
    <div
      className={cn("w-full", className)}
      style={{
        backgroundColor: "#f5f7fa",
        boxShadow:
          "8px 8px 16px rgba(174,185,201,0.4), -8px -8px 16px rgba(255,255,255,0.9)",
        borderRadius: "2rem",
      }}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-8 pt-6 pb-2">
        <h3
          className="text-lg font-bold tracking-tight"
          style={{ color: "#1e293b" }}
        >
          {title}
        </h3>
        {onExport && !loading && !error && (
          <button
            onClick={onExport}
            title="Export chart as image"
            className="text-xs font-bold uppercase tracking-widest px-4 py-2 rounded-xl transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
            style={{
              backgroundColor: "#f5f7fa",
              boxShadow:
                "3px 3px 6px rgba(174,185,201,0.4), -3px -3px 6px rgba(255,255,255,0.9)",
              color: "#94a3b8",
            }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="inline-block mr-1"
              style={{ verticalAlign: "text-bottom" }}
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Export
          </button>
        )}
      </div>

      {/* Content area */}
      <div className="px-6 pb-6">
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : (
          children
        )}
      </div>
    </div>
  );
}
