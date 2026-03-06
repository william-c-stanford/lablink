/**
 * Auth Store — JWT kept only in memory (never localStorage/sessionStorage)
 *
 * Holds the access token and a minimal decoded user profile.
 * On a hard refresh the token is lost and the app redirects to /login,
 * which keeps us PCI-DSS / SOC-2 friendly for in-memory token storage.
 */

import { create } from "zustand";
import { devtools } from "zustand/middleware";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  role: "admin" | "scientist" | "viewer";
  labId: string;
}

export interface AuthState {
  /** JWT access token — in memory only */
  accessToken: string | null;
  /** Decoded user profile from JWT claims */
  user: UserProfile | null;
  /** True while a token refresh is in flight */
  isRefreshing: boolean;
  /** True once we've attempted to restore session on mount */
  isInitialized: boolean;
}

export interface AuthActions {
  setAuth: (accessToken: string, user: UserProfile) => void;
  clearAuth: () => void;
  setRefreshing: (refreshing: boolean) => void;
  setInitialized: () => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export type AuthStore = AuthState & AuthActions;

export const useAuthStore = create<AuthStore>()(
  devtools(
    (set) => ({
      // ---- Initial state ----
      accessToken: null,
      user: null,
      isRefreshing: false,
      isInitialized: false,

      // ---- Actions ----
      setAuth: (accessToken, user) =>
        set({ accessToken, user }, false, "auth/setAuth"),

      clearAuth: () =>
        set({ accessToken: null, user: null }, false, "auth/clearAuth"),

      setRefreshing: (isRefreshing) =>
        set({ isRefreshing }, false, "auth/setRefreshing"),

      setInitialized: () =>
        set({ isInitialized: true }, false, "auth/setInitialized"),
    }),
    { name: "AuthStore" },
  ),
);

// ---------------------------------------------------------------------------
// Selector helpers (stable references, avoiding unnecessary re-renders)
// ---------------------------------------------------------------------------

export const selectAccessToken = (s: AuthStore) => s.accessToken;
export const selectUser = (s: AuthStore) => s.user;
export const selectIsAuthenticated = (s: AuthStore) => s.accessToken !== null;
export const selectIsRefreshing = (s: AuthStore) => s.isRefreshing;
export const selectIsInitialized = (s: AuthStore) => s.isInitialized;
