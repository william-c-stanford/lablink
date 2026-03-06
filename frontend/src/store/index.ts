/**
 * Central re-export for all Zustand stores.
 *
 * Usage:
 *   import { useUIStore, useFilterStore, useAuthStore } from "@/store";
 */

export { useUIStore } from "./uiStore";
export type { UIStore, UIState, UIActions, Toast, ToastVariant } from "./uiStore";

export { useFilterStore } from "./filterStore";
export type {
  FilterStore,
  FilterState,
  FilterActions,
  UploadFilters,
  SearchFilters,
  ExperimentFilters,
  InstrumentType,
  UploadStatus,
  DateRange,
} from "./filterStore";

export { useAuthStore } from "./authStore";
export type { AuthStore, AuthState, AuthActions, UserProfile } from "./authStore";
export {
  selectAccessToken,
  selectUser,
  selectIsAuthenticated,
  selectIsRefreshing,
  selectIsInitialized,
} from "./authStore";

export { useEventStore, MAX_EVENTS } from "./eventStore";
export type { EventStore, EventState, EventActions } from "./eventStore";
export {
  selectEvents,
  selectConnectionStatus,
  selectLastEventAt,
  selectTotalReceived,
  selectIsConnected,
  selectFileIngestedEvents,
  selectJobStatusEvents,
  selectAlertEvents,
  selectLatestByType,
} from "./eventStore";
