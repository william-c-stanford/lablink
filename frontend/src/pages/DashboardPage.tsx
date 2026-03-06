/**
 * DashboardPage -- main overview with stats, recent uploads, agent status.
 *
 * Layout:
 *   1. Stats row: Total Uploads, Active Experiments, Connected Agents, Parse Success Rate
 *   2. Recent uploads list (last 10) with status badges
 *   3. Upload activity chart placeholder (Plotly mount point)
 *   4. Agent status panel
 */

import { useState, useEffect } from 'react'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  StatCard,
  Badge,
  Spinner,
} from '@/components/ui'
import { UploadStatusBadge } from '@/components/ui/badge'
import { useUploads } from '@/api/hooks/useUploads'
import { useExperiments } from '@/api/hooks/useExperiments'
import { useAgents } from '@/api/hooks/useAgents'
import { useSSE } from '@/lib/sse'
import { UploadActivityChart } from '@/components/charts/UploadActivityChart'
import {
  Upload,
  FlaskConical,
  Cpu,
  CheckCircle,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// SSE types
// ---------------------------------------------------------------------------

interface HeartbeatPayload {
  agent_id: string
  queue_depth?: number
  timestamp?: string
  status?: string
}

/** Per-agent live state driven by SSE, overlaid on top of polled data. */
interface AgentLiveState {
  queue_depth: number | null
  last_heartbeat_at: string | null
  status: string
}

export default function DashboardPage() {
  const uploadsQuery = useUploads({ page: 1, page_size: 10 })
  const experimentsQuery = useExperiments({ page: 1 })
  const agentsQuery = useAgents()

  // SSE: live heartbeat + queue depth updates on top of polling baseline
  const { lastEvent } = useSSE('/api/v1/sse/updates')
  const [agentLive, setAgentLive] = useState<Record<string, AgentLiveState>>({})

  useEffect(() => {
    if (!lastEvent) return

    if (lastEvent.type === 'agent.heartbeat') {
      const payload = lastEvent.data as HeartbeatPayload
      if (!payload?.agent_id) return
      setAgentLive((prev) => ({
        ...prev,
        [payload.agent_id]: {
          queue_depth:
            payload.queue_depth ??
            prev[payload.agent_id]?.queue_depth ??
            null,
          last_heartbeat_at: payload.timestamp ?? lastEvent.timestamp,
          status:
            payload.status ??
            prev[payload.agent_id]?.status ??
            'online',
        },
      }))
    }

    if (lastEvent.type === 'agent.connected') {
      const payload = lastEvent.data as HeartbeatPayload
      if (!payload?.agent_id) return
      setAgentLive((prev) => ({
        ...prev,
        [payload.agent_id]: {
          ...prev[payload.agent_id],
          status: 'online',
          last_heartbeat_at: lastEvent.timestamp,
          queue_depth: prev[payload.agent_id]?.queue_depth ?? null,
        },
      }))
    }

    if (lastEvent.type === 'agent.disconnected') {
      const payload = lastEvent.data as HeartbeatPayload
      if (!payload?.agent_id) return
      setAgentLive((prev) => ({
        ...prev,
        [payload.agent_id]: {
          ...prev[payload.agent_id],
          status: 'offline',
          last_heartbeat_at:
            prev[payload.agent_id]?.last_heartbeat_at ?? null,
          queue_depth: prev[payload.agent_id]?.queue_depth ?? null,
        },
      }))
    }
  }, [lastEvent])

  // ---------------------------------------------------------------------------
  // Derived stats
  // ---------------------------------------------------------------------------

  const uploads = extractList(uploadsQuery.data)
  const experiments = extractList(experimentsQuery.data)
  const agents = extractList(agentsQuery.data)

  const totalUploads =
    extractPagination(uploadsQuery.data)?.total_count ?? uploads.length
  const activeExperiments = experiments.filter(
    (e: Record<string, unknown>) =>
      e.status === 'active' || e.status === 'running',
  ).length
  // connectedAgents uses SSE-overlaid status when available
  const connectedAgents = agents.filter((a: Record<string, unknown>) => {
    const live = agentLive[a.id as string]
    const status = live?.status ?? (a.status as string)
    return status === 'online'
  }).length

  const parsedCount = uploads.filter(
    (u: Record<string, unknown>) => u.status === 'parsed',
  ).length
  const failedCount = uploads.filter(
    (u: Record<string, unknown>) => u.status === 'failed',
  ).length
  const parseSuccessRate =
    parsedCount + failedCount > 0
      ? Math.round((parsedCount / (parsedCount + failedCount)) * 100)
      : 100

  const isLoading =
    uploadsQuery.isLoading ||
    experimentsQuery.isLoading ||
    agentsQuery.isLoading

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Page header */}
      <div>
        <h2
          className="text-2xl font-extrabold tracking-tight"
          style={{ color: 'var(--text-dark, #1e293b)' }}
        >
          Dashboard
        </h2>
        <p
          className="text-sm mt-1"
          style={{ color: 'var(--text-muted, #64748b)' }}
        >
          Welcome back -- here's what's happening in your lab.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Uploads"
          value={isLoading ? '-' : totalUploads}
          icon={<Upload size={22} strokeWidth={2} />}
          iconColor="#3b82f6"
        />
        <StatCard
          label="Active Experiments"
          value={isLoading ? '-' : activeExperiments}
          icon={<FlaskConical size={22} strokeWidth={2} />}
          iconColor="#6366f1"
        />
        <StatCard
          label="Connected Agents"
          value={isLoading ? '-' : connectedAgents}
          icon={<Cpu size={22} strokeWidth={2} />}
          iconColor="#f97316"
        />
        <StatCard
          label="Parse Success Rate"
          value={isLoading ? '-' : `${parseSuccessRate}%`}
          icon={<CheckCircle size={22} strokeWidth={2} />}
          iconColor="#22c55e"
        />
      </div>

      {/* Two-column layout: recent uploads + agents */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent uploads */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent Uploads</CardTitle>
          </CardHeader>
          <CardContent>
            {uploadsQuery.isLoading && (
              <div className="flex justify-center py-8">
                <Spinner size="md" />
              </div>
            )}
            {uploadsQuery.isError && (
              <p className="text-sm text-[#ef4444] py-4">
                Failed to load uploads.
              </p>
            )}
            {!uploadsQuery.isLoading && uploads.length === 0 && (
              <p
                className="text-sm py-8 text-center"
                style={{ color: '#94a3b8' }}
              >
                No uploads yet. Upload your first instrument file to get
                started.
              </p>
            )}
            {uploads.length > 0 && (
              <div className="space-y-2">
                {uploads.map((upload: Record<string, unknown>) => (
                  <div
                    key={upload.id as string}
                    className="flex items-center justify-between gap-4 px-4 py-3 rounded-2xl transition-all duration-150 hover:scale-[1.005]"
                    style={{
                      backgroundColor: '#f5f7fa',
                      boxShadow:
                        '3px 3px 6px rgba(174,185,201,0.3), -3px -3px 6px rgba(255,255,255,0.8)',
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-[#1e293b] truncate">
                        {upload.filename as string}
                      </p>
                      <p className="text-xs text-[#94a3b8] mt-0.5">
                        {(upload.instrument_type as string) ?? 'Unknown'} --{' '}
                        {formatDate(upload.created_at as string)}
                      </p>
                    </div>
                    <UploadStatusBadge
                      status={
                        (upload.status as
                          | 'pending'
                          | 'uploading'
                          | 'parsing'
                          | 'parsed'
                          | 'failed'
                          | 'queued') ?? 'pending'
                      }
                      size="sm"
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Agent status panel */}
        <Card>
          <CardHeader>
            <CardTitle>Agent Status</CardTitle>
          </CardHeader>
          <CardContent>
            {agentsQuery.isLoading && (
              <div className="flex justify-center py-8">
                <Spinner size="md" />
              </div>
            )}
            {agentsQuery.isError && (
              <p className="text-sm text-[#ef4444] py-4">
                Failed to load agents.
              </p>
            )}
            {!agentsQuery.isLoading && agents.length === 0 && (
              <p
                className="text-sm py-8 text-center"
                style={{ color: '#94a3b8' }}
              >
                No agents connected. Install the desktop agent to get started.
              </p>
            )}
            {agents.length > 0 && (
              <div className="space-y-3">
                {agents.map((agent: Record<string, unknown>) => {
                  const agentId = agent.id as string
                  const live = agentLive[agentId]
                  const status = live?.status ?? (agent.status as string)
                  const isOnline = status === 'online'
                  const lastHeartbeat =
                    live?.last_heartbeat_at ??
                    (agent.last_heartbeat_at as string | undefined)
                  const queueDepth = live?.queue_depth ?? null

                  return (
                    <div
                      key={agentId}
                      className="flex items-center gap-3 px-4 py-3 rounded-2xl"
                      style={{
                        backgroundColor: '#f5f7fa',
                        boxShadow:
                          'inset 4px 4px 8px rgba(174,185,201,0.35), inset -4px -4px 8px rgba(255,255,255,0.85)',
                      }}
                    >
                      <div
                        className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                          isOnline
                            ? 'bg-[#22c55e] animate-pulse'
                            : 'bg-[#94a3b8]'
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-[#1e293b] truncate">
                          {(agent.name as string) ||
                            (agent.hostname as string) ||
                            'Agent'}
                        </p>
                        <p className="text-xs text-[#94a3b8]">
                          {lastHeartbeat
                            ? `Last seen ${formatRelative(lastHeartbeat)}`
                            : 'Never connected'}
                        </p>
                      </div>
                      {/* Queue depth badge — appears when SSE delivers data */}
                      {queueDepth !== null && (
                        <span
                          className="text-xs font-bold px-2 py-0.5 rounded-full flex-shrink-0"
                          style={{
                            backgroundColor:
                              queueDepth > 0
                                ? 'rgba(249,115,22,0.12)'
                                : 'rgba(34,197,94,0.12)',
                            color: queueDepth > 0 ? '#f97316' : '#22c55e',
                          }}
                          title="Queue depth"
                        >
                          Q:{queueDepth}
                        </span>
                      )}
                      <Badge
                        variant={isOnline ? 'success' : 'default'}
                        size="sm"
                      >
                        {status ?? 'offline'}
                      </Badge>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Upload activity chart */}
      <UploadActivityChart
        uploads={uploads as Array<{ created_at: string; status: string }>}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Safely extract the data array from an envelope response. */
function extractList(envelope: unknown): Record<string, unknown>[] {
  if (!envelope) return []
  const env = envelope as Record<string, unknown>
  const data = env.data
  if (Array.isArray(data)) return data as Record<string, unknown>[]
  return []
}

/** Safely extract pagination from an envelope response. */
function extractPagination(
  envelope: unknown,
): { total_count: number } | null {
  if (!envelope) return null
  const env = envelope as Record<string, unknown>
  const meta = env.meta as Record<string, unknown> | undefined
  return (meta?.pagination as { total_count: number }) ?? null
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

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
