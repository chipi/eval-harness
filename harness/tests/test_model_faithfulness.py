#!/usr/bin/env python3
"""Faithfulness records through the model (RFC-032 step 7), in the suite's store.

    python tests/test_model_faithfulness.py

In a project `evh init` makes, with a code record of three versions and two faithfulness records of it (the second a
newer replay of two of the versions, with a disagreement a person named), written as `evh faithfulness` and
`faithfulness-name` write them:

- the records list by `<model_id>/<n>`, read with their named exceptions, and the next one takes the next number;
- a version's faithfulness is read from the newest record that replayed its commit, never from the model record: an
  older record answers for a commit only it replayed, a version no replay ran has none, a copy of a summary stored in
  the model record is not shown;
- a record is checked against its schema, and the id it is written under (`config_id` as recorded);
- the records are read from the data directory asked for: the catalog's adapter, on a deployment's copy of the data,
  gives the Models page the copy's summaries, and a record written after the copy is not in them;
- the copy holds the records whole, byte for byte, for a dataset that is not hidden.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-faith-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-faithfulness")
release = Path(tempfile.mkdtemp(prefix="evh-faith-release-"))
SHA = "a" * 64
C1, C2, C3 = "aaaaaaa" + "1" * 33, "bbbbbbb" + "2" * 33, "ccccccc" + "3" * 33


def put(rel: str, text: str) -> None:
    _runstore.write_text(proj, rel, text)


def record(n: int, commits: dict[str, int], disagreements: list[dict], at: str, **more) -> dict:
    agree = sum(commits.values()) - len(disagreements)
    return {
        "n": n, "model_id": "code1", "config_id": "replay_v1", "dataset_id": "history", "items_sha256": SHA,
        "versions_sha256": SHA, "adapter_sha256": SHA, "commits": commits, "production_run": "prod_run",
        "counts": {"items": sum(commits.values()), "agree": agree, "differ": len(disagreements), "replay_errors": 0,
                   "production_missing": 0},
        "disagreements": disagreements, "coverage": {}, "at": at, "actor": {"type": "person", "name": "t"}, **more,
    }  # fmt: skip


def differ(item: str, commit: str) -> dict:
    return {"item_id": item, "kind": "differ", "commit": commit, "production": "p", "replay": "r"}


CODE = f"""model_id: code1
kind: code
name: code under test
repo: https://example.org/code1
versions:
  - commit: {C1[:7]}
    deployed: [{{from: '2026-10-01T00:00:00Z', to: '2026-10-10T00:00:00Z'}}]
  - commit: {C2[:7]}
    deployed: [{{from: '2026-10-10T00:00:00Z', to: '2026-10-20T00:00:00Z'}}]
  - commit: {C3[:7]}
    deployed: [{{from: '2026-10-20T00:00:00Z'}}]
"""


def latest_n(*args, **kwargs) -> int | None:
    """The number of the latest record `mf.latest` finds, None when it finds none."""
    from evaluation_harness.model import faithfulness as mf  # noqa: PLC0415

    rec = mf.latest(*args, **kwargs)
    return rec["n"] if rec else None


def dies(fn, *args) -> str:
    """The message of the refusal `fn` exits with, "" when it does not."""
    try:
        fn(*args)
    except SystemExit as exc:
        return str(exc)
    return ""


try:
    r = subprocess.run([sys.executable, str(HARNESS / "scripts" / "cli.py"), "init"], cwd=proj, env=env,
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)  # fmt: skip
    r = (
        r
        if r.returncode
        else subprocess.run(["git", "-C", str(proj), "init", "-q"], capture_output=True, text=True)
    )
    check("setup: a project", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    put("models/code1.yaml", CODE)
    put(
        "faithfulness/code1/1.json",
        json.dumps(record(1, {C1: 10, C2: 6}, [differ("d1", C1), differ("d2", C2)], "2026-11-01T00:00:00Z")),
    )
    put(
        "faithfulness/code1/2.json",
        json.dumps(
            record(
                2,
                {C2: 6, C3: 8},
                [differ("d3", C2), differ("d4", C3), differ("d5", C3)],
                "2026-11-05T00:00:00Z",
            )
        ),
    )
    put(
        "faithfulness/code1/2.exceptions.jsonl",
        json.dumps({"item_id": "d4", "cause": "a clock", "actor": {"type": "person", "name": "t"}, "at": "x"})
        + "\n",
    )
    _runstore.migrate_in(proj)

    import yaml
    from evaluation_harness import _coderec, _faith, _models, _release
    from evaluation_harness import catalog_models as cm
    from evaluation_harness.catalog_adapter import HarnessAdapter
    from evaluation_harness.model import faithfulness as mf
    from evaluation_harness.model.entity import Problem

    check(
        "the records list by `<model_id>/<n>`, and a code record's numbers ascend",
        mf.FAITHFULNESS.ids() == ["code1/1", "code1/2"]
        and mf.numbers("code1") == [1, 2]
        and mf.numbers("nope") == []
        and mf.model_ids() == ["code1"],
        (mf.FAITHFULNESS.ids(), mf.numbers("code1")),
    )
    rec2 = mf.load("code1", 2)
    check(
        "a record is read with the exceptions named beside it; the newest one on a dataset is the latest",
        [e["item_id"] for e in rec2["exceptions"]] == ["d4"]
        and mf.load("code1", 1)["exceptions"] == []
        and latest_n("code1", "history") == 2
        and latest_n("code1", "history", SHA) == 2
        and mf.latest("code1", "history", "f" * 64) is None
        and mf.latest("code1", "other") is None
        and "no faithfulness record code1/9 (made: [1, 2])" in dies(mf.load, "code1", 9),
        (rec2["exceptions"], dies(mf.load, "code1", 9)),
    )
    s = mf.summaries("code1")
    check(
        "a version's faithfulness is the newest record that replayed its commit: the older record answers for the commit "
        "only it replayed; the named exceptions are counted among those that differ",
        s[C1] == {"agreed": 9, "items": 10, "exceptions": [], "run": "code1/1", "at": "2026-11-01T00:00:00Z"}
        and s[C2]
        == {"agreed": 5, "items": 6, "exceptions": [], "run": "code1/2", "at": "2026-11-05T00:00:00Z"}
        and s[C3]
        == {"agreed": 6, "items": 8, "exceptions": ["d4"], "run": "code1/2", "at": "2026-11-05T00:00:00Z"},
        s,
    )
    stored = _models.find(proj / "data", "code1") or {}
    viewed = mf.with_summaries(
        {
            **stored,
            "versions": [
                *stored["versions"][:2],
                {**stored["versions"][2], "faithfulness": {"agreed": 99, "items": 99}},
            ],
        }
    )
    got = [(v["commit"], (v.get("faithfulness") or {}).get("run")) for v in viewed["versions"]]
    check(
        "the model record as the views read it: each version with its summary by its commit's prefix; a copy stored in the "
        "record is replaced by the records' answer",
        got == [(C1[:7], "code1/1"), (C2[:7], "code1/2"), (C3[:7], "code1/2")]
        and viewed["versions"][2]["faithfulness"]["items"] == 8
        and mf.with_summaries(
            {**stored, "versions": [{"commit": "9999999", "faithfulness": {"agreed": 1, "items": 1}}]}
        )["versions"]
        == [{"commit": "9999999"}]
        and "faithfulness"
        not in yaml.safe_load(_runstore.read_text(proj, "models/code1.yaml"))["versions"][0],
        got,
    )
    check(
        "the code record keeps no copy: nothing writes a summary into it",
        not hasattr(_coderec, "record_faithfulness")
        and not hasattr(_faith, "numbers")
        and not hasattr(_faith, "load"),
        [n for n in dir(_coderec) if "faith" in n],
    )

    # ── writing ───────────────────────────────────────────────────────────────────────────────────────────────────
    n = mf.write(record(0, {C3: 2}, [], "2026-11-06T00:00:00Z"))
    mf.append_exception(
        "code1", 2, {"item_id": "d5", "cause": "slack", "actor": {"type": "person", "name": "t"}, "at": "y"}
    )
    check(
        "the next record takes the next number, never over one; a named exception is appended after the others",
        n == 3
        and mf.numbers("code1") == [1, 2, 3]
        and mf.load("code1", 3)["n"] == 3
        and [e["item_id"] for e in mf.exceptions("code1", 2)] == ["d4", "d5"]
        and mf.summaries("code1")[C3]["run"] == "code1/3",
        (n, mf.numbers("code1"), mf.summaries("code1")[C3]),
    )

    # ── the schema ────────────────────────────────────────────────────────────────────────────────────────────────
    good = mf.load("code1", 1)
    good.pop("exceptions")
    short = {k: v for k, v in good.items() if k != "config_id"}
    try:
        mf.FAITHFULNESS.save("code1/1", good, "person:t")
        refused = ""
    except Problem as exc:
        refused = exc.kind
    check(
        "a record is checked against its schema: as written it holds; without its `config_id` (as recorded) or under "
        "another model's folder it does not; a record is written by `evh faithfulness`, never edited",
        mf.FAITHFULNESS.problems("code1/1", good) == []
        and any(p["path"] == ["config_id"] for p in mf.FAITHFULNESS.problems("code1/1", short))
        and mf.FAITHFULNESS.problems("other/1", good)[0]["path"] == ["model_id"]
        and refused == "not-allowed",
        (mf.FAITHFULNESS.problems("code1/1", good), mf.FAITHFULNESS.problems("code1/1", short), refused),
    )

    # ── read where the data is: a deployment's copy ───────────────────────────────────────────────────────────────
    counts = _release.copy_data(proj / "data", release)
    rels = ("code1/1.json", "code1/2.json", "code1/2.exceptions.jsonl", "code1/3.json")
    check(
        "the release copy holds the records whole, byte for byte, for a dataset that is not hidden",
        all(
            _runstore.read_bytes(proj, f"faithfulness/{r}") == (release / "faithfulness" / r).read_bytes()
            for r in rels
        )
        and counts["hidden_faithfulness"] == 0,
        counts,
    )
    check(
        "the records are read from the data directory asked for: the copy's numbers, records and summaries are the project's",
        mf.numbers("code1", release) == [1, 2, 3]
        and mf.load("code1", 2, release) == mf.load("code1", 2)
        and mf.summaries("code1", release) == mf.summaries("code1")
        and mf.model_ids(release) == ["code1"]
        and latest_n("code1", "history", data=release) == 3,
        mf.summaries("code1", release),
    )
    mf.write(record(0, {C1: 4}, [differ("d9", C1), differ("d8", C1)], "2026-11-09T00:00:00Z"))
    A_copy, A_proj = HarnessAdapter(release), HarnessAdapter()

    def fa(A):
        """Each version's faithfulness as the adapter's Models page data has it."""
        rec = next(x for x in A.models() if x["record"]["model_id"] == "code1")["record"]
        return {v["commit"]: v.get("faithfulness") for v in rec["versions"]}

    check(
        "the Models page's data on a deployment's copy is the copy's records' (a record written after the copy is not in "
        "them), and the project's is the project's",
        (fa(A_copy)[C1[:7]] or {}).get("run") == "code1/1"
        and (fa(A_proj)[C1[:7]] or {}).get("run") == "code1/4"
        and (fa(A_copy)[C3[:7]] or {}).get("run") == "code1/3",
        (fa(A_copy), fa(A_proj)),
    )
    rows = cm.version_rows(next(x for x in A_copy.models() if x["record"]["model_id"] == "code1")["record"])
    check(
        "a version row says how many agreed, how many were named and the record (the page and `evh models --model`)",
        rows[0][3].startswith("2 of 2 agreed")
        and "code1/3" in rows[0][3]
        and rows[2][3].startswith("9 of 10 agreed")
        and "code1/1" in rows[2][3],
        rows,
    )
    shown = subprocess.run([sys.executable, str(HARNESS / "scripts" / "cli.py"), "periods", "--model", "code1", "--json"],
                           cwd=proj, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)  # fmt: skip
    periods = json.loads(shown.stdout)["result"]["values"]["periods"] if shown.returncode == 0 else []
    check(
        "`evh periods` reads each version's faithfulness from the records too",
        [(x["commit"][:7], (x["faithfulness"] or {}).get("run")) for x in periods]
        == [(C1[:7], "code1/4"), (C2[:7], "code1/2"), (C3[:7], "code1/3")],
        (shown.stderr[-300:], periods),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(release, ignore_errors=True)

sys.exit(summary())
