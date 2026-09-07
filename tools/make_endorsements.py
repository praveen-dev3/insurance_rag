"""Render the six endorsements in tools/data/endorsement_content.py to PDF.

Run once:  python tools/make_endorsements.py

Two rendering decisions matter for what happens downstream:

  * Exclusion tables are drawn as monospace text, one logical row per
    flowable, rather than as a reportlab Table. A real Table lays each cell
    out as its own text run, and pypdf then extracts the grid in an order
    that interleaves columns - which would mean the corpus was scrambled
    before any chunker got to see it, and the chunking comparison would be
    measuring the PDF extractor instead. Monospace rows extract verbatim.

  * Every page carries a running header with the form number, edition date
    and policy line. That is what rag/metadata.py reads back out, and it is
    also what makes an orphaned exclusion row recoverable in principle -
    the point of the exercise is that the naive chunker still loses it.
"""

import sys
import textwrap
from pathlib import Path

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data.endorsement_content import ENDORSEMENTS  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "insurance_docs"

# Monospace column width, in characters, that fits the frame at 7.5pt
# Courier. Descriptions are wrapped to this by hand so the extracted text
# has predictable line breaks.
MONO_WIDTH = 96
MONO_INDENT = 6


# ------------------------------------------------------------------
# STYLES
# ------------------------------------------------------------------

BODY = ParagraphStyle(
    "body",
    fontName="Times-Roman",
    fontSize=9.5,
    leading=13,
    alignment=TA_JUSTIFY,
    spaceAfter=7,
)

HEADING = ParagraphStyle(
    "heading",
    fontName="Times-Bold",
    fontSize=10.5,
    leading=14,
    spaceBefore=11,
    spaceAfter=5,
)

TITLE = ParagraphStyle(
    "title",
    fontName="Times-Bold",
    fontSize=13,
    leading=17,
    spaceAfter=3,
)

META = ParagraphStyle(
    "meta",
    fontName="Times-Roman",
    fontSize=9,
    leading=12.5,
    spaceAfter=2,
)

TABLE_TITLE = ParagraphStyle(
    "table_title",
    fontName="Times-Bold",
    fontSize=9.5,
    leading=13,
    spaceBefore=8,
    spaceAfter=4,
)

MONO = ParagraphStyle(
    "mono",
    fontName="Courier",
    fontSize=7.5,
    leading=9.6,
    spaceAfter=3.5,
)

MONO_HEAD = ParagraphStyle(
    "mono_head",
    fontName="Courier-Bold",
    fontSize=7.5,
    leading=9.6,
    spaceAfter=4,
)

NOTE = ParagraphStyle(
    "note",
    fontName="Times-Italic",
    fontSize=9,
    leading=12.5,
    spaceBefore=5,
    spaceAfter=7,
    leftIndent=14,
)


# ------------------------------------------------------------------
# ROW RENDERING
# ------------------------------------------------------------------

def render_row(code, description, disposition):
    """
    One exclusion row as a block of monospace lines.

    The code leads the first line and continuation lines are indented, so
    a row is visually and textually one unit. Disposition is folded into
    the same block rather than into a separate column, because a chunker
    that keeps the code but drops the disposition has kept nothing useful.
    """

    prefix = f"{code}  "
    body_width = MONO_WIDTH - len(prefix)

    lines = textwrap.wrap(description.strip().rstrip(".") + ".", body_width)

    rendered = [prefix + lines[0]]
    rendered.extend(" " * len(prefix) + line for line in lines[1:])

    for index, line in enumerate(
        textwrap.wrap(
            f"Disposition: {disposition.strip().rstrip('.')}.",
            body_width - MONO_INDENT
        )
    ):
        rendered.append(" " * (len(prefix) + MONO_INDENT) + line)

    return "\n".join(rendered)


def render_table(payload):
    """An exclusion table: title, column header, then one flowable per row."""

    flowables = [
        Paragraph(payload["title"], TABLE_TITLE),
        Preformatted(
            "CODE  EXCLUSION AND DISPOSITION",
            MONO_HEAD
        ),
    ]

    for code, description, disposition in payload["rows"]:
        # KeepTogether so a row's continuation lines cannot be split by a
        # page break. The chunker is allowed to make that mistake; the
        # renderer is not.
        flowables.append(
            KeepTogether(
                Preformatted(
                    render_row(code, description, disposition),
                    MONO
                )
            )
        )

    if payload["note"]:
        flowables.append(Paragraph(f"Note: {payload['note']}", NOTE))

    return flowables


# ------------------------------------------------------------------
# DOCUMENT
# ------------------------------------------------------------------

def running_header(document):
    """Draw the form identity on every page."""

    def draw(canvas, doc):

        canvas.saveState()

        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(
            0.9 * inch,
            LETTER[1] - 0.62 * inch,
            f"FORM {document['form_number']}   ED. {document['edition_date']}   "
            f"POLICY LINE: {document['policy_line'].upper()}   "
            f"EFFECTIVE: {document['effective']}"
        )

        canvas.setLineWidth(0.4)
        canvas.line(
            0.9 * inch,
            LETTER[1] - 0.70 * inch,
            LETTER[0] - 0.9 * inch,
            LETTER[1] - 0.70 * inch
        )

        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            0.9 * inch,
            0.58 * inch,
            f"Form {document['form_number']} ed. {document['edition_date']}"
        )
        canvas.drawRightString(
            LETTER[0] - 0.9 * inch,
            0.58 * inch,
            f"Page {canvas.getPageNumber()}"
        )

        canvas.restoreState()

    return draw


def build_story(document):
    """The flowables for one endorsement, front matter first."""

    story = [
        Paragraph(
            f"ENDORSEMENT {document['form_number']} "
            f"(ED. {document['edition_date']})",
            TITLE
        ),
        Paragraph(document["title"], TITLE),
        Spacer(1, 6),
        Paragraph(f"Form Number: {document['form_number']}", META),
        Paragraph(f"Edition Date: {document['edition_date']}", META),
        Paragraph(f"Policy Line: {document['policy_line']}", META),
        Paragraph(f"Effective Date: {document['effective']}", META),
        Paragraph(f"Supersedes: {document['supersedes']}", META),
        Spacer(1, 10),
        Paragraph(
            "ATTACHING TO AND FORMING PART OF THE POLICY SHOWN IN THE "
            "DECLARATIONS. ALL OTHER TERMS AND CONDITIONS REMAIN UNCHANGED.",
            BODY
        ),
        Spacer(1, 4),
    ]

    for kind, payload in document["blocks"]:

        if kind == "h":
            story.append(Paragraph(payload, HEADING))
        elif kind == "p":
            story.append(Paragraph(payload, BODY))
        else:
            story.extend(render_table(payload))

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            f"END OF FORM {document['form_number']} "
            f"ED. {document['edition_date']}.",
            BODY
        )
    )

    return story


def write_pdf(document, output_dir):

    path = output_dir / document["file"]

    template = BaseDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.85 * inch,
        bottomMargin=0.8 * inch,
        title=f"{document['form_number']} - {document['title']}",
        author="Underwriting",
    )

    frame = Frame(
        template.leftMargin,
        template.bottomMargin,
        template.width,
        template.height,
        id="body"
    )

    template.addPageTemplates([
        PageTemplate(
            id="endorsement",
            frames=[frame],
            onPage=running_header(document)
        )
    ])

    template.build(build_story(document))

    return path


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for document in ENDORSEMENTS:
        path = write_pdf(document, OUTPUT_DIR)
        print(f"Wrote {path.name}")

    print(f"\n{len(ENDORSEMENTS)} endorsements written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
