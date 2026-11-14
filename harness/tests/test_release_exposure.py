#!/usr/bin/env python3
"""The deployment's copy of the data carries a sealed side's exposure register (RFC-032 step 6).

    python tests/test_release_exposure.py

In a throwaway git project ($0, offline), in whichever store the suite runs in: a dataset with a seal and an exposure
row for one of its items, copied by `_release.py copy-data`. With the copy as the project (files, as a deployment's
is), `evh exposure` counts the item as read: the catalog and the inspector leave exposed items out of a sealed side's
scores by this register, and the copy did not have it (a deployed catalog showed the full number). The copy's rows
are the project's, whole: ids, who, what; on a dataset whose text is hidden, what a person wrote of the item is not
published (its rows, ids and who stay).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-relexp-"))
dest = Path(tempfile.mkdtemp(prefix="evh-relexp-copy-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-release-exposure")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_ACTOR"):
    env.pop(k, None)
ROW = {
    "item_id": "b",
    "what": "a comparison",
    "at": "2026-11-12T10:00:00Z",
    "by": "person:ana",
    "recorded_at": "2026-11-12T10:00:00Z",
    "recorded_by": "person:ana",
    "source": "hand",
}


def run(*cmd, e):
    return subprocess.run(
        list(cmd), cwd=proj, env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL
    )


try:
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    (proj / "data").mkdir()
    _runstore.write_text(proj, "project.yaml", f"format: {_format.FORMAT}\n")
    items = [{"item_id": i, "source_path": f"{i}.txt", "source_sha256": "0" * 64} for i in "abc"]
    rec = {"dataset_id": "held_v1", "version": "", "items": items, "sealed": {"at": "2026-11-10T09:00:00Z"}}
    _runstore.write_text(proj, "datasets/held_v1.json", json.dumps(rec))
    _runstore.write_text(proj, "exposure/held_v1.jsonl", json.dumps(ROW) + "\n")
    _runstore.write_text(
        proj, "datasets/held_h.json", json.dumps({**rec, "dataset_id": "held_h", "text": "hidden"})
    )
    _runstore.write_text(proj, "exposure/held_h.jsonl", json.dumps(ROW) + "\n")

    r = run(sys.executable, str(HERE / "cli.py"), "exposure", "--dataset-id", "held_v1", "--json", e=env)
    got = json.loads(r.stdout)["result"]["values"]["exposure"][0] if r.returncode == 0 else {}
    check("setup: in the project the item is read", got.get("exposed") == 1, (r.stdout + r.stderr)[-300:])

    copy = dest / "data"
    r = run(sys.executable, str(HERE / "_release.py"), "copy-data", str(proj / "data"), str(copy), e=env)
    check("copy-data", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check(
        "the copy holds the register, row for row",
        (copy / "exposure" / "held_v1.jsonl").is_file()
        and [json.loads(x) for x in (copy / "exposure" / "held_v1.jsonl").read_text().splitlines()] == [ROW],
        sorted(str(p.relative_to(copy)) for p in copy.rglob("*") if p.is_file())[:20],
    )
    from evaluation_harness._release import HIDDEN_WHAT

    hid = copy / "exposure" / "held_h.jsonl"
    check(
        "a hidden dataset's register is copied with what was written of its item replaced, ids and who kept",
        hid.is_file()
        and [json.loads(x) for x in hid.read_text().splitlines()] == [{**ROW, "what": HIDDEN_WHAT}],
        hid.read_text() if hid.is_file() else "no copy",
    )
    on_copy = dict(env, EVAL_HOME=str(dest), EVAL_STORE="files")
    r = run(sys.executable, str(HERE / "cli.py"), "exposure", "--dataset-id", "held_v1", "--json", e=on_copy)
    got = json.loads(r.stdout)["result"]["values"]["exposure"][0] if r.returncode == 0 else {}
    check(
        "with the copy as the project, the exposed item is counted read (a score leaves it out)",
        got.get("exposed") == 1 and got.get("reads") == 1,
        (r.stdout + r.stderr)[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(dest, ignore_errors=True)

sys.exit(summary())
