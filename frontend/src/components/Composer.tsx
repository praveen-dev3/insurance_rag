/**
 * The message input.
 *
 * A textarea rather than an input: policy questions run long, and a
 * one-line box that scrolls sideways hides what you typed. Enter sends
 * and Shift+Enter breaks the line, which is what chat interfaces have
 * trained everyone to expect.
 */

import { useEffect, useRef } from 'react'

interface ComposerProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  onStop: () => void
  /** True while an answer streams: Send becomes Stop. */
  busy: boolean
  /** True when the index is not ready; nothing can be asked yet. */
  disabled: boolean
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  disabled,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Grow with the content instead of scrolling inside a one-line box.
  // Height is reset to auto first so the box can also shrink when text
  // is deleted — scrollHeight never decreases on its own.
  useEffect(() => {
    const element = textareaRef.current
    if (!element) return

    element.style.height = 'auto'
    // Capped so a pasted wall of text cannot swallow the transcript.
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [value])

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        // A real <form> so the browser's implicit submit works; the
        // default page reload is what has to be suppressed.
        event.preventDefault()
        onSubmit()
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        rows={1}
        disabled={disabled}
        // The placeholder doubles as the explanation for why the input
        // is dead while the index loads.
        placeholder={
          disabled
            ? 'The index is not ready yet…'
            : 'Ask about coverage, exclusions, premiums…'
        }
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          // Enter sends; Shift+Enter is a newline.
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            onSubmit()
          }
        }}
      />

      {/* Send and Stop occupy the same slot: only one is ever valid, and
          swapping them keeps the button under the cursor. */}
      {busy ? (
        <button type="button" className="stop" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="send" disabled={disabled || !value.trim()}>
          Send
        </button>
      )}
    </form>
  )
}
