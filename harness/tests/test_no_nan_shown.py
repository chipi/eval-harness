#!/usr/bin/env python3
"""A number nobody could work out is shown as "—", never as nan or inf (RFC-041 F3's class: unknown read as zero, or as
garbage).

    EVAL_STORE=files python tests/test_no_nan_shown.py
    EVAL_STORE=sqlite python tests/test_no_nan_shown.py

In a throwaway project ($0, offline: a stand-in adapter, three arms that cost nothing and score alike):

- `evh cost-report` of runs that billed $0 against a recorded $0 has no ratio to print: its per-arm and TOTAL rows say
  "—" in the ratio column (the same width), text and --json alike;
- `evh rank-stability` of arms that tie on every item has no rho to print: "—", and null in --json;
- a source check: `float("nan")`, `float("inf")`, `math.nan` and `math.inf` appear in the scripts only where this
  file lists the site and why it never reaches a reader, and `NaN` / `Infinity` in the page scripts likewise.
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import tokenize
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-nonan-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-nonan", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

#: Every item costs nothing and every arm scores the same: nothing to divide by, nothing to correlate.
ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    return SimpleNamespace(output="same", tokens_in=10, tokens_out=5, cost_usd=0.0, latency_ms=None, extra={},
                           meta={"usage": {"cost": 0.0}})

def score(output, reference):
    return {"wer": 0.25}

PRIMARY_METRIC = "wer"
"""
BAD = re.compile(r"\b(nan|inf|infinity)\b|NaN|Infinity", re.IGNORECASE)


def evh(*args):
    return _cli.run(proj, env, *args)


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
    src = proj / "tutorial" / "items"
    src.mkdir(parents=True)
    for n in range(12):
        (src / f"t{n:02d}.txt").write_text(f"item {n}\n")
    (proj / "free_adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "free_v1", "--source-dir", "tutorial/items")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "free_v1")
    check("setup: a frozen dataset of 12 items", r.returncode == 0, r.stderr[-300:])
    for name in ("a", "b", "c"):
        _runstore.write_text(
            proj, f"systems/{name}_v1.yaml", f"system_id: {name}_v1\nadapter: free_adapter.py\n"
        )
        r = evh("run", "--system", f"{name}_v1", "--dataset", "free_v1", "--run-id", name)
        check(
            f"setup: the run {name} (billed $0, recorded $0)", r.returncode == 0, (r.stdout + r.stderr)[-300:]
        )

    # -- cost-report: 0 billed against 0 recorded ------------------------------------------------------------------
    r = evh("cost-report", "--dataset-id", "free_v1")
    text = r.stdout + r.stderr
    total = next((ln for ln in text.splitlines() if ln.strip().startswith("TOTAL")), "")
    rows = [ln for ln in text.splitlines() if re.match(r"\s+[abc]_v1\b", ln)]
    check(
        "cost-report: exits 0 and has the table",
        r.returncode == 0 and bool(total) and len(rows) == 3,
        text[-500:],
    )
    check("cost-report: no nan or inf anywhere in the text", not BAD.search(text), text[-500:])
    check("cost-report: the TOTAL ratio is —", total.rstrip().endswith("—") and "0.0000" in total, total)
    check("cost-report: every arm's ratio is —", all(ln.rstrip().endswith("—") for ln in rows), rows)
    widths = {len(ln.rstrip()) for ln in [total, *rows]}
    check(
        "cost-report: the ratio keeps its column (every row as wide as the others)", len(widths) == 1, widths
    )
    r = evh("cost-report", "--dataset-id", "free_v1", "--json")
    check(
        "cost-report --json: parses, and has no NaN or Infinity",
        r.returncode == 0 and not BAD.search(r.stdout) and bool(json.loads(r.stdout)),
        r.stdout[-300:] + r.stderr[-300:],
    )

    # -- rank-stability: every arm ties on every item --------------------------------------------------------------
    r = evh("rank-stability", "free_v1", "--draws", "20")
    text = r.stdout + r.stderr
    sizes = [ln for ln in text.splitlines() if re.match(r"\s+\d+\s+[—0-9.-]", ln)]
    check(
        "rank-stability: exits 0 and has a row per half size", r.returncode == 0 and bool(sizes), text[-500:]
    )
    check("rank-stability: no nan anywhere in the text", not BAD.search(text), text[-500:])
    check("rank-stability: rho and P(same winner) are —", all(ln.count("—") >= 2 for ln in sizes), sizes)
    r = evh("rank-stability", "free_v1", "--draws", "20", "--json")
    check(
        "rank-stability --json: parses, no NaN, rho is null",
        r.returncode == 0 and not BAD.search(r.stdout) and "null" in r.stdout,
        r.stdout[-400:] + r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)


# -- a source check: where a NaN or an infinity may exist ----------------------------------------------------------
#: {file under scripts/ or the page scripts: why what it makes never reaches a reader}. A new site is a new line here,
#: with its reason, or a fix.
PY_SITES = {
    "leaderboard.py": 'float("inf"): the default of a sort key (a row without the column sorts last); never printed',
    "data_migrate.py": 'float("-inf"): a sort key for a file with no time; never printed',
    "migrations/m0007_results.py": 'float("-inf"): a sort key for a file with no time; never printed',
    "stats.py": "math.nan: pearson/spearman's `constant`, for a side with no spread; every caller that prints it passes "
    "a constant or tests `r == r` (rank_stability) and prints a missing rho as —",
}
JS_SITES = {
    "catalog.js": "isNaN (parsing a sort cell: a non-number sorts as text) and Infinity (no page limit); never shown",
    "forest.js": "Infinity / -Infinity: the seeds of a min and a max over the plotted values; never shown",
    "inspect.js": "Infinity / -Infinity: the seeds of a min and a max over the plotted values; never shown",
    "group.js": "Infinity: no limit on the rows opened; never shown",
}


def py_sites() -> dict[str, list[int]]:
    """{file: lines} of `float("nan")`, `float('inf')`, `float("-inf")`, `math.nan`, `math.inf`, from the tokens."""
    found: dict[str, list[int]] = {}
    for f in sorted((HARNESS / "scripts").rglob("*.py")):
        toks = [
            t
            for t in tokenize.generate_tokens(io.StringIO(f.read_text()).readline)
            if t.type
            not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
        ]
        for i, t in enumerate(toks):
            hit = (
                t.type == tokenize.NAME
                and t.string == "float"
                and i + 2 < len(toks)
                and toks[i + 1].string == "("
                and toks[i + 2].type == tokenize.STRING
                and re.fullmatch(r"[\"'][+-]?(nan|inf|infinity)[\"']", toks[i + 2].string, re.IGNORECASE)
            ) or (
                t.type == tokenize.NAME
                and t.string == "math"
                and i + 2 < len(toks)
                and toks[i + 1].string == "."
                and toks[i + 2].string in ("nan", "inf")
            )
            # Before Python 3.12 an f-string is one STRING token: look inside it, where `float('nan')` was hiding.
            hit = hit or (
                t.type == tokenize.STRING
                and re.match(r"[a-zA-Z]*f", t.string, re.IGNORECASE) is not None
                and re.search(r"float\(\s*[\"'][+-]?(nan|inf|infinity)[\"']", t.string, re.IGNORECASE)
                is not None
            )
            if hit:
                found.setdefault(f.relative_to(HARNESS / "scripts").as_posix(), []).append(t.start[0])
    return found


def js_sites() -> dict[str, list[int]]:
    """{file: lines} of `NaN` and `Infinity` in the page scripts (comments left out)."""
    found: dict[str, list[int]] = {}
    for d in ("catalog_assets", "workbench"):
        for f in sorted((HARNESS / d).glob("*.js")):
            for n, ln in enumerate(f.read_text().splitlines(), 1):
                code = re.sub(r"/\*.*?\*/|//.*$", "", ln)
                if re.search(r"\bNaN\b|\bInfinity\b|\bisNaN\b", code):
                    found.setdefault(f.name, []).append(n)
    return found


found = py_sites()
check(
    "source: float('nan') / float('inf') / math.nan / math.inf only where the list says why",
    set(found) <= set(PY_SITES),
    {f: ln for f, ln in found.items() if f not in PY_SITES},
)
check(
    "source: every listed Python site still exists (a stale line is a lie)",
    set(PY_SITES) <= set(found),
    sorted(set(PY_SITES) - set(found)),
)
found_js = js_sites()
check(
    "source: NaN / Infinity in the page scripts only where the list says why",
    set(found_js) <= set(JS_SITES),
    {f: ln for f, ln in found_js.items() if f not in JS_SITES},
)

summary()
