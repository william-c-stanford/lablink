/**
 * LabLink Chart Components
 *
 * Instrument-specific Plotly.js visualizations for parsed lab data.
 * All charts use the neuromorphic design system and LabLink color palette.
 */

// Shared types
export type {
  MeasurementValue,
  Peak,
  PlateLayout,
  ChartConfig,
} from "./types";
export {
  LABLINK_COLORS,
  SERIES_COLORS,
  DEFAULT_PLOTLY_CONFIG,
  BASE_LAYOUT,
} from "./types";

// Shared wrapper
export { ChartWrapper } from "./ChartWrapper";
export type { ChartWrapperProps } from "./ChartWrapper";

// Instrument charts
export { SpectrophotometerChart } from "./SpectrophotometerChart";
export type { SpectrophotometerChartProps } from "./SpectrophotometerChart";

export { PlateHeatmap } from "./PlateHeatmap";
export type { PlateHeatmapProps } from "./PlateHeatmap";

export { ChromatogramChart } from "./ChromatogramChart";
export type { ChromatogramChartProps } from "./ChromatogramChart";

export { PCRAmplificationChart } from "./PCRAmplificationChart";
export type { PCRAmplificationChartProps } from "./PCRAmplificationChart";

export { UploadActivityChart } from "./UploadActivityChart";
export type { UploadActivityChartProps } from "./UploadActivityChart";
