#!/usr/bin/env python3
"""`evh cost-report` counts what judging cost (RFC-032 step 7). $0, offline.

    python tests/test_cost_judging.py

A judge's calls are no run: each verdict under data/judge-verdicts/<scorer>/<judging set>/<judge>/ records its own
cost_usd and whether the provider reported it (`cost_known`). The report ends with what judging cost per scorer, judging
set and judge: `billed` from the verdicts the provider billed, `estimated` from the ones priced on the scorer's table;
a dataset filter keeps the judging sets of that dataset; `--json` carries the same lines the text printed. And on this
repository's 3,280 verdicts, the report's total is the sum of the files.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runfix  # noqa: E402
import _runstore  # noqa: E402

PY = sys.executable
KEEP = {
    k: v for k, v in os.environ.items() if (not k.startswith("EVAL_") or k == "EVAL_STORE") and k != "COLUMNS"
}


def evh(proj: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    e = {**KEEP, "EVAL_HOME": str(proj), "EVAL_NO_CACHE": "1", "EVAL_BUILD_REF": "test-cost-judging", **env}
    return subprocess.run([PY, str(HERE / "cli.py"), *args], cwd=proj, env=e, capture_output=True, text=True)


def rows_into(proj: Path, score_dir: Path, text: str) -> None:
    """A score's rows, in the suite's store as `evh` reads the project."""
    with _runstore._InProject(proj):
        _runstore.put_rows_text(score_dir, text)


def verdict(
    proj: Path, scorer: str, set_id: str, judge: str, name: str, cost: float, known: bool = True, **more
):
    _runstore.write_text(
        proj,
        f"judge-verdicts/{scorer}/{set_id}/{judge}/{name}.json",
        json.dumps(
            {
                "judge": judge,
                "cost_usd": cost,
                "cost_known": known,
                "created_at": "2026-11-14T10:00:00Z",
                **more,
            }
        ),
    )


def judging_set(proj: Path, set_id: str, dataset_id: str):
    _runstore.write_text(
        proj, f"judging-sets/{set_id}.json", json.dumps({"dataset_id": dataset_id, "arms": []})
    )


def judging_lines(text: str) -> list[str]:
    """The lines of the judging table: from its heading on."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    start = next((i for i, ln in enumerate(lines) if "what judging cost" in ln), None)
    return [] if start is None else lines[start:]


def cells(line: str) -> list[str]:
    return line.split()


# ── a fixture project: one arm with a bill, two scorers' verdicts on two datasets ─────────────────────────────────────
syn = Path(tempfile.mkdtemp(prefix="evh-cost-judging-"))
try:
    sd = _runfix.put_run(
        syn / "data",
        {
            "run_id": "one_1",
            "config_id": "arm_one_v1",
            "dataset_id": "dsv",
            "scores": {"acc": 0.5, "total_cost_usd": 0.004},
            "metric_kinds": {"acc": "quality", "total_cost_usd": "cost"},
            "primary_metric": "acc",
            "created_at": "2026-11-01T10:00:00Z",
        },
    )
    rows_into(
        syn,
        sd,
        "".join(
            json.dumps(
                {"item_id": f"i{i}", "acc": 0.5, "cost_usd": 0.001, "_meta": {"usage": {"cost": 0.001}}}
            )
            + "\n"
            for i in range(4)
        ),
    )
    judging_set(syn, "dsv-2arms-aaaa", "dsv")
    judging_set(syn, "other-2arms-bbbb", "other")
    for k, cost in enumerate((0.10, 0.20, 0.30)):
        verdict(syn, "js-a-v1", "dsv-2arms-aaaa", "ja", f"i{k}.primary.b0", cost)
    verdict(syn, "js-a-v1", "dsv-2arms-aaaa", "jb", "i0.primary.b0", 0.40)
    verdict(syn, "js-a-v1", "dsv-2arms-aaaa", "jb", "i0.position.b0", 0.50, cost_usd_earlier_attempts=0.25)
    verdict(syn, "js-b-v1", "other-2arms-bbbb", "jc", "i0.primary.b0", 0.05, known=False)
    verdict(syn, "js-b-v1", "other-2arms-bbbb", "jc", "i1.primary.b0", 1.00)

    r = evh(syn, "cost-report")
    j = judging_lines(r.stdout + r.stderr)
    by = {cells(ln)[0]: cells(ln) for ln in j if "@" in ln}
    check(
        "cost-report: exits 0 and ends with the judging table",
        r.returncode == 0 and bool(j),
        r.stdout + r.stderr,
    )
    a, b = by.get("js-a-v1@dsv-2arms-aaaa", []), by.get("js-b-v1@other-2arms-bbbb", [])
    check(
        "a line per scorer and judging set: its verdicts and what they billed, the estimated apart, its dataset",
        a[1:4] == ["5", "1.5000", "0.0000"] and b[1:4] == ["2", "1.0000", "0.0500"] and a[-1] == "(dsv)",
        by,
    )
    judges = {cells(ln)[0]: cells(ln) for ln in j if ln.startswith("    ")}
    check(
        "a line per judge under it (a retried verdict's cost includes its earlier attempts, as recorded)",
        judges.get("ja", [])[1:3] == ["3", "0.6000"]
        and judges.get("jb", [])[1:3] == ["2", "0.9000"]
        and judges.get("jc", [])[1:4] == ["2", "1.0000", "0.0500"],
        judges,
    )
    total = next((cells(ln) for ln in j if ln.startswith("  TOTAL")), [])
    check("its TOTAL is the sum of every verdict", total[1:4] == ["7", "2.5000", "0.0500"], total)
    check(
        "the verdicts priced on the scorer's table are counted and said, never added to billed",
        any("1 verdict(s) had no provider bill" in ln for ln in j),
        j,
    )
    check(
        "the arms' table is still there, before the judging",
        "arm_one_v1" in r.stdout and r.stdout.index("arm_one_v1") < r.stdout.index("what judging cost"),
        r.stdout,
    )

    r = evh(syn, "cost-report", "--dataset-id", "dsv")
    j = judging_lines(r.stdout)
    check(
        "--dataset-id keeps the judging sets of that dataset (a set names its dataset)",
        any("js-a-v1@dsv-2arms-aaaa" in ln for ln in j)
        and not any("js-b-v1" in ln for ln in j)
        and next(cells(ln) for ln in j if ln.startswith("  TOTAL"))[1:3] == ["5", "1.5000"],
        r.stdout,
    )
    r = evh(syn, "cost-report", "--dataset-id", "other")
    check(
        "a dataset with judging and no run: the judging is reported, not 'no runs matched'",
        r.returncode == 0
        and any("js-b-v1@other-2arms-bbbb" in ln for ln in judging_lines(r.stdout))
        and "arm_one_v1" not in r.stdout,
        r.stdout + r.stderr,
    )
    r = evh(syn, "cost-report", "--dataset-id", "nothing")
    check(
        "a dataset with neither: refused as before",
        r.returncode != 0 and "no runs matched" in r.stdout + r.stderr,
        r.stdout + r.stderr,
    )
    r = evh(syn, "cost-report", "--match", "arm_one")
    check(
        "--match names arms: judging is left out",
        r.returncode == 0 and not judging_lines(r.stdout) and "arm_one_v1" in r.stdout,
        r.stdout,
    )

    # --json: the lines are the text's, and the rows are there to read.
    r = evh(syn, "cost-report", "--json")
    doc = json.loads(r.stdout)
    blocks = [ln for b in doc["result"]["blocks"] for ln in b.get("lines", [])]
    text = [ln for ln in r.stderr.splitlines() if ln.strip()]
    rows = doc["result"]["values"]["judging"]
    check(
        "--json: its lines are the text's, in order", blocks == text and bool(text), (blocks[-3:], text[-3:])
    )
    check(
        "--json: the judging rows say the same as the table",
        len(rows) == 3
        and abs(sum(x["billed"] for x in rows) - 2.5) < 1e-9
        and abs(sum(x["estimated"] for x in rows) - 0.05) < 1e-9
        and sum(x["verdicts"] for x in rows) == 7
        and {x["dataset"] for x in rows} == {"dsv", "other"},
        rows,
    )
    r = evh(syn, "cost-report", "--dataset-id", "dsv", "--json")
    check(
        "--json with a dataset: only that dataset's rows",
        {x["dataset"] for x in json.loads(r.stdout)["result"]["values"]["judging"]} == {"dsv"},
        r.stdout[-300:],
    )

    # A project with no verdicts prints what it always did.
    empty = Path(tempfile.mkdtemp(prefix="evh-cost-judging-empty-"))
    try:
        sd2 = _runfix.put_run(
            empty / "data",
            {
                "run_id": "one_1",
                "config_id": "arm_one_v1",
                "dataset_id": "dsv",
                "scores": {"acc": 0.5},
                "primary_metric": "acc",
                "created_at": "2026-11-01T10:00:00Z",
            },
        )
        rows_into(
            empty,
            sd2,
            json.dumps({"item_id": "i0", "acc": 0.5, "cost_usd": 0.001, "_meta": {"usage": {"cost": 0.001}}})
            + "\n",
        )
        r = evh(empty, "cost-report")
        check(
            "no verdicts: no judging section",
            r.returncode == 0 and "judging" not in r.stdout and "arm_one_v1" in r.stdout,
            r.stdout,
        )
    finally:
        shutil.rmtree(empty, ignore_errors=True)
finally:
    shutil.rmtree(syn, ignore_errors=True)

# ── this repository's verdicts: the report's total is the sum of the files ──────────────────────────────────────────────
files = sorted((HARNESS / "data" / "judge-verdicts").glob("*/*/*/*.json"))
docs = [json.loads(f.read_text()) for f in files]
want_billed = sum(float(d.get("cost_usd") or 0) for d in docs if d.get("cost_known", True))
want_est = sum(float(d.get("cost_usd") or 0) for d in docs if not d.get("cost_known", True))
repo = {"EVAL_STORE": "files"}  # this repository's data is files
r = evh(HARNESS, "cost-report", "--json", **repo)
rows = json.loads(r.stdout)["result"]["values"]["judging"]
check(
    "this repository: every verdict is counted, and its cost is the sum of the files",
    len(files) > 0
    and sum(x["verdicts"] for x in rows) == len(files)
    and abs(sum(x["billed"] for x in rows) - want_billed) < 1e-6
    and abs(sum(x["estimated"] for x in rows) - want_est) < 1e-6,
    (len(files), sum(x["verdicts"] for x in rows), want_billed, sum(x["billed"] for x in rows)),
)
check(
    "this repository: per scorer and judging set, as many as there are folders",
    {(x["scorer"], x["set"]) for x in rows} == {(f.parts[-4], f.parts[-3]) for f in files},
)
r = evh(HARNESS, "cost-report", "--dataset-id", "cnn_dailymail_200", "--json", **repo)
rows_cnn = json.loads(r.stdout)["result"]["values"]["judging"]
r = evh(HARNESS, "cost-report", "--dataset-id", "ag_news_200", "--json", **repo)
check(
    "this repository: the dataset filter goes through the judging set's dataset_id (every set is on cnn_dailymail_200)",
    sum(x["verdicts"] for x in rows_cnn) == len(files)
    and "judging" not in (json.loads(r.stdout)["result"].get("values") or {}),
    r.stdout[-200:],
)

sys.exit(summary())
