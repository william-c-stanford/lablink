/**
 * ExperimentsPage -- experiment list, create modal, state transitions.
 *
 * Neuromorphic design:
 *   - nm-glow-blue "Create Experiment" button
 *   - nm-outset experiment cards with status badges
 *   - Expandable rows showing linked uploads + transition buttons
 *   - Create experiment modal (Dialog component)
 */

import { useState } from 'react'
import {
  Card,
  CardContent,
  Button,
  Input,
  InputGroup,
  Spinner,
  Badge,
} from '@/components/ui'
import { Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ExperimentStatusBadge } from '@/components/ui/badge'
import type { ExperimentStatus } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogBody,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import {
  useExperiments,
  useCreateExperiment,
  useTransitionExperiment,
} from '@/api/hooks/useExperiments'
import { FlaskConical, ChevronDown, ChevronUp } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExperimentRecord {
  id: string
  intent?: string
  name?: string
  hypothesis?: string
  description?: string
  status: ExperimentStatus
  linked_uploads?: Array<{ id: string; filename: string }>
  upload_count?: number
  created_at: string
  updated_at?: string
}

// ---------------------------------------------------------------------------
// State machine transitions
// ---------------------------------------------------------------------------

const TRANSITIONS: Record<string, { label: string; target: string }[]> = {
  draft: [{ label: 'Start', target: 'active' }],
  active: [
    { label: 'Complete', target: 'completed' },
    { label: 'Cancel', target: 'cancelled' },
  ],
  completed: [],
  cancelled: [],
  archived: [],
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ExperimentsPage() {
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Create form state
  const [newIntent, setNewIntent] = useState('')
  const [newHypothesis, setNewHypothesis] = useState('')
  const [newDescription, setNewDescription] = useState('')

  // API hooks
  const experimentsQuery = useExperiments({ page: 1 })
  const createExperiment = useCreateExperiment()
  const transitionExperiment = useTransitionExperiment()

  // Envelope extraction
  const envelope = experimentsQuery.data as Record<string, unknown> | undefined
  const experiments = (
    Array.isArray(envelope?.data) ? envelope!.data : []
  ) as ExperimentRecord[]

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleCreate() {
    if (!newIntent.trim()) return
    createExperiment.mutate(
      {
        intent: newIntent,
        hypothesis: newHypothesis || undefined,
        parameters: newDescription ? { description: newDescription } : undefined,
      } as Record<string, unknown>,
      {
        onSuccess: () => {
          setIsCreateOpen(false)
          setNewIntent('')
          setNewHypothesis('')
          setNewDescription('')
        },
      },
    )
  }

  function handleTransition(id: string, targetStatus: string) {
    transitionExperiment.mutate({
      id,
      status: targetStatus as ExperimentStatus,
    })
  }

  return (
    <div className="space-y-6" data-testid="experiments-page">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2
            className="text-2xl font-extrabold tracking-tight"
            style={{ color: '#1e293b' }}
          >
            Experiments
          </h2>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>
            Plan, run, and track your experiments.
          </p>
        </div>

        <Button
          variant="primary"
          size="md"
          onClick={() => setIsCreateOpen(true)}
          leftIcon={<FlaskConical size={16} strokeWidth={2} />}
          data-testid="create-experiment-btn"
        >
          Create Experiment
        </Button>
      </div>

      {/* Transition error */}
      {transitionExperiment.isError && (
        <div
          className="rounded-2xl px-5 py-3 text-sm font-medium"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow:
              'inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)',
            color: '#ef4444',
          }}
        >
          {transitionExperiment.error instanceof Error
            ? transitionExperiment.error.message
            : 'Transition failed'}
        </div>
      )}

      {/* Loading */}
      {experimentsQuery.isLoading && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      )}

      {/* Error */}
      {experimentsQuery.isError && (
        <div
          className="rounded-2xl px-5 py-4 text-sm font-medium text-center"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow:
              'inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)',
            color: '#ef4444',
          }}
        >
          Failed to load experiments. Please try again.
        </div>
      )}

      {/* Empty state */}
      {!experimentsQuery.isLoading && experiments.length === 0 && (
        <div className="text-center py-16">
          <div
            className="w-16 h-16 rounded-3xl flex items-center justify-center mx-auto mb-4"
            style={{
              backgroundColor: '#f5f7fa',
              boxShadow:
                'inset 6px 6px 12px rgba(174,185,201,0.4), inset -6px -6px 12px rgba(255,255,255,0.9)',
              color: '#94a3b8',
            }}
          >
            <FlaskConical size={28} strokeWidth={1.5} />
          </div>
          <p className="text-sm font-semibold" style={{ color: '#64748b' }}>
            No experiments yet
          </p>
          <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>
            Create your first experiment to start tracking results.
          </p>
        </div>
      )}

      {/* Experiment list */}
      {experiments.length > 0 && (
        <div className="space-y-3" data-testid="experiment-list">
          {/* Table header */}
          <div className="grid grid-cols-12 gap-4 px-5 py-2 text-xs font-bold uppercase tracking-widest text-[#94a3b8]">
            <span className="col-span-4">Name</span>
            <span className="col-span-2">Status</span>
            <span className="col-span-2">Uploads</span>
            <span className="col-span-2">Created</span>
            <span className="col-span-2 text-right">Actions</span>
          </div>

          {experiments.map((exp) => {
            const isExpanded = expandedId === exp.id
            const transitions = TRANSITIONS[exp.status] ?? []

            return (
              <div key={exp.id}>
                {/* Main row */}
                <div
                  className="grid grid-cols-12 gap-4 items-center px-5 py-3.5 rounded-2xl transition-all duration-150 cursor-pointer"
                  style={{
                    backgroundColor: '#f5f7fa',
                    boxShadow: isExpanded
                      ? 'inset 4px 4px 8px rgba(174,185,201,0.35), inset -4px -4px 8px rgba(255,255,255,0.85)'
                      : '4px 4px 8px rgba(174,185,201,0.3), -4px -4px 8px rgba(255,255,255,0.8)',
                  }}
                  onClick={() =>
                    setExpandedId(isExpanded ? null : exp.id)
                  }
                >
                  <div className="col-span-4 flex items-center gap-2 min-w-0">
                    {isExpanded ? (
                      <ChevronUp
                        size={16}
                        className="flex-shrink-0 text-[#94a3b8]"
                      />
                    ) : (
                      <ChevronDown
                        size={16}
                        className="flex-shrink-0 text-[#94a3b8]"
                      />
                    )}
                    <span className="text-sm font-semibold text-[#1e293b] truncate">
                      {exp.intent ?? exp.name ?? 'Untitled'}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <ExperimentStatusBadge
                      status={exp.status}
                      size="sm"
                    />
                  </div>
                  <span className="col-span-2 text-xs text-[#94a3b8]">
                    {exp.upload_count ?? exp.linked_uploads?.length ?? 0}{' '}
                    linked
                  </span>
                  <span className="col-span-2 text-xs text-[#94a3b8]">
                    {formatDate(exp.created_at)}
                  </span>
                  <div className="col-span-2 flex justify-end gap-2">
                    {transitions.map((t) => (
                      <Button
                        key={t.target}
                        variant={
                          t.target === 'cancelled' ? 'ghost' : 'primary'
                        }
                        size="xs"
                        loading={
                          transitionExperiment.isPending &&
                          transitionExperiment.variables?.id === exp.id
                        }
                        onClick={(e) => {
                          e.stopPropagation()
                          handleTransition(exp.id, t.target)
                        }}
                      >
                        {t.label}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                  <div
                    className="mt-1 px-8 py-5 rounded-2xl"
                    style={{
                      backgroundColor: '#f5f7fa',
                      boxShadow:
                        'inset 4px 4px 8px rgba(174,185,201,0.3), inset -4px -4px 8px rgba(255,255,255,0.8)',
                    }}
                  >
                    {exp.hypothesis && (
                      <div className="mb-3">
                        <span className="text-xs font-bold uppercase tracking-widest text-[#94a3b8]">
                          Hypothesis
                        </span>
                        <p className="text-sm text-[#1e293b] mt-1">
                          {exp.hypothesis}
                        </p>
                      </div>
                    )}

                    {exp.description && (
                      <div className="mb-3">
                        <span className="text-xs font-bold uppercase tracking-widest text-[#94a3b8]">
                          Description
                        </span>
                        <p className="text-sm text-[#1e293b] mt-1">
                          {exp.description}
                        </p>
                      </div>
                    )}

                    <div>
                      <span className="text-xs font-bold uppercase tracking-widest text-[#94a3b8]">
                        Linked Uploads
                      </span>
                      {exp.linked_uploads && exp.linked_uploads.length > 0 ? (
                        <div className="mt-2 space-y-1.5">
                          {exp.linked_uploads.map((u) => (
                            <div
                              key={u.id}
                              className="flex items-center gap-2 px-3 py-2 rounded-xl"
                              style={{
                                backgroundColor: '#f5f7fa',
                                boxShadow:
                                  '2px 2px 4px rgba(174,185,201,0.3), -2px -2px 4px rgba(255,255,255,0.8)',
                              }}
                            >
                              <span className="text-sm text-[#1e293b] font-medium truncate">
                                {u.filename}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-[#94a3b8] mt-1">
                          No uploads linked to this experiment.
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Create experiment modal */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent maxWidth="max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Experiment</DialogTitle>
            <DialogDescription>
              Define a new experiment to track results and link uploads.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <div className="space-y-5">
              <InputGroup
                label="Name / Intent"
                htmlFor="exp-intent"
                required
              >
                <Input
                  id="exp-intent"
                  placeholder="e.g. DNA Quantification Batch #43"
                  value={newIntent}
                  onChange={(e) => setNewIntent(e.target.value)}
                  required
                />
              </InputGroup>

              <InputGroup label="Hypothesis" htmlFor="exp-hypothesis">
                <Textarea
                  id="exp-hypothesis"
                  placeholder="What do you expect to find?"
                  value={newHypothesis}
                  onChange={(e) => setNewHypothesis(e.target.value)}
                />
              </InputGroup>

              <InputGroup label="Description" htmlFor="exp-desc">
                <Textarea
                  id="exp-desc"
                  placeholder="Additional context or parameters..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                />
              </InputGroup>
            </div>
          </DialogBody>
          <DialogFooter>
            <DialogClose>
              <Button variant="secondary" size="md">
                Cancel
              </Button>
            </DialogClose>
            <Button
              variant="primary"
              size="md"
              onClick={handleCreate}
              loading={createExperiment.isPending}
              disabled={!newIntent.trim()}
              data-testid="create-experiment-submit"
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}
