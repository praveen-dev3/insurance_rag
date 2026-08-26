"""Endorsement provenance: what form a piece of text came from.

An exclusion code means nothing on its own. "E-17 is excluded absolutely"
is only actionable once you know it is E-17 *of Form HO-0304 ed. 03-24 on
the homeowners line* - the same two-character code is a different exclusion
on a different form, and a stale edition of the same form can say the
opposite of the current one. So provenance is not decoration here; it is
part of the answer, and it has to survive chunking.

This module does three things:

  * reads the four required fields off a rendered endorsement,
  * recognises the structural landmarks (clause headings, exclusion table
    headers, exclusion rows) that rag/chunking.py splits on,
  * strips the page furniture that would otherwise be chunked as content.

Nothing here is specific to one form. The patterns key off the shape the
endorsements are actually written in, and anything that does not match
degrades to UNSPECIFIED rather than raising - a corpus with one odd
document should ingest, not crash.
"""

import re
from dataclasses import dataclass, asdict

# Chroma rejects None in a metadata value, and an absent key silently
# fails an equality filter rather than erroring. Both failure modes are
# quiet, so unknown fields get an explicit marker instead.
UNSPECIFIED = "unspecified"

# The base wording predates the endorsement numbering scheme and carries
# no form header. Its policy line is still known, so record it rather than
# letting a real document sit in the index as entirely unclassified.
KNOWN_DOCUMENTS = {
    "policy.pdf": {
        "policy_line": "motor",
        "title": "Two-Wheeler Package Policy (base wording)",
    },
}


# ------------------------------------------------------------------
# PAGE FURNITURE
# ------------------------------------------------------------------

# The running header and footer repeat on every page. Left in, they are
# chunked as if they were content: the same 12 tokens recur across dozens
# of chunks, which both wastes budget and hands a keyword retriever a
# match on every page of a form. Stripped identically for every chunking
# strategy, so the comparison is unaffected.
_RUNNING_HEADER = re.compile(
    r"^FORM\s+\S+\s+ED\.\s+\S+\s+POLICY LINE:", re.IGNORECASE
)
_RUNNING_FOOTER = re.compile(r"^Form\s+\S+\s+ed\.\s+\S+\s*$", re.IGNORECASE)
_PAGE_NUMBER = re.compile(r"^Page\s+\d+\s*$", re.IGNORECASE)


def is_page_furniture(line):
    """True for a running header, running footer or page number."""

    stripped = line.strip()

    if not stripped:
        return False

    return bool(
        _RUNNING_HEADER.match(stripped)
        or _RUNNING_FOOTER.match(stripped)
        or _PAGE_NUMBER.match(stripped)
    )


def strip_page_furniture(text):
    """Drop header/footer lines, keeping everything else byte-identical."""

    return "\n".join(
        line for line in text.splitlines()
        if not is_page_furniture(line)
    )


# ------------------------------------------------------------------
# DOCUMENT-LEVEL METADATA
# ------------------------------------------------------------------

@dataclass
class DocumentMetadata:
    """The four fields the brief requires on every chunk, plus a title."""

    source_file: str
    form_number: str = UNSPECIFIED
    policy_line: str = UNSPECIFIED
    edition_date: str = UNSPECIFIED
    title: str = UNSPECIFIED

    def as_dict(self):
        return asdict(self)


# Front matter, e.g. "Form Number: HO-0304". Most reliable: it is set by
# the issuer rather than reconstructed from a filename.
_FRONT_MATTER = {
    "form_number": re.compile(r"^Form Number:\s*(\S+)", re.IGNORECASE),
    "edition_date": re.compile(r"^Edition Date:\s*(\S+)", re.IGNORECASE),
    "policy_line": re.compile(r"^Policy Line:\s*(.+?)\s*$", re.IGNORECASE),
    "title": re.compile(r"^ENDORSEMENT\s+\S+\s+\(ED\.\s+[^)]+\)\s*$"),
}

# Fallback: the running header carries the same three fields.
_HEADER_FIELDS = re.compile(
    r"^FORM\s+(?P<form>\S+)\s+ED\.\s+(?P<edition>\S+)\s+"
    r"POLICY LINE:\s*(?P<line>[A-Za-z_ ]+?)\s+EFFECTIVE:",
    re.IGNORECASE,
)

# Last resort: "HO-0304_water_damage_ed_03-24.pdf".
_FILENAME = re.compile(
    r"^(?P<form>[A-Z]{2}-\d{4}).*?_ed_(?P<edition>\d{2}-\d{2})", re.IGNORECASE
)


def extract_document_metadata(source_file, first_page_text):
    """
    Read the four required fields off the front page of a document.

    Three sources are tried in descending order of trust: issuer front
    matter, the running header, then the filename. A document matching
    none of them still gets a record - with UNSPECIFIED fields and its
    source_file intact - because the brief's failure condition is a chunk
    with no source_file, and that must not be reachable.
    """

    metadata = DocumentMetadata(source_file=source_file)

    known = KNOWN_DOCUMENTS.get(source_file, {})

    for field, value in known.items():
        setattr(metadata, field, value)

    lines = (first_page_text or "").splitlines()

    # 1. Front matter.
    for line in lines:

        stripped = line.strip()

        for field, pattern in _FRONT_MATTER.items():

            if field == "title":
                continue

            match = pattern.match(stripped)

            if match and getattr(metadata, field) in (UNSPECIFIED, ""):
                setattr(metadata, field, match.group(1).strip())

    # 2. Running header.
    if metadata.form_number == UNSPECIFIED:

        for line in lines:

            match = _HEADER_FIELDS.match(line.strip())

            if match:
                metadata.form_number = match.group("form")
                metadata.edition_date = match.group("edition")

                if metadata.policy_line == UNSPECIFIED:
                    metadata.policy_line = match.group("line").strip().lower()

                break

    # 3. Filename.
    if metadata.form_number == UNSPECIFIED:

        match = _FILENAME.match(source_file)

        if match:
            metadata.form_number = match.group("form").upper()
            metadata.edition_date = match.group("edition")

    # The document title is the line after the "ENDORSEMENT <form>" banner.
    if metadata.title == UNSPECIFIED:

        for index, line in enumerate(lines):

            if _FRONT_MATTER["title"].match(line.strip()):

                if index + 1 < len(lines):
                    metadata.title = lines[index + 1].strip()

                break

    metadata.policy_line = (metadata.policy_line or UNSPECIFIED).lower()

    return metadata


# ------------------------------------------------------------------
# STRUCTURAL LANDMARKS
# ------------------------------------------------------------------

# "3. EXCLUSIONS APPLICABLE TO WATER DAMAGE" - a top-level clause heading.
CLAUSE_HEADING = re.compile(r"^(?P<number>\d{1,2})\.\s+(?P<title>[A-Z][A-Z0-9 ,\-/()]{4,})\s*$")

# "3.1 We do not cover loss described in ..." - a numbered sub-clause.
SUBCLAUSE = re.compile(r"^(?P<number>\d{1,2}\.\d{1,2})\s+(?=\S)")

# "EXCLUSION TABLE 3.1 - WATER DAMAGE EXCLUSIONS"
TABLE_HEADING = re.compile(
    r"^EXCLUSION TABLE\s+(?P<number>\d{1,2}\.\d{1,2})\s*[-–]\s*(?P<title>.+?)\s*$",
    re.IGNORECASE,
)

# The table's column header line.
TABLE_COLUMNS = re.compile(r"^CODE\s+EXCLUSION AND DISPOSITION\s*$", re.IGNORECASE)

# "E-17  Constant or repeated seepage ..." - the first line of a row.
EXCLUSION_ROW = re.compile(r"^(?P<code>E-\d{2})\s{2,}(?=\S)")

# "Note: Exclusion E-17 is directed at ..."
TABLE_NOTE = re.compile(r"^Note:\s*", re.IGNORECASE)


def exclusion_code(line):
    """The code this line starts an exclusion row for, or None."""

    match = EXCLUSION_ROW.match(line)

    return match.group("code") if match else None


def clause_of(line):
    """
    The clause identifier this line opens, or None if it opens none.

    Both "3. EXCLUSIONS ..." and "3.1 We do not cover ..." open a clause;
    a continuation line inside either opens nothing, and inherits whatever
    clause was already in effect.
    """

    stripped = line.strip()

    if not stripped:
        return None

    heading = CLAUSE_HEADING.match(stripped)

    if heading:
        return heading.group("number")

    table = TABLE_HEADING.match(stripped)

    if table:
        return table.group("number")

    subclause = SUBCLAUSE.match(stripped)

    if subclause:
        return subclause.group("number")

    return None


def clause_label(line):
    """A human-readable label for a clause heading, for citation display."""

    stripped = line.strip()

    heading = CLAUSE_HEADING.match(stripped)

    if heading:
        return f"{heading.group('number')}. {heading.group('title').title()}"

    table = TABLE_HEADING.match(stripped)

    if table:
        return f"Exclusion Table {table.group('number')}"

    subclause = SUBCLAUSE.match(stripped)

    if subclause:
        return f"Clause {subclause.group('number')}"

    return UNSPECIFIED
