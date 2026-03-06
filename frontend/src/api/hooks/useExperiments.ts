/**
 * Experiment hooks -- CRUD, state transitions, upload linking.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import {
  queryKeys,
  type ExperimentCreate,
  type ExperimentUpdate,
  type ExperimentStatus,
  type OutcomeRequest,
} from '@/api/hooks'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ExperimentFilters {
  status?: ExperimentStatus
  campaign_id?: string
  page?: number
}

// ---------------------------------------------------------------------------
// useExperiments — paginated list
// ---------------------------------------------------------------------------

export function useExperiments(filters?: ExperimentFilters) {
  return useQuery({
    queryKey: queryKeys.experiments(filters),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/experiments', {
        params: {
          query: {
            page: filters?.page ?? 1,
            page_size: 50,
            status: filters?.status,
            campaign_id: filters?.campaign_id,
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}

// ---------------------------------------------------------------------------
// useExperiment — single by ID
// ---------------------------------------------------------------------------

export function useExperiment(id: string) {
  return useQuery({
    queryKey: queryKeys.experiment(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        '/experiments/{experiment_id}',
        {
          params: { path: { experiment_id: id } },
        },
      )
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

// ---------------------------------------------------------------------------
// useCreateExperiment
// ---------------------------------------------------------------------------

export function useCreateExperiment() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async (body: ExperimentCreate) => {
      const { data, error } = await apiClient.POST('/experiments', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
}

// ---------------------------------------------------------------------------
// useUpdateExperiment
// ---------------------------------------------------------------------------

export function useUpdateExperiment() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({ id, ...body }: ExperimentUpdate & { id: string }) => {
      const { data, error } = await apiClient.PATCH(
        '/experiments/{experiment_id}',
        {
          params: { path: { experiment_id: id } },
          body,
        },
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['experiments'] })
      qc.invalidateQueries({ queryKey: queryKeys.experiment(vars.id) })
    },
  })
}

// ---------------------------------------------------------------------------
// useTransitionExperiment — status state machine transition via PATCH
// ---------------------------------------------------------------------------

export function useTransitionExperiment() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      id,
      status,
    }: {
      id: string
      status: ExperimentStatus
    }) => {
      const { data, error } = await apiClient.PATCH(
        '/experiments/{experiment_id}',
        {
          params: { path: { experiment_id: id } },
          body: { status },
        },
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['experiments'] })
      qc.invalidateQueries({ queryKey: queryKeys.experiment(vars.id) })
    },
  })
}

// ---------------------------------------------------------------------------
// useLinkUpload — associate an upload with an experiment
// ---------------------------------------------------------------------------

export function useLinkUpload() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      experimentId,
      uploadId,
    }: {
      experimentId: string
      uploadId: string
    }) => {
      const { data, error } = await apiClient.POST(
        '/experiments/{experiment_id}/link-upload',
        {
          params: { path: { experiment_id: experimentId } },
          body: { upload_id: uploadId },
        },
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({
        queryKey: queryKeys.experiment(vars.experimentId),
      })
    },
  })
}

// ---------------------------------------------------------------------------
// useRecordOutcome
// ---------------------------------------------------------------------------

export function useRecordOutcome() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      experimentId,
      ...body
    }: OutcomeRequest & { experimentId: string }) => {
      const { data, error } = await apiClient.POST(
        '/experiments/{experiment_id}/outcome',
        {
          params: { path: { experiment_id: experimentId } },
          body,
        },
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({
        queryKey: queryKeys.experiment(vars.experimentId),
      })
      qc.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
}
