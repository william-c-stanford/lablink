/**
 * Layout component exports.
 *
 * All layout components apply neuromorphic design tokens:
 *   AppShell   — root layout (sidebar + topbar + content + mobile nav)
 *   Sidebar    — desktop left-nav panel (nm-outset, nm-inset active state)
 *   Topbar     — sticky header (nm-shadow-sm, nm-inset search, nm-btn actions)
 *   BottomNav  — mobile bottom navigation bar (lg:hidden, nm-outset)
 */

export { AppShell } from "./AppShell";
export type { AppShellProps } from "./AppShell";

export { Sidebar } from "./Sidebar";

export { Topbar } from "./Topbar";

export { BottomNav } from "./BottomNav";
