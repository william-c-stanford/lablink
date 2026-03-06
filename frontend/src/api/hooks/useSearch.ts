/**
 * Search hooks -- full-text search with debounced input.
 */

import { useQuery } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { apiClient } from '@/api/client'
import { queryKeys, type SearchRequest } from '@/api/hooks'

// ---------------------------------------------------------------------------
// useDebounce — generic debounce helper
// ---------------------------------------------------------------------------

export function useDebounce<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}

// ---------------------------------------------------------------------------
// useSearch — POST /search with debounced query string
// ---------------------------------------------------------------------------

export function useSearch(
  params: SearchRequest,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.search(params),
    queryFn: async () => {
      const { data, error } = await apiClient.POST('/search', { body: params })
      if (error) throw error
      return data
    },
    enabled: options?.enabled ?? Boolean(params.query),
    staleTime: 30_000,
  })
}

// ---------------------------------------------------------------------------
// useDebouncedSearch — convenience wrapper that debounces the query param
// ---------------------------------------------------------------------------

export function useDebouncedSearch(
  rawQuery: string,
  filters?: Omit<SearchRequest, 'query'>,
  debounceMs = 300,
) {
  const debouncedQuery = useDebounce(rawQuery, debounceMs)

  const params: SearchRequest = {
    query: debouncedQuery || undefined,
    instrument_type: filters?.instrument_type,
    measurement_type: filters?.measurement_type,
    project_id: filters?.project_id,
    date_from: filters?.date_from,
    date_to: filters?.date_to,
    page: filters?.page ?? 1,
    page_size: filters?.page_size ?? 20,
  }

  return useSearch(params, {
    enabled: debouncedQuery.length >= 2,
  })
}
