/**
 * Agent hooks -- list agents and pair via code.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { queryKeys } from '@/api/hooks'

// ---------------------------------------------------------------------------
// useAgents — list connected agents (auto-refreshes every 30 s)
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
    refetchInterval: 30_000,
  })
}

// ---------------------------------------------------------------------------
// useAgentPair — POST /agents/pair to generate a pairing code
// ---------------------------------------------------------------------------

export function useAgentPair() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST('/agents/pair', {})
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
    },
  })
}

// ---------------------------------------------------------------------------
// useApprovePairingCode — POST /agents/pair/:code to approve
// ---------------------------------------------------------------------------

export function useApprovePairingCode() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      code,
      agentName,
    }: {
      code: string
      agentName: string
    }) => {
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
