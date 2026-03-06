/**
 * PCRAmplificationChart — Real-time PCR amplification curve visualization.
 *
 * Features:
 *   - Line chart: x = cycle number, y = fluorescence (RFU)
 *   - One trace per well/sample, colored distinctly
 *   - Horizontal dashed line at Ct threshold value
 *   - Ct value annotations where curves cross the threshold
 *   - Log scale toggle for y-axis
 *   - Legend with sample names
 *   - Neuromorphic card wrapper
 *
 * Note: The PCR parser produces Ct values (single-point per well), not full
 * amplification curves. When full curve data is available (cycle-by-cycle
 * fluorescence), this component renders them. When only Ct summary data is
 * available, it displays a Ct value bar chart as a fallback.
 */

import * as React from "react";
import Plot from "react-plotly.js";
import { ChartWrapper } from "./ChartWrapper";
import {
  type MeasurementValue,
  LABLINK_COLORS,
  SERIES_COLORS,
  DEFAULT_PLOTLY_CONFIG,
  BASE_LAYOUT,
} from "./types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PCRAmplificationChartProps {
  /** Measurement data from the PCR parser */
  measurements: MeasurementValue[];
  /** Ct/Cq threshold line value (horizontal dashed line) */
  ctThreshold?: number;
  /** Chart title */
  title?: string;
  /** Show loading skeleton */
  loading?: boolean;
  /** Error message */
  error?: string;
  /** Retry callback */
  onRetry?: () => void;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ViewMode = "curves" | "ct-summary";

interface CurveData {
  label: string;
  well?: string;
  cycles: number[];
  fluorescence: number[];
  ctValue?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Check if data contains full amplification curves (cycle-by-cycle) or only Ct summaries.
 * Amplification curve data has measurement_type = "fluorescence" with many points per sample.
 */
function hasAmplificationCurves(measurements: MeasurementValue[]): boolean {
  const fluorescenceMeasurements = measurements.filter(
    (m) => m.measurement_type === "fluorescence"
  );
  // If there are many fluorescence measurements, assume curve data
  return fluorescenceMeasurements.length > 5;
}

/**
 * Group fluorescence measurements into per-well curves.
 */
function buildCurveData(measurements: MeasurementValue[]): CurveData[] {
  const fluorescence = measurements.filter(
    (m) => m.measurement_type === "fluorescence"
  );
  const ctMeasurements = measurements.filter(
    (m) => m.measurement_type === "ct_value"
  );

  // Build Ct lookup by well or sample
  const ctLookup = new Map<string, number>();
  for (const m of ctMeasurements) {
    const key = m.well_position || m.sample_name || "";
    if (key && m.value > 0) ctLookup.set(key, m.value);
  }

  // Group fluorescence by well/sample
  const curveMap = new Map<string, { cycles: number[]; values: number[]; well?: string; sample?: string }>();
  for (const m of fluorescence) {
    const key = m.well_position || m.sample_name || "Unknown";
    if (!curveMap.has(key)) {
      curveMap.set(key, {
        cycles: [],
        values: [],
        well: m.well_position || undefined,
        sample: m.sample_name || undefined,
      });
    }
    const entry = curveMap.get(key)!;
    // Use wavelength_nm as cycle number proxy if no explicit cycle info
    // (some exports store cycle in the value itself, depends on export format)
    entry.cycles.push(entry.cycles.length + 1);
    entry.values.push(m.value);
  }

  const curves: CurveData[] = [];
  for (const [key, data] of curveMap) {
    const label = data.sample
      ? `${data.sample}${data.well ? ` (${data.well})` : ""}`
      : key;
    curves.push({
      label,
      well: data.well,
      cycles: data.cycles,
      fluorescence: data.values,
      ctValue: ctLookup.get(key),
    });
  }

  return curves;
}

/**
 * Build Ct summary data for the bar chart fallback.
 */
function buildCtSummary(measurements: MeasurementValue[]) {
  const ctMeasurements = measurements.filter(
    (m) => m.measurement_type === "ct_value" && m.value > 0
  );

  const labels: string[] = [];
  const values: number[] = [];
  const colors: string[] = [];
  const wells: string[] = [];

  for (const m of ctMeasurements) {
    const label = m.sample_name || m.well_position || `Well ${labels.length + 1}`;
    labels.push(label);
    values.push(m.value);
    wells.push(m.well_position || "");

    // Color by Ct quality
    if (m.quality_flag === "missing") {
      colors.push(LABLINK_COLORS.textSubtle);
    } else if (m.value > 35) {
      colors.push(LABLINK_COLORS.yellow);
    } else if (m.value > 40) {
      colors.push(LABLINK_COLORS.red);
    } else {
      colors.push(LABLINK_COLORS.blue);
    }
  }

  // Count undetermined wells
  const undetermined = measurements.filter(
    (m) => m.measurement_type === "ct_value" && (m.value === 0 || m.quality_flag === "missing")
  ).length;

  return { labels, values, colors, wells, undetermined };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PCRAmplificationChart({
  measurements,
  ctThreshold,
  title = "PCR Amplification",
  loading,
  error,
  onRetry,
}: PCRAmplificationChartProps) {
  const plotRef = React.useRef<{ el: HTMLElement } | null>(null);
  const [logScale, setLogScale] = React.useState(false);

  const hasCurves = React.useMemo(
    () => hasAmplificationCurves(measurements),
    [measurements]
  );
  const [viewMode, setViewMode] = React.useState<ViewMode>(
    hasCurves ? "curves" : "ct-summary"
  );

  React.useEffect(() => {
    setViewMode(hasCurves ? "curves" : "ct-summary");
  }, [hasCurves]);

  const handleExport = React.useCallback(() => {
    const el = plotRef.current?.el;
    if (el) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).Plotly?.downloadImage(el, {
        format: "png",
        filename: "lablink-pcr-amplification",
        scale: 2,
      });
    }
  }, []);

  const isEmpty = measurements.length === 0;

  // Build curve traces
  const curveTraces = React.useMemo(() => {
    if (viewMode !== "curves") return [];
    const curves = buildCurveData(measurements);
    return curves.map((curve, idx) => ({
      x: curve.cycles,
      y: curve.fluorescence,
      type: "scatter" as const,
      mode: "lines" as const,
      name: curve.label,
      line: {
        color: SERIES_COLORS[idx % SERIES_COLORS.length],
        width: 2,
      },
      hovertemplate:
        `<b>${curve.label}</b><br>` +
        "Cycle: %{x}<br>" +
        "RFU: %{y:.1f}<extra></extra>",
    })) as Plotly.Data[];
  }, [measurements, viewMode]);

  // Build Ct summary traces
  const ctSummary = React.useMemo(() => {
    if (viewMode !== "ct-summary") return null;
    return buildCtSummary(measurements);
  }, [measurements, viewMode]);

  // Ct threshold shapes and annotations
  const thresholdShapes = React.useMemo(() => {
    if (!ctThreshold || viewMode !== "curves") return [];
    return [
      {
        type: "line" as const,
        x0: 0,
        x1: 1,
        xref: "paper" as const,
        y0: ctThreshold,
        y1: ctThreshold,
        line: {
          color: LABLINK_COLORS.red,
          width: 2,
          dash: "dash" as const,
        },
      },
    ];
  }, [ctThreshold, viewMode]);

  const thresholdAnnotations = React.useMemo(() => {
    if (!ctThreshold || viewMode !== "curves") return [];
    return [
      {
        x: 1,
        xref: "paper" as const,
        y: ctThreshold,
        text: `Ct Threshold (${ctThreshold})`,
        showarrow: false,
        font: { size: 10, color: LABLINK_COLORS.red },
        xanchor: "right" as const,
        yshift: -12,
      },
    ];
  }, [ctThreshold, viewMode]);

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
          {/* Controls bar */}
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            {/* View mode toggle (only if curves available) */}
            {hasCurves && (
              <div className="flex gap-2">
                {(["curves", "ct-summary"] as ViewMode[]).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setViewMode(mode)}
                    className="text-xs font-bold uppercase tracking-widest px-4 py-2 rounded-xl transition-all duration-200"
                    style={{
                      backgroundColor: "#f5f7fa",
                      boxShadow:
                        viewMode === mode
                          ? "inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)"
                          : "3px 3px 6px rgba(174,185,201,0.4), -3px -3px 6px rgba(255,255,255,0.9)",
                      color:
                        viewMode === mode
                          ? LABLINK_COLORS.blue
                          : LABLINK_COLORS.textMuted,
                    }}
                  >
                    {mode === "curves" ? "Amplification" : "Ct Summary"}
                  </button>
                ))}
              </div>
            )}

            {/* Log scale toggle (only for curves) */}
            {viewMode === "curves" && (
              <button
                onClick={() => setLogScale((prev) => !prev)}
                className="text-xs font-bold uppercase tracking-widest px-4 py-2 rounded-xl transition-all duration-200 ml-auto"
                style={{
                  backgroundColor: "#f5f7fa",
                  boxShadow: logScale
                    ? "inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)"
                    : "3px 3px 6px rgba(174,185,201,0.4), -3px -3px 6px rgba(255,255,255,0.9)",
                  color: logScale ? LABLINK_COLORS.blue : LABLINK_COLORS.textMuted,
                }}
              >
                Log Scale
              </button>
            )}
          </div>

          {/* Amplification curves chart */}
          {viewMode === "curves" && (
            <Plot
              ref={plotRef as React.Ref<Plot>}
              data={curveTraces}
              layout={{
                ...BASE_LAYOUT,
                xaxis: {
                  title: {
                    text: "Cycle Number",
                    font: { size: 12, color: LABLINK_COLORS.textMuted },
                  },
                  gridcolor: "rgba(174,185,201,0.15)",
                  zerolinecolor: "rgba(174,185,201,0.3)",
                  dtick: 5,
                },
                yaxis: {
                  title: {
                    text: "Fluorescence (RFU)",
                    font: { size: 12, color: LABLINK_COLORS.textMuted },
                  },
                  gridcolor: "rgba(174,185,201,0.15)",
                  zerolinecolor: "rgba(174,185,201,0.3)",
                  type: logScale ? ("log" as const) : ("linear" as const),
                },
                showlegend: true,
                legend: {
                  orientation: "h" as const,
                  y: -0.25,
                  font: { size: 10 },
                },
                shapes: thresholdShapes,
                annotations: thresholdAnnotations,
              }}
              config={{
                ...DEFAULT_PLOTLY_CONFIG,
                scrollZoom: true,
              }}
              useResizeHandler
              style={{ width: "100%", height: "420px" }}
            />
          )}

          {/* Ct summary bar chart */}
          {viewMode === "ct-summary" && ctSummary && (
            <>
              <Plot
                ref={plotRef as React.Ref<Plot>}
                data={[
                  {
                    x: ctSummary.labels,
                    y: ctSummary.values,
                    type: "bar" as const,
                    marker: {
                      color: ctSummary.colors,
                      opacity: 0.85,
                    },
                    hovertemplate:
                      "<b>%{x}</b><br>Ct: %{y:.2f}<extra></extra>",
                  } as Plotly.Data,
                ]}
                layout={{
                  ...BASE_LAYOUT,
                  xaxis: {
                    title: {
                      text: "Sample / Well",
                      font: { size: 12, color: LABLINK_COLORS.textMuted },
                    },
                    tickangle: -45,
                    tickfont: { size: 9 },
                  },
                  yaxis: {
                    title: {
                      text: "Ct Value",
                      font: { size: 12, color: LABLINK_COLORS.textMuted },
                    },
                    gridcolor: "rgba(174,185,201,0.15)",
                    autorange: "reversed" as const,
                  },
                  showlegend: false,
                  shapes: ctThreshold
                    ? [
                        {
                          type: "line" as const,
                          x0: 0,
                          x1: 1,
                          xref: "paper" as const,
                          y0: ctThreshold,
                          y1: ctThreshold,
                          line: {
                            color: LABLINK_COLORS.red,
                            width: 2,
                            dash: "dash" as const,
                          },
                        },
                      ]
                    : [],
                }}
                config={DEFAULT_PLOTLY_CONFIG}
                useResizeHandler
                style={{ width: "100%", height: "400px" }}
              />

              {/* Undetermined wells info */}
              {ctSummary.undetermined > 0 && (
                <div
                  className="mt-3 px-4 py-2 rounded-xl text-xs font-bold"
                  style={{
                    backgroundColor: "#f5f7fa",
                    boxShadow:
                      "inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)",
                    color: LABLINK_COLORS.yellow,
                  }}
                >
                  {ctSummary.undetermined} undetermined well
                  {ctSummary.undetermined > 1 ? "s" : ""} (no amplification
                  detected)
                </div>
              )}
            </>
          )}
        </>
      )}
    </ChartWrapper>
  );
}
