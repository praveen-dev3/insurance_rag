/**
 * The contract between the FastAPI server and this UI.
 *
 * Field names are snake_case wherever they come straight off the wire,
 * and camelCase only for state this app owns (see `Settings`). Renaming
 * server fields on arrival would mean maintaining a mapping layer whose
 * only job is cosmetic, and every mismatch it hides is a bug that would
 * otherwise have been a type error.
 */

export type Role = 'user' | 'assistant'

/** Which retrievers run. Mirrors rag.retrieval.RETRIEVAL_MODES. */
export type Mode = 'hybrid' | 'dense' | 'sparse'

/** Mirrors rag.rerankers.RERANKERS. */
export type RerankerKey = 'none' | 'ms-marco' | 'bge' | 'cohere'

/**
 * One chunk, carrying whatever each pipeline stage scored it.
 *
 * Every stage's score is kept rather than just the final one, because
 * the interesting question when retrieval goes wrong is not "what won?"
 * but "which stage lost the right answer?" — a chunk with `sparse_rank`
 * 1 and a terrible `rerank_score` tells that story on its own.
 *
 * `null` means "this stage never saw the chunk", which is different from
 * a score of zero.
 */
export interface Source {
  id: string
  text: string
  source: string
  /** Pre-formatted page reference, e.g. "7" or "3-4". */
  pages: string
  page_start: number
  page_end: number
  /** Vector distance; lower is closer. Null when dense search skipped it. */
  distance: number | null
  dense_rank: number | null
  bm25_score: number | null
  sparse_rank: number | null
  rrf_score: number
  fused_rank: number | null
  mmr_rank: number | null
  rerank_score: number | null
  /** Legacy alias for rerank_score, kept so older payloads still render. */
  cross_score: number | null
  /** Set only on chunks that survived the relevance floor. */
  final_rank: number | null
  /** Which retrievers found it: ["dense"], ["bm25"], or both. */
  matched_by: string[]
}

export type StageName =
  | 'dense'
  | 'sparse'
  | 'fused'
  | 'mmr'
  | 'reranked'
  | 'final'

/** The question as each transform left it. */
export interface Queries {
  original: string
  /** Follow-up resolved against the conversation. */
  condensed: string
  /** Null unless query rewriting was enabled. */
  rewritten: string | null
  /** The invented passage HyDE embedded. Never shown as fact. */
  hyde: string | null
  /** What BM25 and the reranker saw. */
  search_query: string
  /** What was embedded for the dense search. */
  dense_query: string
}

/** What every stage saw and what it passed on. Renders the inspector. */
export interface Trace {
  question: string
  search_query: string
  dense_query: string
  mode: Mode
  filters: Record<string, unknown>
  config: Record<string, unknown> & { queries?: Queries }
  /** Per-stage wall clock, for spotting which stage costs the latency. */
  timings_ms: Record<string, number>
  stages: Record<StageName, Source[]>
  /** Scored too low to be worth quoting — the "I don't know" path. */
  dropped_below_floor: Source[]
}

/** Mirrors rag.diagnostics.LABELS. */
export type FailureLabel =
  | 'retrieval_failure'
  | 'generation_failure'
  | 'correct_refusal'
  | 'missed_refusal'
  | 'ok'

export interface Diagnosis {
  label: FailureLabel
  /** The judge's one-sentence justification for this verdict. */
  reason: string
  /** What the label means and where to fix it. Server-supplied. */
  explanation: string
  context_sufficient: boolean | null
  answer_grounded: boolean | null
  refused: boolean
}

export interface Message {
  id: string
  role: Role
  content: string
  /** Undefined until the `sources` event lands. */
  sources?: Source[]
  trace?: Trace
  diagnosis?: Diagnosis
  /** Set only when condensation actually changed the question. */
  standaloneQuestion?: string
  streaming?: boolean
  error?: string
}

/**
 * GET /api/health. Everything is optional because the server answers
 * `{ready: false, error}` when the index failed to load, and the UI has
 * to render that state rather than crash on a missing field.
 */
export interface Health {
  ready: boolean
  error: string | null
  chunks?: number
  collection?: string
  llm_model?: string
  modes?: Mode[]
  top_k?: number
  /** Document names, for the filter chips. */
  sources?: string[]
  /** [first, last] page across the corpus, to bound the page inputs. */
  page_range?: [number, number]
  embedding?: {
    key: string
    model_id: string
    dimensions: number
    max_tokens: number
    /** True when the model needs distinct query/passage prefixes. */
    asymmetric: boolean
    note: string
  }
  embedding_models?: string[]
  reranker?: { key: string; min_score: number | null; model_id?: string }
  rerankers?: RerankerKey[]
  chunking?: {
    strategy: string
    strategies: string[]
    chunk_size: number
    overlap: number
  }
  defaults?: Record<string, unknown>
  failure_labels?: Record<FailureLabel, string>
}

/**
 * Everything the user can change per question.
 *
 * Held in the client and sent with each request rather than stored on
 * the server: the settings are an experiment knob, and two tabs
 * comparing "hybrid" against "dense only" must not fight over one piece
 * of shared server state.
 */
export interface Settings {
  mode: Mode
  topK: number
  /** Empty string means "whatever the server is configured with". */
  reranker: RerankerKey | ''
  useMmr: boolean
  mmrLambda: number
  useRewrite: boolean
  useHyde: boolean
  diagnose: boolean
  /** Empty array means every document. */
  sources: string[]
  pageMin: number | null
  pageMax: number | null
}

/** One labelled evaluation question, offered as a one-click probe. */
export interface GoldenCase {
  id: string
  question: string
  expected_pages: number[]
  answerable: boolean
  tags: string[]
}

/** Metric names are k-dependent ("hit_rate@1"), hence the index signature. */
export interface EvalMetricBlock {
  [metric: string]: number
}

export interface EvalRun {
  label: string
  k: number
  cases: number
  /** Keyed by stage: fused / reranked / final. */
  metrics: Record<string, EvalMetricBlock>
  latency_ms: { mean: number; p95: number }
  misses: string[]
  /** Found by fusion, then discarded by the reranker. */
  lost_in_rerank: string[]
  chunks_indexed?: number
}

/**
 * One frame of the SSE stream, discriminated on `type`.
 *
 * Order is guaranteed: `sources`, `trace`, then `token`* , then
 * optionally `diagnosis`, then `done` — or `error` at any point.
 */
export type ChatEvent =
  | {
      type: 'sources'
      standalone_question: string
      queries: Queries
      chunks: Source[]
    }
  | { type: 'trace'; trace: Trace }
  | { type: 'token'; text: string }
  | { type: 'diagnosis'; diagnosis: Diagnosis }
  | { type: 'done' }
  | { type: 'error'; message: string }
