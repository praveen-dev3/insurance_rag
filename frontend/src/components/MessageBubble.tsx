/**
 * One turn of the conversation.
 *
 * The assistant variant carries more than prose: the resolved question,
 * the sources it cited, a failure verdict when diagnosis is on, and a
 * way into the inspector. All of it is collapsed by default — the answer
 * is what the user came for, and the machinery is one click away.
 */

import type { Message } from '../types'
import { RichText } from './RichText'
import { SourceList } from './SourceList'

/** Server labels are snake_case; these are what a human should read. */
const VERDICT_LABEL: Record<string, string> = {
  ok: 'grounded',
  retrieval_failure: 'retrieval failure',
  generation_failure: 'generation failure',
  correct_refusal: 'correct refusal',
  missed_refusal: 'answered anyway',
}

interface MessageBubbleProps {
  message: Message
  /** Omitted for user turns, which have nothing to inspect. */
  onInspect?: (message: Message) => void
}

export function MessageBubble({ message, onInspect }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  // Sources arrive before the first token, so their presence — not their
  // length — is what says retrieval has finished. An empty array is a
  // real result: nothing cleared the relevance floor.
  const hasSources = !isUser && message.sources !== undefined

  return (
    <article className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className="avatar" aria-hidden>
        {isUser ? 'You' : 'AI'}
      </div>

      <div className="bubble">
        {/* Shown only when condensation rewrote a follow-up, so the user
            can see what was actually searched for. */}
        {message.standaloneQuestion && (
          <p className="rewritten" title="Follow-up resolved for retrieval">
            interpreted as: {message.standaloneQuestion}
          </p>
        )}

        {message.content ? (
          <div className="prose">
            <RichText text={message.content} />
            {/* Blinking caret only while tokens are still arriving. */}
            {message.streaming && <span className="caret" />}
          </div>
        ) : (
          // No text yet: retrieval is running, or the first token has
          // not landed. Dots rather than a spinner, because the wait is
          // short and a spinner reads as "something is wrong".
          message.streaming && (
            <div className="thinking">
              <span />
              <span />
              <span />
            </div>
          )
        )}

        {/* Errors sit below whatever text did arrive, so a stream that
            failed halfway keeps the part that worked. */}
        {message.error && <p className="error">{message.error}</p>}

        {message.diagnosis && (
          <p
            className={`verdict-pill ${message.diagnosis.label}`}
            title={message.diagnosis.reason || message.diagnosis.explanation}
          >
            {VERDICT_LABEL[message.diagnosis.label] ?? message.diagnosis.label}
          </p>
        )}

        {hasSources && (
          <div className="answer-tools">
            {/* <details> rather than local state: the browser handles the
                open/closed toggle, and each answer keeps its own. */}
            <details className="sources-block">
              <summary>
                Sources
                <span className="count">{message.sources!.length}</span>
              </summary>
              <SourceList sources={message.sources!} />
            </details>

            {message.trace && onInspect && (
              <button
                type="button"
                className="inspect-button"
                onClick={() => onInspect(message)}
              >
                Inspect retrieval
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  )
}
