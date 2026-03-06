/**
 * Shared TypeScript types for LabLink chart components.
 *
 * These mirror the backend canonical schemas (MeasurementValue, ParsedResult)
 * and add chart-specific types (Peak, PlateLayout, ChartConfig).
 */

// ---------------------------------------------------------------------------
// MeasurementValue — mirrors backend lablink.schemas.canonical.MeasurementValue
// ---------------------------------------------------------------------------

export interface MeasurementValue {
  sample_id?: string | null;
  sample_name?: string | null;
  well_position?: string | null;
  value: number;
  unit: string;
  qudt_uri?: string | null;
  measurement_type: string;
  channel?: string | null;
  wavelength_nm?: number | null;
  timestamp?: string | null;
  quality_flag?: string | null;
}

// ---------------------------------------------------------------------------
// Peak — HPLC chromatography peak annotation
// ---------------------------------------------------------------------------

export interface Peak {
  /** Peak number/index (1-based) */
  peak_number: number;
  /** Retention time in minutes */
  retention_time: number;
  /** Signal intensity at peak apex (mAU) */
  height: number;
  /** Peak area (mAU*s) */
  area?: number;
  /** Area percent of total */
  area_percent?: number;
  /** Peak width at half-height (min) */
  width?: number;
  /** Peak/compound label */
  label: string;
  /** Start retention time of peak region (min) */
  start_time?: number;
  /** End retention time of peak region (min) */
  end_time?: number;
}

// ---------------------------------------------------------------------------
// PlateLayout — plate reader grid configuration
// ---------------------------------------------------------------------------

export interface PlateLayout {
  rows: number;
  cols: number;
  format: "96-well" | "384-well" | string;
  wells_with_data?: number;
}

// ---------------------------------------------------------------------------
// ChartConfig — shared Plotly layout/config options
// ---------------------------------------------------------------------------

export interface ChartConfig {
  /** Whether the chart should auto-resize to its container */
  responsive?: boolean;
  /** Show/hide the Plotly modebar */
  displayModeBar?: boolean | "hover";
  /** Custom modebar buttons to show */
  modeBarButtonsToRemove?: string[];
  /** Static plot (no interactions) */
  staticPlot?: boolean;
  /** Image export format */
  toImageButtonOptions?: {
    format: "png" | "svg" | "jpeg" | "webp";
    filename: string;
    width?: number;
    height?: number;
    scale?: number;
  };
}

// ---------------------------------------------------------------------------
// LabLink color palette constants
// ---------------------------------------------------------------------------

export const LABLINK_COLORS = {
  blue: "#3b82f6",
  blueDark: "#2563eb",
  bg: "#f5f7fa",
  text: "#1e293b",
  textMuted: "#64748b",
  textSubtle: "#94a3b8",
  green: "#10b981",
  red: "#ef4444",
  yellow: "#f59e0b",
  purple: "#8b5cf6",
  orange: "#f97316",
  teal: "#14b8a6",
  pink: "#ec4899",
  indigo: "#6366f1",
} as const;

/**
 * Ordered series color palette for multi-trace charts.
 * Distinct hues chosen for color-blind friendliness.
 */
export const SERIES_COLORS = [
  LABLINK_COLORS.blue,
  LABLINK_COLORS.green,
  LABLINK_COLORS.red,
  LABLINK_COLORS.yellow,
  LABLINK_COLORS.purple,
  LABLINK_COLORS.orange,
  LABLINK_COLORS.teal,
  LABLINK_COLORS.pink,
  LABLINK_COLORS.indigo,
  LABLINK_COLORS.blueDark,
] as const;

// ---------------------------------------------------------------------------
// Default Plotly config (shared across all chart components)
// ---------------------------------------------------------------------------

export const DEFAULT_PLOTLY_CONFIG: Partial<Plotly.Config> = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: [
    "sendDataToCloud",
    "lasso2d",
    "select2d",
    "autoScale2d",
  ],
  toImageButtonOptions: {
    format: "png",
    filename: "lablink-chart",
    scale: 2,
  },
};

/**
 * Base Plotly layout properties shared across all LabLink charts.
 */
export const BASE_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: {
    family: "'Plus Jakarta Sans', sans-serif",
    color: LABLINK_COLORS.text,
  },
  margin: { l: 60, r: 30, t: 40, b: 50 },
  autosize: true,
};

// Plotly namespace type stub for config/layout references above
declare namespace Plotly {
  interface Config {
    responsive?: boolean;
    displaylogo?: boolean;
    modeBarButtonsToRemove?: string[];
    toImageButtonOptions?: {
      format: string;
      filename: string;
      scale?: number;
    };
    displayModeBar?: boolean | "hover";
    staticPlot?: boolean;
  }
  interface Layout {
    paper_bgcolor?: string;
    plot_bgcolor?: string;
    font?: { family?: string; color?: string; size?: number };
    margin?: { l?: number; r?: number; t?: number; b?: number };
    autosize?: boolean;
    [key: string]: unknown;
  }
}
