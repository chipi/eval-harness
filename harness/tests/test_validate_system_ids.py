#!/usr/bin/env python3
"""validate notes a system id that contains the dataset id of one of its own runs (what a system is run for is
the run's, not the system's), and the note changes nothing about the exit code.

    python tests/test_validate_system_ids.py

In a throwaway project ($0, offline), in whichever store the suite runs in: one system whose id embeds its run's
dataset id as a whole token, one that does not, one whose id is a dataset id, one that embeds a dataset it has
no run on, and one that carries the dataset id inside a longer word.
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

proj = Path(tempfile.mkdtemp(prefix="evh-validate-sysid-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-validate-system-ids")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_ACTOR"):
    env.pop(k, None)


def validate():
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), "validate"],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )


def run(i, system, dataset):
    base = {"dataset_id": dataset, "system_id": system, "build": {"ref": "test"}}
    _runstore.make_run(
        proj / "data" / "runs",
        f"r{i}",
        base,
        scores=[
            {
                "scorer": "s",
                "first": True,
                "rows": [{"item_id": "a"}],
                "metrics": {
                    **base,
                    "run_id": f"r{i}",
                    "created_at": "2026-11-12T10:00:00Z",
                    "scores": {},
                    "n_items": 1,
                },
            }
        ],
    )
    _runstore.write_text(
        proj,
        f"datasets/{dataset}.json",
        json.dumps(
            {
                "dataset_id": dataset,
                "version": "1.0",
                "description": dataset,
                "created_at": "2026-11-10T00:00:00Z",
                "items": [{"item_id": "a", "source_path": "a.txt", "source_sha256": "0" * 64}],
            }
        ),
    )


def note_of(out):
    return next((ln for ln in out.splitlines() if "dataset id of one of their own runs" in ln), "")


try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    with _runstore._InProject(proj):
        run(1, "plain_v1", "curated_smoke_v2")
        run(2, "imp_curated_smoke_v2__vs_opus", "curated_smoke_v2")
        run(3, "silver_x__curated_smoke_v2", "curated_smoke_v2")
        run(4, "ds_v1", "ds_v1")  # the system id is the dataset id
        run(5, "imp_other_v3_run", "curated_smoke_v2")  # names a dataset it has no run on
        run(6, "mydsx_v1", "ds")  # "ds" only inside a longer word
        run(7, "plain_v1", "other_v3")
        run(8, "curated_smoke_v2_arm", "curated_smoke_v2")  # at the start
    r = validate()
    out = r.stdout + r.stderr
    note = note_of(out)
    check(
        "a system id with its run's dataset id in it is noted",
        "imp_curated_smoke_v2__vs_opus" in note,
        out[-600:],
    )
    check(
        "the note names three, then 'and N more'",
        "curated_smoke_v2_arm, ds_v1, imp_curated_smoke_v2__vs_opus, and 1 more" in note
        and "silver_x" not in note,
        note,
    )
    check("the note counts them", "4 system id(s)" in note, note)
    check(
        "a system that does not embed its dataset, a dataset it has no run on, a longer word: not noted",
        "plain_v1" not in note and "imp_other_v3_run" not in note and "mydsx_v1" not in note,
        note,
    )
    check("the note cites what a system is run for", "run's, not the system's" in note, note)
    check(
        "a note changes no exit code and fails nothing",
        r.returncode == 0 and "FAIL" not in out and "VALIDATION PASSED" in out,
        f"exit {r.returncode}: {out[-400:]}",
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
