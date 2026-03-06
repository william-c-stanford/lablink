/**
 * Auth hooks -- login, register, logout, current user.
 *
 * Wraps the openapi-fetch apiClient and syncs token state with both
 * lib/auth.ts (in-memory token) and the Zustand AuthStore.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient, setAccessToken } from '@/api/client'
import { setToken, clearToken, getToken } from '@/lib/auth'
import { useAuthStore } from '@/store/authStore'
import type { components } from '@/api/schema'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type UserResponse = components['schemas']['UserResponse']
export type TokenResponse = components['schemas']['TokenResponse']

interface LoginPayload {
  email: string
  password: string
}

interface RegisterPayload {
  email: string
  password: string
  displayName: string
  orgName: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Store tokens in both lib/auth (fetch helper) and api/client (openapi-fetch). */
function persistTokens(
  tokenData: { access_token: string; refresh_token?: string },
  userData: UserResponse,
) {
  setToken(tokenData.access_token, tokenData.refresh_token)
  setAccessToken(tokenData.access_token)

  useAuthStore.getState().setAuth(tokenData.access_token, {
    id: userData.id,
    email: userData.email,
    name: userData.full_name ?? userData.email,
    role:
      (userData as Record<string, unknown>).role as
        | 'admin'
        | 'scientist'
        | 'viewer' ?? 'scientist',
    labId:
      ((userData as Record<string, unknown>).organization_id as string) ?? '',
  })
}

// ---------------------------------------------------------------------------
// useLogin
// ---------------------------------------------------------------------------

export function useLogin() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({ email, password }: LoginPayload) => {
      const { data, error } = await apiClient.POST('/auth/login', {
        body: { email, password },
      })
      if (error) throw error
      return data
    },
    onSuccess: (envelope) => {
      const payload = (envelope as Record<string, unknown>).data as {
        user: UserResponse
        token: {
          access_token: string
          refresh_token: string
          token_type: string
          expires_in: number
        }
      }
      persistTokens(payload.token, payload.user)
      qc.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })
}

// ---------------------------------------------------------------------------
// useRegister
// ---------------------------------------------------------------------------

export function useRegister() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      email,
      password,
      displayName,
      orgName,
    }: RegisterPayload) => {
      const { data, error } = await apiClient.POST('/auth/register', {
        body: {
          email,
          password,
          full_name: displayName,
          org_name: orgName,
        },
      })
      if (error) throw error
      return data
    },
    onSuccess: (envelope) => {
      const payload = (envelope as Record<string, unknown>).data as {
        user: UserResponse
        token: {
          access_token: string
          refresh_token: string
          token_type: string
          expires_in: number
        }
      }
      persistTokens(payload.token, payload.user)
      qc.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })
}

// ---------------------------------------------------------------------------
// useCurrentUser
// ---------------------------------------------------------------------------

export function useCurrentUser() {
  const accessToken = useAuthStore((s) => s.accessToken)

  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const { data, error } = await apiClient.POST('/auth/refresh', {})
      if (error) throw error
      return data
    },
    enabled: Boolean(accessToken),
    staleTime: 5 * 60_000,
    retry: false,
  })
}

// ---------------------------------------------------------------------------
// useLogout
// ---------------------------------------------------------------------------

export function useLogout() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      clearToken()
      setAccessToken(null)
      useAuthStore.getState().clearAuth()
    },
    onSuccess: () => {
      qc.clear()
    },
  })
}
