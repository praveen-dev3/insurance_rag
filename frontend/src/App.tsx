/**
 * The application shell: sidebar (settings) | chat | inspector.
 *
 * All conversation state lives here rather than in a store. There is one
 * conversation, it is not persisted, and every piece of it is read by at
 * least two of the three panes — a store would add indirection without
 * removing any coupling.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchGoldenSet, fetchHealth, reindex, streamChat } from './api'
import { Composer } from './components/Composer'
import { InspectionPanel } from './components/InspectionPanel'
import { MessageBubble } from './components/MessageBubble'
import { Sidebar } from './components/Sidebar'
import type { GoldenCase, Health, Message, Settings } from './types'
import './App.css'

/** Used only if /api/golden-set is unavailable. The last one is
 *  deliberately out of scope, so the refusal path stays one click away. */
const FALLBACK_SUGGESTIONS = [
  'What is covered under this policy?',
  'What are the reasons my claim might get rejected?',
  'What is the chassis number of the bike?',
  'What is the maternity benefit under this policy?',
]

/**
 * Defaults match the server's, and every optional stage starts off.
 * Someone opening the app should see the configuration the measured
 * numbers in the README describe, not a pile of experiments.
 */
const INITIAL_SETTINGS: Settings = {
  mode: 'hybrid',
  topK: 3,
  reranker: '',
  useMmr: false,
  mmrLambda: 0.7,
  useRewrite: false,
  useHyde: false,
  diagnose: false,
  sources: [],
  pageMin: null,
  pageMax: null,
}

// A module-level counter rather than crypto.randomUUID: ids only need to
// be unique within one page load, and a monotonic counter keeps React's
// keys stable and debuggable.
let messageCounter = 0
const nextId = () => `m${++messageCounter}`

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [settings, setSettings] = useState<Settings>(INITIAL_SETTINGS)
  const [busy, setBusy] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [inspectOpen, setInspectOpen] = useState(false)
  // The message the inspector is showing. Null means "follow the newest".
  const [inspected, setInspected] = useState<Message | null>(null)
  const [golden, setGolden] = useState<GoldenCase[]>([])

  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchHealth()
      .then((result) => {
        setHealth(result)

        // Adopt the server's top-k so the slider agrees with what the
        // backend would have done unasked.
        if (result.top_k) {
          setSettings((current) => ({ ...current, topK: result.top_k! }))
        }
      })
      .catch((error: Error) =>
        // A failed health check is itself a state to render: the composer
        // stays disabled and the sidebar shows why.
        setHealth({ ready: false, error: error.message }),
      )

    // The golden set doubles as a set of one-click probes whose expected
    // pages are already known, which makes trying to break retrieval
    // easy. Failing to load it is not worth surfacing — the fallback
    // suggestions cover it.
    fetchGoldenSet()
      .then((payload) => setGolden(payload.cases))
      .catch(() => setGolden([]))
  }, [])

  // Follow the answer as it streams in.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages])

  /**
   * Update the in-flight assistant message.
   *
   * Every SSE event patches the same (last) message, so this is the one
   * mutation path during streaming. It also keeps the inspector pointed
   * at the live answer — unless the user pinned an older one by clicking
   * its Inspect button, in which case that choice wins.
   */
  const patchLast = useCallback((patch: (message: Message) => Message) => {
    setMessages((current) => {
      if (current.length === 0) return current

      const updated = [...current]
      const patched = patch(updated[updated.length - 1])
      updated[updated.length - 1] = patched

      setInspected((pinned) =>
        pinned === null || pinned.id === patched.id ? patched : pinned,
      )

      return updated
    })
  }, [])

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim()

      if (!trimmed || busy || !health?.ready) return

      // The turns already on screen are the context for this question;
      // capture them before the new pair is appended, or the server
      // would receive the question twice — once as history.
      const history = messages.filter((message) => !message.error)

      setDraft('')
      setBusy(true)
      setSettingsOpen(false)

      const assistantId = nextId()

      // Both bubbles are appended up front so the user sees their own
      // message immediately and the assistant's thinking dots appear
      // without waiting for the first byte.
      setMessages((current) => [
        ...current,
        { id: nextId(), role: 'user', content: trimmed },
        { id: assistantId, role: 'assistant', content: '', streaming: true },
      ])

      // Unpin the inspector so it follows this new answer.
      setInspected(null)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        for await (const event of streamChat({
          question: trimmed,
          history,
          settings,
          signal: controller.signal,
        })) {
          if (event.type === 'sources') {
            patchLast((message) => ({
              ...message,
              sources: event.chunks,
              // Only worth showing when condensation actually changed
              // something; otherwise it is noise on every turn.
              standaloneQuestion:
                event.standalone_question !== trimmed
                  ? event.standalone_question
                  : undefined,
            }))
          } else if (event.type === 'trace') {
            patchLast((message) => ({ ...message, trace: event.trace }))
          } else if (event.type === 'token') {
            patchLast((message) => ({
              ...message,
              content: message.content + event.text,
            }))
          } else if (event.type === 'diagnosis') {
            patchLast((message) => ({
              ...message,
              diagnosis: event.diagnosis,
            }))
          } else if (event.type === 'error') {
            patchLast((message) => ({ ...message, error: event.message }))
          }
        }
      } catch (error) {
        // Aborting is a deliberate user action, not a failure to report.
        if ((error as Error).name !== 'AbortError') {
          patchLast((message) => ({
            ...message,
            error: (error as Error).message,
          }))
        }
      } finally {
        // Runs on success, error and abort alike — otherwise a stopped
        // answer would keep its blinking caret forever.
        patchLast((message) => ({ ...message, streaming: false }))
        abortRef.current = null
        setBusy(false)
      }
    },
    [busy, health, messages, patchLast, settings],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const clear = useCallback(() => {
    // Abort first: a stream left running would keep patching messages
    // back into the array we are about to empty.
    abortRef.current?.abort()
    setMessages([])
    setInspected(null)
  }, [])

  const runReindex = useCallback(async () => {
    setReindexing(true)

    try {
      const stats = await reindex()

      // The endpoint returns fresh stats, so merge rather than refetch.
      setHealth((current) => ({
        ...(current ?? { error: null }),
        ...stats,
        ready: true,
      }))
    } catch (error) {
      setHealth({ ready: false, error: (error as Error).message })
    } finally {
      setReindexing(false)
    }
  }, [])

  const updateSettings = useCallback(
    (patch: Partial<Settings>) =>
      setSettings((current) => ({ ...current, ...patch })),
    [],
  )

  // Three answerable probes and one out-of-scope one, so the empty state
  // demonstrates both what the app does and what it refuses to do.
  const suggestions =
    golden.length > 0
      ? [
          ...golden.filter((item) => item.answerable).slice(0, 3),
          ...golden.filter((item) => !item.answerable).slice(0, 1),
        ].map((item) => item.question)
      : FALLBACK_SUGGESTIONS

  return (
    <div className={`app ${inspectOpen ? 'with-inspect' : ''}`}>
      <Sidebar
        health={health}
        settings={settings}
        onChange={updateSettings}
        onReindex={runReindex}
        onClear={clear}
        reindexing={reindexing}
        busy={busy}
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />

      {/* Backdrop for the mobile settings drawer. A button rather than a
          div so dismissing it works from the keyboard too. */}
      {settingsOpen && (
        <button
          type="button"
          className="scrim"
          aria-label="Close settings"
          onClick={() => setSettingsOpen(false)}
        />
      )}

      <main className="chat">
        {/* Hidden on desktop by CSS; the only way to reach the settings
            drawer on a phone. */}
        <header className="topbar">
          <button
            type="button"
            className="topbar-button"
            onClick={() => setSettingsOpen(true)}
          >
            ☰ Settings
          </button>

          <span className="topbar-title">Insurance RAG</span>

          <button
            type="button"
            className="topbar-button"
            onClick={clear}
            disabled={busy}
          >
            New
          </button>
        </header>

        {/* Restates the active pipeline, because a surprising answer is
            usually explained by a setting left on in the sidebar. */}
        <div className="chat-toolbar">
          <span className="pipeline-summary">
            {settings.mode}
            {settings.reranker && ` · ${settings.reranker}`}
            {settings.useMmr && ' · MMR'}
            {settings.useRewrite && ' · rewrite'}
            {settings.useHyde && ' · HyDE'}
            {settings.sources.length > 0 &&
              ` · ${settings.sources.length} doc filter`}
          </span>

          <button
            type="button"
            className={`inspect-toggle ${inspectOpen ? 'on' : ''}`}
            onClick={() => setInspectOpen(!inspectOpen)}
          >
            {inspectOpen ? 'Hide inspector' : 'Inspect'}
          </button>
        </div>

        <div className="transcript" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="empty">
              <h2>Ask your policy documents anything.</h2>
              <p>
                Every answer is grounded in the indexed PDFs and cites the
                document and page it came from. Open the inspector to see
                which retriever found each chunk.
              </p>

              <div className="suggestions">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => send(suggestion)}
                    disabled={!health?.ready}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                onInspect={(target) => {
                  // Pins the inspector to this answer, so it stops
                  // following the newest one.
                  setInspected(target)
                  setInspectOpen(true)
                }}
              />
            ))
          )}
        </div>

        <div className="composer-wrap">
          <Composer
            value={draft}
            onChange={setDraft}
            onSubmit={() => send(draft)}
            onStop={stop}
            busy={busy}
            disabled={!health?.ready}
          />

          <p className="disclaimer">
            Answers come only from the indexed documents.
          </p>
        </div>
      </main>

      <InspectionPanel
        message={inspected}
        open={inspectOpen}
        onClose={() => setInspectOpen(false)}
      />
    </div>
  )
}
