import { describe, it, expect, beforeEach } from "vitest";
import { useFilterStore } from "../filterStore";

const defaultUpload = {
  status: "all",
  instrumentType: "all",
  projectId: null,
  dateRange: { from: null, to: null },
  searchQuery: "",
} as const;

const defaultSearch = {
  instrumentType: "all",
  projectId: null,
  dateRange: { from: null, to: null },
  query: "",
} as const;

const defaultExperiments = {
  status: "all",
  projectId: null,
  searchQuery: "",
} as const;

beforeEach(() => {
  useFilterStore.setState({
    uploads: { ...defaultUpload },
    search: { ...defaultSearch },
    experiments: { ...defaultExperiments },
  });
});

describe("filterStore — upload filters", () => {
  it("has correct defaults", () => {
    expect(useFilterStore.getState().uploads).toEqual(defaultUpload);
  });

  it("setUploadFilters merges partial updates", () => {
    useFilterStore.getState().setUploadFilters({ status: "parsed", searchQuery: "ATP" });
    const { uploads } = useFilterStore.getState();
    expect(uploads.status).toBe("parsed");
    expect(uploads.searchQuery).toBe("ATP");
    // untouched fields preserved
    expect(uploads.instrumentType).toBe("all");
  });

  it("setUploadFilters updates date range", () => {
    useFilterStore.getState().setUploadFilters({
      dateRange: { from: "2026-01-01", to: "2026-03-06" },
    });
    expect(useFilterStore.getState().uploads.dateRange.from).toBe("2026-01-01");
    expect(useFilterStore.getState().uploads.dateRange.to).toBe("2026-03-06");
  });

  it("resetUploadFilters restores defaults", () => {
    useFilterStore.getState().setUploadFilters({ status: "failed", searchQuery: "error" });
    useFilterStore.getState().resetUploadFilters();
    expect(useFilterStore.getState().uploads).toEqual(defaultUpload);
  });
});

describe("filterStore — search filters", () => {
  it("has correct defaults", () => {
    expect(useFilterStore.getState().search).toEqual(defaultSearch);
  });

  it("setSearchFilters merges partial updates", () => {
    useFilterStore.getState().setSearchFilters({ query: "HPLC run 42", instrumentType: "hplc" });
    const { search } = useFilterStore.getState();
    expect(search.query).toBe("HPLC run 42");
    expect(search.instrumentType).toBe("hplc");
  });

  it("resetSearchFilters restores defaults", () => {
    useFilterStore.getState().setSearchFilters({ query: "test", projectId: "proj-1" });
    useFilterStore.getState().resetSearchFilters();
    expect(useFilterStore.getState().search).toEqual(defaultSearch);
  });
});

describe("filterStore — experiment filters", () => {
  it("has correct defaults", () => {
    expect(useFilterStore.getState().experiments).toEqual(defaultExperiments);
  });

  it("setExperimentFilters merges partial updates", () => {
    useFilterStore.getState().setExperimentFilters({ status: "running", searchQuery: "exp-99" });
    const { experiments } = useFilterStore.getState();
    expect(experiments.status).toBe("running");
    expect(experiments.searchQuery).toBe("exp-99");
  });

  it("resetExperimentFilters restores defaults", () => {
    useFilterStore.getState().setExperimentFilters({ status: "completed" });
    useFilterStore.getState().resetExperimentFilters();
    expect(useFilterStore.getState().experiments).toEqual(defaultExperiments);
  });
});

describe("filterStore — resetAllFilters", () => {
  it("resets all filter slices simultaneously", () => {
    useFilterStore.getState().setUploadFilters({ status: "failed" });
    useFilterStore.getState().setSearchFilters({ query: "xyz" });
    useFilterStore.getState().setExperimentFilters({ status: "running" });

    useFilterStore.getState().resetAllFilters();

    const state = useFilterStore.getState();
    expect(state.uploads).toEqual(defaultUpload);
    expect(state.search).toEqual(defaultSearch);
    expect(state.experiments).toEqual(defaultExperiments);
  });
});
