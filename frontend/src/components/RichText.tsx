import { Fragment, type ReactNode } from 'react'

/**
 * Renders the small subset of Markdown the model actually emits:
 * paragraphs, bullet/numbered lists, **bold**, *italic* and `code`.
 *
 * A full Markdown dependency would be dead weight for this, and parsing
 * here means partial text arriving mid-stream still renders sensibly.
 */

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*|"[^"\n]{3,}")/g

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    const key = `${keyPrefix}-${index}`

    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }

    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }

    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={key}>{part.slice(1, -1)}</em>
    }

    // Quoted spans are how the model returns verbatim policy wording.
    if (part.startsWith('"') && part.endsWith('"') && part.length > 4) {
      return (
        <q key={key} className="quote">
          {part.slice(1, -1)}
        </q>
      )
    }

    return <Fragment key={key}>{part}</Fragment>
  })
}

const BULLET = /^\s*([-*•]|\d+[.)])\s+/

export function RichText({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []

  let paragraph: string[] = []
  let listItems: string[] = []
  let ordered = false

  const flushParagraph = () => {
    if (paragraph.length === 0) return

    const key = `p-${blocks.length}`
    blocks.push(<p key={key}>{renderInline(paragraph.join(' '), key)}</p>)
    paragraph = []
  }

  const flushList = () => {
    if (listItems.length === 0) return

    const key = `l-${blocks.length}`
    const items = listItems.map((item, index) => (
      <li key={`${key}-${index}`}>{renderInline(item, `${key}-${index}`)}</li>
    ))

    blocks.push(
      ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>,
    )

    listItems = []
  }

  for (const line of lines) {
    if (!line.trim()) {
      flushParagraph()
      flushList()
      continue
    }

    const match = line.match(BULLET)

    if (match) {
      flushParagraph()
      ordered = /\d/.test(match[1])
      listItems.push(line.replace(BULLET, ''))
      continue
    }

    flushList()
    paragraph.push(line.trim())
  }

  flushParagraph()
  flushList()

  return <>{blocks}</>
}
