/**
 * AgentsPage -- full agent monitoring page with live SSE updates.
 *
 * Layout:
 *   1. Page header with connected/total counts
 *   2. Grid of agent cards (nm-outset), one per agent
 *      - Agent name + hostname
 *      - Online/offline status dot (green pulse if online, grey if offline)
 *      - Last heartbeat time (auto-updated by SSE agent.heartbeat events)
 *      - Queue depth (updated live from SSE heartbeat payload)
 *      - Live upload badge when SSE fires upload.status_changed for this agent
 *   3. "No agents connected" empty state
 *
 * SSE integration:
 *   - useSSE('/api/v1/sse/updates') drives live heartbeat + queue depth updates
 *   - useAgents() provides the initial load (polling every 30s as baseline)
 *   - SSE events overlay on top of polled data in local state
 */

import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent, Spinner } from '@/components/ui'
import { useAgents } from '@/api/hooks/useAgents'
import { useSSE } from '@/lib/sse'
import { Server, Wifi, WifiOff, Activity } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentRecord {
  id: string
  name?: string
  hostname?: string
  status: 'online' | 'offline' | 'idle' | string
  last_heartbeat_at?: string
  queue_depth?: number
  version?: string
  platform?: string
}

interface HeartbeatPayload {
  agent_id: string
  queue_depth?: number
  timestamp?: string
  status?: string
}

interface UploadStatusPayload {
  agent_id?: string
  upload_id: string
  filename?: string
  status: string
}

interface AgentLiveState {
  queue_depth: number | null
  last_heartbeat_at: string | null
  status: string
  /** Transient upload activity badge: resets after 8s */
  activeUpload: { upload_id: string; filename?: string; status: string } | null
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentsPage() {
  const agentsQuery = useAgents()
  const { lastEvent, connected: sseConnected } = useSSE('/api/v1/sse/updates')

  // Map from agent_id -> live overrides (SSE-driven)
  const [liveState, setLiveState] = useState<Record<string, AgentLiveState>>({})

  // ---------------------------------------------------------------------------
  // SSE event handler
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!lastEvent) return

    if (lastEvent.type === 'agent.heartbeat') {
      const payload = lastEvent.data as HeartbeatPayload
      if (!payload?.agent_id) return

      setLiveState((prev) => ({
        ...prev,
        [payload.agent_id]: {
          ...prev[payload.agent_id],
          queue_depth: payload.queue_depth ?? prev[payload.agent_id]?.queue_depth ?? null,
          last_heartbeat_at: payload.timestamp ?? lastEvent.timestamp,
          status: payload.status ?? prev[payload.agent_id]?.status ?? 'online',
          activeUpload: prev[payload.agent_id]?.activeUpload ?? null,
        },
      }))
    }

    if (lastEvent.type === 'agent.connected') {
      const payload = lastEvent.data as HeartbeatPayload
      if (!payload?.agent_id) return
      setLiveState((prev) => ({
        ...prev,
        [payload.agent_id]: {
          ...prev[payload.agent_id],
          status: 'online',
          last_heartbeat_at: lastEvent.timestamp,
          queue_depth: prev[payload.agent_id]?.queue_depth ?? null,
          activeUpload: prev[payload.agent_id]?.activeUpload ?? null,
        },
      }))
    }

    if (lastEvent.type === 'agent.disconnected') {
      const payload = lastEvent.data as HeartbeatPayload
      if (!payload?.agent_id) return
      setLiveState((prev) => ({
        ...prev,
        [payload.agent_id]: {
          ...prev[payload.agent_id],
          status: 'offline',
          last_heartbeat_at: prev[payload.agent_id]?.last_heartbeat_at ?? null,
          queue_depth: prev[payload.agent_id]?.queue_depth ?? null,
          activeUpload: null,
        },
      }))
    }

    if (lastEvent.type === 'upload.status_changed') {
      const payload = lastEvent.data as UploadStatusPayload
      if (!payload?.agent_id) return

      setLiveState((prev) => ({
        ...prev,
        [payload.agent_id]: {
          ...prev[payload.agent_id],
          status: prev[payload.agent_id]?.status ?? 'online',
          last_heartbeat_at: prev[payload.agent_id]?.last_heartbeat_at ?? null,
          queue_depth: prev[payload.agent_id]?.queue_depth ?? null,
          activeUpload: {
            upload_id: payload.upload_id,
            filename: payload.filename,
            status: payload.status,
          },
        },
      }))

      // Auto-clear the upload badge after 8 seconds
      const agentId = payload.agent_id
      setTimeout(() => {
        setLiveState((prev) => {
          const current = prev[agentId]
          if (!current) return prev
          // Only clear if it's still the same upload
          if (current.activeUpload?.upload_id !== payload.upload_id) return prev
          return {
            ...prev,
            [agentId]: { ...current, activeUpload: null },
          }
        })
      }, 8_000)
    }
  }, [lastEvent])

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------

  const envelope = agentsQuery.data as Record<string, unknown> | undefined
  const agents = (Array.isArray(envelope?.data) ? envelope!.data : []) as AgentRecord[]

  const connectedCount = agents.filter((a) => {
    const live = liveState[a.id]
    const status = live?.status ?? a.status
    return status === 'online'
  }).length

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2
            className="text-2xl font-extrabold tracking-tight"
            style={{ color: '#1e293b' }}
          >
            Agents
          </h2>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>
            Monitor connected desktop agents and live activity.
          </p>
        </div>

        {/* SSE connection indicator */}
        <div
          className="flex items-center gap-2 px-4 py-2 rounded-2xl text-xs font-semibold"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow: '4px 4px 8px rgba(174,185,201,0.3), -4px -4px 8px rgba(255,255,255,0.8)',
            color: sseConnected ? '#22c55e' : '#94a3b8',
          }}
        >
          {sseConnected ? (
            <Wifi size={14} strokeWidth={2} />
          ) : (
            <WifiOff size={14} strokeWidth={2} />
          )}
          {sseConnected ? 'Live' : 'Connecting...'}
        </div>
      </div>

      {/* Summary bar */}
      {!agentsQuery.isLoading && agents.length > 0 && (
        <div
          className="flex items-center gap-6 px-5 py-3 rounded-2xl"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow: 'inset 4px 4px 8px rgba(174,185,201,0.3), inset -4px -4px 8px rgba(255,255,255,0.85)',
          }}
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: '#94a3b8' }}>
              Total
            </span>
            <span className="text-sm font-extrabold" style={{ color: '#1e293b' }}>
              {agents.length}
            </span>
          </div>
          <div
            className="w-px h-4"
            style={{ backgroundColor: 'rgba(174,185,201,0.4)' }}
          />
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#22c55e]" />
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: '#94a3b8' }}>
              Online
            </span>
            <span className="text-sm font-extrabold" style={{ color: '#22c55e' }}>
              {connectedCount}
            </span>
          </div>
          <div
            className="w-px h-4"
            style={{ backgroundColor: 'rgba(174,185,201,0.4)' }}
          />
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#94a3b8]" />
            <span className="text-xs font-bold uppercase tracking-widest" style={{ color: '#94a3b8' }}>
              Offline
            </span>
            <span className="text-sm font-extrabold" style={{ color: '#94a3b8' }}>
              {agents.length - connectedCount}
            </span>
          </div>
        </div>
      )}

      {/* Loading */}
      {agentsQuery.isLoading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" />
        </div>
      )}

      {/* Error */}
      {agentsQuery.isError && (
        <div
          className="rounded-2xl px-5 py-4 text-sm font-medium text-center"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow: 'inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)',
            color: '#ef4444',
          }}
        >
          Failed to load agents. Please try again.
        </div>
      )}

      {/* Empty state */}
      {!agentsQuery.isLoading && !agentsQuery.isError && agents.length === 0 && (
        <div className="text-center py-20">
          <div
            className="w-20 h-20 rounded-3xl flex items-center justify-center mx-auto mb-5"
            style={{
              backgroundColor: '#f5f7fa',
              boxShadow: 'inset 8px 8px 16px rgba(174,185,201,0.4), inset -8px -8px 16px rgba(255,255,255,0.9)',
              color: '#94a3b8',
            }}
          >
            <Server size={32} strokeWidth={1.5} />
          </div>
          <p className="text-base font-semibold" style={{ color: '#64748b' }}>
            No agents connected
          </p>
          <p className="text-sm mt-1" style={{ color: '#94a3b8' }}>
            Install the LabLink desktop agent to start monitoring lab instruments.
          </p>
        </div>
      )}

      {/* Agent cards grid */}
      {agents.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              live={liveState[agent.id] ?? null}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// AgentCard
// ---------------------------------------------------------------------------

interface AgentCardProps {
  agent: AgentRecord
  live: AgentLiveState | null
}

function AgentCard({ agent, live }: AgentCardProps) {
  const status = live?.status ?? agent.status
  const isOnline = status === 'online'
  const lastHeartbeat = live?.last_heartbeat_at ?? agent.last_heartbeat_at
  const queueDepth = live?.queue_depth ?? agent.queue_depth ?? null
  const activeUpload = live?.activeUpload ?? null

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          {/* Icon + name */}
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
              style={{
                backgroundColor: '#f5f7fa',
                boxShadow: isOnline
                  ? `4px 4px 8px rgba(174,185,201,0.3), -4px -4px 8px rgba(255,255,255,0.8), 0 0 12px rgba(34,197,94,0.2)`
                  : '4px 4px 8px rgba(174,185,201,0.3), -4px -4px 8px rgba(255,255,255,0.8)',
                color: isOnline ? '#22c55e' : '#94a3b8',
              }}
            >
              <Server size={18} strokeWidth={2} />
            </div>
            <div className="min-w-0">
              <CardTitle>
                <span className="truncate block">
                  {agent.name ?? agent.hostname ?? `Agent ${agent.id.slice(0, 8)}`}
                </span>
              </CardTitle>
              {agent.hostname && agent.name && (
                <p className="text-xs mt-0.5 truncate" style={{ color: '#94a3b8' }}>
                  {agent.hostname}
                </p>
              )}
            </div>
          </div>

          {/* Status dot */}
          <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5">
            <span
              className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                isOnline ? 'bg-[#22c55e] animate-pulse' : 'bg-[#94a3b8]'
              }`}
            />
            <span
              className="text-xs font-semibold capitalize"
              style={{ color: isOnline ? '#22c55e' : '#94a3b8' }}
            >
              {status}
            </span>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        <div className="space-y-3">
          {/* Stats row: queue depth + last heartbeat */}
          <div className="grid grid-cols-2 gap-3">
            {/* Queue depth */}
            <div
              className="px-3 py-2.5 rounded-xl"
              style={{
                backgroundColor: '#f5f7fa',
                boxShadow: 'inset 3px 3px 6px rgba(174,185,201,0.3), inset -3px -3px 6px rgba(255,255,255,0.85)',
              }}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <Activity size={12} strokeWidth={2} style={{ color: '#94a3b8' }} />
                <span className="text-xs font-bold uppercase tracking-widest" style={{ color: '#94a3b8' }}>
                  Queue
                </span>
              </div>
              <span
                className="text-xl font-extrabold"
                style={{
                  color: queueDepth !== null && queueDepth > 0 ? '#f97316' : '#1e293b',
                }}
              >
                {queueDepth !== null ? queueDepth : '--'}
              </span>
            </div>

            {/* Last heartbeat */}
            <div
              className="px-3 py-2.5 rounded-xl"
              style={{
                backgroundColor: '#f5f7fa',
                boxShadow: 'inset 3px 3px 6px rgba(174,185,201,0.3), inset -3px -3px 6px rgba(255,255,255,0.85)',
              }}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-xs font-bold uppercase tracking-widest" style={{ color: '#94a3b8' }}>
                  Last Seen
                </span>
              </div>
              <span className="text-xs font-semibold" style={{ color: '#64748b' }}>
                {lastHeartbeat ? formatRelative(lastHeartbeat) : 'Never'}
              </span>
            </div>
          </div>

          {/* Agent metadata */}
          {(agent.version ?? agent.platform) && (
            <div className="flex items-center gap-3 text-xs" style={{ color: '#94a3b8' }}>
              {agent.version && <span>v{agent.version}</span>}
              {agent.version && agent.platform && (
                <span className="w-1 h-1 rounded-full bg-[#cbd5e1]" />
              )}
              {agent.platform && <span>{agent.platform}</span>}
            </div>
          )}

          {/* Live upload activity badge */}
          {activeUpload && (
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-xl transition-all duration-300"
              style={{
                backgroundColor: '#f5f7fa',
                boxShadow: '3px 3px 6px rgba(174,185,201,0.3), -3px -3px 6px rgba(255,255,255,0.8)',
                borderLeft: '3px solid #3b82f6',
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-pulse flex-shrink-0"
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold truncate" style={{ color: '#1e293b' }}>
                  {activeUpload.filename ?? activeUpload.upload_id.slice(0, 16)}
                </p>
                <p className="text-xs capitalize" style={{ color: '#64748b' }}>
                  {activeUpload.status}
                </p>
              </div>
              <UploadStatusPill status={activeUpload.status} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// UploadStatusPill — small inline badge for upload activity
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  pending:   { bg: 'rgba(148,163,184,0.15)', text: '#64748b' },
  uploading: { bg: 'rgba(59,130,246,0.12)',  text: '#3b82f6' },
  parsing:   { bg: 'rgba(249,115,22,0.12)',  text: '#f97316' },
  parsed:    { bg: 'rgba(34,197,94,0.12)',   text: '#22c55e' },
  failed:    { bg: 'rgba(239,68,68,0.12)',   text: '#ef4444' },
  queued:    { bg: 'rgba(99,102,241,0.12)',  text: '#6366f1' },
}

function UploadStatusPill({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.pending
  return (
    <span
      className="text-xs font-bold px-2 py-0.5 rounded-full flex-shrink-0 capitalize"
      style={{ backgroundColor: colors.bg, color: colors.text }}
    >
      {status}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelative(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime()
    const seconds = Math.floor(diff / 1_000)
    if (seconds < 5) return 'just now'
    if (seconds < 60) return `${seconds}s ago`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
  } catch {
    return iso
  }
}

export default AgentsPage
