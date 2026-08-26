"""Chunking strategies.

Four strategies. The first three do the same final step - pack small
pieces of text into token-budgeted windows with overlap - and differ only
in how small those pieces start out:

  fixed      every token is its own piece, so windows land wherever the
             budget runs out, mid-sentence included. The baseline.
  recursive  split on structure first (blank line, line, sentence,
             clause, word) and never break a piece that already fits, so
             a window ends at a boundary a human would recognise.
  sentence   pieces are sentences, and the overlap is counted in
             sentences rather than tokens, so consecutive chunks share
             whole thoughts.

The fourth does not pack blindly at all:

  structure  splits on the document's own landmarks - form header, clause
             heading, exclusion table - and treats an exclusion row as
             atomic. Every chunk is stamped with the form number, edition
             date and the clause it sits under, and a chunk continuing a
             table repeats that table's header. So an exclusion row can
             never be retrieved without the form that scopes it.

The distinction matters because "recursive" is structure-aware about
*prose* and completely blind to *tables*. Its coarsest separator is a
blank line, and an exclusion table has none - it is thirty consecutive
non-blank lines. So recursive falls through to splitting on ". " and cuts
the table wherever 220 tokens runs out, which is how E-17 ends up in a
chunk that never names HO-0304.

Pieces carry the page they came from, so a chunk assembled from pieces
either side of a page break still cites the exact range it covers.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

import tiktoken

from rag.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHUNK_STRATEGY,
    SENTENCE_OVERLAP,
)
from rag.metadata import (
    CLAUSE_HEADING,
    TABLE_COLUMNS,
    TABLE_HEADING,
    TABLE_NOTE,
    UNSPECIFIED,
    clause_label,
    clause_of,
    exclusion_code,
)

CHUNK_STRATEGIES = ("fixed", "recursive", "sentence", "structure")

# Tried in order; the first one that breaks the text into pieces small
# enough to fit the budget wins. Ordered coarse to fine so structure is
# preserved wherever possible.
SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " "]

# Sentence end followed by whitespace, or a line break. Abbreviations
# common in policy documents are not treated as sentence ends.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_ABBREVIATIONS = ("Rs.", "No.", "Sec.", "Cl.", "Mr.", "Ms.", "Dr.", "vs.")

_encoding = None


def get_encoding():

    global _encoding

    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")

    return _encoding


def count_tokens(text):
    return len(get_encoding().encode(text))


@dataclass
class Piece:
    """A unit of text small enough to be packed, and the page it is on."""

    text: str
    page: int
    tokens: int


# ============================================================
# SPLITTERS
# ============================================================

def _token_pieces(text, page):
    """Every token as its own piece - the flat-window baseline."""

    encoding = get_encoding()

    return [
        Piece(text=encoding.decode([token_id]), page=page, tokens=1)
        for token_id in encoding.encode(text)
    ]


def _recursive_split(text, max_tokens, separators=None):
    """
    Split only as finely as needed to get under the token budget.

    A paragraph that already fits is returned whole; only oversized ones
    are split further, and then by the coarsest separator that helps.
    """

    separators = SEPARATORS if separators is None else separators

    if count_tokens(text) <= max_tokens:
        return [text] if text.strip() else []

    if not separators:
        # Out of separators: fall back to a hard token cut so a single
        # unbroken run of characters cannot exceed the budget.
        encoding = get_encoding()
        token_ids = encoding.encode(text)

        return [
            encoding.decode(token_ids[start:start + max_tokens])
            for start in range(0, len(token_ids), max_tokens)
        ]

    separator = separators[0]
    parts = text.split(separator)

    pieces = []

    for index, part in enumerate(parts):

        # Put the separator back, so joining the pieces reproduces the
        # original text rather than silently deleting punctuation.
        if index < len(parts) - 1:
            part = part + separator

        if not part.strip():
            continue

        pieces.extend(
            _recursive_split(part, max_tokens, separators[1:])
        )

    return pieces


def _sentence_split(text):
    """Split into sentences, keeping common abbreviations intact."""

    # Protect abbreviations from the sentence regex, then restore them.
    guarded = text

    for index, abbreviation in enumerate(_ABBREVIATIONS):
        guarded = guarded.replace(abbreviation, f"\x00{index}\x00")

    sentences = _SENTENCE_SPLIT.split(guarded)

    restored = []

    for sentence in sentences:

        for index, abbreviation in enumerate(_ABBREVIATIONS):
            sentence = sentence.replace(f"\x00{index}\x00", abbreviation)

        if sentence.strip():
            restored.append(sentence.strip())

    return restored


# ============================================================
# PACKING
# ============================================================

def _pack(pieces, chunk_size, overlap_tokens=None, overlap_pieces=None):
    """
    Greedily fill windows of `chunk_size` tokens, then step back by the
    requested overlap so consecutive chunks share context.

    Overlap is expressed either in tokens (fixed, recursive) or in whole
    pieces (sentence). Exactly one of the two is used.
    """

    chunks = []
    window = []
    window_tokens = 0

    def flush():

        if not window:
            return

        text = "".join(piece.text for piece in window)

        if text.strip():

            pages = [piece.page for piece in window]

            chunks.append({
                "text": text,
                "page_start": min(pages),
                "page_end": max(pages),
            })

    for piece in pieces:

        # A single oversized piece still has to go somewhere; emit the
        # current window first so it is not diluted.
        if window_tokens + piece.tokens > chunk_size and window:

            flush()

            if overlap_pieces:
                carry = window[-overlap_pieces:]
            else:
                carry = []
                carried_tokens = 0

                for previous in reversed(window):

                    if carried_tokens + previous.tokens > (overlap_tokens or 0):
                        break

                    carry.insert(0, previous)
                    carried_tokens += previous.tokens

            window = carry
            window_tokens = sum(item.tokens for item in carry)

        window.append(piece)
        window_tokens += piece.tokens

    flush()

    return chunks


# ============================================================
# STRATEGIES: fixed / recursive / sentence
# ============================================================

def _pieces_for(strategy, pages):
    """Turn a document's pages into packable pieces, page tags intact."""

    pieces = []

    for page in pages:

        # The trailing newline keeps the last line of a page from being
        # glued to the first line of the next one.
        text = page["text"] + "\n"

        if strategy == "fixed":
            pieces.extend(_token_pieces(text, page["page"]))
            continue

        if strategy == "recursive":
            parts = _recursive_split(text, CHUNK_SIZE)
        else:
            parts = [
                sentence + " "
                for sentence in _sentence_split(text)
            ]

        for part in parts:
            pieces.append(
                Piece(text=part, page=page["page"], tokens=count_tokens(part))
            )

    return pieces


# ============================================================
# STRATEGY: structure
# ============================================================

@dataclass
class Unit:
    """
    One indivisible piece of an endorsement.

    kind is one of:
      heading       a top-level clause heading, e.g. "3. EXCLUSIONS ..."
      table_header  "EXCLUSION TABLE 3.1 - ..." plus its column line
      row           one exclusion row and its continuation lines
      note          the italic note under a table
      para          anything else
    """

    kind: str
    text: str
    page_start: int
    page_end: int
    clause: str
    label: str
    codes: tuple = ()

    @property
    def tokens(self):
        return count_tokens(self.text)


def _line_stream(pages):
    """Every line of a document with the page it came from."""

    for page in pages:
        for line in page["text"].splitlines():
            yield line, page["page"]


def _parse_units(pages):
    """
    Walk a document's lines and group them into indivisible units.

    A unit ends when the next line opens something new: a clause heading,
    a table header, another exclusion row, or a blank line inside prose.
    Continuation lines of an exclusion row - which are indented, and carry
    the Disposition - are folded into that row's unit, because a code
    without its disposition is worse than useless.
    """

    units = []

    clause = UNSPECIFIED
    label = UNSPECIFIED

    current = None

    def close():

        nonlocal current

        if current is not None and current.text.strip():
            units.append(current)

        current = None

    def open_unit(kind, line, page, codes=()):

        nonlocal current

        close()

        current = Unit(
            kind=kind,
            text=line,
            page_start=page,
            page_end=page,
            clause=clause,
            label=label,
            codes=codes,
        )

    for line, page in _line_stream(pages):

        stripped = line.strip()

        if not stripped:
            # A blank line ends a paragraph but not a table: the rows are
            # consecutive, so a blank here means prose.
            if current is not None and current.kind == "para":
                close()
            continue

        heading = CLAUSE_HEADING.match(stripped)
        table = TABLE_HEADING.match(stripped)
        code = exclusion_code(line)

        if heading:
            clause = heading.group("number")
            label = clause_label(stripped)
            open_unit("heading", stripped, page)
            close()
            continue

        if table:
            clause = table.group("number")
            label = clause_label(stripped)
            open_unit("table_header", stripped, page)
            continue

        if TABLE_COLUMNS.match(stripped):
            # Belongs with the table header it follows.
            if current is not None and current.kind == "table_header":
                current.text += "\n" + stripped
                current.page_end = page
            continue

        if code:
            open_unit("row", line.rstrip(), page, codes=(code,))
            continue

        if TABLE_NOTE.match(stripped):
            open_unit("note", stripped, page)
            continue

        # A continuation line: indented text under an exclusion row, or a
        # wrapped line of prose. Either way it belongs to the open unit.
        if current is not None and current.kind in ("row", "note"):
            current.text += "\n" + line.rstrip()
            current.page_end = page
            continue

        opened = clause_of(stripped)

        if opened and current is not None and current.kind == "para":
            close()

        if opened:
            clause = opened
            label = clause_label(stripped)

        if current is None or current.kind != "para":
            open_unit("para", stripped, page)
        else:
            current.text += " " + stripped
            current.page_end = page

    close()

    return units


def _provenance(metadata, unit, table_header):
    """
    The context banner stamped on the top of every structure chunk.

    This is the whole point of the strategy. A chunk of exclusion rows
    that does not name its form is not an answer to anything - the same
    code means something different on another form, and a superseded
    edition can say the opposite. Repeating the table header on a
    continuation chunk costs about forty tokens and is what stops row
    E-17 being retrieved as an orphan.
    """

    lines = []

    if metadata.get("form_number", UNSPECIFIED) != UNSPECIFIED:
        lines.append(
            f"FORM {metadata['form_number']} "
            f"ED. {metadata['edition_date']} | "
            f"POLICY LINE: {metadata['policy_line'].upper()} | "
            f"{metadata.get('title', '')}".rstrip(" |")
        )
    else:
        lines.append(f"SOURCE: {metadata['source_file']}")

    if unit.label not in (UNSPECIFIED, ""):
        lines.append(f"SECTION: {unit.label}")

    if table_header is not None:
        lines.append(table_header.text)

    return "\n".join(lines)


def _structure_chunks(pages, metadata, chunk_size):
    """
    Pack units into chunks that respect the document's own boundaries.

    Three rules, in priority order:

      1. A chunk never spans two top-level clauses. A heading closes the
         open chunk before it opens the next.
      2. An exclusion row is atomic and is never separated from its table
         header or its form number - if a row will not fit, the chunk is
         flushed and the table header is repeated at the top of the next.
      3. Only then does the token budget apply.

    Rule 3 last is the difference from every other strategy here, where
    the budget comes first and structure is whatever survives it.
    """

    units = _parse_units(pages)

    chunks = []

    window = []
    table_header = None
    pending_heading = None

    def flush():

        nonlocal window

        if not window:
            return

        banner = _provenance(metadata, window[0], table_header)

        body = "\n".join(unit.text for unit in window)

        pages_covered = [unit.page_start for unit in window]
        pages_covered += [unit.page_end for unit in window]

        codes = []

        for unit in window:
            codes.extend(unit.codes)

        chunks.append({
            "text": f"{banner}\n\n{body}",
            "page_start": min(pages_covered),
            "page_end": max(pages_covered),
            "clause": window[0].clause,
            "clause_label": window[0].label,
            "exclusion_codes": codes,
        })

        window = []

    def budget():
        """Tokens left, after reserving room for the repeated banner."""

        banner_tokens = count_tokens(
            _provenance(metadata, window[0] if window else units[0], table_header)
        )

        return max(chunk_size - banner_tokens, 60)

    for unit in units:

        if unit.kind == "heading":
            # Rule 1: a new top-level clause starts a new chunk.
            flush()
            table_header = None
            pending_heading = unit
            continue

        if unit.kind == "table_header":
            flush()
            table_header = unit
            pending_heading = None
            continue

        # A paragraph too large to ever fit is split on prose boundaries
        # rather than dropped. Rows are never in this branch: a single
        # exclusion row is far below any sane budget.
        if unit.kind != "row" and unit.tokens > chunk_size:

            flush()

            for part in _recursive_split(unit.text, budget()):

                window = [
                    Unit(
                        kind=unit.kind,
                        text=part,
                        page_start=unit.page_start,
                        page_end=unit.page_end,
                        clause=unit.clause,
                        label=unit.label,
                    )
                ]
                flush()

            pending_heading = None
            continue

        current_tokens = sum(item.tokens for item in window)

        if window and current_tokens + unit.tokens > budget():
            # Rule 2: flush rather than split. The banner - including the
            # table header - is re-emitted on the next chunk by flush().
            flush()

        if not window and pending_heading is not None:
            window.append(pending_heading)
            pending_heading = None

        window.append(unit)

    flush()

    return chunks


# ============================================================
# ENTRY POINT
# ============================================================

def detect_clause_in_text(text):
    """
    The first clause a chunk of text sits under, found after the fact.

    The packing strategies do not track structure while they chunk, so
    their chunks are labelled by scanning the result. It is best-effort by
    construction: a chunk that begins mid-table has no clause marker in it
    at all, and gets UNSPECIFIED - which is itself the finding.
    """

    for line in text.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        opened = clause_of(stripped)

        if opened:
            return opened, clause_label(stripped)

    return UNSPECIFIED, UNSPECIFIED


def _collect_codes(text):
    """Every exclusion code whose row opens inside this chunk."""

    return [
        code
        for code in (exclusion_code(line) for line in text.splitlines())
        if code
    ]


def create_chunks(documents, strategy=None, chunk_size=None, overlap=None,
                  on_progress=None):
    """
    Split every document into chunks, each carrying its provenance.

    Documents are processed one source at a time, and pieces stream
    across page boundaries within a source, so a clause interrupted by a
    page break stays in one chunk.

    Every chunk leaves here with source_file, form_number, policy_line and
    edition_date attached, whichever strategy produced it. The strategies
    differ in what is in the chunk *text*, not in whether it is labelled -
    a filter on policy_line has to work identically across a comparison,
    or the comparison is measuring two things at once.
    """

    strategy = strategy or CHUNK_STRATEGY
    chunk_size = chunk_size or CHUNK_SIZE
    overlap = CHUNK_OVERLAP if overlap is None else overlap

    if strategy not in CHUNK_STRATEGIES:
        raise ValueError(
            f"Unknown chunk strategy '{strategy}'. "
            f"Expected one of {CHUNK_STRATEGIES}."
        )

    pages_by_source = defaultdict(list)

    for document in documents:
        pages_by_source[document["source"]].append(document)

    chunks = []

    for source in sorted(pages_by_source):

        pages = sorted(
            pages_by_source[source],
            key=lambda page: page["page"]
        )

        # Every page of a source carries the same document metadata; the
        # first one is as good as any.
        metadata = pages[0].get("metadata") or {"source_file": source}

        if strategy == "structure":
            packed = _structure_chunks(pages, metadata, chunk_size)

        else:
            pieces = _pieces_for(strategy, pages)

            if strategy == "sentence":
                packed = _pack(
                    pieces,
                    chunk_size,
                    overlap_pieces=max(SENTENCE_OVERLAP, 0)
                )
            else:
                packed = _pack(pieces, chunk_size, overlap_tokens=overlap)

            for chunk in packed:
                clause, label = detect_clause_in_text(chunk["text"])
                chunk["clause"] = clause
                chunk["clause_label"] = label
                chunk["exclusion_codes"] = _collect_codes(chunk["text"])

        for chunk in packed:
            chunk["source"] = source
            chunk["metadata"] = metadata
            chunks.append(chunk)

    message = (
        f"Created {len(chunks)} chunks "
        f"[strategy={strategy}, size={chunk_size}, overlap={overlap}]."
    )

    print(message)

    if on_progress is not None:
        on_progress(message)

    return chunks
