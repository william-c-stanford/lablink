/**
 * PlateHeatmap — 96/384-well plate heatmap visualization.
 *
 * Renders a heatmap grid of plate reader data:
 *   - Rows: A-H (96-well) or A-P (384-well)
 *   - Columns: 1-12 (96-well) or 1-24 (384-well)
 *   - Color scale: cool (low) to warm (high) values
 *   - Hover tooltip: well position + value + sample name
 *   - Click well to select/highlight
 *   - Missing wells rendered as gray
 */

import * as React from "react";
import Plot from "react-plotly.js";
import { ChartWrapper } from "./ChartWrapper";
import {
  type MeasurementValue,
  LABLINK_COLORS,
  DEFAULT_PLOTLY_CONFIG,
  BASE_LAYOUT,
} from "./types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PlateHeatmapProps {
  /** Measurement data with well_position fields (e.g., "A1", "B12") */
  measurements: MeasurementValue[];
  /** Plate format determines grid dimensions */
  plateFormat: "96-well" | "384-well";
  /** Chart title */
  title?: string;
  /** Show loading skeleton */
  loading?: boolean;
  /** Error message */
  error?: string;
  /** Retry callback for error state */
  onRetry?: () => void;
  /** Callback when a well is clicked */
  onWellClick?: (wellPosition: string, value: number | null) => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PLATE_CONFIGS = {
  "96-well": {
    rows: "ABCDEFGH".split(""),
    cols: Array.from({ length: 12 }, (_, i) => i + 1),
  },
  "384-well": {
    rows: "ABCDEFGHIJKLMNOP".split(""),
    cols: Array.from({ length: 24 }, (_, i) => i + 1),
  },
} as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseWellPosition(well: string): { row: string; col: number } | null {
  const match = well.match(/^([A-P])(\d{1,2})$/i);
  if (!match) return null;
  return { row: match[1].toUpperCase(), col: parseInt(match[2], 10) };
}

function buildHeatmapData(
  measurements: MeasurementValue[],
  plateFormat: "96-well" | "384-well"
) {
  const config = PLATE_CONFIGS[plateFormat];
  const rows = config.rows;
  const cols = config.cols;

  // Build a lookup map: "A1" -> MeasurementValue
  const wellMap = new Map<string, MeasurementValue>();
  for (const m of measurements) {
    if (m.well_position) {
      wellMap.set(m.well_position.toUpperCase(), m);
    }
  }

  // Build z-matrix (values), customdata (metadata), and hover text
  // Plotly heatmap: z[row][col], rows displayed bottom-to-top by default
  // We reverse rows so A is at the top
  const z: (number | null)[][] = [];
  const customdata: (string | null)[][] = [];
  const hovertext: string[][] = [];

  for (const row of rows) {
    const zRow: (number | null)[] = [];
    const cdRow: (string | null)[] = [];
    const htRow: string[] = [];
    for (const col of cols) {
      const well = `${row}${col}`;
      const m = wellMap.get(well);
      if (m) {
        zRow.push(m.value);
        cdRow.push(m.sample_name || m.sample_id || null);
        const sampleLabel = m.sample_name || m.sample_id || "";
        htRow.push(
          `<b>${well}</b><br>` +
            `Value: ${m.value.toFixed(4)} ${m.unit}<br>` +
            (sampleLabel ? `Sample: ${sampleLabel}` : "")
        );
      } else {
        zRow.push(null);
        cdRow.push(null);
        htRow.push(`<b>${well}</b><br>No data`);
      }
    }
    z.push(zRow);
    customdata.push(cdRow);
    hovertext.push(htRow);
  }

  return {
    z,
    customdata,
    hovertext,
    xLabels: cols.map(String),
    yLabels: [...rows],
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PlateHeatmap({
  measurements,
  plateFormat,
  title = "Plate Reader",
  loading,
  error,
  onRetry,
  onWellClick,
}: PlateHeatmapProps) {
  const plotRef = React.useRef<{ el: HTMLElement } | null>(null);
  const [selectedWell, setSelectedWell] = React.useState<string | null>(null);

  const handleExport = React.useCallback(() => {
    const el = plotRef.current?.el;
    if (el) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).Plotly?.downloadImage(el, {
        format: "png",
        filename: "lablink-plate-heatmap",
        scale: 2,
      });
    }
  }, []);

  const isEmpty = measurements.length === 0;

  const { z, hovertext, xLabels, yLabels } = React.useMemo(
    () => buildHeatmapData(measurements, plateFormat),
    [measurements, plateFormat]
  );

  // Determine chart height based on plate format
  const chartHeight = plateFormat === "384-well" ? 550 : 400;

  const handleClick = React.useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: any) => {
      if (!event.points || event.points.length === 0) return;
      const point = event.points[0];
      const rowLabel = yLabels[point.pointIndex[0]];
      const colLabel = xLabels[point.pointIndex[1]];
      const wellPos = `${rowLabel}${colLabel}`;
      const value = point.z;

      setSelectedWell((prev) => (prev === wellPos ? null : wellPos));
      onWellClick?.(wellPos, value);
    },
    [yLabels, xLabels, onWellClick]
  );

  return (
    <ChartWrapper
      title={title}
      loading={loading}
      error={error}
      onRetry={onRetry}
      onExport={!isEmpty ? handleExport : undefined}
    >
      {isEmpty ? (
        <div
          className="flex items-center justify-center py-16 text-sm font-semibold"
          style={{ color: "#94a3b8" }}
        >
          No data available
        </div>
      ) : (
        <>
          {/* Selected well info bar */}
          {selectedWell && (
            <div
              className="mb-3 px-4 py-2 rounded-xl text-xs font-bold"
              style={{
                backgroundColor: "#f5f7fa",
                boxShadow:
                  "inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)",
                color: LABLINK_COLORS.blue,
              }}
            >
              Selected: {selectedWell}
              {(() => {
                const m = measurements.find(
                  (m) =>
                    m.well_position?.toUpperCase() === selectedWell
                );
                return m
                  ? ` | Value: ${m.value.toFixed(4)} ${m.unit}${m.sample_name ? ` | Sample: ${m.sample_name}` : ""}`
                  : " | No data";
              })()}
            </div>
          )}

          <Plot
            ref={plotRef as React.Ref<Plot>}
            data={[
              {
                z,
                x: xLabels,
                y: yLabels,
                type: "heatmap" as const,
                colorscale: [
                  [0, "#dbeafe"],      // blue-100
                  [0.25, "#93c5fd"],   // blue-300
                  [0.5, "#3b82f6"],    // blue-500
                  [0.75, "#f59e0b"],   // yellow-500
                  [1, "#ef4444"],      // red-500
                ],
                hovertext,
                hoverinfo: "text" as const,
                showscale: true,
                colorbar: {
                  title: { text: measurements[0]?.unit || "Value", font: { size: 11 } },
                  thickness: 15,
                  len: 0.9,
                  outlinewidth: 0,
                },
                xgap: 2,
                ygap: 2,
                zmin: undefined,
                zmax: undefined,
              } as Plotly.Data,
            ]}
            layout={{
              ...BASE_LAYOUT,
              margin: { l: 40, r: 80, t: 30, b: 40 },
              xaxis: {
                title: { text: "Column", font: { size: 11, color: LABLINK_COLORS.textMuted } },
                side: "top" as const,
                dtick: 1,
                tickfont: { size: 10 },
              },
              yaxis: {
                title: { text: "Row", font: { size: 11, color: LABLINK_COLORS.textMuted } },
                autorange: "reversed" as const,
                dtick: 1,
                tickfont: { size: 10 },
              },
            }}
            config={{
              ...DEFAULT_PLOTLY_CONFIG,
              displayModeBar: "hover",
            }}
            onClick={handleClick}
            useResizeHandler
            style={{ width: "100%", height: `${chartHeight}px` }}
          />

          {/* Plate format badge */}
          <div className="flex justify-end mt-2">
            <span
              className="text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full"
              style={{
                backgroundColor: "#f5f7fa",
                boxShadow:
                  "inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)",
                color: LABLINK_COLORS.textSubtle,
              }}
            >
              {plateFormat}
            </span>
          </div>
        </>
      )}
    </ChartWrapper>
  );
}
