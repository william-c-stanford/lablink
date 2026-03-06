/**
 * TanStack Query hooks for all LabLink API endpoints.
 *
 * Each hook maps to one or more API operations and handles:
 * - Typed request parameters (from generated schema)
 * - Proper cache key structuring
 * - Cache invalidation patterns
 * - Optimistic updates where appropriate
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { apiClient, uploadFile, type UploadFileOptions } from './client'
import type { components } from './schema'

// ---------------------------------------------------------------------------
// Convenience type aliases from generated schemas
// ---------------------------------------------------------------------------

export type UploadResponse = components['schemas']['UploadResponse']
export type UploadStatus = UploadResponse['status']

export type ExperimentResponse = components['schemas']['ExperimentResponse']
export type ExperimentStatus = ExperimentResponse['status']

export type InstrumentResponse = components['schemas']['InstrumentResponse']
export type InstrumentType = InstrumentResponse['instrument_type']

export type AgentResponse = components['schemas']['AgentResponse']
export type AgentStatus = AgentResponse['status']

export type CampaignResponse = components['schemas']['CampaignResponse']
export type ParsedDataResponse = components['schemas']['ParsedDataResponse']
export type OrganizationResponse = components['schemas']['OrganizationResponse']
export type ProjectResponse = components['schemas']['ProjectResponse']
export type AuditEventResponse = components['schemas']['AuditEventResponse']
export type WebhookResponse = components['schemas']['WebhookResponse']
export type ApiTokenResponse = components['schemas']['ApiTokenResponse']

export type TokenResponse = components['schemas']['TokenResponse']
export type UserResponse = components['schemas']['UserResponse']

export type ExperimentCreate = components['schemas']['ExperimentCreate']
export type ExperimentUpdate = components['schemas']['ExperimentUpdate']
export type CampaignCreate = components['schemas']['CampaignCreate']
export type InstrumentCreate = components['schemas']['InstrumentCreate']
export type InstrumentUpdate = components['schemas']['InstrumentUpdate']
export type AgentCreate = components['schemas']['AgentCreate']
export type HeartbeatRequest = components['schemas']['HeartbeatRequest']
export type WebhookCreate = components['schemas']['WebhookCreate']
export type ProjectCreate = components['schemas']['ProjectCreate']
export type ProjectUpdate = components['schemas']['ProjectUpdate']
export type SearchRequest = components['schemas']['SearchRequest']
export type ExportCreateRequest = components['schemas']['ExportCreateRequest']
export type OutcomeRequest = components['schemas']['OutcomeRequest']
export type LinkUploadRequest = components['schemas']['LinkUploadRequest']

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const queryKeys = {
  health: ['health'] as const,

  // Auth
  apiTokens: (page?: number) => ['auth', 'api-tokens', page] as const,

  // Organizations
  organizations: (page?: number) => ['organizations', page] as const,
  organization: (id: string) => ['organizations', id] as const,

  // Projects
  projects: (page?: number) => ['projects', page] as const,
  project: (id: string) => ['projects', id] as const,

  // Instruments
  instruments: (filters?: { instrument_type?: string; page?: number }) =>
    ['instruments', filters] as const,
  instrument: (id: string) => ['instruments', id] as const,

  // Agents
  agents: (page?: number) => ['agents', page] as const,
  agent: (id: string) => ['agents', id] as const,

  // Uploads
  uploads: (filters?: { status?: UploadStatus; project_id?: string; page?: number }) =>
    ['uploads', filters] as const,
  upload: (id: string) => ['uploads', id] as const,

  // Data
  parsedData: (uploadId: string) => ['data', uploadId] as const,
  chartData: (uploadId: string) => ['data', uploadId, 'chart'] as const,
  search: (params: SearchRequest) => ['search', params] as const,

  // Experiments
  experiments: (filters?: { status?: ExperimentStatus; campaign_id?: string; page?: number }) =>
    ['experiments', filters] as const,
  experiment: (id: string) => ['experiments', id] as const,

  // Campaigns
  campaigns: (page?: number) => ['campaigns', page] as const,
  campaign: (id: string) => ['campaigns', id] as const,
  campaignProgress: (id: string) => ['campaigns', id, 'progress'] as const,

  // Webhooks
  webhooks: (page?: number) => ['webhooks', page] as const,
  webhook: (id: string) => ['webhooks', id] as const,

  // Audit
  auditEvents: (filters?: { entity_type?: string; entity_id?: string; page?: number }) =>
    ['audit', filters] as const,

  // Admin
  usageStats: ['admin', 'stats'] as const,
} as const

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/health')
      if (error) throw error
      return data
    },
    staleTime: 60_000,
  })
}

// ---------------------------------------------------------------------------
// Auth — API tokens
// ---------------------------------------------------------------------------

export function useApiTokens(page = 1) {
  return useQuery({
    queryKey: queryKeys.apiTokens(page),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/auth/api-tokens', {
        params: { query: { page, page_size: 20 } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCreateApiToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['ApiTokenCreate']) => {
      const { data, error } = await apiClient.POST('/auth/api-tokens', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auth', 'api-tokens'] })
    },
  })
}

export function useRevokeApiToken() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tokenId: string) => {
      const { data, error } = await apiClient.DELETE('/auth/api-tokens/{token_id}', {
        params: { path: { token_id: tokenId } },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auth', 'api-tokens'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Organizations
// ---------------------------------------------------------------------------

export function useOrganizations(page = 1) {
  return useQuery({
    queryKey: queryKeys.organizations(page),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/organizations', {
        params: { query: { page, page_size: 50 } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useOrganization(id: string) {
  return useQuery({
    queryKey: queryKeys.organization(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/organizations/{org_id}', {
        params: { path: { org_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export function useProjects(page = 1) {
  return useQuery({
    queryKey: queryKeys.projects(page),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/projects', {
        params: { query: { page, page_size: 50 } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useProject(id: string) {
  return useQuery({
    queryKey: queryKeys.project(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/projects/{project_id}', {
        params: { path: { project_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ProjectCreate) => {
      const { data, error } = await apiClient.POST('/projects', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useUpdateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...body }: ProjectUpdate & { id: string }) => {
      const { data, error } = await apiClient.PATCH('/projects/{project_id}', {
        params: { path: { project_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: queryKeys.project(vars.id) })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await apiClient.DELETE('/projects/{project_id}', {
        params: { path: { project_id: id } },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Instruments
// ---------------------------------------------------------------------------

export function useInstruments(filters?: { instrument_type?: string; page?: number }) {
  return useQuery({
    queryKey: queryKeys.instruments(filters),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/instruments', {
        params: {
          query: {
            page: filters?.page ?? 1,
            page_size: 50,
            instrument_type: filters?.instrument_type,
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}

export function useInstrument(id: string) {
  return useQuery({
    queryKey: queryKeys.instrument(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/instruments/{instrument_id}', {
        params: { path: { instrument_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

export function useCreateInstrument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: InstrumentCreate) => {
      const { data, error } = await apiClient.POST('/instruments', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['instruments'] })
    },
  })
}

export function useUpdateInstrument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...body }: InstrumentUpdate & { id: string }) => {
      const { data, error } = await apiClient.PATCH('/instruments/{instrument_id}', {
        params: { path: { instrument_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['instruments'] })
      qc.invalidateQueries({ queryKey: queryKeys.instrument(vars.id) })
    },
  })
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export function useAgents(page = 1) {
  return useQuery({
    queryKey: queryKeys.agents(page),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/agents', {
        params: { query: { page, page_size: 50 } },
      })
      if (error) throw error
      return data
    },
    refetchInterval: 30_000, // Refresh every 30s for live status
  })
}

export function useAgent(id: string) {
  return useQuery({
    queryKey: queryKeys.agent(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/agents/{agent_id}', {
        params: { path: { agent_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

export function useRegisterAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: AgentCreate) => {
      const { data, error } = await apiClient.POST('/agents', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}

export function useGeneratePairingCode() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST('/agents/pair', {})
      if (error) throw error
      return data
    },
  })
}

export function useApprovePairingCode() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ code, agentName }: { code: string; agentName: string }) => {
      const { data, error } = await apiClient.POST('/agents/pair/{code}', {
        params: { path: { code } },
        body: { name: agentName },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}

export function useRecordHeartbeat() {
  return useMutation({
    mutationFn: async ({ agentId, ...body }: HeartbeatRequest & { agentId: string }) => {
      const { data, error } = await apiClient.POST('/agents/{agent_id}/heartbeat', {
        params: { path: { agent_id: agentId } },
        body,
      })
      if (error) throw error
      return data
    },
  })
}

// ---------------------------------------------------------------------------
// Uploads
// ---------------------------------------------------------------------------

export function useUploads(filters?: { status?: UploadStatus; project_id?: string; page?: number }) {
  return useQuery({
    queryKey: queryKeys.uploads(filters),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/uploads', {
        params: {
          query: {
            page: filters?.page ?? 1,
            page_size: 50,
            status: filters?.status,
            project_id: filters?.project_id,
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}

export function useUpload(id: string) {
  return useQuery({
    queryKey: queryKeys.upload(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/uploads/{upload_id}', {
        params: { path: { upload_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

export function useUploadFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (options: UploadFileOptions) => uploadFile(options),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['uploads'] })
    },
  })
}

export function useReparseUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ uploadId, instrumentType }: { uploadId: string; instrumentType?: string }) => {
      const { data, error } = await apiClient.POST('/uploads/{upload_id}/reparse', {
        params: {
          path: { upload_id: uploadId },
          query: { instrument_type: instrumentType },
        },
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.upload(vars.uploadId) })
      qc.invalidateQueries({ queryKey: ['uploads'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Parsed Data & Charts
// ---------------------------------------------------------------------------

export function useParsedData(uploadId: string) {
  return useQuery({
    queryKey: queryKeys.parsedData(uploadId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/data/{upload_id}', {
        params: { path: { upload_id: uploadId } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(uploadId),
  })
}

export function useChartData(uploadId: string) {
  return useQuery({
    queryKey: queryKeys.chartData(uploadId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/data/{upload_id}/chart', {
        params: { path: { upload_id: uploadId } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(uploadId),
  })
}

export function useSearch(params: SearchRequest, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.search(params),
    queryFn: async () => {
      const { data, error } = await apiClient.POST('/search', { body: params })
      if (error) throw error
      return data
    },
    enabled: options?.enabled ?? true,
    staleTime: 30_000,
  })
}

export function useCreateExport() {
  return useMutation({
    mutationFn: async (body: ExportCreateRequest) => {
      const { data, error } = await apiClient.POST('/exports', { body })
      if (error) throw error
      return data
    },
  })
}

// ---------------------------------------------------------------------------
// Experiments
// ---------------------------------------------------------------------------

export function useExperiments(filters?: {
  status?: ExperimentStatus
  campaign_id?: string
  page?: number
}) {
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

export function useExperiment(id: string) {
  return useQuery({
    queryKey: queryKeys.experiment(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/experiments/{experiment_id}', {
        params: { path: { experiment_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

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

export function useUpdateExperiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...body }: ExperimentUpdate & { id: string }) => {
      const { data, error } = await apiClient.PATCH('/experiments/{experiment_id}', {
        params: { path: { experiment_id: id } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['experiments'] })
      qc.invalidateQueries({ queryKey: queryKeys.experiment(vars.id) })
    },
  })
}

export function useRecordOutcome() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ experimentId, ...body }: OutcomeRequest & { experimentId: string }) => {
      const { data, error } = await apiClient.POST('/experiments/{experiment_id}/outcome', {
        params: { path: { experiment_id: experimentId } },
        body,
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.experiment(vars.experimentId) })
      qc.invalidateQueries({ queryKey: ['experiments'] })
    },
  })
}

export function useLinkUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ experimentId, uploadId }: { experimentId: string; uploadId: string }) => {
      const { data, error } = await apiClient.POST('/experiments/{experiment_id}/link-upload', {
        params: { path: { experiment_id: experimentId } },
        body: { upload_id: uploadId },
      })
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.experiment(vars.experimentId) })
    },
  })
}

export function useUnlinkUpload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ experimentId, uploadId }: { experimentId: string; uploadId: string }) => {
      const { data, error } = await apiClient.DELETE(
        '/experiments/{experiment_id}/link-upload/{upload_id}',
        {
          params: { path: { experiment_id: experimentId, upload_id: uploadId } },
        }
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.experiment(vars.experimentId) })
    },
  })
}

// ---------------------------------------------------------------------------
// Campaigns
// ---------------------------------------------------------------------------

export function useCampaigns(page = 1) {
  return useQuery({
    queryKey: queryKeys.campaigns(page),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/campaigns', {
        params: { query: { page, page_size: 50 } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCampaign(id: string) {
  return useQuery({
    queryKey: queryKeys.campaign(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/campaigns/{campaign_id}', {
        params: { path: { campaign_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
  })
}

export function useCampaignProgress(id: string) {
  return useQuery({
    queryKey: queryKeys.campaignProgress(id),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/campaigns/{campaign_id}/progress', {
        params: { path: { campaign_id: id } },
      })
      if (error) throw error
      return data
    },
    enabled: Boolean(id),
    refetchInterval: 60_000,
  })
}

export function useCreateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CampaignCreate) => {
      const { data, error } = await apiClient.POST('/campaigns', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Webhooks
// ---------------------------------------------------------------------------

export function useWebhooks(page = 1) {
  return useQuery({
    queryKey: queryKeys.webhooks(page),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/webhooks', {
        params: { query: { page, page_size: 50 } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCreateWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: WebhookCreate) => {
      const { data, error } = await apiClient.POST('/webhooks', { body })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })
}

export function useDeleteWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { data, error } = await apiClient.DELETE('/webhooks/{webhook_id}', {
        params: { path: { webhook_id: id } },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks'] })
    },
  })
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export function useAuditEvents(filters?: {
  entity_type?: string
  entity_id?: string
  page?: number
}) {
  return useQuery({
    queryKey: queryKeys.auditEvents(filters),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/audit', {
        params: {
          query: {
            page: filters?.page ?? 1,
            page_size: 50,
            entity_type: filters?.entity_type,
            entity_id: filters?.entity_id,
          },
        },
      })
      if (error) throw error
      return data
    },
  })
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export function useUsageStats() {
  return useQuery({
    queryKey: queryKeys.usageStats,
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/admin/stats')
      if (error) throw error
      return data
    },
    staleTime: 300_000, // 5 min
  })
}
