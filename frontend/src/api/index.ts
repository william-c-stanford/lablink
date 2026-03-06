/**
 * LabLink API — barrel export
 *
 * Re-exports the typed API client and all generated schema types
 * so consumers can import from a single entry point:
 *
 *   import { apiClient, type components } from '@/api'
 */

export { apiClient, uploadFile, openSSEConnection, setAccessToken, getAccessToken, clearAccessToken, unwrapResponse } from './client'
export type { ApiResponse, UploadFileOptions, SSEOptions } from './client'

// Generated schema types (from openapi-typescript)
export type { paths, components, operations, webhooks } from './schema'
