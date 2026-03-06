/**
 * Tests for the LabLink API client.
 *
 * Uses MSW (Mock Service Worker) to intercept HTTP requests and return
 * Envelope[T]-shaped responses matching the backend pattern.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setAccessToken, getAccessToken, clearAccessToken, unwrapResponse, uploadFile } from '../client'

// ---------------------------------------------------------------------------
// Token management tests
// ---------------------------------------------------------------------------

describe('Token management', () => {
  afterEach(() => {
    clearAccessToken()
  })

  it('initially has no access token', () => {
    clearAccessToken()
    expect(getAccessToken()).toBeNull()
  })

  it('sets and retrieves the access token', () => {
    setAccessToken('test-jwt-token')
    expect(getAccessToken()).toBe('test-jwt-token')
  })

  it('clears the access token', () => {
    setAccessToken('test-jwt-token')
    clearAccessToken()
    expect(getAccessToken()).toBeNull()
  })

  it('overwrites existing token', () => {
    setAccessToken('old-token')
    setAccessToken('new-token')
    expect(getAccessToken()).toBe('new-token')
  })

  it('accepts null to clear token', () => {
    setAccessToken('token')
    setAccessToken(null)
    expect(getAccessToken()).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// unwrapResponse tests
// ---------------------------------------------------------------------------

describe('unwrapResponse', () => {
  const mockMeta = {
    request_id: '550e8400-e29b-41d4-a716-446655440000',
    timestamp: '2026-03-06T12:00:00Z',
    pagination: null,
  }

  it('returns data from a successful envelope', () => {
    const envelope = { data: { id: '123', name: 'Test' }, meta: mockMeta, errors: [] }
    expect(unwrapResponse(envelope)).toEqual({ id: '123', name: 'Test' })
  })

  it('throws when envelope has errors', () => {
    const envelope = {
      data: null,
      meta: mockMeta,
      errors: [
        {
          code: 'NOT_FOUND',
          message: 'Resource not found',
          suggestion: 'Use list endpoint to find valid IDs',
          field: null,
        },
      ],
    }
    expect(() => unwrapResponse(envelope)).toThrow('[NOT_FOUND] Resource not found')
  })

  it('includes suggestion in error message when present', () => {
    const envelope = {
      data: null,
      meta: mockMeta,
      errors: [
        {
          code: 'VALIDATION_ERROR',
          message: 'Invalid status',
          suggestion: 'Valid statuses: planned, running',
          field: 'status',
        },
      ],
    }
    expect(() => unwrapResponse(envelope)).toThrow(
      '[VALIDATION_ERROR] Invalid status — Valid statuses: planned, running'
    )
  })

  it('throws when data is null with no errors', () => {
    const envelope = { data: null, meta: mockMeta, errors: [] }
    expect(() => unwrapResponse(envelope)).toThrow('Empty response data')
  })

  it('handles array data', () => {
    const items = [{ id: '1' }, { id: '2' }]
    const envelope = { data: items, meta: mockMeta, errors: [] }
    expect(unwrapResponse(envelope)).toEqual(items)
  })

  it('throws using first error code when multiple errors present', () => {
    const envelope = {
      data: null,
      meta: mockMeta,
      errors: [
        { code: 'FIRST_ERROR', message: 'First problem', field: 'field1' },
        { code: 'SECOND_ERROR', message: 'Second problem', field: 'field2' },
      ],
    }
    expect(() => unwrapResponse(envelope)).toThrow('[FIRST_ERROR] First problem')
  })
})

// ---------------------------------------------------------------------------
// uploadFile tests (with mocked fetch)
// ---------------------------------------------------------------------------

describe('uploadFile', () => {
  const originalFetch = global.fetch

  beforeEach(() => {
    clearAccessToken()
  })

  afterEach(() => {
    global.fetch = originalFetch
    clearAccessToken()
  })

  it('sends multipart/form-data POST request', async () => {
    const mockResponse = {
      data: {
        id: 'upload-123',
        filename: 'test.csv',
        status: 'uploaded',
        content_hash: 'abc123',
        file_size_bytes: 1024,
        s3_key: 'uploads/test.csv',
        created_at: '2026-03-06T12:00:00Z',
      },
      meta: { request_id: '123', timestamp: '2026-03-06T12:00:00Z' },
      errors: [],
    }

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse,
    })

    const file = new File(['wavelength,absorbance\n260,1.2'], 'test.csv', { type: 'text/csv' })
    const result = await uploadFile({ file })

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v1/uploads',
      expect.objectContaining({ method: 'POST' })
    )
    expect(result).toEqual(mockResponse)
  })

  it('includes auth token in upload request', async () => {
    setAccessToken('test-bearer-token')

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: {}, meta: {}, errors: [] }),
    })

    const file = new File(['data'], 'test.csv', { type: 'text/csv' })
    await uploadFile({ file })

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/v1/uploads',
      expect.objectContaining({
        headers: { Authorization: 'Bearer test-bearer-token' },
      })
    )
  })

  it('appends project_id query parameter when provided', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: {}, meta: {}, errors: [] }),
    })

    const file = new File(['data'], 'test.csv', { type: 'text/csv' })
    await uploadFile({ file, projectId: 'proj-456' })

    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toContain('project_id=proj-456')
  })

  it('appends instrument_id query parameter when provided', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: {}, meta: {}, errors: [] }),
    })

    const file = new File(['data'], 'test.csv', { type: 'text/csv' })
    await uploadFile({ file, instrumentId: 'inst-789' })

    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(url).toContain('instrument_id=inst-789')
  })

  it('throws on non-ok HTTP response', async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({
        errors: [{ code: 'VALIDATION_ERROR', message: 'Invalid file format' }],
      }),
    })

    const file = new File(['bad data'], 'test.csv', { type: 'text/csv' })
    await expect(uploadFile({ file })).rejects.toThrow('Invalid file format')
  })

  it('handles fetch network error gracefully', async () => {
    global.fetch = vi.fn().mockRejectedValueOnce(new Error('Network error'))

    const file = new File(['data'], 'test.csv', { type: 'text/csv' })
    await expect(uploadFile({ file })).rejects.toThrow('Network error')
  })
})

// ---------------------------------------------------------------------------
// openSSEConnection tests
// ---------------------------------------------------------------------------

describe('openSSEConnection', () => {
  it('is exported from the module', async () => {
    const { openSSEConnection } = await import('../client')
    expect(typeof openSSEConnection).toBe('function')
  })
})
