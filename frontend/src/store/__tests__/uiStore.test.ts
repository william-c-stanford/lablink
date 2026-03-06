import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../uiStore";

// Reset store state before each test
beforeEach(() => {
  useUIStore.setState({
    sidebarCollapsed: false,
    toasts: [],
    globalLoading: false,
  });
});

describe("uiStore — sidebar", () => {
  it("starts with sidebar expanded", () => {
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("toggleSidebar collapses an expanded sidebar", () => {
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
  });

  it("toggleSidebar expands a collapsed sidebar", () => {
    useUIStore.setState({ sidebarCollapsed: true });
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("setSidebarCollapsed sets explicitly", () => {
    useUIStore.getState().setSidebarCollapsed(true);
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    useUIStore.getState().setSidebarCollapsed(false);
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });
});

describe("uiStore — toasts", () => {
  it("starts with empty toast queue", () => {
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it("addToast adds a toast and returns its id", () => {
    const id = useUIStore.getState().addToast({
      title: "Hello",
      variant: "success",
      duration: 4000,
    });
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].id).toBe(id);
    expect(toasts[0].title).toBe("Hello");
    expect(toasts[0].variant).toBe("success");
  });

  it("removeToast removes only the targeted toast", () => {
    const id1 = useUIStore.getState().addToast({ title: "A", variant: "info", duration: 4000 });
    const id2 = useUIStore.getState().addToast({ title: "B", variant: "info", duration: 4000 });
    useUIStore.getState().removeToast(id1);
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].id).toBe(id2);
  });

  it("clearToasts empties the queue", () => {
    useUIStore.getState().addToast({ title: "X", variant: "error", duration: 6000 });
    useUIStore.getState().addToast({ title: "Y", variant: "warning", duration: 5000 });
    useUIStore.getState().clearToasts();
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it("toastSuccess adds success toast with default 4s duration", () => {
    useUIStore.getState().toastSuccess("Great!", "All good");
    const [toast] = useUIStore.getState().toasts;
    expect(toast.variant).toBe("success");
    expect(toast.duration).toBe(4000);
    expect(toast.description).toBe("All good");
  });

  it("toastError adds error toast with default 6s duration", () => {
    useUIStore.getState().toastError("Oops");
    const [toast] = useUIStore.getState().toasts;
    expect(toast.variant).toBe("error");
    expect(toast.duration).toBe(6000);
  });

  it("toastWarning adds warning toast with default 5s duration", () => {
    useUIStore.getState().toastWarning("Watch out");
    const [toast] = useUIStore.getState().toasts;
    expect(toast.variant).toBe("warning");
    expect(toast.duration).toBe(5000);
  });

  it("toastInfo adds info toast", () => {
    useUIStore.getState().toastInfo("FYI");
    const [toast] = useUIStore.getState().toasts;
    expect(toast.variant).toBe("info");
  });

  it("each toast gets a unique id", () => {
    const id1 = useUIStore.getState().addToast({ title: "A", variant: "info", duration: 4000 });
    const id2 = useUIStore.getState().addToast({ title: "B", variant: "info", duration: 4000 });
    expect(id1).not.toBe(id2);
  });

  it("toast has createdAt timestamp", () => {
    const before = Date.now();
    useUIStore.getState().addToast({ title: "TS", variant: "info", duration: 4000 });
    const after = Date.now();
    const [toast] = useUIStore.getState().toasts;
    expect(toast.createdAt).toBeGreaterThanOrEqual(before);
    expect(toast.createdAt).toBeLessThanOrEqual(after);
  });
});

describe("uiStore — globalLoading", () => {
  it("starts as false", () => {
    expect(useUIStore.getState().globalLoading).toBe(false);
  });

  it("setGlobalLoading sets to true", () => {
    useUIStore.getState().setGlobalLoading(true);
    expect(useUIStore.getState().globalLoading).toBe(true);
  });

  it("setGlobalLoading sets back to false", () => {
    useUIStore.setState({ globalLoading: true });
    useUIStore.getState().setGlobalLoading(false);
    expect(useUIStore.getState().globalLoading).toBe(false);
  });
});
