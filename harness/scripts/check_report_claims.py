#!/usr/bin/env python3
"""Every headline number in the reports must match the committed runs. $0, no network.

    python scripts/check_report_claims.py

WHY THIS EXISTS. Three external reviewers could only check the reports against each
other and against arithmetic, because no run was committed -- so a figure that had gone
stale (a rescore, a rerun, a changed arm set) was invisible until someone noticed a
contradiction between two documents. The runs are committed now, so the reports can be
checked against the data instead of against themselves.

Each entry is (report, label, claimed value, run, metric). A claim that drifts fails
here rather than in a reader's head.
"""
import json
import re
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AmbiguousRuns, runs_by_arm  # noqa: E402

if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
    # It used to fall through and run the whole check, so `--help`
    # returned 0 only when every assertion happened to pass -- the trap
    # validate_tree and check_model_facts already learned.
    print(__doc__)
    raise SystemExit(0)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = HERE.parent / "data" / "runs"
RESCORED = HERE.parent / "data" / "runs-rescored"
#: The pre-registered first-stage prediction. Its four runs lived in an ignored
#: directory until round 2, so the most-advertised number in the repo -- 0.7891 -- was
#: the one number no reader could check.
PAIR = HERE.parent / "data" / "runs-pair"

#: (label, runs-dir, config_id, metric, claimed). NER reads the rescored directory,
#: because that is the instrument its report states -- the un-rescored copies carry the
#: pre-fix glm_l and comparing against them would pass for the wrong reason.
CLAIMS = [
    ("NER span_marker f1",        RESCORED, "fn_span_marker_n200_v1", "f1",        0.7674),
    ("NER openai_m f1",           RESCORED, "fn_openai_m_n200_v1",    "f1",        0.6864),
    ("NER gliner f1",             RESCORED, "fn_gliner_n200_v1",      "f1",        0.4540),
    ("NER capitalized typed",     RESCORED, "fn_capitalized_n200_v1", "f1",        0.1913),
    ("NER capitalized untyped",   RESCORED, "fn_capitalized_n200_v1", "untyped_f1",0.6191),
    ("NER nothing = the floor",   RESCORED, "fn_nothing_n200_v1",     "f1",        0.1250),
    ("NER glm_l parsed",          RESCORED, "fn_glm_l_n200_v1",       "parsed",    0.8857),
    ("SciFact glm_s ndcg@10",     DATA,     "sf_glm_s_n200_v1",       "ndcg_10",   0.7437),
    ("SciFact e5_base ndcg@10",   DATA,     "sf_e5_base_n200_v1",     "ndcg_10",   0.7191),
    ("SciFact bm25 ndcg@10",      DATA,     "sf_bm25_n200_v1",        "ndcg_10",   0.6451),
    ("SciFact rerank recall@100", DATA,     "sf_glm_s_n200_v1",       "recall_100",0.8586),
    ("AG News bert_mini",         DATA,     "ag_bert_mini_n200_v1",   "correct",   0.9450),
    ("DBpedia qwen_m",            DATA,     "db_qwen_m_n200_v1",      "correct",   0.9929),
    ("Summarisation bart_l",      DATA,     "cnn_bart_l_n200_v1",     "coverage",  0.3461),
]

#: (label, claimed, a - b) — the DIFFERENCES the reports lead with.
#: The registered prediction, checked as a RANGE rather than a point, because that is
#: what was registered: 0.786-0.797 before the arm existed.
PREDICTIONS = [
    ("SciFact prediction: glm_s on e5_base lands in 0.786-0.797",
     PAIR, "sf_glm_s_e5first_n200_v1", "ndcg_10", 0.786, 0.797),
]

DELTAS = [
    ("NER fine-tuning is worth +0.3134", 0.3134,
     (RESCORED, "fn_span_marker_n200_v1", "f1"), (RESCORED, "fn_gliner_n200_v1", "f1")),
    ("SciFact BM25 -> e5_base = +0.0740", 0.0740,
     (DATA, "sf_e5_base_n200_v1", "ndcg_10"), (DATA, "sf_bm25_n200_v1", "ndcg_10")),
    ("SciFact prediction: glm_s gains +0.0469 from the first stage alone", 0.0469,
     (PAIR, "sf_glm_s_e5first_n200_v1", "ndcg_10"),
     (PAIR, "sf_glm_s_bm25first_n200_v1", "ndcg_10")),
    ("SciFact worst -> best reranker = +0.0420", 0.0420,
     (DATA, "sf_glm_s_n200_v1", "ndcg_10"), (DATA, "sf_gemma_s_n200_v1", "ndcg_10")),
]

TOL = 5e-4
ok: list = []


def check(label: str, cond: bool, detail: str = "") -> None:
    ok.append(cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{('   ' + detail) if detail and not cond else ''}")


def score(base: Path, cid: str, metric: str):
    for d in glob.glob(str(base / f"{cid}_*")):
        m = json.load(open(Path(d) / "metrics.json"))
        if m.get("config_id") == cid:
            return m["scores"].get(metric)
    return None


missing = 0
for label, base, cid, metric, claimed in CLAIMS:
    got = score(base, cid, metric)
    if got is None:
        missing += 1
        print(f"  --   {label}: run not present ({cid}) — skipped")
        continue
    check(label, abs(got - claimed) <= TOL, f"claimed {claimed}, run says {got:.6f}")

for label, claimed, (b1, c1, m1), (b2, c2, m2) in DELTAS:
    a, b = score(b1, c1, m1), score(b2, c2, m2)
    if a is None or b is None:
        missing += 1
        print(f"  --   {label}: a run is missing — skipped")
        continue
    check(label, abs((a - b) - claimed) <= TOL, f"claimed {claimed}, run says {a - b:.6f}")

# ---- COSTS, WHICH NOTHING CHECKED AT ALL ---------------------------------------
#
# 17 headline numbers were verified here and not one of them was a cost -- so when two
# of four reports were left quoting price-table estimates under a heading announcing
# they had been corrected, `make ci` stayed green. The costs were the figures most
# recently found wrong and the ones left unchecked, because this file predates that
# finding and was never revisited.
#
# Every per-arm "$" cell in a report must equal what the provider BILLED, summed from
# `_meta.usage.cost` in that run's predictions. The price table is the fallback for an
# arm with no bill and must never be what a report quotes.
import glob as _glob  # noqa: E402

COST_REPORTS = {
    "REPORT_NER.md": ("fn_", "few_nerd_280"),
    "REPORT_RETRIEVAL.md": ("sf_", "scifact_200"),
    "REPORT_SUMMARIZATION.md": ("cnn_", "cnn_dailymail_200"),
    "REPORT_CLASSIFICATION.md": ("ag_", "ag_news_200"),
}


def _billed_and_recorded(prefix, dataset_id):
    out = {}
    for f in _glob.glob(str(DATA / f"{prefix}*" / "metrics.json")):
        m = json.load(open(f))
        if m.get("dataset_id") != dataset_id:
            continue
        pj = Path(f).parent / "predictions.jsonl"
        if not pj.is_file():
            continue
        rec = bil = 0.0
        for line in pj.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rec += float(r.get("cost_usd") or 0)
            bil += float((((r.get("_meta") or {}).get("usage") or {}).get("cost") or 0))
        out[m["config_id"].replace(prefix, "").replace("_n200_v1", "")] = (bil, rec)
    return out


_stale_cost = []
_checked_cost = 0
for _rep, (_pref, _ds) in COST_REPORTS.items():
    _text = (ROOT / "research" / _rep).read_text()
    _data = _billed_and_recorded(_pref, _ds)
    for _line in _text.splitlines():
        if not _line.startswith("|"):
            continue
        _cells = [c.strip() for c in _line.strip("|").split("|")]
        _arm = re.sub(r"[`*\u27f3 ]", "", _cells[0])
        if _arm not in _data:
            continue
        _bil, _rec = _data[_arm]
        if _bil <= 0 or abs(_bil - _rec) < 1e-9:
            continue          # no bill, or the table happens to be right
        for _c in _cells[1:]:
            # THE DOLLAR SIGN IS REQUIRED. With it optional this matched any
            # four-decimal cell, so an f1 of 0.6864 was read as a cost. That was
            # harmless while the check only flagged exact price-table matches, and
            # became 214 false failures the moment it also flagged "neither" -- a
            # latent looseness that only shows when something downstream gets stricter.
            _m = re.fullmatch(r"\$([0-9]+\.[0-9]{3,4})", _c.replace("**", ""))
            if not _m:
                continue
            _v = float(_m.group(1))
            if abs(_v - _bil) < 0.0002:
                _checked_cost += 1
            elif abs(_v - _rec) < 0.0002:
                _stale_cost.append(f"{_rep}: {_arm} shows ${_v:.4f} (price table); "
                                   f"billed ${_bil:.4f}")
            elif _v > 0 and abs(_v - _bil) / max(_bil, 1e-9) > 0.02:
                # NEITHER the bill nor the price table. This used to pass: the check
                # only recognised the one wrong value it knew about, so a cost that was
                # simply made up sailed through. Found by external review.
                _stale_cost.append(f"{_rep}: {_arm} shows ${_v:.4f}, which is neither "
                                   f"the bill (${_bil:.4f}) nor the price table "
                                   f"(${_rec:.4f})")
# The cost verdict is asserted AFTER the code-block scan below, which also appends to
# `_stale_cost`. Asserting here ran before that scan had found anything, so 20 stale
# classification cells passed while the list was still empty -- a check evaluated
# before its inputs exist is a check that cannot fail.

# ---- EVERY ARM ROW IN EVERY REPORT, against the run it names ---------------------
#
# Three times in one review a correction was applied where it was found and not where
# it was repeated: the retrieval parser fix reached a new prose section but not §3.1;
# then not the §0 headline; then not the synthesis table, the headroom table or the
# pasted Holm block. Each was caught by a human reading, which does not scale and did
# not catch the first two.
#
# So: any markdown table row whose first cell names an arm, and whose first numeric
# cell is that arm's PRIMARY metric, must agree with the committed run. That is the
# shape of every table that went stale.
#
# Deliberately narrow. Only the first numeric cell, only rows starting with an arm
# name, and only where the value is within 0.5 of the run's primary metric -- a row
# whose leading number is something else entirely (a count, a price) is skipped rather
# than guessed at. It catches a stale score, which is the failure that happened.
PRIMARY_BY_DATASET = {
    "few_nerd_280": ("fn_", "f1", RESCORED),
    "scifact_200": ("sf_", "ndcg_10", HERE.parent / "data" / "runs-reparsed"),
    # "accuracy" was wrong: the runs record `correct`. `_vals` came back empty and
    # 0 classification rows were checked for a week, while the aggregate floor of 40
    # was cleared by the other three reports. Found by external review.
    "ag_news_200": ("ag_", "correct", DATA),
    "dbpedia_280": ("db_", "correct", DATA),
    "cnn_dailymail_200": ("cnn_", "coverage", DATA),
}
REPORT_DATASETS = {
    "REPORT_NER.md": ["few_nerd_280"],
    "REPORT_RETRIEVAL.md": ["scifact_200"],
    "REPORT_CLASSIFICATION.md": ["ag_news_200", "dbpedia_280"],
    "REPORT_SUMMARIZATION.md": ["cnn_dailymail_200"],
    # SYNTHESIS tables are keyed by EXPERIMENT, not by arm, so this check cannot
    # reach them and the per-report floor below deliberately excludes it.
    "REPORT_SYNTHESIS.md": list(PRIMARY_BY_DATASET),
}
def _runs_for(base, dataset_id, prefix):
    """One deterministic answer per arm, or a hard failure. See _common.runs_by_arm.

    Every lookup in this file used to be its own glob -- three took the last hit, two
    the first, one had a different exclusion rule -- so with two runs sharing a
    config_id the answer depended on filesystem order. Green on APFS, red on ext4, and
    `make ci` was called green for a week on the only machine anyone ran it on.
    """
    try:
        return runs_by_arm(base, dataset_id, prefix=prefix, strip="_n200_v1")
    except AmbiguousRuns as exc:
        print(f"FAIL  {exc}")
        sys.exit(1)


def _billed_of(run_dir):
    """What the provider charged for this run, summed from _meta.usage.cost."""
    pj = run_dir / "predictions.jsonl"
    if not pj.is_file():
        return 0.0
    total = 0.0
    for line in pj.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            total += float((((r.get("_meta") or {}).get("usage") or {}).get("cost") or 0))
    return total


#: Column headers that mean "this cell is the arm's primary metric on this dataset".
#: The check is COLUMN-AWARE for a reason: a row's first number is not always its score.
#: Matching on position flagged nine legitimate cells -- the "as first measured" column
#: of a before/after correction table, and a paired-run table whose columns are "over
#: BM25" and "over e5_base" for entirely different runs. A check that cries wolf on
#: honest history teaches you to ignore it.
METRIC_HEADERS = {
    "f1": {"f1"},
    "ndcg_10": {"ndcg@10", "ndcg_10"},
    "correct": {"accuracy", "acc", "correct"},
    "coverage": {"coverage"},
}
_stale_rows = []
_rows_checked = 0
_rows_per_report: dict = {}
for _rep, _dss in REPORT_DATASETS.items():
    _lines = (ROOT / "research" / _rep).read_text().splitlines()
    for _ds in _dss:
        _pref, _metric, _base = PRIMARY_BY_DATASET[_ds]
        _vals = {}
        for f in _glob.glob(str(_base / f"{_pref}*" / "metrics.json")):
            if "20260929" in Path(f).parent.name:
                continue
            _m = json.load(open(f))
            if _m.get("dataset_id") != _ds:
                continue
            _v = (_m.get("scores") or {}).get(_metric)
            if _v is not None:
                _vals[_m["config_id"].replace(_pref, "").replace("_n200_v1", "")] = _v
        _col = None
        for _i, _line in enumerate(_lines):
            if not _line.startswith("|"):
                _col = None
                continue
            _cells = [c.strip() for c in _line.strip("|").split("|")]
            # A header row: remember which column holds the primary metric, if any.
            _low = [c.lower().replace("*", "").strip() for c in _cells]
            if any(h in METRIC_HEADERS[_metric] for h in _low):
                _col = next(j for j, h in enumerate(_low)
                            if h in METRIC_HEADERS[_metric])
                continue
            if _col is None or _col >= len(_cells):
                continue
            _arm = re.sub(r"[`*\u27f3 ]", "", _cells[0])
            if _arm not in _vals:
                continue
            _mm = re.fullmatch(r"\*{0,2}(0\.[0-9]{3,4})\*{0,2}", _cells[_col])
            if not _mm:
                continue
            _rows_checked += 1
            _rows_per_report[_rep] = _rows_per_report.get(_rep, 0) + 1
            if abs(float(_mm.group(1)) - _vals[_arm]) > 0.0002:
                _stale_rows.append(f"{_rep}:{_i+1}: {_arm} shows {_mm.group(1)}, "
                                   f"the run says {_vals[_arm]:.4f}")
# ---- AND THE SAME THING INSIDE CODE BLOCKS ---------------------------------------
#
# Both checks above read only lines starting with "|". The classification report's
# leaderboards are fenced code blocks, so 0 of its rows were ever checked -- and its
# cost cells were still price-table figures, summing to $0.49 in a section whose own
# header says "$0.58 billed". Found by external review.
#
# NARROW ON PURPOSE, because a loose version of this was worse than nothing. My first
# attempt took "the first number after an arm name" in any code block, and produced 58
# failures of which nearly all were wrong: it read the Δ column of a family-test block
# as an f1, and matched `qwen_m` in the DBpedia block against the AG News run, because
# both datasets appear in one report. A check that cries wolf gets muted.
#
# So a block is scanned only when BOTH hold:
#   - the section heading above it names this dataset, and
#   - the block's own header line names this dataset's primary metric column.
# Within such a block a record runs from one arm name to the next (these blocks put two
# tables side by side), its FIRST number is the metric and its LAST is the cost.
_num = re.compile(r"^\$?([0-9]+\.[0-9]{3,4})$")
_DATASET_IN_HEADING = {
    "ag_news_200": ("ag news",),
    "dbpedia_280": ("dbpedia",),
    "few_nerd_280": ("few-nerd", "few nerd", "ner"),
    "scifact_200": ("scifact",),
    "cnn_dailymail_200": ("cnn", "dailymail", "summaris"),
}
_METRIC_COLUMN = {"correct": "accuracy", "f1": "f1",
                  "ndcg_10": "ndcg", "coverage": "coverage"}

for _rep, _dss in REPORT_DATASETS.items():
    _lines = (ROOT / "research" / _rep).read_text().splitlines()
    _single = len(_dss) == 1          # a one-dataset report needs no heading match
    for _ds in _dss:
        _pref, _metric, _base = PRIMARY_BY_DATASET[_ds]
        _vals, _bills = {}, {}
        for _arm, _dirs in _runs_for(_base, _ds, _pref).items():
            _m = json.load(open(_dirs[0] / "metrics.json"))
            _v = (_m.get("scores") or {}).get(_metric)
            if _v is not None:
                _vals[_arm] = _v
            _bills[_arm] = _billed_of(_dirs[0])
        _heading_ok = _single
        _in_block = _scan = _has_cost = False
        for _i, _line in enumerate(_lines):
            if _line.startswith("#") and not _in_block:
                _low = _line.lower()
                _heading_ok = _single or any(
                    t in _low for t in _DATASET_IN_HEADING.get(_ds, ()))
                continue
            if _line.startswith("```"):
                if _in_block:
                    _in_block = _scan = False
                else:
                    _in_block = True
                    _scan = False
                continue
            if not _in_block:
                continue
            _toks = _line.split()
            if not _toks:
                continue
            if _toks[0] in ("arm", "config"):      # the block's header row
                _low = _line.lower()
                _scan = _heading_ok and _METRIC_COLUMN[_metric] in _low
                _has_cost = "$/200" in _line or "cost" in _low
                continue
            if not _scan:
                continue
            _idx = [j for j, t in enumerate(_toks) if t in _vals]
            for _k, _j in enumerate(_idx):
                _arm = _toks[_j]
                _stop = _idx[_k + 1] if _k + 1 < len(_idx) else len(_toks)
                _rec = [t for t in _toks[_j + 1:_stop] if _num.fullmatch(t)]
                if not _rec:
                    continue
                _got = float(_num.fullmatch(_rec[0]).group(1))
                if abs(_got - _vals[_arm]) <= 0.5:
                    _rows_checked += 1
                    _rows_per_report[_rep] = _rows_per_report.get(_rep, 0) + 1
                    if abs(_got - _vals[_arm]) > 0.0002:
                        _stale_rows.append(f"{_rep}:{_i+1}: {_arm} shows {_got:.4f}, "
                                           f"the run says {_vals[_arm]:.4f}")
                if _has_cost and len(_rec) > 1 and _bills.get(_arm):
                    _c = float(_num.fullmatch(_rec[-1]).group(1))
                    if _c > 0 and abs(_c - _bills[_arm]) > 0.0002:
                        _stale_cost.append(f"{_rep}:{_i+1}: {_arm} costs ${_c:.4f}, "
                                           f"billed ${_bills[_arm]:.4f}")
                    elif _c > 0:
                        _checked_cost += 1

check("report cost cells quote the BILL, not the price table", not _stale_cost,
      "; ".join(_stale_cost[:4]) + (f" (+{len(_stale_cost)-4} more)"
                                    if len(_stale_cost) > 4 else ""))
check("and cost cells were actually found to check", _checked_cost >= 20,
      f"only {_checked_cost} matched a billed figure")
check("every arm row states the run's primary metric", not _stale_rows,
      "; ".join(_stale_rows[:5]) + (f" (+{len(_stale_rows)-5} more)"
                                    if len(_stale_rows) > 5 else ""))
check("and arm rows were actually found to check", _rows_checked >= 40,
      f"only {_rows_checked} rows matched an arm")
# PER REPORT, not in aggregate. The aggregate floor is what let classification sit at
# zero rows while NER, retrieval and summarisation carried the total past 40.
for _rep in [r for r in REPORT_DATASETS if r != "REPORT_SYNTHESIS.md"]:
    _n = _rows_per_report.get(_rep, 0)
    check(f"...including {_rep} ({_n} rows)", _n > 0,
          "no arm row in this report was checked against a run")

# ---- RATIOS AND COUNTS, the other two classes nothing checked -------------------
#
# Round 2: "it also checks only single-run primary metrics, so it wouldn't have caught
# any of the round-1 cost, ratio or tie-count errors." Cost was added above. These are
# the other two, and they are where round 2 actually found wrong numbers: 38x was 19.6x,
# 18x was 11.4x, the Pareto frontier was 8 of 24 and not 7.
#
# Each is RECOMPUTED from the committed runs and compared to what the report states.


def _arm_costs(prefix, dataset_id):
    """Billed cost per arm, excluding the 2026-09-29 re-runs (which duplicate arms)."""
    out = {}
    for f in _glob.glob(str(DATA / f"{prefix}*" / "metrics.json")):
        if "20260929" in Path(f).parent.name:
            continue
        m = json.load(open(f))
        if m.get("dataset_id") != dataset_id:
            continue
        pj = Path(f).parent / "predictions.jsonl"
        if not pj.is_file():
            continue
        bil = rec = 0.0
        for line in pj.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rec += float(r.get("cost_usd") or 0)
            bil += float((((r.get("_meta") or {}).get("usage") or {}).get("cost") or 0))
        out[m["config_id"].replace(prefix, "").replace("_n200_v1", "")] = bil or rec
    return out


#: (label, prefix, dataset, cheap arm, claimed ratio against the DEAREST paid arm)
#: (label, prefix, dataset, cheapest tied arm, the synthesis table row that states it)
CHEAPNESS = [
    ("Summarisation cheapest-tied vs dearest", "cnn_", "cnn_dailymail_200",
     "deepseek_s", "| Summarisation · CNN/DM | 15 arms (13 paid) |"),
    ("DBpedia cheapest-tied vs dearest", "db_", "dbpedia_280",
     "gemma_m", "| Classification · DBpedia | 19 arms (18 paid) |"),
    # Was gemma_s / 9 arms around bert_mini. The bert-base leader ties with one paid arm.
    ("AG News cheapest-tied vs dearest", "ag_", "ag_news_200",
     "anthropic_m", "| Classification · AG News | 3 arms (1 paid) |"),
]
# THE CLAIMED RATIO IS READ OUT OF THE REPORT, NOT OUT OF THIS FILE.
#
# My first version of this block compared the recomputed ratio to a literal written
# here -- which is precisely the bug round 2 found in `check_model_facts.py`, that a
# checker comparing its own constants to the data verifies the checker. I fixed it
# there and reintroduced it here within the hour, and only caught it by reverting a
# report number and watching this pass 28/28.
SYNTH = (ROOT / "research" / "REPORT_SYNTHESIS.md").read_text()
SUMM = (ROOT / "research" / "REPORT_SUMMARIZATION.md").read_text()


def _claimed_ratio(text, row_key, pattern=r"\*\*([0-9,.]+)× cheaper\*\*"):
    """The 'N× cheaper' the named table row states, or None."""
    for line in text.splitlines():
        if row_key in line:
            m = re.search(pattern, line)
            if m:
                return float(m.group(1).replace(",", ""))
    return None


for label, pref, ds, cheap, row_key in CHEAPNESS:
    claimed = _claimed_ratio(SYNTH, row_key)
    if claimed is None:
        missing += 1
        print(f"  --   {label}: no '× cheaper' claim found for {row_key!r} — skipped")
        continue
    c = _arm_costs(pref, ds)
    paid = {k: v for k, v in c.items() if v > 0}
    if cheap not in paid:
        missing += 1
        print(f"  --   {label}: {cheap} not present — skipped")
        continue
    got = max(paid.values()) / paid[cheap]
    check(f"{label} (report says {claimed:g}×)", abs(got - claimed) / claimed <= 0.02,
          f"the report says {claimed:g}×, the bill gives {got:.1f}×")

#: Pairwise cost ratios the summarisation report states in its separation tables.
CNN = _arm_costs("cnn_", "cnn_dailymail_200")
for dear, cheap in (("anthropic_m", "deepseek_m"), ("openai_l", "deepseek_m")):
    m = re.search(r"`deepseek_m` vs `" + dear + r"` — ([0-9.]+)×", SUMM)
    if not m:
        missing += 1
        print(f"  --   Summarisation {cheap} vs {dear}: no ratio stated — skipped")
        continue
    claimed = float(m.group(1))
    if CNN.get(dear) and CNN.get(cheap):
        got = CNN[dear] / CNN[cheap]
        check(f"Summarisation {dear} is {claimed}× {cheap} (as the report states)",
              abs(got - claimed) / claimed <= 0.05,
              f"the report says {claimed}×, the bill gives {got:.1f}×")

# Pareto frontier over the 24 HOSTED summarisation arms: quality, cost, latency.
_cnn_q = {}
for f in _glob.glob(str(DATA / "cnn_*" / "metrics.json")):
    if "20260929" in Path(f).parent.name:
        continue
    m = json.load(open(f))
    if m.get("dataset_id") != "cnn_dailymail_200":
        continue
    arm = m["config_id"].replace("cnn_", "").replace("_n200_v1", "")
    sc = m.get("scores") or {}
    # Hosted = what the run says it called, not a list of names to leave out. The list
    # was ("bart_l", "lead3"); three more local arms arrived and every one of them would
    # have been counted as hosted.
    if (m.get("params") or {}).get("provider") != "litellm":
        continue
    _cnn_q[arm] = (sc.get("coverage", 0), CNN.get(arm, 0), sc.get("latency_ms", 0))
_hosted = dict(_cnn_q)
_front = [a for a in _hosted if not any(
    b != a and _hosted[b][0] >= _hosted[a][0] and _hosted[b][1] <= _hosted[a][1]
    and _hosted[b][2] <= _hosted[a][2]
    and (_hosted[b][0] > _hosted[a][0] or _hosted[b][1] < _hosted[a][1]
         or _hosted[b][2] < _hosted[a][2])
    for b in _hosted)]
if len(_hosted) == 24:
    m = re.search(r"\*\*(\d+) of 24\*\* \| three arms", SUMM)
    if m:
        check(f"Summarisation Pareto frontier is the {m.group(1)} of 24 the report states",
              len(_front) == int(m.group(1)),
              f"the report says {m.group(1)} of 24, recomputed {len(_front)}")
    else:
        missing += 1
        print("  --   Pareto frontier: the report states no 'N of 24' — skipped")
else:
    missing += 1
    print(f"  --   Pareto frontier: {len(_hosted)} hosted arms, not 24 — skipped")

for label, base, cid, metric, lo, hi in PREDICTIONS:
    got = score(base, cid, metric)
    if got is None:
        missing += 1
        print(f"  --   {label}: run not present ({cid}) — skipped")
        continue
    check(label, lo <= got <= hi, f"registered {lo}-{hi}, run says {got:.6f}")

print(f"\n{sum(ok)}/{len(ok)} claims verified against the committed runs"
      + (f", {missing} skipped (runs absent)" if missing else ""))

# A SKIPPED CLAIM IS A FAILED CHECK, NOT A PASSED ONE. With no runs on disk every claim
# skipped, `ok` stayed empty, `all([])` was True, and this printed "0/0 claims verified"
# and exited 0 -- the check reporting success for having checked nothing. The runs are
# committed, so a missing one means the tree is broken or the claim names a run that
# does not exist; neither is a pass.
if missing:
    print(f"FAIL  {missing} claim(s) could not be checked because their run is absent.")
    print("      Every claimed run is committed, so this means the claim names a run")
    print("      that does not exist, or data/runs{,-rescored} is incomplete.")
    sys.exit(1)
if not ok:
    print("FAIL  no claims were checked at all — this check is not looking at the repo")
    sys.exit(1)
sys.exit(0 if all(ok) else 1)
