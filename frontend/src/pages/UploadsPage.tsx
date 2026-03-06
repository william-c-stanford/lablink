/**
 * UploadsPage -- drag-and-drop upload zone, filterable upload list, detail view.
 *
 * Neuromorphic design:
 *   - nm-inset dashed border drop zone
 *   - nm-outset card rows with status badges
 *   - nm-inset filter bar
 *   - Upload progress indicator
 */

import { useState, useCallback, useRef } from 'react'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Button,
  Input,
  Spinner,
} from '@/components/ui'
import { NativeSelect } from '@/components/ui/select'
import { UploadStatusBadge } from '@/components/ui/badge'
import type { UploadStatus } from '@/components/ui/badge'
import { useUploads, useUploadFile } from '@/api/hooks/useUploads'
import { Upload, FileUp } from 'lucide-react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UploadRecord {
  id: string
  filename: string
  instrument_type: string | null
  status: UploadStatus
  file_size: number
  created_at: string
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function UploadsPage() {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [instrumentFilter, setInstrumentFilter] = useState<string>('')
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  // API hooks
  const uploadsQuery = useUploads({
    page,
    page_size: 20,
    status: statusFilter ? (statusFilter as UploadStatus) : undefined,
  })
  const uploadFileMutation = useUploadFile()

  // Envelope extraction
  const envelope = uploadsQuery.data as Record<string, unknown> | undefined
  const uploads = (
    Array.isArray(envelope?.data) ? envelope!.data : []
  ) as UploadRecord[]
  const pagination = (
    (envelope?.meta as Record<string, unknown>)?.pagination as {
      total_count: number
      page: number
      page_size: number
      has_more: boolean
    }
  ) ?? null

  // Filter by instrument type client-side (backend doesn't have instrument_type filter on uploads)
  const filteredUploads = instrumentFilter
    ? uploads.filter((u) => u.instrument_type === instrumentFilter)
    : uploads

  // ---------------------------------------------------------------------------
  // Upload handlers
  // ---------------------------------------------------------------------------

  const doUpload = useCallback(
    (file: File) => {
      setUploadProgress(0)
      uploadFileMutation.mutate(
        { file },
        {
          onSuccess: () => {
            setUploadProgress(100)
            setTimeout(() => setUploadProgress(null), 1500)
          },
          onError: () => {
            setUploadProgress(null)
          },
        },
      )
    },
    [uploadFileMutation],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback(() => {
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) doUpload(file)
    },
    [doUpload],
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) doUpload(file)
    },
    [doUpload],
  )

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2
          className="text-2xl font-extrabold tracking-tight"
          style={{ color: '#1e293b' }}
        >
          Uploads
        </h2>
        <p className="text-sm mt-1" style={{ color: '#64748b' }}>
          Upload and manage instrument data files.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className="rounded-[32px] p-10 text-center transition-all duration-200 cursor-pointer"
        style={{
          backgroundColor: '#f5f7fa',
          boxShadow: isDragging
            ? 'inset 8px 8px 16px rgba(174,185,201,0.5), inset -8px -8px 16px rgba(255,255,255,0.95)'
            : 'inset 6px 6px 12px rgba(174,185,201,0.4), inset -6px -6px 12px rgba(255,255,255,0.9)',
          border: isDragging
            ? '2px dashed #3b82f6'
            : '2px dashed rgba(174,185,201,0.5)',
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow:
              '4px 4px 8px rgba(174,185,201,0.4), -4px -4px 8px rgba(255,255,255,0.9)',
            color: isDragging ? '#3b82f6' : '#94a3b8',
          }}
        >
          <FileUp size={24} strokeWidth={2} />
        </div>
        <p className="text-sm font-semibold" style={{ color: '#64748b' }}>
          Drag and drop instrument files here
        </p>
        <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>
          or click to browse -- .csv, .xlsx, .xls, .txt
        </p>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          onChange={handleFileSelect}
          accept=".csv,.xlsx,.xls,.txt"
        />
      </div>

      {/* Upload progress */}
      {uploadProgress !== null && (
        <div
          className="rounded-full h-2 overflow-hidden"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow:
              'inset 2px 2px 4px rgba(174,185,201,0.4), inset -2px -2px 4px rgba(255,255,255,0.9)',
          }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${uploadProgress}%`,
              backgroundColor: '#3b82f6',
              boxShadow: '0 0 12px rgba(59,130,246,0.4)',
            }}
          />
        </div>
      )}

      {/* Upload error */}
      {uploadFileMutation.isError && (
        <div
          className="rounded-2xl px-5 py-3 text-sm font-medium"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow:
              'inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)',
            color: '#ef4444',
          }}
        >
          {uploadFileMutation.error instanceof Error
            ? uploadFileMutation.error.message
            : 'Upload failed'}
        </div>
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3">
        <NativeSelect
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
          wrapperClassName="w-48"
          placeholder="All statuses"
        >
          <option value="">All statuses</option>
          <option value="parsed">Parsed</option>
          <option value="parsing">Parsing</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
          <option value="queued">Queued</option>
        </NativeSelect>

        <NativeSelect
          value={instrumentFilter}
          onChange={(e) => {
            setInstrumentFilter(e.target.value)
            setPage(1)
          }}
          wrapperClassName="w-56"
          placeholder="All instruments"
        >
          <option value="">All instruments</option>
          <option value="spectrophotometer">Spectrophotometer</option>
          <option value="plate_reader">Plate Reader</option>
          <option value="hplc">HPLC</option>
          <option value="pcr">PCR</option>
          <option value="balance">Balance</option>
        </NativeSelect>
      </div>

      {/* Upload list */}
      {uploadsQuery.isLoading && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      )}

      {uploadsQuery.isError && (
        <div
          className="rounded-2xl px-5 py-4 text-sm font-medium text-center"
          style={{
            backgroundColor: '#f5f7fa',
            boxShadow:
              'inset 4px 4px 8px rgba(174,185,201,0.4), inset -4px -4px 8px rgba(255,255,255,0.9)',
            color: '#ef4444',
          }}
        >
          Failed to load uploads. Please try again.
        </div>
      )}

      {!uploadsQuery.isLoading && filteredUploads.length === 0 && (
        <p
          className="text-sm py-12 text-center font-medium"
          style={{ color: '#94a3b8' }}
        >
          No uploads found matching your filters.
        </p>
      )}

      {filteredUploads.length > 0 && (
        <div className="space-y-2">
          {/* Table header */}
          <div className="grid grid-cols-12 gap-4 px-5 py-2 text-xs font-bold uppercase tracking-widest text-[#94a3b8]">
            <span className="col-span-4">Filename</span>
            <span className="col-span-2">Instrument</span>
            <span className="col-span-2">Status</span>
            <span className="col-span-2">Date</span>
            <span className="col-span-2 text-right">Size</span>
          </div>

          {filteredUploads.map((upload) => (
            <div
              key={upload.id}
              className="grid grid-cols-12 gap-4 items-center px-5 py-3.5 rounded-2xl transition-all duration-150 cursor-pointer hover:scale-[1.003]"
              style={{
                backgroundColor: '#f5f7fa',
                boxShadow:
                  '4px 4px 8px rgba(174,185,201,0.3), -4px -4px 8px rgba(255,255,255,0.8)',
              }}
            >
              <span className="col-span-4 text-sm font-semibold text-[#1e293b] truncate">
                {upload.filename}
              </span>
              <span className="col-span-2 text-xs font-medium text-[#64748b] capitalize">
                {upload.instrument_type?.replace('_', ' ') ?? '--'}
              </span>
              <span className="col-span-2">
                <UploadStatusBadge status={upload.status ?? 'pending'} size="sm" />
              </span>
              <span className="col-span-2 text-xs text-[#94a3b8]">
                {formatDate(upload.created_at)}
              </span>
              <span className="col-span-2 text-xs text-[#94a3b8] text-right font-mono">
                {formatSize(upload.file_size)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {pagination && (
        <div className="flex items-center justify-between pt-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="text-sm font-medium" style={{ color: '#64748b' }}>
            Page {pagination.page} of{' '}
            {Math.ceil(pagination.total_count / pagination.page_size)}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!pagination.has_more}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
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

function formatSize(bytes: number): string {
  if (!bytes || bytes === 0) return '--'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
