/**
 * Filter Store — active search/filter criteria shared across pages
 *
 * Persisted to sessionStorage so filters survive page navigations within
 * the same browser session but reset on a fresh open.
 */

import { create } from "zustand";
import { devtools, persist, createJSONStorage } from "zustand/middleware";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type InstrumentType =
  | "spectrophotometer"
  | "plate_reader"
  | "hplc"
  | "pcr"
  | "balance"
  | string; // allow future instrument types from the backend

export type UploadStatus =
  | "uploading"
  | "parsing"
  | "parsed"
  | "failed"
  | "all";

export interface DateRange {
  from: string | null; // ISO date string "YYYY-MM-DD"
  to: string | null;
}

export interface UploadFilters {
  status: UploadStatus;
  instrumentType: InstrumentType | "all";
  projectId: string | null;
  dateRange: DateRange;
  searchQuery: string;
}

export interface SearchFilters {
  instrumentType: InstrumentType | "all";
  projectId: string | null;
  dateRange: DateRange;
  query: string;
}

export interface ExperimentFilters {
  status: string | "all";
  projectId: string | null;
  searchQuery: string;
}

export interface FilterState {
  uploads: UploadFilters;
  search: SearchFilters;
  experiments: ExperimentFilters;
}

export interface FilterActions {
  // Uploads page filters
  setUploadFilters: (filters: Partial<UploadFilters>) => void;
  resetUploadFilters: () => void;

  // Search page filters
  setSearchFilters: (filters: Partial<SearchFilters>) => void;
  resetSearchFilters: () => void;

  // Experiments page filters
  setExperimentFilters: (filters: Partial<ExperimentFilters>) => void;
  resetExperimentFilters: () => void;

  // Reset all filters
  resetAllFilters: () => void;
}

// ---------------------------------------------------------------------------
// Default values
// ---------------------------------------------------------------------------

const defaultUploadFilters: UploadFilters = {
  status: "all",
  instrumentType: "all",
  projectId: null,
  dateRange: { from: null, to: null },
  searchQuery: "",
};

const defaultSearchFilters: SearchFilters = {
  instrumentType: "all",
  projectId: null,
  dateRange: { from: null, to: null },
  query: "",
};

const defaultExperimentFilters: ExperimentFilters = {
  status: "all",
  projectId: null,
  searchQuery: "",
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export type FilterStore = FilterState & FilterActions;

export const useFilterStore = create<FilterStore>()(
  devtools(
    persist(
      (set) => ({
        // ---- Initial state ----
        uploads: { ...defaultUploadFilters },
        search: { ...defaultSearchFilters },
        experiments: { ...defaultExperimentFilters },

        // ---- Upload filters ----
        setUploadFilters: (filters) =>
          set(
            (s) => ({ uploads: { ...s.uploads, ...filters } }),
            false,
            "filter/setUploadFilters",
          ),

        resetUploadFilters: () =>
          set(
            { uploads: { ...defaultUploadFilters } },
            false,
            "filter/resetUploadFilters",
          ),

        // ---- Search filters ----
        setSearchFilters: (filters) =>
          set(
            (s) => ({ search: { ...s.search, ...filters } }),
            false,
            "filter/setSearchFilters",
          ),

        resetSearchFilters: () =>
          set(
            { search: { ...defaultSearchFilters } },
            false,
            "filter/resetSearchFilters",
          ),

        // ---- Experiment filters ----
        setExperimentFilters: (filters) =>
          set(
            (s) => ({ experiments: { ...s.experiments, ...filters } }),
            false,
            "filter/setExperimentFilters",
          ),

        resetExperimentFilters: () =>
          set(
            { experiments: { ...defaultExperimentFilters } },
            false,
            "filter/resetExperimentFilters",
          ),

        // ---- Reset all ----
        resetAllFilters: () =>
          set(
            {
              uploads: { ...defaultUploadFilters },
              search: { ...defaultSearchFilters },
              experiments: { ...defaultExperimentFilters },
            },
            false,
            "filter/resetAllFilters",
          ),
      }),
      {
        name: "lablink-filters",
        storage: createJSONStorage(() => sessionStorage),
      },
    ),
    { name: "FilterStore" },
  ),
);
