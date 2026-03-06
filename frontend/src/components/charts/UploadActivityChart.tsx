/**
 * UploadActivityChart — stacked bar chart showing upload volume over the last N days.
 *
 * Buckets each upload by calendar day and splits counts into two stacks:
 *   - "Parsed"  (green, #10b981) — uploads whose status === "parsed"
 *   - "Failed"  (red,   #ef4444) — uploads whose status === "failed"
 *
 * All other statuses (pending, uploading, parsing, queued) are intentionally
 * omitted from the chart; they represent in-flight uploads with no terminal
 * outcome yet.
 */

import * as React from "react";
import Plot from "react-plotly.js";
import { ChartWrapper } from "./ChartWrapper";
import { DEFAULT_PLOTLY_CONFIG, BASE_LAYOUT, LABLINK_COLORS } from "./types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UploadActivityChartProps {
  /** Array of upload objects — only `created_at` and `status` are required. */
  uploads: Array<{ created_at: string; status: string }>;
  /**
   * How many calendar days to show (counting backwards from today).
   * @default 30
   */
  days?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a Date as "Mon D" e.g. "Mar 6" */
function fmtLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Zero-pad a number to 2 digits */
function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

/** Return "YYYY-MM-DD" for a Date (local timezone) */
function toDateKey(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

interface DayBucket {
  label: string;
  parsed: number;
  failed: number;
}

/**
 * Buckets the uploads array into `days` day buckets ending today.
 * Returns an array ordered from oldest to newest.
 */
function bucketByDay(
  uploads: Array<{ created_at: string; status: string }>,
  days: number
): DayBucket[] {
  // Build date range: [today - (days-1), today]
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const bucketMap = new Map<string, DayBucket>();

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = toDateKey(d);
    bucketMap.set(key, { label: fmtLabel(d), parsed: 0, failed: 0 });
  }

  for (const upload of uploads) {
    if (!upload.created_at) continue;
    const key = toDateKey(new Date(upload.created_at));
    const bucket = bucketMap.get(key);
    if (!bucket) continue; // outside the window
    if (upload.status === "parsed") {
      bucket.parsed += 1;
    } else if (upload.status === "failed") {
      bucket.failed += 1;
    }
  }

  return Array.from(bucketMap.values());
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function UploadActivityChart({
  uploads,
  days = 30,
}: UploadActivityChartProps) {
  const buckets = React.useMemo(
    () => bucketByDay(uploads, days),
    [uploads, days]
  );

  const labels = buckets.map((b) => b.label);
  const parsedCounts = buckets.map((b) => b.parsed);
  const failedCounts = buckets.map((b) => b.failed);

  const totalUploads = parsedCounts.reduce((s, n) => s + n, 0) +
    failedCounts.reduce((s, n) => s + n, 0);

  const isEmpty = uploads.length === 0 || totalUploads === 0;

  const parsedTrace: Plotly.Data = {
    x: labels,
    y: parsedCounts,
    type: "bar" as const,
    name: "Parsed",
    marker: {
      color: LABLINK_COLORS.green,
      opacity: 0.85,
    },
    hovertemplate: "<b>%{x}</b><br>Parsed: %{y}<extra></extra>",
  } as Plotly.Data;

  const failedTrace: Plotly.Data = {
    x: labels,
    y: failedCounts,
    type: "bar" as const,
    name: "Failed",
    marker: {
      color: LABLINK_COLORS.red,
      opacity: 0.85,
    },
    hovertemplate: "<b>%{x}</b><br>Failed: %{y}<extra></extra>",
  } as Plotly.Data;

  return (
    <ChartWrapper title={`Upload Activity (${days} days)`}>
      {isEmpty ? (
        <div
          className="flex items-center justify-center h-64 text-sm font-semibold"
          style={{ color: LABLINK_COLORS.textSubtle }}
        >
          No uploads yet
        </div>
      ) : (
        <Plot
          data={[parsedTrace, failedTrace]}
          layout={{
            ...BASE_LAYOUT,
            barmode: "stack" as const,
            xaxis: {
              tickangle: -45,
              tickfont: {
                family: "'Plus Jakarta Sans', sans-serif",
                size: 10,
                color: LABLINK_COLORS.textMuted,
              },
              gridcolor: "rgba(174,185,201,0.1)",
              zerolinecolor: "rgba(174,185,201,0.2)",
              showgrid: false,
            },
            yaxis: {
              title: {
                text: "Uploads",
                font: { size: 12, color: LABLINK_COLORS.textMuted },
              },
              gridcolor: "rgba(174,185,201,0.15)",
              zerolinecolor: "rgba(174,185,201,0.3)",
              tickformat: "d",
            },
            showlegend: true,
            legend: {
              orientation: "h" as const,
              y: -0.25,
              x: 0,
              font: {
                family: "'Plus Jakarta Sans', sans-serif",
                size: 11,
                color: LABLINK_COLORS.textMuted,
              },
            },
            margin: { l: 50, r: 20, t: 20, b: 80 },
          }}
          config={DEFAULT_PLOTLY_CONFIG}
          useResizeHandler
          style={{ width: "100%", height: "300px" }}
        />
      )}
    </ChartWrapper>
  );
}
