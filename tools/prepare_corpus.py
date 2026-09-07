"""Guarantee the seven-document evaluation corpus exists, at a fixed path.

Why this exists rather than just reading insurance_docs/: that folder is a
working directory. Documents get dropped into it and cleared out of it
while other work is going on, and an evaluation whose corpus silently
changes between the baseline run and the after run is not an evaluation -
it is two unrelated measurements with a delta printed between them.

So the Week 4 experiment reads from eval/corpus/, which this script
builds and verifies:

  * the six endorsements are re-rendered from tools/data/endorsement_content.py,
    which is source-controlled text, so they are reproducible byte-for-byte
    in content even if the PDFs are deleted;
  * policy.pdf is copied from insurance_docs/ if present, and restored
    from git if not, because it is a tracked binary we cannot regenerate;
  * anything else in insurance_docs/ - a manual dropped in for unrelated
    work - is deliberately NOT copied, and is named in the output so the
    exclusion is on the record rather than silent.

Usage:  python tools/prepare_corpus.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.endorsement_content import ENDORSEMENTS  # noqa: E402
from make_endorsements import write_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "eval" / "corpus"
SOURCE = ROOT / "insurance_docs"

# The base wording. Tracked in git, not reproducible from source text, so
# it is restored rather than rebuilt.
BASE_WORDING = "policy.pdf"


def restore_base_wording(destination):
    """Copy policy.pdf into the corpus, from disk or from git."""

    target = destination / BASE_WORDING

    if target.exists():
        return "already present"

    live = SOURCE / BASE_WORDING

    if live.exists():
        shutil.copy2(live, target)
        return f"copied from {SOURCE.name}/"

    # Not on disk. It is tracked, so git still has it.
    try:
        blob = subprocess.run(
            ["git", "show", f"HEAD:insurance_docs/{BASE_WORDING}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout

        target.write_bytes(blob)

        return "restored from git HEAD"

    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        return f"MISSING and could not be restored: {error}"


def corpus_files():
    """The seven documents, in a stable order."""

    return sorted(CORPUS.glob("*.pdf"))


def prepare(verbose=True):

    CORPUS.mkdir(parents=True, exist_ok=True)

    for document in ENDORSEMENTS:
        write_pdf(document, CORPUS)

    status = restore_base_wording(CORPUS)

    files = corpus_files()

    if verbose:

        print(f"Corpus at {CORPUS.relative_to(ROOT)}:")

        for path in files:
            print(f"  {path.name}  ({path.stat().st_size:,} bytes)")

        print(f"\n{BASE_WORDING}: {status}")

        # Name what was left behind, so an excluded document is a stated
        # decision rather than an accident nobody notices.
        if SOURCE.exists():

            skipped = [
                path.name for path in sorted(SOURCE.glob("*.pdf"))
                if path.name != BASE_WORDING
                and path.name not in {d["file"] for d in ENDORSEMENTS}
            ]

            if skipped:
                print(
                    "\nDeliberately NOT in the evaluation corpus "
                    f"(present in {SOURCE.name}/ but out of scope for this "
                    f"task): {', '.join(skipped)}"
                )

    if len(files) != len(ENDORSEMENTS) + 1:
        raise SystemExit(
            f"Expected {len(ENDORSEMENTS) + 1} documents, found {len(files)}. "
            "The corpus is incomplete; refusing to evaluate against it."
        )

    return files


if __name__ == "__main__":
    prepare()
