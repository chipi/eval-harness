#!/usr/bin/env python3
"""`evh judge-score --dry-run` says the real run will refuse when a stored verdict is of another judge definition.

    python tests/test_judge_dry_run_refusal.py

No network, no key, no money: the dry run calls nothing. A throwaway project holds two arms' runs,
one item, and a stored verdict whose judge_fp is not the scorer's judge now (its prices were edited).
"""

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["EVAL_STORE"] = "files"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _runfix
import _runfix
import _runstore
import yaml
from evaluation_harness import _outputs, ops
from evaluation_harness import judge_score as js
from evaluation_harness._check import check, summary
from evaluation_harness.ops import cli as ops_cli

HERE = Path(__file__).resolve().parents[1]
ARMS = ["arm0_v1", "arm1_v1"]


def dry(extra: list[str] | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = ops_cli.main(
            ops.OPS["judge-score"],
            [
                "--dataset-id",
                "ds",
                "--scorer",
                "judge-dry-test-v1",
                "--unvalidated",
                "--dry-run",
                *(extra or []),
            ],
        )
    return rc, out.getvalue(), err.getvalue()


with tempfile.TemporaryDirectory() as tmp:
    td = Path(tmp)
    with _runstore._InProject(td / "proj") as data:
        sc = yaml.safe_load((HERE / "data" / "scorers" / "judge-summ-v1.yaml").read_text(encoding="utf-8"))
        sc.update(scorer_id="judge-dry-test-v1", dataset_id="ds", arms_match="_v1")
        sc.pop("supersedes", None)
        (data / "scorers").mkdir(parents=True)
        (data / "scorers" / "judge-dry-test-v1.yaml").write_text(yaml.safe_dump(sc), encoding="utf-8")
        pf = data / "scorers" / "examples" / "summeval-judging" / "prompt.txt"
        pf.parent.mkdir(parents=True)
        pf.write_text(
            (HERE.parent / "examples" / "summeval-judging" / "prompt.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (data / "datasets").mkdir()
        (data / "datasets" / "ds.json").write_text(
            json.dumps({"dataset_id": "ds", "items": [{"item_id": "itemA"}]}), encoding="utf-8"
        )
        (data / "materialized" / "ds").mkdir(parents=True)
        (data / "materialized" / "ds" / "itemA.txt").write_text("An article about itemA.", encoding="utf-8")
        for name in ARMS:
            d = data / "runs" / f"{name}_2026"
            _outputs.writer(d).add("itemA", f"summary by {name}")
            _runfix.put_run(
                data,
                {
                    "system_id": name,
                    "run_id": f"{name}_2026",
                    "dataset_id": "ds",
                    "created_at": "2026",
                    "primary_metric": "coverage",
                    "scores": {"coverage": 0.3},
                    "metric_kinds": {"coverage": "quality"},
                    "params": {"family": "x"},
                    "fingerprint": {"hash": "abc", "arm": {"config_id": name}},
                },
                [{"item_id": "itemA", "coverage": 0.3}],
            )
        repo_sets = sorted(p.name for p in (HERE / "data" / "judging-sets").glob("*.json"))
        saved = (js.DATA, js.MATERIALIZED, js.SCORERS, js.SETS, js.VERDICTS)
        js.DATA, js.MATERIALIZED = data, data / "materialized"
        js.SCORERS, js.SETS, js.VERDICTS = data / "scorers", data / "judging-sets", data / "judge-verdicts"
        try:
            rc, out, err = dry()
            check("a clean dry run: exit 0 and an estimate", rc == 0 and "DRY RUN" in out, out + err)
            check("a clean dry run: no refusal foreseen", "refuse" not in out.lower(), out)

            sid = next(ln.split()[-1] for ln in out.splitlines() if ln.startswith("judging set"))
            rec = js.verdict_path(js.VERDICTS / "judge-dry-test-v1" / sid, "gemma_l", "itemA", "primary", 0)
            rec.parent.mkdir(parents=True)
            rec.write_text(
                json.dumps({"judge_fp": "0" * 16, "set_id": sid, "output": "{}"}), encoding="utf-8"
            )

            rc, out, err = dry()
            head = out.split("DRY RUN")[0]
            check(
                "a stale record: the dry run still estimates and exits 0 (a note, as run's dry run gives)",
                rc == 0 and "DRY RUN" in out,
                out + err,
            )
            check(
                "a stale record: before the estimate it says the real run refuses, which judge, and the way out",
                "WARNING" in head
                and "will refuse" in head
                and "gemma_l" in head
                and "different judge definition" in head
                and "new scorer version" in head
                and "judged again" in head,
                head,
            )
            check("a stale record: names the path of one stored record", rec.name in head, head)

            rc2, out2, err2 = dry(["--json"])
            check(
                "--json: the warning is in the answer's warnings",
                rc2 == 0 and "will refuse" in out2,
                out2 + err2,
            )

            rc3: object = None
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    rc3 = ops_cli.main(
                        ops.OPS["judge-score"],
                        [
                            "--dataset-id",
                            "ds",
                            "--scorer",
                            "judge-dry-test-v1",
                            "--unvalidated",
                            "--no-calls",
                        ],
                    )
            except SystemExit as exc:
                rc3 = exc.code
            check("the real run on the same record still refuses (exit 1)", rc3 not in (0, None), str(rc3))
            check(
                "the refused run writes no judging set: not the test project's, not this repository's",
                not list((data / "judging-sets").glob("*.json"))
                and sorted(p.name for p in (HERE / "data" / "judging-sets").glob("*.json")) == repo_sets,
                [p.name for p in (data / "judging-sets").glob("*.json")],
            )
        finally:
            js.DATA, js.MATERIALIZED, js.SCORERS, js.SETS, js.VERDICTS = saved

sys.exit(summary())
