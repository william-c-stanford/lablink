/**
 * LabLink API Client
 *
 * Type-safe API client built on openapi-fetch using types auto-generated
 * from the backend OpenAPI spec (openapi.json → src/api/schema.d.ts).
 *
 * Usage:
 *   import { apiClient } from '@/api/client'
 *   const { data, error } = await apiClient.GET('/experiments')
 */

import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'

// ---------------------------------------------------------------------------
// Token management (in-memory, never stored in localStorage for security)
// ---------------------------------------------------------------------------

let accessToken: string | null = null

/** Set the JWT access token (called after login/refresh). */
export function setAccessToken(token: string | null): void {
  accessToken = token
}

/** Get the current access token (for SSE connections, etc.). */
export function getAccessToken(): string | null {
  return accessToken
}

/** Clear the token (logout). */
export function clearAccessToken(): void {
  accessToken = null
}

// ---------------------------------------------------------------------------
// Auth middleware — injects Bearer token and handles 401 auto-refresh
// ---------------------------------------------------------------------------

/** Pending refresh promise to avoid concurrent refresh requests. */
let refreshPromise: Promise<void> | null = null

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (accessToken) {
      request.headers.set('Authorization', `Bearer ${accessToken}`)
    }
    return request
  },

  async onResponse({ response, request }) {
    // Auto-refresh on 401 Unauthorized
    if (response.status === 401 && accessToken) {
      // Deduplicate concurrent 401 responses
      if (!refreshPromise) {
        refreshPromise = refreshToken().finally(() => {
          refreshPromise = null
        })
      }

      try {
        await refreshPromise
        // Retry the original request with the new token
        if (accessToken) {
          request.headers.set('Authorization', `Bearer ${accessToken}`)
        }
        return fetch(request)
      } catch {
        // Refresh failed — clear token and let caller handle 401
        clearAccessToken()
      }
    }
    return response
  },
}

// ---------------------------------------------------------------------------
// Base client configuration
// ---------------------------------------------------------------------------

export const apiClient = createClient<paths>({
  // Backend routes are mounted under /api/v1.
  // In dev, Vite proxies /api/* to http://localhost:8000.
  baseUrl: '/api/v1',
})

apiClient.use(authMiddleware)

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

/** Refresh the access token via POST /auth/refresh. */
async function refreshToken(): Promise<void> {
  const { data, error } = await apiClient.POST('/auth/refresh', {})
  if (error || !data?.data) {
    throw new Error('Token refresh failed')
  }
  const token = data.data as { access_token: string }
  setAccessToken(token.access_token)
}

// ---------------------------------------------------------------------------
// Typed response helpers
// ---------------------------------------------------------------------------

export type ApiResponse<T> = {
  data: T | null
  meta: {
    request_id: string
    timestamp: string
    pagination?: {
      total_count: number
      page: number
      page_size: number
      has_more: boolean
    } | null
  }
  errors: Array<{
    code: string
    message: string
    field?: string | null
    suggestion?: string | null
    retry?: boolean
    retry_after?: number | null
  }>
}

/** Extract the data payload from an Envelope response, throwing on errors. */
export function unwrapResponse<T>(envelope: ApiResponse<T>): T {
  if (envelope.errors && envelope.errors.length > 0) {
    const err = envelope.errors[0]
    const msg = err.suggestion ? `${err.message} — ${err.suggestion}` : err.message
    throw new Error(`[${err.code}] ${msg}`)
  }
  if (envelope.data === null || envelope.data === undefined) {
    throw new Error('Empty response data')
  }
  return envelope.data
}

// ---------------------------------------------------------------------------
// Upload helper (multipart/form-data)
// ---------------------------------------------------------------------------

export interface UploadFileOptions {
  file: File
  projectId?: string
  instrumentId?: string
  allowDuplicate?: boolean
}

/**
 * Upload an instrument data file with optional project/instrument association.
 * Uses the native fetch API for multipart uploads since openapi-fetch
 * does not yet support form-data bodies with type safety.
 */
export async function uploadFile(options: UploadFileOptions) {
  const { file, projectId, instrumentId, allowDuplicate = false } = options

  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams()
  if (projectId) params.set('project_id', projectId)
  if (instrumentId) params.set('instrument_id', instrumentId)
  if (allowDuplicate) params.set('allow_duplicate', 'true')

  const url = `/api/v1/uploads${params.toString() ? `?${params}` : ''}`

  const response = await fetch(url, {
    method: 'POST',
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    body: formData,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData?.errors?.[0]?.message ?? `Upload failed: ${response.status}`)
  }

  return response.json()
}

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export interface SSEOptions {
  onMessage: (event: MessageEvent) => void
  onError?: (event: Event) => void
  onOpen?: (event: Event) => void
}

/**
 * Open a Server-Sent Events connection to the real-time updates endpoint.
 * Returns the EventSource so the caller can close it on unmount.
 */
export function openSSEConnection(options: SSEOptions): EventSource {
  const url = `/api/v1/sse/updates${accessToken ? `?token=${encodeURIComponent(accessToken)}` : ''}`
  const source = new EventSource(url)

  source.onmessage = options.onMessage
  source.onerror = options.onError ?? null
  source.onopen = options.onOpen ?? null

  return source
}
