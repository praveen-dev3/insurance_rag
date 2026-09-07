"""Shared plumbing for the four week runners.

Nothing here measures anything. It is only the scaffold that run_task_d,
run_bonus, run_week4 and run_w6 each used to repeat verbatim: put the repo
root on sys.path, open the persistent Chroma client, read a JSON case
file, drop a throwaway collection, and write a result artefact.

Importing this module is what puts the repo root on sys.path, so it has to
be imported before any `rag.*` import in a runner.
"""

import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent

for _entry in (str(TOOLS_DIR), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


def chroma_client(path=None):
    """Open the persistent Chroma client the index-building runners share.

    chromadb and rag.config are imported inside the call so that a runner
    which never touches an index does not pay for them at import time.
    """

    import chromadb

    from rag.config import CHROMA_PATH

    return chromadb.PersistentClient(path=path or CHROMA_PATH)


def drop_collection(client, name):
    """Delete a throwaway collection, tolerating one that never existed.

    Cleanup must never be the thing that fails a run whose measurements
    have already been taken.
    """

    try:
        client.delete_collection(name)
    except Exception:
        pass


def read_json(path):

    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload, default=str):
    """Write one result artefact, creating its directory.

    `default` is exposed rather than hard-coded because two of the Week 6
    artefacts were written without a fallback serialiser, and a fallback
    turns "this payload is not serialisable" from a crash into a string.
    """

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, default=default),
        encoding="utf-8",
    )

    return path


def make_saver(output_dir):
    """The `save(payload, name)` that Week 3 and Week 4 both defined."""

    def save(payload, name):

        path = write_json(Path(output_dir) / name, payload)

        print(f"  wrote {path}")

        return path

    return save


def positional_stage(default="all"):
    """The bare positional both Week 3 and Week 4 accept, as in

        python tools/run_task_d.py retrieval
    """

    return sys.argv[1] if len(sys.argv) > 1 else default
