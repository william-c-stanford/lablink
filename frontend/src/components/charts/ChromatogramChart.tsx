/**
 * ChromatogramChart — HPLC chromatogram visualization.
 *
 * Features:
 *   - Line chart: x = retention time (min), y = signal intensity (mAU)
 *   - Peak annotations: labeled arrows at peak positions
 *   - Optional peak area shading under peak regions
 *   - Multiple channels as separate traces
 *   - Zoom/pan enabled via Plotly modebar
 *   - Neuromorphic card wrapper via ChartWrapper
 *
 * Data comes from the HPLC parser which produces:
 *   - measurement_type "retention_time" with value = RT (min)
 *   - measurement_type "height" with value = peak height (mAU)
 *   - measurement_type "area" with value = peak area (mAU*s)
 */

import * as React from "react";
import Plot from "react-plotly.js";
import { ChartWrapper } from "./ChartWrapper";
import {
  type MeasurementValue,
  type Peak,
  LABLINK_COLORS,
  SERIES_COLORS,
  DEFAULT_PLOTLY_CONFIG,
  BASE_LAYOUT,
} from "./types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ChromatogramChartProps {
  /** All measurements from the HPLC parser (retention_time, height, area, etc.) */
  measurements: MeasurementValue[];
  /**
   * Optional explicit peak list for annotations and shading.
   * If not provided, peaks are derived from the measurements data.
   */
  peaks?: Peak[];
  /** Chart title */
  title?: string;
  /** Show peak area shading under peak regions */
  showPeakShading?: boolean;
  /** Show loading skeleton */
  loading?: boolean;
  /** Error message */
  error?: string;
  /** Retry callback */
  onRetry?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Derive peaks from measurement data when no explicit peaks array is provided.
 * Groups retention_time + height + area measurements by sample_name (peak label).
 */
function derivePeaksFromMeasurements(measurements: MeasurementValue[]): Peak[] {
  const peakMap = new Map<
    string,
    { rt?: number; height?: number; area?: number; areaPct?: number }
  >();

  for (const m of measurements) {
    const label = m.sample_name || `Peak_${peakMap.size + 1}`;
    if (!peakMap.has(label)) {
      peakMap.set(label, {});
    }
    const entry = peakMap.get(label)!;

    switch (m.measurement_type) {
      case "retention_time":
        entry.rt = m.value;
        break;
      case "height":
        entry.height = m.value;
        break;
      case "area":
        entry.area = m.value;
        break;
      case "area_percent":
        entry.areaPct = m.value;
        break;
    }
  }

  const peaks: Peak[] = [];
  let idx = 1;
  for (const [label, data] of peakMap) {
    if (data.rt != null && data.height != null) {
      peaks.push({
        peak_number: idx,
        retention_time: data.rt,
        height: data.height,
        area: data.area,
        area_percent: data.areaPct,
        label,
      });
      idx++;
    }
  }

  return peaks;
}

/**
 * Group chromatogram signal measurements by channel for multi-channel support.
 * Falls back to a single "Signal" channel if no channel is specified.
 */
function groupByChannel(
  measurements: MeasurementValue[]
): Map<string, { x: number[]; y: number[] }> {
  // For chromatogram raw signal data, we use retention_time on x and height on y.
  // Since the HPLC parser outputs separate measurements for RT and height
  // linked by sample_name, we need to pair them.
  const channels = new Map<string, { x: number[]; y: number[] }>();

  // Build peak label -> (rt, height) pairs
  const peakData = new Map<string, { rt?: number; height?: number; channel?: string }>();
  for (const m of measurements) {
    const label = m.sample_name || "unknown";
    if (!peakData.has(label)) {
      peakData.set(label, { channel: m.channel || undefined });
    }
    const entry = peakData.get(label)!;
    if (m.measurement_type === "retention_time") entry.rt = m.value;
    if (m.measurement_type === "height") entry.height = m.value;
    if (m.channel) entry.channel = m.channel;
  }

  for (const [, data] of peakData) {
    if (data.rt == null || data.height == null) continue;
    const channelName = data.channel || "Signal";
    if (!channels.has(channelName)) {
      channels.set(channelName, { x: [], y: [] });
    }
    const ch = channels.get(channelName)!;
    ch.x.push(data.rt);
    ch.y.push(data.height);
  }

  // Sort each channel by retention time
  for (const [, ch] of channels) {
    const sorted = ch.x
      .map((x, i) => ({ x, y: ch.y[i] }))
      .sort((a, b) => a.x - b.x);
    ch.x = sorted.map((p) => p.x);
    ch.y = sorted.map((p) => p.y);
  }

  return channels;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChromatogramChart({
  measurements,
  peaks: explicitPeaks,
  title = "HPLC Chromatogram",
  showPeakShading = true,
  loading,
  error,
  onRetry,
}: ChromatogramChartProps) {
  const plotRef = React.useRef<{ el: HTMLElement } | null>(null);

  const handleExport = React.useCallback(() => {
    const el = plotRef.current?.el;
    if (el) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).Plotly?.downloadImage(el, {
        format: "png",
        filename: "lablink-chromatogram",
        scale: 2,
      });
    }
  }, []);

  const isEmpty = measurements.length === 0;

  // Derive peaks if not explicitly provided
  const peaks = React.useMemo(
    () => explicitPeaks || derivePeaksFromMeasurements(measurements),
    [explicitPeaks, measurements]
  );

  // Build channel traces
  const channels = React.useMemo(
    () => groupByChannel(measurements),
    [measurements]
  );

  // Build Plotly traces
  const traces = React.useMemo(() => {
    const result: Plotly.Data[] = [];
    let colorIdx = 0;

    for (const [channelName, data] of channels) {
      // Main signal line
      result.push({
        x: data.x,
        y: data.y,
        type: "scatter" as const,
        mode: "lines+markers" as const,
        name: channelName,
        line: {
          color: SERIES_COLORS[colorIdx % SERIES_COLORS.length],
          width: 2,
        },
        marker: { size: 4 },
        hovertemplate:
          `<b>${channelName}</b><br>` +
          "RT: %{x:.2f} min<br>" +
          "Signal: %{y:.1f} mAU<extra></extra>",
      } as Plotly.Data);

      // Peak area shading (filled regions under peaks)
      if (showPeakShading && peaks.length > 0) {
        for (const peak of peaks) {
          if (peak.start_time != null && peak.end_time != null) {
            // Find data points within peak range
            const peakX: number[] = [peak.start_time];
            const peakY: number[] = [0];
            for (let i = 0; i < data.x.length; i++) {
              if (data.x[i] >= peak.start_time && data.x[i] <= peak.end_time) {
                peakX.push(data.x[i]);
                peakY.push(data.y[i]);
              }
            }
            peakX.push(peak.end_time);
            peakY.push(0);

            if (peakX.length > 2) {
              result.push({
                x: peakX,
                y: peakY,
                type: "scatter" as const,
                fill: "tozeroy" as const,
                mode: "lines" as const,
                line: { width: 0 },
                fillcolor: `${SERIES_COLORS[colorIdx % SERIES_COLORS.length]}20`,
                showlegend: false,
                hoverinfo: "skip" as const,
              } as Plotly.Data);
            }
          }
        }
      }

      colorIdx++;
    }

    return result;
  }, [channels, peaks, showPeakShading]);

  // Build peak annotations
  const annotations = React.useMemo(() => {
    return peaks.map((peak) => ({
      x: peak.retention_time,
      y: peak.height,
      text: peak.label,
      showarrow: true,
      arrowhead: 2,
      arrowsize: 0.8,
      arrowwidth: 1.5,
      arrowcolor: LABLINK_COLORS.textSubtle,
      ax: 0,
      ay: -35,
      font: {
        size: 10,
        color: LABLINK_COLORS.text,
        family: "'Plus Jakarta Sans', sans-serif",
      },
      bgcolor: "rgba(245,247,250,0.9)",
      bordercolor: "rgba(174,185,201,0.3)",
      borderwidth: 1,
      borderpad: 3,
    }));
  }, [peaks]);

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
          <Plot
            ref={plotRef as React.Ref<Plot>}
            data={traces}
            layout={{
              ...BASE_LAYOUT,
              xaxis: {
                title: {
                  text: "Retention Time (min)",
                  font: { size: 12, color: LABLINK_COLORS.textMuted },
                },
                gridcolor: "rgba(174,185,201,0.15)",
                zerolinecolor: "rgba(174,185,201,0.3)",
                rangeslider: { visible: false },
              },
              yaxis: {
                title: {
                  text: "Signal Intensity (mAU)",
                  font: { size: 12, color: LABLINK_COLORS.textMuted },
                },
                gridcolor: "rgba(174,185,201,0.15)",
                zerolinecolor: "rgba(174,185,201,0.3)",
              },
              showlegend: channels.size > 1,
              legend: { orientation: "h" as const, y: -0.2, font: { size: 11 } },
              annotations,
              dragmode: "zoom" as const,
            }}
            config={{
              ...DEFAULT_PLOTLY_CONFIG,
              scrollZoom: true,
            }}
            useResizeHandler
            style={{ width: "100%", height: "420px" }}
          />

          {/* Peak summary table */}
          {peaks.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-xs" style={{ color: LABLINK_COLORS.textMuted }}>
                <thead>
                  <tr
                    className="border-b font-bold uppercase tracking-widest"
                    style={{ borderColor: "rgba(174,185,201,0.3)" }}
                  >
                    <th className="text-left py-2 px-2">#</th>
                    <th className="text-left py-2 px-2">Peak</th>
                    <th className="text-right py-2 px-2">RT (min)</th>
                    <th className="text-right py-2 px-2">Height (mAU)</th>
                    {peaks.some((p) => p.area != null) && (
                      <th className="text-right py-2 px-2">Area</th>
                    )}
                    {peaks.some((p) => p.area_percent != null) && (
                      <th className="text-right py-2 px-2">Area %</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {peaks.map((peak) => (
                    <tr
                      key={peak.peak_number}
                      className="border-b"
                      style={{ borderColor: "rgba(174,185,201,0.15)" }}
                    >
                      <td className="py-1.5 px-2">{peak.peak_number}</td>
                      <td className="py-1.5 px-2 font-semibold" style={{ color: LABLINK_COLORS.text }}>
                        {peak.label}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {peak.retention_time.toFixed(3)}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono">
                        {peak.height.toFixed(1)}
                      </td>
                      {peaks.some((p) => p.area != null) && (
                        <td className="py-1.5 px-2 text-right font-mono">
                          {peak.area?.toFixed(1) ?? "-"}
                        </td>
                      )}
                      {peaks.some((p) => p.area_percent != null) && (
                        <td className="py-1.5 px-2 text-right font-mono">
                          {peak.area_percent?.toFixed(2) ?? "-"}%
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </ChartWrapper>
  );
}
