/**
 * SearchPage -- full-text search with filter chips and result cards.
 *
 * Neuromorphic design:
 *   - Large nm-inset search input (centered)
 *   - Filter chips as nm-btn / nm-btn-active toggles
 *   - nm-outset result cards with highlighted matches
 */

import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Card,
  CardContent,
  Badge,
  Input,
  Spinner,
  HighlightedText,
} from '@/components/ui'
import { NativeSelect } from '@/components/ui/select'
import { useDebouncedSearch, useDebounce } from '@/api/hooks/useSearch'
import { Search as SearchIcon } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SearchHit {
  id: string
  upload_id?: string
  filename?: string
  instrument_type?: string
  measurement_type?: string
  sample_count?: number
  score?: number
  created_at?: string
  highlights?: string[]
  snippet?: string
  title?: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SearchPage() {
  const navigate = useNavigate()

  const [query, setQuery] = useState('')
  const [instrumentType, setInstrumentType] = useState('')
  const [projectId, setProjectId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const searchResult = useDebouncedSearch(query, {
    instrument_type: instrumentType || undefined,
    project_id: projectId || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page: 1,
    page_size: 20,
  })

  // Extract results from envelope
  const envelope = searchResult.data as Record<string, unknown> | undefined
  const resultData = envelope?.data as Record<string, unknown> | undefined
  const hits = (
    Array.isArray(resultData?.hits) ? resultData!.hits : []
  ) as SearchHit[]
  const totalCount =
    (resultData?.total as number) ??
    (
      (envelope?.meta as Record<string, unknown>)?.pagination as {
        total_count: number
      }
    )?.total_count ??
    hits.length

  const debouncedQuery = useDebounce(query, 300)
  const isSearching = searchResult.isLoading && debouncedQuery.length >= 2

  // ---------------------------------------------------------------------------
  // Filter chip helpers
  // ---------------------------------------------------------------------------

  const INSTRUMENT_TYPES = [
    'spectrophotometer',
    'plate_reader',
    'hplc',
    'pcr',
    'balance',
  ]

  return (
    <div className="space-y-6" data-testid="search-page">
      {/* Page header */}
      <div>
        <h2
          className="text-2xl font-extrabold tracking-tight"
          style={{ color: '#1e293b' }}
        >
          Search
        </h2>
        <p className="text-sm mt-1" style={{ color: '#64748b' }}>
          Search across all uploaded instrument data.
        </p>
      </div>

      {/* Search input -- large, centered, nm-inset */}
      <div className="max-w-2xl mx-auto">
        <Input
          type="search"
          placeholder="Search uploads, measurements, samples..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="text-base py-4 px-6"
          data-testid="search-input"
          leftIcon={
            <SearchIcon
              size={20}
              strokeWidth={2}
              className="text-[#94a3b8]"
            />
          }
        />
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2 items-center">
        <span
          className="text-xs font-bold uppercase tracking-widest mr-2"
          style={{ color: '#94a3b8' }}
        >
          Filters:
        </span>

        {INSTRUMENT_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            onClick={() =>
              setInstrumentType((prev) => (prev === type ? '' : type))
            }
          >
            <Badge
              variant={instrumentType === type ? 'primary' : 'default'}
              size="md"
              className="cursor-pointer"
            >
              {type.replace('_', ' ')}
            </Badge>
          </button>
        ))}

        {/* Date range filters */}
        <div className="flex items-center gap-2 ml-auto">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="text-xs rounded-xl px-3 py-2 nm-inset bg-[#f5f7fa] text-[#1e293b] border-0 appearance-none"
            placeholder="From"
          />
          <span className="text-xs text-[#94a3b8]">to</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="text-xs rounded-xl px-3 py-2 nm-inset bg-[#f5f7fa] text-[#1e293b] border-0 appearance-none"
            placeholder="To"
          />
        </div>
      </div>

      {/* Loading */}
      {isSearching && (
        <div className="flex justify-center py-8">
          <Spinner size="md" />
        </div>
      )}

      {/* No results */}
      {!isSearching &&
        debouncedQuery.length >= 2 &&
        hits.length === 0 && (
          <p
            className="text-sm py-12 text-center font-medium"
            style={{ color: '#94a3b8' }}
          >
            No results found for "{debouncedQuery}"
          </p>
        )}

      {/* Results count */}
      {hits.length > 0 && (
        <p className="text-xs font-bold" style={{ color: '#94a3b8' }}>
          {totalCount} result{totalCount !== 1 ? 's' : ''} found
        </p>
      )}

      {/* Results list */}
      {hits.length > 0 && (
        <div className="space-y-3" data-testid="search-results">
          {hits.map((hit, i) => (
            <Card
              key={hit.id ?? `hit-${i}`}
              variant="outset"
              hoverable
              className="cursor-pointer"
              onClick={() => {
                if (hit.upload_id) {
                  navigate({ to: '/uploads' })
                }
              }}
            >
              <CardContent className="py-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-bold text-[#1e293b]">
                      {hit.filename ?? hit.title ?? 'Untitled'}
                    </h3>

                    {/* Snippet / highlights */}
                    {hit.snippet && (
                      <p className="text-xs text-[#64748b] mt-1 line-clamp-2">
                        {hit.snippet}
                      </p>
                    )}
                    {hit.highlights && hit.highlights.length > 0 && (
                      <div className="mt-1.5 space-y-0.5">
                        {hit.highlights.slice(0, 2).map((hl, j) => (
                          <p key={j} className="text-xs text-[#64748b]">
                            <HighlightedText text={hl} />
                          </p>
                        ))}
                      </div>
                    )}

                    {/* Metadata row */}
                    <div className="flex items-center gap-3 mt-2">
                      {hit.instrument_type && (
                        <Badge variant="outline" size="sm">
                          {hit.instrument_type.replace('_', ' ')}
                        </Badge>
                      )}
                      {hit.sample_count != null && (
                        <span className="text-xs text-[#94a3b8]">
                          {hit.sample_count} samples
                        </span>
                      )}
                      {hit.created_at && (
                        <span className="text-xs text-[#94a3b8]">
                          {formatDate(hit.created_at)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Relevance score */}
                  {hit.score != null && (
                    <div
                      className="flex-shrink-0 text-xs font-bold px-2.5 py-1 rounded-xl"
                      style={{
                        backgroundColor: '#f5f7fa',
                        boxShadow:
                          'inset 2px 2px 4px rgba(174,185,201,0.35), inset -2px -2px 4px rgba(255,255,255,0.85)',
                        color: '#3b82f6',
                      }}
                    >
                      {(hit.score * 100).toFixed(0)}%
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Empty state -- no query yet */}
      {query.length === 0 && (
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
            <SearchIcon size={28} strokeWidth={1.5} />
          </div>
          <p className="text-sm font-semibold" style={{ color: '#64748b' }}>
            Start typing to search your lab data
          </p>
          <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>
            Search across filenames, sample names, measurements, and more.
          </p>
        </div>
      )}
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
