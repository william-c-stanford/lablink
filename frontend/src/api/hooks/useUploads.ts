/**
 * Upload hooks -- list, get, upload file, reparse.
 *
 * Re-exports the hooks from the central hooks.ts for a clean per-domain API,
 * adding convenience wrappers where needed.
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { apiClient, uploadFile, type UploadFileOptions } from '@/api/client'
import { queryKeys, type UploadStatus } from '@/api/hooks'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UploadFilters {
  status?: UploadStatus
  project_id?: string
  page?: number
  page_size?: number
}

// ---------------------------------------------------------------------------
// useUploads — paginated list with optional filters
// ---------------------------------------------------------------------------

export function useUploads(filters?: UploadFilters) {
  return useQuery({
    queryKey: queryKeys.uploads(filters),
    queryFn: async () => {
      const { data, error } = await apiClient.GET('/uploads', {
        params: {
          query: {
            page: filters?.page ?? 1,
            page_size: filters?.page_size ?? 50,
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

// ---------------------------------------------------------------------------
// useUpload — single upload by ID
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// useUploadFile — multipart file upload mutation
// ---------------------------------------------------------------------------

export function useUploadFile() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: (options: UploadFileOptions) => uploadFile(options),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['uploads'] })
    },
  })
}

// ---------------------------------------------------------------------------
// useReparseUpload — trigger re-parsing of an upload
// ---------------------------------------------------------------------------

export function useReparseUpload() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      uploadId,
      instrumentType,
    }: {
      uploadId: string
      instrumentType?: string
    }) => {
      const { data, error } = await apiClient.POST(
        '/uploads/{upload_id}/reparse',
        {
          params: {
            path: { upload_id: uploadId },
            query: { instrument_type: instrumentType },
          },
        },
      )
      if (error) throw error
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: queryKeys.upload(vars.uploadId) })
      qc.invalidateQueries({ queryKey: ['uploads'] })
    },
  })
}
