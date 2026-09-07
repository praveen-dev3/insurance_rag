/**
 * Every call to the FastAPI server.
 *
 * All paths are relative, so the same build works whether it is served
 * by uvicorn itself or by Vite's dev server proxying /api — there is no
 * base-URL constant to configure and no environment-specific bundle.
 */

import type {
  ChatEvent,
  EvalRun,
  GoldenCase,
  Health,
  Message,
  Settings,
} from './types'

/**
 * Pull a useful message out of a failed response.
 *
 * FastAPI puts its message in `detail`; anything that failed before
 * reaching FastAPI (a proxy, a 502) will not be JSON at all, hence the
 * catch and the status-code fallback.
 */
async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    return body.detail ?? `Request failed (${response.status})`
  } catch {
    return `Request failed (${response.status})`
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)

  if (!response.ok) {
    throw new Error(await readError(response))
  }

  return response.json()
}

export const fetchHealth = () => getJson<Health>('/api/health')

export const fetchGoldenSet = () =>
  getJson<{ cases: GoldenCase[] }>('/api/golden-set')

/**
 * The evaluator writes one JSON file per command, and a sweep file holds
 * an array of runs while a single run holds one object — so the caller
 * has to handle both shapes. See MetricsView in InspectionPanel.
 */
export const fetchEvalResults = () =>
  getJson<{
    runs: Record<string, { command: string; result: EvalRun | EvalRun[] }>
  }>('/api/eval-results')

/** Rebuilds both indexes server-side; slow, and returns fresh stats. */
export async function reindex(): Promise<Health> {
  const response = await fetch('/api/reindex', { method: 'POST' })

  if (!response.ok) {
    throw new Error(await readError(response))
  }

  return response.json()
}

interface ChatOptions {
  question: string
  history: Message[]
  settings: Settings
  signal?: AbortSignal
}

/**
 * Translate UI state into the server's request shape.
 *
 * Filters are omitted entirely when empty rather than sent as empty
 * values: `{sources: []}` would otherwise read as "search no documents"
 * instead of "do not filter".
 */
function requestBody({ question, history, settings }: ChatOptions) {
  const filters: Record<string, unknown> = {}

  if (settings.sources.length > 0) filters.sources = settings.sources
  if (settings.pageMin !== null) filters.page_min = settings.pageMin
  if (settings.pageMax !== null) filters.page_max = settings.pageMax

  return {
    question,
    mode: settings.mode,
    top_k: settings.topK,
    // Empty string means "server default", which the server expresses
    // as null.
    reranker: settings.reranker || null,
    use_mmr: settings.useMmr,
    mmr_lambda: settings.mmrLambda,
    use_rewrite: settings.useRewrite,
    use_hyde: settings.useHyde,
    diagnose: settings.diagnose,
    filters: Object.keys(filters).length > 0 ? filters : null,
    // Only role and content travel; the local ids, traces and diagnoses
    // are UI bookkeeping the server has no use for.
    history: history.map((message) => ({
      role: message.role,
      content: message.content,
    })),
  }
}

/**
 * POST the question and yield Server-Sent Events as they arrive.
 *
 * EventSource is the usual way to consume SSE, but it can only issue GET
 * requests, and this endpoint needs a JSON body carrying the history and
 * settings. So the stream is read straight off the fetch body instead.
 *
 * SSE frames are separated by a blank line, and a frame can be split
 * across network chunks (or several frames can arrive in one) — hence
 * the buffer and the loop, rather than parsing each chunk on its own.
 */
export async function* streamChat(
  options: ChatOptions,
): AsyncGenerator<ChatEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // Lets the Stop button abort the request rather than merely hiding
    // its output, so the server stops generating too.
    signal: options.signal,
    body: JSON.stringify(requestBody(options)),
  })

  if (!response.ok || !response.body) {
    throw new Error(await readError(response))
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()

    if (done) break

    // `stream: true` keeps a multi-byte character split across two
    // network chunks from being decoded as two replacement characters.
    buffer += decoder.decode(value, { stream: true })

    let boundary = buffer.indexOf('\n\n')

    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')

      // A frame may legally carry several `data:` lines, which the spec
      // says to concatenate.
      const payload = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('')

      if (!payload) continue

      try {
        yield JSON.parse(payload) as ChatEvent
      } catch {
        // A malformed frame is not worth killing the whole stream over —
        // the answer already on screen stays, and the next frame may
        // well be fine.
      }
    }
  }
}
