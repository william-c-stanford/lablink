/**
 * HighlightedText — safely renders backend highlight strings that contain
 * `<mark>...</mark>` tags as React elements, with no `dangerouslySetInnerHTML`.
 *
 * Example input:  "foo <mark>bar</mark> baz"
 * Example output: [<span>foo </span>, <mark>bar</mark>, <span> baz</span>]
 */

import React from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface HighlightedTextProps {
  text: string
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface Segment {
  value: string
  highlighted: boolean
}

/**
 * Splits a highlight string into plain and marked segments.
 * Only `<mark>...</mark>` tags are treated specially; all other content is
 * treated as plain text, so no other HTML tag can be injected.
 */
function parseHighlight(text: string): Segment[] {
  const segments: Segment[] = []
  // Match literal <mark>…</mark> only (case-sensitive, no attributes allowed)
  const pattern = /<mark>([\s\S]*?)<\/mark>/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    // Plain text before the <mark>
    if (match.index > lastIndex) {
      segments.push({ value: text.slice(lastIndex, match.index), highlighted: false })
    }
    // The marked content (capture group 1)
    segments.push({ value: match[1], highlighted: true })
    lastIndex = pattern.lastIndex
  }

  // Any trailing plain text after the last </mark>
  if (lastIndex < text.length) {
    segments.push({ value: text.slice(lastIndex), highlighted: false })
  }

  return segments
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const markStyle: React.CSSProperties = {
  background: 'rgba(59,130,246,0.2)',
  color: '#1e293b',
  borderRadius: '2px',
  padding: '0 2px',
}

export function HighlightedText({ text, className }: HighlightedTextProps): React.ReactElement {
  const segments = parseHighlight(text)

  return (
    <span className={className}>
      {segments.map((seg, i) =>
        seg.highlighted ? (
          <mark key={i} style={markStyle}>
            {seg.value}
          </mark>
        ) : (
          <span key={i}>{seg.value}</span>
        ),
      )}
    </span>
  )
}
