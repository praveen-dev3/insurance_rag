"""One entry point for every week's tooling.

    python weeks.py --help          list every command, grouped by week
    python weeks.py <command> ...   run one, forwarding all its flags

Each command below is the same code that `python tools/<module>.py` runs,
reached through a name instead of a path. Both spellings still work and
both produce identical output, so anything a write-up records as
`python tools/run_w6.py --stage judge --judge judge_v2` reproduces
verbatim.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
TOOLS_DIR = REPO_ROOT / "tools"

# name -> (module, entry function, does the module parse its own flags?)
#
# `parses_args` is False for the scripts that read sys.argv positionally or
# take no arguments at all. For those, `--help` is answered here from the
# module docstring rather than forwarded, because forwarding it to a runner
# that treats any positional as a stage name would start a paid run.
COMMANDS = {
    # ---- week 3: chunking, filters, and the first cited answers ----
    "make-endorsements": ("make_endorsements", "main", False),
    "chunk-report": ("chunk_report", "main", False),
    "run-task-d": ("run_task_d", "main", False),
    "run-bonus": ("run_bonus", "main", False),

    # ---- week 4: labelled failures, and the one change that fixed them ----
    "prepare-corpus": ("prepare_corpus", "prepare", False),
    "build-golden": ("build_w4_golden", "main", False),
    "run-week4": ("run_week4", "main", False),

    # ---- week 5: a week of traffic, sampled and coded into a taxonomy ----
    "w5-traffic": ("w5_traffic", "main", True),
    "w5-sample": ("w5_sample", "main", True),
    "w5-read": ("w5_read", "main", True),
    "w5-taxonomy": ("w5_taxonomy", "main", True),
    "w5-replay": ("w5_replay", "main", True),

    # ---- week 6: 25 cases, an LLM judge, agreement with hand labels ----
    "run-w6": ("run_w6", "main", True),
    "w6-label": ("w6_label", "main", True),
    "w6-ragas": ("w6_ragas", "main", True),

    # ---- week 7: the Week 5 prediction, checked with a number ----
    "w7-retrieval-delta": ("w7_retrieval_delta", "main", False),

    # ---- week 7, task set D: race the claims agent against a workflow ----
    "w7d-race": ("w7d_race", "main", True),

    # ---- week 8, task set D: score the claims agent's path, not just its answer ----
    "w8d-eval": ("w8d_run", "main", True),

    # ---- week 9, task set D: bolt the claims-system MCP server on by config alone ----
    "w9d-eval": ("w9d_run", "main", True),

    # ---- anytime ----
    "resolve-chunk": ("resolve_chunk", "main", True),
}

GROUPS = (
    ("w3", "chunking, filters, and the first cited answers",
     ("make-endorsements", "chunk-report", "run-task-d", "run-bonus")),
    ("w4", "labelled failures, and the one change that fixed them",
     ("prepare-corpus", "build-golden", "run-week4")),
    ("w5", "a week of traffic, sampled and coded into a taxonomy",
     ("w5-traffic", "w5-sample", "w5-read", "w5-taxonomy", "w5-replay")),
    ("w6", "25 cases, an LLM judge, and agreement with hand labels",
     ("run-w6", "w6-label", "w6-ragas")),
    ("w7", "the Week 5 prediction, checked with a number",
     ("w7-retrieval-delta",)),
    ("w7d", "race the claims agent against a fixed workflow",
     ("w7d-race",)),
    ("w8d", "score the claims agent's path, not just its answer",
     ("w8d-eval",)),
    ("w9d", "bolt the claims-system MCP server on by config alone",
     ("w9d-eval",)),
    ("util", "anytime",
     ("resolve-chunk",)),
)

HELP_FLAGS = ("-h", "--help", "help")


def tolerate_console_encoding():
    """Some docstrings carry an em dash, and cp1252 consoles refuse it."""

    for stream in (sys.stdout, sys.stderr):

        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def docstring(module):
    """Read a module's docstring without importing it.

    Parsing beats importing here: `weeks.py --help` would otherwise pay for
    chromadb, torch and reportlab just to print sixteen lines of text, and
    would fail outright on any module whose dependency is not installed.
    """

    source = (TOOLS_DIR / f"{module}.py").read_text(encoding="utf-8")

    return ast.get_docstring(ast.parse(source)) or ""


def summary(module):
    """The one-line description: the first line of the module docstring."""

    return docstring(module).strip().splitlines()[0] if docstring(module) else ""


def print_help():

    print(__doc__.strip())
    print()

    for prefix, blurb, names in GROUPS:

        print(f"{prefix} - {blurb}")

        for name in names:
            module = COMMANDS[name][0]
            print(f"  {name:<18} {summary(module)}")

        print()

    print("Every command also still runs by its old path, unchanged:")
    print("  python tools/<module>.py ...    (see the names in tools/)")


def resolve(name):
    """Accept a command by either spelling: run-w6 or run_w6."""

    wanted = name.replace("_", "-")

    return COMMANDS.get(wanted)


def main(argv=None):

    tolerate_console_encoding()

    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in HELP_FLAGS:
        print_help()
        return 0

    name = argv[0]
    entry = resolve(name)

    if entry is None:
        print(f"weeks.py: unknown command '{name}'\n", file=sys.stderr)
        print_help()
        return 2

    module_name, function_name, parses_args = entry
    rest = argv[1:]

    # A runner that reads sys.argv[1] as a stage name would treat --help as
    # "not the retrieval-only stage" and start a full paid run. Answer here.
    if not parses_args and any(flag in HELP_FLAGS for flag in rest):
        print(docstring(module_name).strip())
        return 0

    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))

    module = __import__(module_name)

    # The underlying scripts read sys.argv directly, so hand them an argv
    # that looks like the one they would have been launched with. argv[0]
    # becomes the argparse `prog`, so their usage line names this command.
    sys.argv = [f"weeks.py {name}"] + rest

    return getattr(module, function_name)()


if __name__ == "__main__":
    sys.exit(main())
