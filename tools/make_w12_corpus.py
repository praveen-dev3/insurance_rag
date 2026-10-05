"""Render the Week 12 wordings to PDF so the real Week 3-4 pipeline can index them.

Run once:  python weeks.py make-w12-corpus

Writes to insurance_docs_w12/ rather than insurance_docs/: the Week 3-10
corpus, its golden sets and every number already reported against it stay
exactly as they were. The capstone points the same RagEngine at this folder
(see w12_retrieval.py), so what is measured is the shipped retrieval
pipeline over a corpus that happens to have two editions of the flood form,
not a toy keyword search standing in for it.
"""

import sys
from pathlib import Path

from data.w12_wordings import DOCUMENTS
from make_endorsements import write_pdf

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "insurance_docs_w12"


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for document in DOCUMENTS:
        path = write_pdf(document, OUTPUT_DIR)
        print(f"  wrote {path.name}")

    print(f"\n{len(DOCUMENTS)} wordings written to {OUTPUT_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
