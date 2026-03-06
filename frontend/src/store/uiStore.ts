/**
 * UI Store — Zustand store for global UI state
 *
 * Covers:
 *  - Sidebar collapsed / expanded state
 *  - Toast notification queue
 *  - Global loading overlay
 */

import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ToastVariant = "success" | "error" | "warning" | "info";

export interface Toast {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
  /** Duration in milliseconds. 0 = persistent until dismissed. */
  duration: number;
  createdAt: number;
}

export interface UIState {
  // Sidebar
  sidebarCollapsed: boolean;

  // Toasts
  toasts: Toast[];

  // Global loading overlay (e.g. during auth refresh)
  globalLoading: boolean;
}

export interface UIActions {
  // Sidebar
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Toasts
  addToast: (toast: Omit<Toast, "id" | "createdAt">) => string;
  removeToast: (id: string) => void;
  clearToasts: () => void;

  // Convenience toast helpers
  toastSuccess: (title: string, description?: string, duration?: number) => string;
  toastError: (title: string, description?: string, duration?: number) => string;
  toastWarning: (title: string, description?: string, duration?: number) => string;
  toastInfo: (title: string, description?: string, duration?: number) => string;

  // Global loading
  setGlobalLoading: (loading: boolean) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _toastCounter = 0;

function generateToastId(): string {
  _toastCounter += 1;
  return `toast-${Date.now()}-${_toastCounter}`;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export type UIStore = UIState & UIActions;

export const useUIStore = create<UIStore>()(
  devtools(
    persist(
      (set, get) => ({
        // ---- Initial state ----
        sidebarCollapsed: false,
        toasts: [],
        globalLoading: false,

        // ---- Sidebar ----
        toggleSidebar: () =>
          set(
            (s) => ({ sidebarCollapsed: !s.sidebarCollapsed }),
            false,
            "ui/toggleSidebar",
          ),

        setSidebarCollapsed: (collapsed) =>
          set({ sidebarCollapsed: collapsed }, false, "ui/setSidebarCollapsed"),

        // ---- Toasts ----
        addToast: (toast) => {
          const id = generateToastId();
          const entry: Toast = { id, createdAt: Date.now(), ...toast };
          set(
            (s) => ({ toasts: [...s.toasts, entry] }),
            false,
            "ui/addToast",
          );
          return id;
        },

        removeToast: (id) =>
          set(
            (s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }),
            false,
            "ui/removeToast",
          ),

        clearToasts: () => set({ toasts: [] }, false, "ui/clearToasts"),

        // ---- Convenience helpers ----
        toastSuccess: (title, description, duration = 4000) =>
          get().addToast({ title, description, variant: "success", duration }),

        toastError: (title, description, duration = 6000) =>
          get().addToast({ title, description, variant: "error", duration }),

        toastWarning: (title, description, duration = 5000) =>
          get().addToast({ title, description, variant: "warning", duration }),

        toastInfo: (title, description, duration = 4000) =>
          get().addToast({ title, description, variant: "info", duration }),

        // ---- Global loading ----
        setGlobalLoading: (loading) =>
          set({ globalLoading: loading }, false, "ui/setGlobalLoading"),
      }),
      {
        name: "lablink-ui",
        // Only persist sidebar state; toasts are ephemeral
        partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }),
      },
    ),
    { name: "UIStore" },
  ),
);
