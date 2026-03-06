/**
 * SpectrophotometerChart — UV-Vis visualization for NanoDrop / Cary data.
 *
 * Two chart modes controlled by tabs:
 *   1. Wavelength Scan — line chart: x = wavelength (nm), y = absorbance (AU)
 *   2. Purity Ratios  — bar chart: 260/280 ratio per sample with DNA (1.8) / RNA (2.0) reference lines
 *
 * Uses data from the SpectrophotometerParser (measurement_type = "absorbance" | "purity_ratio").
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

export interface SpectrophotometerChartProps {
  /** Measurement data from the spectrophotometer parser */
  measurements: MeasurementValue[];
  /** Chart title (defaults to "UV-Vis Spectrophotometer") */
  title?: string;
  /** Show loading skeleton */
  loading?: boolean;
  /** Error message */
  error?: string;
  /** Retry callback for error state */
  onRetry?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type TabMode = "scan" | "purity";

function buildScanTraces(measurements: MeasurementValue[]): Plotly.Data[] {
  // Filter to absorbance measurements with wavelength data
  const absorbanceMeasurements = measurements.filter(
    (m) =>
      m.measurement_type === "absorbance" && m.wavelength_nm != null
  );

  if (absorbanceMeasurements.length === 0) return [];

  // Group by sample_name
  const bySample = new Map<string, { x: number[]; y: number[] }>();
  for (const m of absorbanceMeasurements) {
    const name = m.sample_name || m.sample_id || "Unknown";
    if (!bySample.has(name)) {
      bySample.set(name, { x: [], y: [] });
    }
    const entry = bySample.get(name)!;
    entry.x.push(m.wavelength_nm!);
    entry.y.push(m.value);
  }

  const traces: Plotly.Data[] = [];
  let colorIdx = 0;
  for (const [sampleName, data] of bySample) {
    // Sort by wavelength
    const sorted = data.x
      .map((x, i) => ({ x, y: data.y[i] }))
      .sort((a, b) => a.x - b.x);

    traces.push({
      x: sorted.map((p) => p.x),
      y: sorted.map((p) => p.y),
      type: "scatter" as const,
      mode: "lines" as const,
      name: sampleName,
      line: {
        color: SERIES_COLORS[colorIdx % SERIES_COLORS.length],
        width: 2,
      },
      hovertemplate:
        "<b>%{fullData.name}</b><br>" +
        "Wavelength: %{x:.1f} nm<br>" +
        "Absorbance: %{y:.4f} AU<extra></extra>",
    } as Plotly.Data);
    colorIdx++;
  }

  return traces;
}

function buildPurityTraces(
  measurements: MeasurementValue[]
): { traces: Plotly.Data[]; hasData: boolean } {
  // Filter to purity_ratio measurements (260/280)
  const ratioMeasurements = measurements.filter(
    (m) => m.measurement_type === "purity_ratio"
  );

  if (ratioMeasurements.length === 0) {
    return { traces: [], hasData: false };
  }

  const sampleNames = ratioMeasurements.map(
    (m) => m.sample_name || m.sample_id || "Unknown"
  );
  const values = ratioMeasurements.map((m) => m.value);

  // Color bars based on purity range
  const barColors = values.map((v) => {
    if (v >= 1.7 && v <= 2.2) return LABLINK_COLORS.green;
    if (v >= 1.5 && v <= 2.5) return LABLINK_COLORS.yellow;
    return LABLINK_COLORS.red;
  });

  const traces: Plotly.Data[] = [
    {
      x: sampleNames,
      y: values,
      type: "bar" as const,
      marker: { color: barColors, opacity: 0.85 },
      hovertemplate:
        "<b>%{x}</b><br>260/280 Ratio: %{y:.2f}<extra></extra>",
    } as Plotly.Data,
  ];

  return { traces, hasData: true };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SpectrophotometerChart({
  measurements,
  title = "UV-Vis Spectrophotometer",
  loading,
  error,
  onRetry,
}: SpectrophotometerChartProps) {
  const [activeTab, setActiveTab] = React.useState<TabMode>("scan");
  const plotRef = React.useRef<{ el: HTMLElement } | null>(null);

  // Check which modes have data
  const hasScanData = measurements.some(
    (m) => m.measurement_type === "absorbance" && m.wavelength_nm != null
  );
  const hasPurityData = measurements.some(
    (m) => m.measurement_type === "purity_ratio"
  );

  // Auto-select tab if only one mode has data
  React.useEffect(() => {
    if (!hasScanData && hasPurityData) setActiveTab("purity");
    else if (hasScanData && !hasPurityData) setActiveTab("scan");
  }, [hasScanData, hasPurityData]);

  const handleExport = React.useCallback(() => {
    const el = plotRef.current?.el;
    if (el) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).Plotly?.downloadImage(el, {
        format: "png",
        filename: "lablink-spectrophotometer",
        scale: 2,
      });
    }
  }, []);

  const isEmpty = measurements.length === 0;

  return (
    <ChartWrapper
      title={title}
      loading={loading}
      error={error}
      onRetry={onRetry}
      onExport={!isEmpty ? handleExport : undefined}
    >
      {isEmpty ? (
        <div className="flex items-center justify-center py-16 text-sm font-semibold" style={{ color: "#94a3b8" }}>
          No data available
        </div>
      ) : (
        <>
          {/* Tab switcher */}
          {hasScanData && hasPurityData && (
            <div className="flex gap-2 mb-4">
              {(["scan", "purity"] as TabMode[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="text-xs font-bold uppercase tracking-widest px-4 py-2 rounded-xl transition-all duration-200"
                  style={{
                    backgroundColor: "#f5f7fa",
                    boxShadow:
                      activeTab === tab
                        ? "inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)"
                        : "3px 3px 6px rgba(174,185,201,0.4), -3px -3px 6px rgba(255,255,255,0.9)",
                    color:
                      activeTab === tab
                        ? LABLINK_COLORS.blue
                        : LABLINK_COLORS.textMuted,
                  }}
                >
                  {tab === "scan" ? "Wavelength Scan" : "Purity Ratios"}
                </button>
              ))}
            </div>
          )}

          {/* Chart */}
          {activeTab === "scan" && hasScanData && (
            <Plot
              ref={plotRef as React.Ref<Plot>}
              data={buildScanTraces(measurements)}
              layout={{
                ...BASE_LAYOUT,
                xaxis: {
                  title: { text: "Wavelength (nm)", font: { size: 12, color: LABLINK_COLORS.textMuted } },
                  gridcolor: "rgba(174,185,201,0.15)",
                  zerolinecolor: "rgba(174,185,201,0.3)",
                },
                yaxis: {
                  title: { text: "Absorbance (AU)", font: { size: 12, color: LABLINK_COLORS.textMuted } },
                  gridcolor: "rgba(174,185,201,0.15)",
                  zerolinecolor: "rgba(174,185,201,0.3)",
                },
                showlegend: true,
                legend: { orientation: "h" as const, y: -0.2, font: { size: 11 } },
              }}
              config={DEFAULT_PLOTLY_CONFIG}
              useResizeHandler
              style={{ width: "100%", height: "400px" }}
            />
          )}

          {activeTab === "purity" && hasPurityData && (() => {
            const { traces } = buildPurityTraces(measurements);
            return (
              <Plot
                ref={plotRef as React.Ref<Plot>}
                data={traces}
                layout={{
                  ...BASE_LAYOUT,
                  xaxis: {
                    title: { text: "Sample", font: { size: 12, color: LABLINK_COLORS.textMuted } },
                    tickangle: -45,
                  },
                  yaxis: {
                    title: { text: "260/280 Ratio", font: { size: 12, color: LABLINK_COLORS.textMuted } },
                    gridcolor: "rgba(174,185,201,0.15)",
                    zerolinecolor: "rgba(174,185,201,0.3)",
                  },
                  showlegend: false,
                  shapes: [
                    // DNA reference line at 1.8
                    {
                      type: "line",
                      x0: 0,
                      x1: 1,
                      xref: "paper",
                      y0: 1.8,
                      y1: 1.8,
                      line: { color: LABLINK_COLORS.blue, width: 2, dash: "dash" },
                    },
                    // RNA reference line at 2.0
                    {
                      type: "line",
                      x0: 0,
                      x1: 1,
                      xref: "paper",
                      y0: 2.0,
                      y1: 2.0,
                      line: { color: LABLINK_COLORS.green, width: 2, dash: "dash" },
                    },
                  ],
                  annotations: [
                    {
                      x: 1,
                      xref: "paper",
                      y: 1.8,
                      text: "DNA (1.8)",
                      showarrow: false,
                      font: { size: 10, color: LABLINK_COLORS.blue },
                      xanchor: "left" as const,
                      xshift: 5,
                    },
                    {
                      x: 1,
                      xref: "paper",
                      y: 2.0,
                      text: "RNA (2.0)",
                      showarrow: false,
                      font: { size: 10, color: LABLINK_COLORS.green },
                      xanchor: "left" as const,
                      xshift: 5,
                    },
                  ],
                }}
                config={DEFAULT_PLOTLY_CONFIG}
                useResizeHandler
                style={{ width: "100%", height: "400px" }}
              />
            );
          })()}

          {/* Fallback when selected tab has no data */}
          {activeTab === "scan" && !hasScanData && (
            <div className="flex items-center justify-center py-16 text-sm font-semibold" style={{ color: "#94a3b8" }}>
              No wavelength scan data available
            </div>
          )}
          {activeTab === "purity" && !hasPurityData && (
            <div className="flex items-center justify-center py-16 text-sm font-semibold" style={{ color: "#94a3b8" }}>
              No purity ratio data available
            </div>
          )}
        </>
      )}
    </ChartWrapper>
  );
}
