import { create } from "zustand";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Toast {
  id: string;
  message: string;
  type: "info" | "success" | "warning" | "error";
  /** Auto-dismiss duration in ms. Defaults to 5000. Set to 0 to persist. */
  duration?: number;
}

interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // Filters
  activeFilters: Record<string, string[]>;
  setFilter: (key: string, values: string[]) => void;
  clearFilters: () => void;

  // Toasts
  toasts: Toast[];
  addToast: (toast: Omit<Toast, "id">) => void;
  removeToast: (id: string) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

let toastCounter = 0;

export const useUIStore = create<UIState>((set) => ({
  // Sidebar ----------------------------------------------------------------
  sidebarCollapsed: false,
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

  // Filters ----------------------------------------------------------------
  activeFilters: {},
  setFilter: (key, values) =>
    set((state) => ({
      activeFilters: { ...state.activeFilters, [key]: values },
    })),
  clearFilters: () => set({ activeFilters: {} }),

  // Toasts -----------------------------------------------------------------
  toasts: [],
  addToast: (toast) => {
    const id = `toast-${++toastCounter}-${Date.now()}`;
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }));

    const duration = toast.duration ?? 5000;
    if (duration > 0) {
      setTimeout(() => {
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        }));
      }, duration);
    }
  },
  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),
}));
