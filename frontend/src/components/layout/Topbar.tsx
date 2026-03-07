/**
 * Topbar — sticky application header for authenticated pages.
 *
 * Neuromorphic design:
 *   - Background: var(--bg) with var(--nm-shadow-sm) — raised above content
 *   - Search input: nm-inset-sm — recessed input well
 *   - Action buttons: nm-btn — raised interactive pill
 *   - User avatar: blue glow + raised circle
 *   - Notification panel: nm-shadow-lg dropdown card
 *
 * Slots:
 *   Left:   Mobile hamburger + page title
 *   Center: Global search (hidden on mobile)
 *   Right:  Notification bell + user avatar
 */

import { useState, type KeyboardEvent } from 'react'
import { Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { Search, Bell, Menu, X, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore, useAuthStore, selectUser } from '@/store'

// ---------------------------------------------------------------------------
// Topbar
// ---------------------------------------------------------------------------

export function Topbar() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const user = useAuthStore(selectUser)

  const [searchQuery, setSearchQuery] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)

  const navigate = useNavigate()

  function handleSearchKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate({ to: '/search' })
    }
    if (e.key === 'Escape') {
      setSearchQuery('')
      ;(e.target as HTMLInputElement).blur()
    }
  }

  return (
    <div
      className="h-full flex items-center gap-3 px-4 sm:px-6"
      style={{
        backgroundColor: 'var(--bg)',
        boxShadow: 'var(--nm-shadow-sm)',
      }}
    >
      {/* ── Mobile menu toggle ──────────────────────────────────────────── */}
      <button
        onClick={toggleSidebar}
        className="nm-btn lg:hidden w-9 h-9 rounded-xl flex items-center justify-center transition-colors duration-200"
        style={{ color: 'var(--text-muted)' }}
        aria-label="Toggle navigation menu"
      >
        <Menu size={18} strokeWidth={2} />
      </button>

      {/* ── Page title (desktop) ────────────────────────────────────────── */}
      <PageTitle />

      {/* ── Spacer ──────────────────────────────────────────────────────── */}
      <div className="flex-1" />

      {/* ── Global search ───────────────────────────────────────────────── */}
      <div className="hidden md:flex items-center">
        <div
          className="relative flex items-center w-64 lg:w-80 h-9 rounded-xl overflow-hidden transition-all duration-200"
          style={{
            backgroundColor: 'var(--bg)',
            boxShadow: searchFocused
              ? 'var(--nm-inset-sm), 0 0 0 2px rgba(59,130,246,0.25)'
              : 'var(--nm-inset-sm)',
          }}
        >
          <Search
            size={15}
            strokeWidth={2}
            className="absolute left-3 pointer-events-none"
            style={{ color: 'var(--text-subtle)' }}
          />
          <input
            type="search"
            placeholder="Search experiments, uploads…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKey}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            className="w-full h-full bg-transparent border-none outline-none pl-9 pr-8 text-sm font-medium"
            style={{ fontFamily: 'var(--font-sans)', color: 'var(--text-dark)' }}
            aria-label="Global search"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 transition-colors"
              style={{ color: 'var(--text-subtle)' }}
              aria-label="Clear search"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* ── Notification bell ───────────────────────────────────────────── */}
      <div className="relative">
        <button
          onClick={() => setNotifOpen((o) => !o)}
          className={cn(
            'nm-btn relative w-9 h-9 rounded-xl flex items-center justify-center transition-colors duration-200',
            notifOpen && 'nm-btn-active',
          )}
          style={{ color: notifOpen ? 'var(--blue)' : 'var(--text-muted)' }}
          aria-label="Notifications"
          aria-expanded={notifOpen}
          aria-haspopup="true"
        >
          <Bell size={18} strokeWidth={2} />
          {/* Unread dot */}
          <span
            className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-[#3b82f6] border-2 border-[#f5f7fa]"
            aria-hidden="true"
          />
        </button>

        {notifOpen && (
          <NotificationPanel onClose={() => setNotifOpen(false)} />
        )}
      </div>

      {/* ── User avatar ─────────────────────────────────────────────────── */}
      <UserAvatar user={user} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// PageTitle — derived from current pathname
// ---------------------------------------------------------------------------

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/uploads': 'Uploads',
  '/search': 'Search',
  '/experiments': 'Experiments',
  '/agents': 'Agents',
  '/settings': 'Settings',
}

function PageTitle() {
  const path = useRouterState({ select: (s) => s.location.pathname })
  const title = PAGE_TITLES[path] ?? 'LabLink'

  return (
    <h1
      className="text-base font-bold tracking-tight"
      style={{ color: 'var(--text-dark)', fontFamily: 'var(--font-sans)' }}
    >
      {title}
    </h1>
  )
}

// ---------------------------------------------------------------------------
// NotificationPanel
// ---------------------------------------------------------------------------

interface NotificationPanelProps {
  onClose: () => void
}

type NotifType = 'success' | 'info' | 'error' | 'warning'

const NOTIF_DOT_COLORS: Record<NotifType, string> = {
  success: '#22c55e',
  info: '#6366f1',
  error: '#ef4444',
  warning: '#f97316',
}

function NotificationPanel({ onClose }: NotificationPanelProps) {
  return (
    <div
      className="absolute right-0 top-full mt-2 z-50 w-80 rounded-2xl overflow-hidden animate-fade-in"
      style={{
        backgroundColor: 'var(--bg)',
        boxShadow: '12px 12px 24px rgba(174,185,201,0.40), -12px -12px 24px rgba(255,255,255,0.90)',
      }}
      role="dialog"
      aria-label="Notifications panel"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid rgba(174,185,201,0.25)' }}
      >
        <span className="text-sm font-bold" style={{ color: 'var(--text-dark)' }}>
          Notifications
        </span>
        <button
          onClick={onClose}
          className="transition-colors"
          style={{ color: 'var(--text-subtle)' }}
          aria-label="Close notifications"
        >
          <X size={16} />
        </button>
      </div>

      {/* Items */}
      <div className="p-3 space-y-0.5">
        {SAMPLE_NOTIFICATIONS.map((n, i) => (
          <NotificationItem key={i} {...n} />
        ))}
      </div>

      {/* Footer */}
      <div
        className="px-4 py-3 text-center"
        style={{ borderTop: '1px solid rgba(174,185,201,0.25)' }}
      >
        <Link
          to="/uploads"
          className="text-xs font-bold hover:underline"
          style={{ color: 'var(--blue)' }}
          onClick={onClose}
        >
          View all activity
        </Link>
      </div>
    </div>
  )
}

const SAMPLE_NOTIFICATIONS = [
  {
    title: 'Upload parsed successfully',
    description: 'spectro_sample_001.csv — NanoDrop UV-Vis',
    time: '2m ago',
    type: 'success' as NotifType,
  },
  {
    title: 'Agent connected',
    description: 'Instrument PC #3 is now online',
    time: '12m ago',
    type: 'info' as NotifType,
  },
  {
    title: 'Parse failed',
    description: 'hplc_run_034.csv — unrecognised format',
    time: '1h ago',
    type: 'error' as NotifType,
  },
]

interface NotificationItemProps {
  title: string
  description: string
  time: string
  type: NotifType
}

function NotificationItem({ title, description, time, type }: NotificationItemProps) {
  return (
    <div className="flex gap-3 px-1 py-2.5 rounded-xl transition-colors hover:bg-white/40">
      <div
        className="flex-shrink-0 w-2 h-2 rounded-full mt-1.5"
        style={{ backgroundColor: NOTIF_DOT_COLORS[type] }}
        aria-hidden="true"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold truncate" style={{ color: 'var(--text-dark)' }}>
          {title}
        </p>
        <p className="text-xs truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
          {description}
        </p>
      </div>
      <span
        className="flex-shrink-0 text-xs mt-0.5"
        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-subtle)' }}
      >
        {time}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// UserAvatar
// ---------------------------------------------------------------------------

interface UserAvatarProps {
  user: { name: string; email: string; role: string } | null
}

function UserAvatar({ user }: UserAvatarProps) {
  const initials = user
    ? user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : '?'

  return (
    <button
      className="nm-btn flex items-center gap-2 h-9 pl-1 pr-3 rounded-xl transition-colors duration-200"
      style={{ color: 'var(--text-dark)' }}
      aria-label="User menu"
      aria-haspopup="true"
    >
      {/* Avatar disc */}
      <div
        className="w-7 h-7 rounded-full flex items-center justify-center bg-[#3b82f6] text-white text-xs font-bold flex-shrink-0"
        style={{
          boxShadow:
            '0 0 12px rgba(59,130,246,0.35), 2px 2px 4px rgba(174,185,201,0.40)',
        }}
      >
        {initials}
      </div>

      {/* Name */}
      <span
        className="hidden sm:block text-sm font-semibold truncate max-w-[120px]"
        style={{ fontFamily: 'var(--font-sans)', color: 'var(--text-dark)' }}
      >
        {user?.name ?? 'Guest'}
      </span>

      <ChevronDown size={14} strokeWidth={2.5} style={{ color: 'var(--text-subtle)' }} />
    </button>
  )
}
