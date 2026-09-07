/**
 * The settings pane: everything that changes how the next question is
 * retrieved.
 *
 * It is a control panel, not a preferences screen. Each option maps to
 * one stage of the pipeline, and the blurbs say what turning it off
 * would cost — the point is to make the retrieval stages visible and
 * comparable, not to hide them behind sensible defaults.
 *
 * On narrow screens this becomes an off-canvas drawer; `open` and
 * `onClose` are ignored by the desktop layout.
 */

import type { Health, Mode, RerankerKey, Settings } from '../types'

const MODES: { id: Mode; label: string; blurb: string }[] = [
  {
    id: 'hybrid',
    label: 'Hybrid',
    blurb: 'BM25 + vectors, fused with Reciprocal Rank Fusion.',
  },
  {
    id: 'dense',
    label: 'Vector only',
    blurb: 'Semantic nearest neighbours. Good at paraphrase.',
  },
  {
    id: 'sparse',
    label: 'Keyword only',
    blurb: 'BM25. Good at exact clauses, codes and policy numbers.',
  },
]

const RERANKER_LABELS: Record<RerankerKey, string> = {
  none: 'None (fusion order)',
  'ms-marco': 'Cross-encoder (ms-marco)',
  bge: 'BGE reranker',
  cohere: 'Cohere Rerank',
}

interface ToggleProps {
  label: string
  hint: string
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
}

/**
 * A checkbox wearing a card.
 *
 * Built on a real `<input type="checkbox">` inside a `<label>` rather
 * than a styled div, so keyboard focus, space-to-toggle and screen
 * reader announcements all work without being reimplemented.
 */
function Toggle({ label, hint, checked, disabled, onChange }: ToggleProps) {
  return (
    <label className={`toggle ${checked ? 'on' : ''}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-body">
        <span className="toggle-label">{label}</span>
        <span className="toggle-hint">{hint}</span>
      </span>
    </label>
  )
}

interface SidebarProps {
  health: Health | null
  settings: Settings
  /** Partial patch, so each control only states what it changed. */
  onChange: (patch: Partial<Settings>) => void
  onReindex: () => void
  onClear: () => void
  reindexing: boolean
  /** True while an answer is streaming; settings are frozen mid-answer. */
  busy: boolean
  /** Only meaningful on narrow screens, where the sidebar is a drawer. */
  open: boolean
  onClose: () => void
}

export function Sidebar({
  health,
  settings,
  onChange,
  onReindex,
  onClear,
  reindexing,
  busy,
  open,
  onClose,
}: SidebarProps) {
  // Fall back to the always-available options while /api/health is in
  // flight, so the controls render immediately rather than popping in.
  const rerankers = health?.rerankers ?? ['none', 'ms-marco']
  const documents = health?.sources ?? []
  const [firstPage, lastPage] = health?.page_range ?? [1, 1]

  const toggleSource = (name: string) => {
    const next = settings.sources.includes(name)
      ? settings.sources.filter((item) => item !== name)
      : [...settings.sources, name]

    onChange({ sources: next })
  }

  return (
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div className="brand">
        <span className="brand-mark" aria-hidden>
          ◈
        </span>
        <div>
          <h1>Insurance RAG</h1>
          <p>Hybrid · rerank · trace</p>
        </div>

        {/* Drawer dismissal; hidden by CSS on desktop. */}
        <button
          type="button"
          className="drawer-close"
          onClick={onClose}
          aria-label="Close settings"
        >
          ×
        </button>
      </div>

      <section className="panel">
        <h2>Retrieval</h2>

        {/* role=radiogroup rather than three <input type=radio>: the
            visual design is a stack of cards, and faking the ARIA is
            cheaper here than fighting the native control's layout. */}
        <div className="modes" role="radiogroup" aria-label="Retrieval mode">
          {MODES.map((option) => (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={settings.mode === option.id}
              className={`mode ${settings.mode === option.id ? 'active' : ''}`}
              onClick={() => onChange({ mode: option.id })}
              disabled={busy}
            >
              <span className="mode-label">{option.label}</span>
              <span className="mode-blurb">{option.blurb}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>
          Chunks to the LLM
          <span className="value">{settings.topK}</span>
        </h2>

        {/* Capped at 8: past that the prompt is mostly irrelevant text,
            which costs money and dilutes the answer. */}
        <input
          type="range"
          min={1}
          max={8}
          value={settings.topK}
          disabled={busy}
          onChange={(event) => onChange({ topK: Number(event.target.value) })}
        />

        <p className="hint">
          How many reranked chunks are quoted in the grounded prompt.
        </p>
      </section>

      <section className="panel">
        <h2>Reranker</h2>

        <select
          className="select"
          value={settings.reranker}
          disabled={busy}
          onChange={(event) =>
            onChange({ reranker: event.target.value as RerankerKey | '' })
          }
        >
          {/* Empty value = defer to whatever RERANKER the server runs. */}
          <option value="">Server default</option>
          {rerankers.map((key) => (
            <option key={key} value={key}>
              {RERANKER_LABELS[key] ?? key}
            </option>
          ))}
        </select>

        <p className="hint">
          A second pass that reads question and chunk together. Set to
          “None” to see what fusion alone returns.
        </p>
      </section>

      <section className="panel">
        <h2>Query &amp; diversity</h2>

        <div className="toggles">
          <Toggle
            label="MMR"
            hint="Drop near-duplicate chunks before reranking."
            checked={settings.useMmr}
            disabled={busy}
            onChange={(value) => onChange({ useMmr: value })}
          />

          {/* λ only exists when MMR is on, so it appears with it rather
              than sitting greyed out. */}
          {settings.useMmr && (
            <div className="slider-row">
              <span>
                λ {settings.mmrLambda.toFixed(2)}
                <em> · 1 = relevance, 0 = diversity</em>
              </span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={settings.mmrLambda}
                disabled={busy}
                onChange={(event) =>
                  onChange({ mmrLambda: Number(event.target.value) })
                }
              />
            </div>
          )}

          <Toggle
            label="Query rewriting"
            hint="Restate the question in policy vocabulary first."
            checked={settings.useRewrite}
            disabled={busy}
            onChange={(value) => onChange({ useRewrite: value })}
          />

          <Toggle
            label="HyDE"
            hint="Embed a hypothetical answer instead of the question."
            checked={settings.useHyde}
            disabled={busy}
            onChange={(value) => onChange({ useHyde: value })}
          />

          <Toggle
            label="Diagnose"
            hint="Label the result: retrieval failure vs generation failure."
            checked={settings.diagnose}
            disabled={busy}
            onChange={(value) => onChange({ diagnose: value })}
          />
        </div>
      </section>

      <section className="panel">
        <h2>
          Filters
          {/* Only offered once something is actually filtered — an
              always-visible "clear" invites clicking it for no reason. */}
          {(settings.sources.length > 0 ||
            settings.pageMin !== null ||
            settings.pageMax !== null) && (
            <button
              type="button"
              className="link"
              onClick={() =>
                onChange({ sources: [], pageMin: null, pageMax: null })
              }
            >
              clear
            </button>
          )}
        </h2>

        <div className="chips">
          {documents.map((name) => (
            <button
              key={name}
              type="button"
              className={`chip ${settings.sources.includes(name) ? 'on' : ''}`}
              disabled={busy}
              onClick={() => toggleSource(name)}
            >
              {name}
            </button>
          ))}
        </div>

        {/* Bounds come from the index, so the inputs cannot ask for a
            page that does not exist. */}
        <div className="page-range">
          <label>
            from p.
            <input
              type="number"
              min={firstPage}
              max={lastPage}
              value={settings.pageMin ?? ''}
              disabled={busy}
              onChange={(event) =>
                onChange({
                  // Empty string clears the bound rather than meaning 0.
                  pageMin: event.target.value ? Number(event.target.value) : null,
                })
              }
            />
          </label>

          <label>
            to p.
            <input
              type="number"
              min={firstPage}
              max={lastPage}
              value={settings.pageMax ?? ''}
              disabled={busy}
              onChange={(event) =>
                onChange({
                  pageMax: event.target.value ? Number(event.target.value) : null,
                })
              }
            />
          </label>
        </div>

        <p className="hint">
          Metadata filtering runs inside both retrievers, so a filtered
          search still fills its top-k from the allowed pages.
        </p>
      </section>

      <section className="panel status">
        <h2>Index</h2>

        {/* Three states: still loading, healthy, or broken. The broken
            one has to be legible — it is the only explanation the user
            gets for a disabled composer. */}
        {health === null ? (
          <p className="hint">Connecting…</p>
        ) : health.ready ? (
          <dl>
            <div>
              <dt>Chunks</dt>
              <dd>{health.chunks}</dd>
            </div>
            <div>
              <dt>Chunking</dt>
              <dd className="mono">
                {health.chunking?.strategy}/{health.chunking?.chunk_size}
              </dd>
            </div>
            <div>
              <dt>Embeddings</dt>
              <dd className="mono" title={health.embedding?.model_id}>
                {health.embedding?.key}
              </dd>
            </div>
            <div>
              <dt>LLM</dt>
              <dd className="mono">{health.llm_model}</dd>
            </div>
          </dl>
        ) : (
          <p className="error">{health.error ?? 'Engine unavailable.'}</p>
        )}
      </section>

      <div className="sidebar-actions">
        <button type="button" onClick={onClear} disabled={busy}>
          New chat
        </button>
        <button type="button" onClick={onReindex} disabled={busy || reindexing}>
          {reindexing ? 'Re-indexing…' : 'Re-index PDFs'}
        </button>
      </div>
    </aside>
  )
}
