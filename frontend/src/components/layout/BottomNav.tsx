/**
 * BottomNav -- mobile-only bottom navigation bar.
 *
 * Neuromorphic design:
 *   - Background: var(--bg) with var(--nm-shadow-md) raised shadow
 *   - Active item: nm-btn-active (inset) + blue text
 *   - Idle item: muted text, no shadow
 *
 * Responsive:
 *   - Visible only on screens below `lg` breakpoint (lg:hidden)
 *   - Desktop navigation is handled by <Sidebar>
 *
 * Nav items mirror the sidebar PRIMARY_NAV list so both navigations
 * stay in sync.
 */

import { Link, useRouterState } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Upload,
  Search,
  FlaskConical,
  Cpu,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Nav item definitions (mirrors Sidebar PRIMARY_NAV)
// ---------------------------------------------------------------------------

interface MobileNavItem {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
  href: string;
}

const MOBILE_NAV_ITEMS: MobileNavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/" },
  { icon: Upload, label: "Uploads", href: "/uploads" },
  { icon: Search, label: "Search", href: "/search" },
  { icon: FlaskConical, label: "Experiments", href: "/experiments" },
  { icon: Cpu, label: "Agents", href: "/agents" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BottomNav() {
  const currentPath = useRouterState({ select: (s) => s.location.pathname });

  return (
    <nav
      className={cn(
        "fixed bottom-0 inset-x-0 z-40",
        "lg:hidden",
        "flex items-center justify-around",
        "h-16 px-2",
      )}
      style={{
        backgroundColor: "var(--bg)",
        boxShadow: "var(--nm-shadow-md)",
      }}
      aria-label="Mobile navigation"
    >
      {MOBILE_NAV_ITEMS.map(({ icon: Icon, label, href }) => {
        const isActive = currentPath === href;
        return (
          <Link
            key={href}
            to={href as "/"}
            className={cn(
              "flex flex-col items-center gap-1 px-3 py-1.5 rounded-xl",
              "text-[11px] font-semibold transition-all duration-200",
              isActive
                ? "text-[#3b82f6]"
                : "text-[#64748b] hover:text-[#3b82f6]",
            )}
            style={
              isActive
                ? {
                    backgroundColor: "var(--bg)",
                    boxShadow: "var(--nm-inset-xs)",
                  }
                : undefined
            }
            aria-current={isActive ? "page" : undefined}
          >
            <Icon
              size={20}
              strokeWidth={isActive ? 2.5 : 2}
              aria-hidden="true"
            />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
