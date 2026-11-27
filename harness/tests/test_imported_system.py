#!/usr/bin/env python3
"""A system whose runs are imported (`evh import-run`) and that names no adapter of its own (0.8.3, B1-B3).

    python tests/test_imported_system.py

In a throwaway project, in whichever store the suite runs in: `evh model-onboard --system` refuses a system whose calls
would go to the bundled demo adapter, and writes nothing; `evh arm-smoke` on a dataset that is not materialized is the
`not-materialized` refusal, not a traceback; `evh model-show` and the catalog's model page find a model's arms through the
systems that name it, imported runs included, and the same arms.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _format
from evaluation_harness import catalog_build as cb
from evaluation_harness._check import check, summary
from evaluation_harness.catalog_adapter import HarnessAdapter

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli, _model_records
import _cli
import _model_records
import _runstore

proj = Path(tempfile.mkdtemp(prefix="evh-imported-system-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-imported-system")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_ACTOR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
STORE = os.environ.get("EVAL_STORE") or "files"


def evh(*args):
    return _cli.run(proj, env, *args)


def out(r):
    return r.stdout + r.stderr


try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "config.yaml").write_text(f"store: {STORE}\n", encoding="utf-8")
    for n, t in (("a", "billing"), ("b", "shipping")):
        _runstore.write_text(proj, f"sources/toy/{n}.txt", t)
    r = evh("dataset-create", "--dataset-id", "toy_v1", "--source-dir", "data/sources/toy")
    check("setup: a dataset", r.returncode == 0, out(r))
    (proj / "scores.jsonl").write_text(
        '{"item_id": "a", "wer": 0.1}\n{"item_id": "b", "wer": 0.2}\n', encoding="utf-8"
    )
    _model_records.put(
        proj,
        {
            "model_id": "m2a-model-200",
            "kind": "ml",
            "aliases": ["m2a"],
            "deployments": [{"id": "lab", "where": "lab"}],
        },
    )
    _runstore.write_text(
        proj, "systems/m2a_b.yaml", "system_id: m2a_b\nmodel_record: m2a-model-200\ndeployment: lab\n"
    )
    r = evh(
        "import-run", "--dataset-id", "toy_v1", "--system-id", "m2a_b", "--scores", "scores.jsonl",
        "--primary-metric", "wer", "--asc", "--build-ref", "t", "--source", "test", "--scorer-id", "wer",
        "--reference-id", "gold/toy_v1",
    )  # fmt: skip
    check("setup: an imported run of the system", r.returncode == 0, out(r))

    # B3: the arms of a model are found through the systems that name it
    r = evh("model-show", "m2a-model-200")
    check(
        "B3 model-show: an imported run's arm is listed under the model its system names",
        r.returncode == 0 and "arms: none" not in out(r) and "m2a_b" in out(r),
        out(r)[-700:],
    )
    site = proj / "site"
    with _runstore._InProject(proj):
        A = HarnessAdapter(proj / "data")
        cb.build(A, site)
        listed = [a for x in A.models() if x["record"]["model_id"] == "m2a-model-200" for a in x["arms"]]
    page = site / "models" / "m2a-model-200.html"
    check(
        "B3 the catalog's model page lists the same arm, from the same source",
        listed == ["runs/toy_v1/m2a_b"]
        and page.is_file()
        and "m2a_b" in page.read_text(encoding="utf-8")
        and "No arm uses this model yet" not in page.read_text(encoding="utf-8"),
        listed,
    )

    # B1: a system whose calls would go to the bundled demo adapter is not onboarded through it
    r = evh("model-onboard", "--model-id", "m2a-model-200", "--system", "m2a_b", "--dataset", "toy_v1")
    check(
        "B1 model-onboard: a system with no adapter of its own is refused (not-configured), not onboarded by the demo adapter",
        r.returncode != 0
        and "ONBOARD PASS" not in out(r)
        and "ERROR (not-configured)" in out(r)
        and "bundled demo adapter" in out(r),
        out(r)[-700:],
    )
    check(
        "B1 model-onboard: nothing is written into the deployment",
        not (_model_records.view(proj, "m2a-model-200").get("deployments") or [{}])[0].get("onboarding"),
    )

    # B2: a dataset that is not materialized is refused as `evh run` refuses it
    shutil.rmtree(proj / "data" / "materialized", ignore_errors=True)
    r = evh("arm-smoke", "--system", "m2a_b", "--dataset", "toy_v1")
    check(
        "B2 arm-smoke: a dataset that is not materialized is the not-materialized refusal",
        r.returncode != 0
        and "FileNotFoundError" not in out(r)
        and "Traceback" not in out(r)
        and "ERROR (not-materialized)" in out(r),
        out(r)[-700:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
