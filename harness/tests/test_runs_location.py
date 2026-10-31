#!/usr/bin/env python3
"""Where runs land: a warning when a run or a re-score writes where git will not keep it, and validate's
note for finished runs already sitting there. The self-hosted triage runs went to data/runs-local, which
git ignores, and nothing said so.

python tests/test_runs_location.py
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _common, validate_tree
from evaluation_harness._check import check, summary

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    # the shape of the harness's own rules: deny every runs-* directory, re-allow one derived set
    (root / ".gitignore").write_text(
        "data/runs/*/*\n!data/runs/*/metrics.json\n"
        "data/runs-*/\n!data/runs-derived/\ndata/runs-derived/*/*\n!data/runs-derived/*/metrics.json\n"
        "data/runs-smoke*/\n",
        encoding="utf-8",
    )
    data = root / "data"
    for d in ("runs", "runs-derived", "runs-local", "runs-smoke-x", "runs-empty"):
        (data / d).mkdir(parents=True)
    for d in ("runs", "runs-derived", "runs-local", "runs-smoke-x"):
        (data / d / "arm_v1_20261031T000000Z").mkdir()
        (data / d / "arm_v1_20261031T000000Z" / "metrics.json").write_text(json.dumps({}), encoding="utf-8")

    for d, want in (("runs", False), ("runs-derived", False), ("runs-local", True), ("runs-smoke-x", True)):
        check(f"ignored_by_git: data/{d} is {want}", _common.ignored_by_git(data / d) is want)
    check("ignored_by_git: a directory not yet created", _common.ignored_by_git(data / "runs-new") is True)
    check(
        "ignored_by_git: outside a checkout is False",
        _common.ignored_by_git(Path(tempfile.gettempdir())) is False,
    )

    def warned(d: str) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _common.warn_if_ignored(data / d)
        return buf.getvalue()

    check("warn: data/runs is silent", warned("runs") == "")
    check("warn: a re-allowed derived set is silent", warned("runs-derived") == "")
    check("warn: a throwaway directory is silent (losing it is the point)", warned("runs-smoke-x") == "")
    out = warned("runs-local")
    check(
        "warn: an ignored results directory warns, and says where runs go",
        "WARNING" in out and "data/runs" in out,
        out,
    )

    old = validate_tree.DATA
    validate_tree.DATA = data
    try:
        validate_tree.notes.clear()
        validate_tree.note_uncommitted_runs()
        got = list(validate_tree.notes)
    finally:
        validate_tree.DATA = old
        validate_tree.notes.clear()
    check(
        "validate: one note, for the ignored directory that holds a finished run",
        len(got) == 1 and "runs-local" in got[0] and "1 finished run" in got[0],
        got,
    )

sys.exit(summary())
