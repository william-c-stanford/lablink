/**
 * Sidebar — primary desktop navigation panel.
 *
 * Neuromorphic design:
 *   - Background: var(--bg)  (#f5f7fa)
 *   - Shadow: var(--nm-shadow-md)  — raises it above the page background
 *   - Active nav item: nm-inset-sm   — presses it in when selected
 *   - Logo icon: nm-glow-blue       — blue ambient glow
 *   - Collapse toggle: nm-btn       — interactive raised button
 *
 * Responsive:
 *   - Desktop: fixed width 260px (expanded) / 72px (collapsed)
 *   - Mobile: hidden — bottom nav used instead (see AppShell)
 *
 * State:
 *   - sidebarCollapsed from UIStore (persisted to localStorage)
 */

import { Link, useRouterState } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store";
import {
  LayoutDashboard,
  Upload,
  Search,
  FlaskConical,
  Cpu,
  Settings,
  ChevronLeft,
  ChevronRight,
  Link2,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Nav item definitions
// ---------------------------------------------------------------------------

interface NavItem {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  label: string;
  href: string;
  badge?: string | number;
}

const PRIMARY_NAV: NavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", href: "/" },
  { icon: Upload, label: "Uploads", href: "/uploads" },
  { icon: Search, label: "Search", href: "/search" },
  { icon: FlaskConical, label: "Experiments", href: "/experiments" },
  { icon: Cpu, label: "Agents", href: "/agents" },
];

const SECONDARY_NAV: NavItem[] = [
  { icon: Settings, label: "Settings", href: "/settings" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Sidebar() {
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  const currentPath = useRouterState({ select: (s) => s.location.pathname });

  return (
    <nav
      className="relative h-full flex flex-col overflow-hidden"
      style={{
        backgroundColor: "var(--bg)",
        boxShadow: "var(--nm-shadow-md)",
      }}
    >
      {/* ── Logo area ──────────────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center h-16 px-4 flex-shrink-0",
          sidebarCollapsed ? "justify-center" : "gap-3",
        )}
        style={{
          borderBottom: "1px solid rgba(174, 185, 201, 0.25)",
        }}
      >
        {/* Logo icon — blue glow */}
        <div
          className={cn(
            "flex-shrink-0 w-10 h-10 rounded-xl",
            "flex items-center justify-center",
            "bg-[#3b82f6] transition-shadow duration-200",
          )}
          style={{
            boxShadow: "0 0 20px rgba(59, 130, 246, 0.45), 4px 4px 8px rgba(174, 185, 201, 0.4), -4px -4px 8px rgba(255, 255, 255, 0.9)",
          }}
        >
          <Link2 size={20} strokeWidth={2.5} className="text-white" />
        </div>

        {/* Brand name — hidden when collapsed */}
        {!sidebarCollapsed && (
          <span
            className="text-xl font-extrabold tracking-tight"
            style={{ color: "#0f172a" }}
          >
            LabLink
          </span>
        )}
      </div>

      {/* ── Primary navigation ─────────────────────────────────────────── */}
      <div className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {PRIMARY_NAV.map((item) => (
          <SidebarNavItem
            key={item.href}
            item={item}
            collapsed={sidebarCollapsed}
            active={currentPath === item.href}
          />
        ))}
      </div>

      {/* ── Divider + secondary nav ────────────────────────────────────── */}
      <div
        className="px-2 pb-2 space-y-1"
        style={{
          borderTop: "1px solid rgba(174, 185, 201, 0.25)",
          paddingTop: "0.5rem",
        }}
      >
        {SECONDARY_NAV.map((item) => (
          <SidebarNavItem
            key={item.href}
            item={item}
            collapsed={sidebarCollapsed}
            active={currentPath === item.href}
          />
        ))}
      </div>

      {/* ── Collapse toggle ────────────────────────────────────────────── */}
      <div className="px-2 pb-4">
        <button
          onClick={toggleSidebar}
          className={cn(
            "nm-btn w-full flex items-center justify-center",
            "h-9 rounded-xl",
            "text-[#64748b] hover:text-[#3b82f6]",
            "transition-colors duration-200",
          )}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <ChevronRight size={18} strokeWidth={2} />
          ) : (
            <span className="flex items-center gap-2 text-sm font-semibold">
              <ChevronLeft size={18} strokeWidth={2} />
              <span>Collapse</span>
            </span>
          )}
        </button>
      </div>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// SidebarNavItem
// ---------------------------------------------------------------------------

interface SidebarNavItemProps {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}

function SidebarNavItem({ item, collapsed, active }: SidebarNavItemProps) {
  const { icon: Icon, label, href, badge } = item;

  return (
    <Link
      to={href as "/"}
      className={cn(
        // Base layout
        "flex items-center gap-3 h-11 rounded-xl px-3",
        "transition-all duration-200",
        // Text style
        "text-sm font-semibold",
        // Active vs idle state
        active
          ? "text-[#3b82f6]"
          : "text-[#64748b] hover:text-[#1e293b]",
        // Collapsed: center the icon
        collapsed && "justify-center px-0",
      )}
      style={
        active
          ? {
              backgroundColor: "var(--bg)",
              boxShadow: "var(--nm-inset-sm)",
            }
          : {}
      }
      aria-current={active ? "page" : undefined}
      title={collapsed ? label : undefined}
    >
      {/* Icon */}
      <Icon
        size={20}
        strokeWidth={active ? 2.5 : 2}
        className="flex-shrink-0"
      />

      {/* Label — hidden when collapsed */}
      {!collapsed && (
        <span className="flex-1 truncate">{label}</span>
      )}

      {/* Badge — hidden when collapsed */}
      {!collapsed && badge !== undefined && (
        <span
          className="ml-auto text-xs font-bold px-2 py-0.5 rounded-full"
          style={{
            backgroundColor: "var(--bg)",
            boxShadow: "var(--nm-inset-xs)",
            color: active ? "#3b82f6" : "#94a3b8",
          }}
        >
          {badge}
        </span>
      )}
    </Link>
  );
}
