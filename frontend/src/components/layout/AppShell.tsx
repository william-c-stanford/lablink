/**
 * AppShell — root layout for all authenticated pages.
 *
 * Layout model (desktop):
 *   ┌──────────┬─────────────────────────────────────┐
 *   │          │  Topbar (h-16, nm-outset)            │
 *   │ Sidebar  ├─────────────────────────────────────┤
 *   │ (260px)  │                                     │
 *   │ nm-outset│  <children>  (scrollable main area) │
 *   │          │                                     │
 *   └──────────┴─────────────────────────────────────┘
 *
 * Layout model (mobile):
 *   ┌─────────────────────────────────────┐
 *   │  Topbar  (h-14)                     │
 *   ├─────────────────────────────────────┤
 *   │  <children>  (scrollable)           │
 *   ├─────────────────────────────────────┤
 *   │  Bottom nav (nm-outset)             │
 *   └─────────────────────────────────────┘
 *
 * Design tokens used:
 *   --bg              : #f5f7fa (page background)
 *   --nm-shadow-md    : raised sidebar shadow
 *   var(--nm-shadow-sm): topbar shadow
 */

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { BottomNav } from "./BottomNav";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AppShellProps {
  /** Page content to render in the main scrolling area */
  children: ReactNode;
  /** Optional additional className for the main content area */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

// Sidebar widths
const SIDEBAR_W_EXPANDED  = 260;
const SIDEBAR_W_COLLAPSED = 72;

/**
 * AppShell wraps every authenticated page with the persistent sidebar and
 * topbar. It reads collapsed state from the Zustand UIStore so the layout
 * responds to the sidebar toggle without re-mounting children.
 *
 * Sidebar width is applied via inline `style` (not Tailwind classes) so it
 * can respond to the `sidebarCollapsed` boolean at runtime.
 */
export function AppShell({ children, className }: AppShellProps) {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const sidebarWidth = sidebarCollapsed ? SIDEBAR_W_COLLAPSED : SIDEBAR_W_EXPANDED;

  return (
    <div
      className="min-h-screen"
      style={{ backgroundColor: "var(--bg)" }}
    >
      {/* ── Desktop sidebar (fixed left column) ────────────────────────── */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40",
          "hidden lg:flex lg:flex-col",
          // Smooth width transition
          "[transition:width_300ms_ease]",
        )}
        style={{ width: `${sidebarWidth}px` }}
        aria-label="Main navigation"
      >
        <Sidebar />
      </aside>

      {/* ── Content area: fills space to the right of the sidebar ─────── */}
      <div
        className={cn(
          "flex flex-col min-h-screen",
          "[transition:margin-left_300ms_ease]",
          // On mobile: no margin (sidebar is hidden, bottom nav used instead)
          // On desktop (lg+): push right by the sidebar width
        )}
        style={{
          // CSS media query cannot reference JS state, so we set marginLeft
          // unconditionally and hide the sidebar via the `hidden lg:flex` above.
          // On mobile the sidebar is hidden so marginLeft has no visual effect.
          marginLeft: `${sidebarWidth}px`,
        }}
      >
        {/* ── Topbar ───────────────────────────────────────────────────── */}
        <header
          className="sticky top-0 z-30"
          style={{ height: "64px" }}
        >
          <Topbar />
        </header>

        {/* ── Main scrolling content ────────────────────────────────────── */}
        <main
          id="main-content"
          className={cn(
            "flex-1",
            "px-4 py-6 sm:px-6 lg:px-8",
            // Extra bottom padding on mobile to clear the bottom nav
            "pb-24 lg:pb-6",
            className,
          )}
          style={{ backgroundColor: "var(--bg)" }}
        >
          {children}
        </main>
      </div>

      {/* ── Mobile bottom navigation ──────────────────────────────────── */}
      <BottomNav />
    </div>
  );
}
