/**
 * The inspection view: why the app answered the way it did.
 *
 * Two tabs. The trace tab shows one question end to end — how it was
 * transformed, how many candidates each stage passed on, how every stage
 * ranked them, and what the answer was. The metrics tab shows the
 * evaluator's numbers, so a single anecdote sits next to the aggregate
 * that says whether it is typical.
 *
 * Everything here is read-only. Diagnosing a failure and changing the
 * configuration are different jobs, and mixing them makes it easy to
 * change three things and learn nothing.
 */

import { useEffect, useState } from 'react'
import { fetchEvalResults } from '../api'
import type { EvalRun, Message, Source, StageName, Trace } from '../types'

/** Pipeline order. The tabs and the funnel both rely on it. */
const STAGE_ORDER: StageName[] = [
  'dense',
  'sparse',
  'fused',
  'mmr',
  'reranked',
  'final',
]

const STAGE_BLURB: Record<StageName, string> = {
  dense: 'Nearest neighbours by meaning. Ranked by vector distance.',
  sparse: 'BM25 keyword matches. Ranked by term score.',
  fused: 'Both lists merged by Reciprocal Rank Fusion.',
  mmr: 'Re-ordered to drop near-duplicates. Empty when MMR is off.',
  reranked: 'Rescored by the cross-encoder reading question + chunk.',
  final: 'What was actually quoted in the prompt.',
}

function number(value: number | null | undefined, digits = 3) {
  if (value === null || value === undefined) return '—'
  return value.toFixed(digits)
}

/**
 * The funnel: how many candidates entered and left each stage.
 *
 * Bars are scaled against the widest stage rather than a fixed maximum,
 * so the shape stays readable whether the pipeline saw 6 candidates or
 * 60. Stages that did not run are hidden — except `final`, because a
 * final count of zero is the most important thing on the panel.
 */
function Funnel({ trace }: { trace: Trace }) {
  const steps = STAGE_ORDER.map((stage) => ({
    stage,
    count: trace.stages[stage]?.length ?? 0,
  })).filter((step) => step.count > 0 || step.stage === 'final')

  const widest = Math.max(...steps.map((step) => step.count), 1)

  return (
    <div className="funnel">
      {steps.map((step) => (
        <div key={step.stage} className="funnel-row">
          <span className="funnel-name">{step.stage}</span>
          <span className="funnel-bar">
            <span
              className={`funnel-fill ${step.stage}`}
              // A 3% floor keeps a single-candidate stage visible rather
              // than collapsing it to nothing.
              style={{ width: `${Math.max((step.count / widest) * 100, 3)}%` }}
            />
          </span>
          <span className="funnel-count">{step.count}</span>
          {/* Only some stages are timed, so a blank cell is normal. */}
          <span className="funnel-ms">
            {trace.timings_ms[step.stage] !== undefined
              ? `${trace.timings_ms[step.stage]}ms`
              : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

/**
 * One stage's ranking.
 *
 * Every column is shown for every stage, even where it is empty — a
 * chunk with a strong BM25 score and no vector distance is precisely the
 * comparison worth making, and hiding the empty column would hide it.
 * Rows that survived to the prompt are highlighted.
 */
function StageTable({ stage, chunks }: { stage: StageName; chunks: Source[] }) {
  if (chunks.length === 0) {
    return <p className="empty-stage">Nothing at this stage.</p>
  }

  return (
    <table className="stage-table">
      <thead>
        <tr>
          <th>#</th>
          <th>page</th>
          {/* The sparse stage has no distance to show, so the column
              carries its BM25 score instead. */}
          <th>{stage === 'sparse' ? 'bm25' : 'dist'}</th>
          <th>rrf</th>
          <th>rerank</th>
          <th>text</th>
        </tr>
      </thead>
      <tbody>
        {chunks.map((chunk, index) => (
          <tr key={chunk.id} className={chunk.final_rank ? 'kept' : ''}>
            <td className="mono">{index + 1}</td>
            <td className="mono">{chunk.pages}</td>
            <td className="mono">
              {stage === 'sparse'
                ? number(chunk.bm25_score, 2)
                : number(chunk.distance, 3)}
            </td>
            <td className="mono">{number(chunk.rrf_score, 4)}</td>
            <td className="mono">{number(chunk.rerank_score, 2)}</td>
            {/* Truncated to keep rows scannable; the full text is in the
                title attribute and in the source cards. */}
            <td className="snippet" title={chunk.text}>
              {chunk.text.trim().slice(0, 90)}…
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/** Question → funnel → stages → answer, for one message. */
function TraceView({ message }: { message: Message }) {
  const trace = message.trace
  // Defaults to `final` because that is what actually reached the LLM;
  // the earlier stages are for when `final` looks wrong.
  const [stage, setStage] = useState<StageName>('final')

  if (!trace) {
    return (
      <p className="hint pad">
        Ask a question to see how each retrieval stage ranked the corpus.
      </p>
    )
  }

  const queries = trace.config.queries

  return (
    <div className="inspect-body">
      <section>
        <h3>Question</h3>
        {/* Each transform is listed only when it changed something, so
            the block stays short in the common case. */}
        <dl className="query-stages">
          <div>
            <dt>asked</dt>
            <dd>{trace.question}</dd>
          </div>
          {queries?.condensed && queries.condensed !== trace.question && (
            <div>
              <dt>condensed</dt>
              <dd>{queries.condensed}</dd>
            </div>
          )}
          {queries?.rewritten && (
            <div>
              <dt>rewritten</dt>
              <dd>{queries.rewritten}</dd>
            </div>
          )}
          {/* Greyed out deliberately: the HyDE passage is invented text
              used as a search probe, and must never read as a finding. */}
          {queries?.hyde && (
            <div>
              <dt>HyDE probe</dt>
              <dd className="faint">{queries.hyde}</dd>
            </div>
          )}
          <div>
            <dt>mode</dt>
            <dd className="mono">
              {trace.mode}
              {Object.keys(trace.filters ?? {}).length > 0 &&
                ` · filtered ${JSON.stringify(trace.filters)}`}
            </dd>
          </div>
        </dl>
      </section>

      <section>
        <h3>Funnel</h3>
        <Funnel trace={trace} />
        {/* The floor is what turns "nothing relevant" into "I don't
            know", so when it fires it deserves an explanation rather
            than a silently empty result. */}
        {trace.dropped_below_floor.length > 0 && (
          <p className="floor-note">
            {trace.dropped_below_floor.length} chunk(s) scored below the
            relevance floor and were dropped — the corpus had nothing
            relevant, so the answer should be “I don't know”.
          </p>
        )}
      </section>

      <section>
        <h3>Stages</h3>

        <div className="stage-tabs">
          {STAGE_ORDER.map((name) => (
            <button
              key={name}
              type="button"
              className={`stage-tab ${stage === name ? 'active' : ''}`}
              onClick={() => setStage(name)}
            >
              {name}
              <span className="stage-count">
                {trace.stages[name]?.length ?? 0}
              </span>
            </button>
          ))}
        </div>

        <p className="stage-blurb">{STAGE_BLURB[stage]}</p>

        {/* The table is wider than the panel on narrow screens; it
            scrolls inside its own container so the page never does. */}
        <div className="table-scroll">
          <StageTable stage={stage} chunks={trace.stages[stage] ?? []} />
        </div>
      </section>

      <section>
        <h3>Answer</h3>
        {/* Repeated here so question, retrieved chunks and answer can be
            read together without scrolling back to the transcript. */}
        <p className="answer-preview">
          {message.content || <em>(still writing…)</em>}
        </p>

        {message.diagnosis && (
          <div className={`verdict ${message.diagnosis.label}`}>
            <strong>{message.diagnosis.label.replace(/_/g, ' ')}</strong>
            <span>{message.diagnosis.explanation}</span>
            {message.diagnosis.reason && <em>{message.diagnosis.reason}</em>}
          </div>
        )}
      </section>
    </div>
  )
}

/**
 * Flattens the evaluator's saved JSON into comparable rows.
 *
 * Sweep commands save an array of runs and single commands save one
 * object, so both shapes have to be unwrapped. Anything without a
 * `metrics` key (a `compare` diff, say) is skipped rather than rendered
 * as a broken row.
 */
function useEvalRuns() {
  const [runs, setRuns] = useState<{ file: string; run: EvalRun }[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchEvalResults()
      .then((payload) => {
        const rows: { file: string; run: EvalRun }[] = []

        for (const [file, entry] of Object.entries(payload.runs)) {
          const result = entry.result

          if (Array.isArray(result)) {
            result.forEach((run) => rows.push({ file, run }))
          } else if (result && 'metrics' in result) {
            rows.push({ file, run: result })
          }
        }

        setRuns(rows)
      })
      .catch((issue: Error) => setError(issue.message))
  }, [])

  return { runs, error }
}

function MetricsView() {
  const { runs, error } = useEvalRuns()

  if (error) return <p className="error pad">{error}</p>

  // No results is the normal first-run state, so it gets the command to
  // fix it rather than an error.
  if (runs.length === 0) {
    return (
      <p className="hint pad">
        No evaluation results yet. Run <code>python evaluate.py
        sweep-retrieval --k 1</code> and reload.
      </p>
    )
  }

  return (
    <div className="inspect-body">
      <p className="hint">
        Measured over the golden set in <code>eval/golden_set.json</code>.
        hit@k is the share of questions where a labelled page reached the
        top k — with k = chunks sent to the LLM, that is the probability
        the model was given something it could answer from.
      </p>

      <div className="table-scroll">
        <table className="stage-table">
          <thead>
            <tr>
              <th>configuration</th>
              <th>k</th>
              <th>hit@k</th>
              <th>recall</th>
              <th>mrr</th>
              <th>ms</th>
            </tr>
          </thead>
          <tbody>
            {runs.map(({ file, run }, index) => (
              // Labels repeat across files (every sweep has a "dense
              // only"), so the key includes the file and the position.
              <tr key={`${file}-${run.label}-${index}`}>
                <td title={file}>{run.label}</td>
                <td className="mono">{run.k}</td>
                {/* Metric names embed k, hence the template key. */}
                <td className="mono strong">
                  {number(run.metrics.final[`hit_rate@${run.k}`], 3)}
                </td>
                <td className="mono">
                  {number(run.metrics.final[`recall@${run.k}`], 3)}
                </td>
                <td className="mono">{number(run.metrics.final.mrr, 3)}</td>
                <td className="mono">{run.latency_ms.mean.toFixed(0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface InspectionPanelProps {
  /** The pinned or live message. Null before anything has been asked. */
  message: Message | null
  open: boolean
  onClose: () => void
}

export function InspectionPanel({
  message,
  open,
  onClose,
}: InspectionPanelProps) {
  const [tab, setTab] = useState<'trace' | 'metrics'>('trace')

  // Unmounted rather than hidden, so the grid column collapses and the
  // transcript gets the width back.
  if (!open) return null

  return (
    <aside className="inspect">
      <header className="inspect-head">
        <div className="inspect-tabs">
          <button
            type="button"
            className={tab === 'trace' ? 'active' : ''}
            onClick={() => setTab('trace')}
          >
            Retrieval trace
          </button>
          <button
            type="button"
            className={tab === 'metrics' ? 'active' : ''}
            onClick={() => setTab('metrics')}
          >
            Metrics
          </button>
        </div>

        <button
          type="button"
          className="drawer-close always"
          onClick={onClose}
          aria-label="Close inspection panel"
        >
          ×
        </button>
      </header>

      {tab === 'trace' ? (
        message ? (
          <TraceView message={message} />
        ) : (
          <p className="hint pad">
            Ask a question, or pick an answer's “Inspect” button, to see
            every stage of retrieval.
          </p>
        )
      ) : (
        <MetricsView />
      )}
    </aside>
  )
}
