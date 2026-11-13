#!/usr/bin/env python3
"""Guards found in the 2026-11-04 review: a family named as a list, a family whose opponents share
different numbers of items, no pairwise verdict without an arm effect, strict JSON in table cells,
and a round's leader tested against its baseline as one of the round's arms (Holm), not alone."""

from __future__ import annotations

import os

os.environ["EVAL_STORE"] = "files"  # reads this repository's committed runs, which are files

import contextlib
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
from evaluation_harness import _jsonout  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

RUNS = HARNESS / "data" / "runs"
CLI = HARNESS / "scripts" / "cli.py"


def evh(*args: str, cwd: Path = HARNESS) -> subprocess.CompletedProcess:
    env = {**os.environ, "EVAL_NO_CACHE": "1"}
    env.pop("EVH_P_CACHE", None)
    return subprocess.run(
        [sys.executable, str(CLI), *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=600
    )


def run_of(config_id: str) -> Path:
    return next(p for p in sorted(RUNS.iterdir()) if p.name.startswith(config_id + "_2"))


def main() -> int:
    # L6: a NaN inside a cell (a dict of scores) must not reach the envelope as the literal NaN.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), _jsonout.collect("probe"):
        _jsonout.table(["run", "scores"], [["r1", {"a": math.nan, "b": [1.0, math.inf]}]])
    try:
        cell = json.loads(buf.getvalue(), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        cell = cell["result"]["blocks"][0]["rows"][0]["scores"]
    except ValueError as e:
        cell = f"not strict JSON: {e}"
    check(
        "json: a NaN or infinity inside a table cell is null, strict JSON",
        cell == {"a": None, "b": [1.0, None]},
        cell,
    )

    # L4: the leaderboard's pairs are read only after the global test finds an arm effect.
    from evaluation_harness.leaderboard import significance  # noqa: PLC0415

    noise = {a: {f"i{n}": ((n * 7 + j) % 5) / 5 for n in range(40)} for j, a in enumerate("abcd")}
    with contextlib.redirect_stdout(io.StringIO()):
        o = significance(noise, "m")
    check(
        "leaderboard: without an arm effect no pair is reported distinguishable, and the data says why",
        o.get("arm_effect") is False
        and o.get("pairwise_valid") is False
        and o.get("distinguishable_pairs") == [],
        {k: o.get(k) for k in ("global_p", "arm_effect", "pairwise_valid", "pairs_distinguishable")},
    )

    # M1: --against as a comma-separated list names the family exactly; one value stays a substring.
    a, b, c = "ag_anthropic_l_v1", "ag_anthropic_m_v1", "ag_anthropic_s_v1"
    # a run's directory keeps the id it was made under (data/renames.json: systems)
    dirs = {x: x.replace("_v1", "_n200_v1") for x in (a, b, c)}
    r = evh("family-test", "--dataset-id", "ag_news_200", "--a", a, "--against", f"{b},{c}", "--json")
    v = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
    check("family-test: --against B,C is the family {B, C}", v.get("family_size") == 2, r.stderr[-300:] or v)
    r = evh("family-test", "--dataset-id", "ag_news_200", "--a", a, "--against", "ag_anthropic_", "--json")
    v1 = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
    check("family-test: one value is still a substring", v1.get("family_size") == 2, r.stderr[-300:] or v1)

    # L5: opponents sharing different numbers of items: no single n is the family's.
    tmp = Path(tempfile.mkdtemp(prefix="evh-family-"))
    try:
        for cid in (a, b, c):
            _runstore.copy_run(run_of(dirs[cid]), tmp / run_of(dirs[cid]).name)
        short = tmp / run_of(dirs[c]).name
        _runstore.put_rows_text(
            short, "".join((_outputs.rows_text(short) or "").splitlines(keepends=True)[:40])
        )
        r = evh(
            "family-test",
            "--dataset-id",
            "ag_news_200",
            "--a",
            a,
            "--against",
            "ag_anthropic_",
            "--runs-dir",
            str(tmp),
            "--json",
        )
        v = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
        t = evh(
            "family-test",
            "--dataset-id",
            "ag_news_200",
            "--a",
            a,
            "--against",
            "ag_anthropic_",
            "--runs-dir",
            str(tmp),
        )
        check(
            "family-test: a family on 40 and 200 shared items has no single n, and the header gives the range",
            v.get("n") is None and v.get("n_range") == [40, 200] and "40-200 items" in t.stdout,
            r.stderr[-300:] or {k: v.get(k) for k in ("n", "n_range", "method")},
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # M4: a round's leader, chosen as its best mean, is corrected for the choice before its test against
    # the baseline can gate a promotion: Bonferroni over the round's arms. A raw p of 0.02 among four
    # arms is 0.08 corrected, not significant; among one it stands.
    sys.argv = ["rounds"]
    from evaluation_harness import rounds  # noqa: PLC0415

    raw = {
        "label": "the baseline it started from",
        "other": "base",
        "verdict": "significant: better",
        "p": 0.02,
        "delta": 0.1,
    }
    real = rounds._against
    try:
        rounds._against = lambda *_a, **_k: dict(raw)
        four = rounds._against_family(
            None, "the baseline it started from", "base", "lead", ["base", "lead", "b", "c", "d"], "m"
        )
        one = rounds._against_family(
            None, "the baseline it started from", "base", "lead", ["base", "lead"], "m"
        )
    finally:
        rounds._against = real
    assert four is not None and one is not None, "_against_family returned nothing"
    check(
        "rounds: the leader's test against the baseline is corrected for the arms it was chosen from",
        four["verdict"] == "not significant"
        and four["family"] == 4
        and abs(four["p_adjusted"] - 0.08) < 1e-12,
        four,
    )
    check(
        "rounds: with one candidate there is nothing to correct for, and the verdict stands",
        one["verdict"] == "significant: better"
        and one["family"] == 1
        and abs(one["p_adjusted"] - 0.02) < 1e-12,
        one,
    )
    check(
        "rounds: the corrected row keeps the promotion from going ahead",
        rounds._promote_hold([four], None).startswith("not ahead of the baseline it started from"),
        rounds._promote_hold([four], None),
    )
    return summary()


if __name__ == "__main__":
    sys.exit(main())
