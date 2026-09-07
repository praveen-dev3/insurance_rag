/**
 * The citations under an answer.
 *
 * Each card shows where the chunk came from and, once expanded, every
 * score that decided its fate plus the verbatim text. The verbatim text
 * matters most: it is what lets a reader check the answer against the
 * document instead of trusting it.
 */

import { useState } from 'react'
import type { Source } from '../types'

/** Em dash for absent scores — a stage that never ran is not a zero. */
function format(value: number | null | undefined, digits = 3) {
  if (value === null || value === undefined) return '—'
  return value.toFixed(digits)
}

/**
 * Which retriever surfaced this chunk, and at what rank.
 *
 * This is the whole argument for hybrid search made visible: a chunk
 * badged "bm25 #1" with no vector badge is one that semantic search
 * missed entirely.
 */
function MatchBadges({ source }: { source: Source }) {
  return (
    <div className="badges">
      {source.dense_rank !== null && (
        <span className="badge badge-dense" title="Rank from vector search">
          vector #{source.dense_rank}
        </span>
      )}
      {source.sparse_rank !== null && (
        <span className="badge badge-sparse" title="Rank from BM25 keyword search">
          bm25 #{source.sparse_rank}
        </span>
      )}
      {source.matched_by.length === 2 && (
        <span className="badge badge-both" title="Found by both retrievers">
          both
        </span>
      )}
    </div>
  )
}

function SourceCard({ source, index }: { source: Source; index: number }) {
  const [open, setOpen] = useState(false)

  return (
    <li className="source-card">
      <button
        type="button"
        className="source-head"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {/* Matches the SOURCE n numbering in the prompt, so a citation in
            the answer can be traced to a specific card. */}
        <span className="source-index">{index}</span>

        <span className="source-title">
          <span className="source-name">{source.source}</span>
          <span className="source-page">page {source.pages}</span>
        </span>

        <MatchBadges source={source} />

        <span className={`chevron ${open ? 'open' : ''}`} aria-hidden>
          ›
        </span>
      </button>

      {open && (
        <div className="source-body">
          {/* One score per pipeline stage, in the order they ran. */}
          <dl className="scores">
            <div>
              <dt>Cross-encoder</dt>
              <dd>{format(source.rerank_score ?? source.cross_score)}</dd>
            </div>
            <div>
              <dt>RRF</dt>
              <dd>{format(source.rrf_score, 5)}</dd>
            </div>
            <div>
              <dt>Vector distance</dt>
              <dd>{format(source.distance, 4)}</dd>
            </div>
            <div>
              <dt>BM25</dt>
              <dd>{format(source.bm25_score)}</dd>
            </div>
          </dl>

          {/* Rendered with white-space: pre-wrap so the PDF's own line
              breaks survive — collapsing them would make a table of
              policy fields unreadable. */}
          <p className="source-text">{source.text}</p>
        </div>
      )}
    </li>
  )
}

export function SourceList({ sources }: { sources: Source[] }) {
  // An empty list is a meaningful outcome, not a loading state: every
  // candidate scored below the relevance floor, which is exactly when
  // the answer should be "I don't know".
  if (sources.length === 0) {
    return (
      <p className="no-sources">
        No chunk passed the relevance threshold for this question.
      </p>
    )
  }

  return (
    <ul className="sources">
      {sources.map((source, index) => (
        <SourceCard key={source.id} source={source} index={index + 1} />
      ))}
    </ul>
  )
}
