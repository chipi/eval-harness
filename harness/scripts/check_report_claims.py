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
import statistics
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
REPARSED = HERE.parent / "data" / "runs-reparsed"

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
    ("NER glm_l parsed",          RESCORED, "fn_glm_l_n200_v1",       "parsed",    0.8893),
    # SciFact reads REPARSED, which is the instrument REPORT_RETRIEVAL states. These
    # four pointed at data/runs, which is harmless only because no claimed arm moved
    # under the parser fix -- a claim about qwen_s would have been verified against
    # 0.7338 rather than the report's 0.7183. Found by external review.
    ("SciFact glm_s ndcg@10",     REPARSED, "sf_glm_s_n200_v1",       "ndcg_10",   0.7437),
    ("SciFact e5_base ndcg@10",   REPARSED, "sf_e5_base_n200_v1",     "ndcg_10",   0.7191),
    ("SciFact bm25 ndcg@10",      REPARSED, "sf_bm25_n200_v1",        "ndcg_10",   0.6451),
    ("SciFact rerank recall@100", REPARSED, "sf_glm_s_n200_v1",       "recall_100",0.8586),
    ("AG News bert_mini",         DATA,     "ag_bert_mini_n200_v1",   "correct",   0.9450),
    ("DBpedia qwen_m",            DATA,     "db_qwen_m_n200_v1",      "correct",   0.9929),
    ("Summarisation bart_l",      DATA,     "cnn_bart_l_n200_v1",     "coverage",  0.3461),
    # The six local arms added 2026-09-30.
    ("AG News bert_base_ta",      DATA,     "ag_bert_base_ta_n200_v1", "correct",  0.9600),
    ("AG News bert_base_fy",      DATA,     "ag_bert_base_fy_n200_v1", "correct",  0.9500),
    ("DBpedia bert_base_fy",      DATA,     "db_bert_base_fy_n200_v1", "correct",  0.9857),
    ("Summarisation bart_m",      DATA,     "cnn_bart_m_n200_v1",      "coverage", 0.3367),
    ("Summarisation bart_s",      DATA,     "cnn_bart_s_n200_v1",      "coverage", 0.3276),
    ("Summarisation bart_l_xsum", DATA,     "cnn_bart_l_xsum_n200_v1", "coverage", 0.2071),
]

#: Which report states each CLAIM. A claim here is a copy of a number in a report, and a
#: copy verified only against the run proves the copy, not the report: change the report's
#: figure and this file still passes. So every claim must also appear, to four decimals,
#: in the report it came from.
CLAIM_REPORT = {"fn_": "REPORT_NER.md", "sf_": "REPORT_RETRIEVAL.md",
                "ag_": "REPORT_CLASSIFICATION.md", "db_": "REPORT_CLASSIFICATION.md",
                "cnn_": "REPORT_SUMMARIZATION.md"}

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

_absent = []
for label, base, cid, metric, claimed in CLAIMS:
    rep = next((r for p, r in CLAIM_REPORT.items() if cid.startswith(p)), None)
    # 4 decimals, or 3 where the report's column is 3dp (NER's parse rate: 0.886).
    _txt = (ROOT / "research" / rep).read_text() if rep else ""
    if rep and f"{claimed:.4f}" not in _txt and f"{claimed:.3f}" not in _txt:
        _absent.append(f"{label}: {claimed:.4f} not in {rep}")
check(f"every claimed figure appears in its report ({len(CLAIMS)} checked)", not _absent,
      "; ".join(_absent[:5]))

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
        # ONLY skip an arm with no bill. This also skipped every arm whose recorded
        # cost already EQUALS its bill -- commented "the table happens to be right",
        # which is a statement about the RUN, not about the cell in the report. So any
        # arm measured since the 2026-09-29 adapter fix had its table cost unchecked,
        # and that is every hosted run from here on. Changing anthropic_l's $0.6897 to
        # $0.5000 passed. Found by external review.
        #
        # When bill == recorded the "price table" branch below is simply unreachable
        # and the "neither" branch still does the work.
        if _bil <= 0:
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
            elif _v > 0:
                # NEITHER the bill nor the price table. This used to pass: the check
                # only recognised the one wrong value it knew about, so a cost that was
                # simply made up sailed through. Found by external review.
                #
                # AND THE 2% TOLERANCE THAT USED TO GUARD THIS BRANCH LEFT A SILENT
                # BAND. The three bands were "within $0.0002 of the bill" (counted),
                # "equals the price table" (flagged) and "more than 2% off" (flagged) --
                # so $0.1421 written as $0.1445, 1.7% off, was neither counted nor
                # flagged. It did not fail and it did not count towards the floor that
                # proves this scan looked at anything. A cost cell is a transcription
                # of a number we hold; there is no tolerance to spend. Round 5, R5-L3.
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

# ---- AND A NARROW SLICE OF PROSE -------------------------------------------------
#
# Numbers in sentences were the one surface nothing reached, and they are how several
# stale figures survived three rounds. The obvious rule -- any 4-decimal number near an
# arm name -- measured 17 true against 21 FALSE positives, because `anthropic_l ...
# 0.6897` is that arm's cost sitting beside its name. A check that cries wolf gets
# muted, so that version was deliberately not shipped.
#
# This is the narrow form an external reviewer proposed and measured: the number must
# follow the arm name IMMEDIATELY, through one of four connectives. Re-measured here
# over all four reports: 5 true, 0 false. It would have caught drift shaped like
# "`span_marker` scored 0.7674".
# WIDENED IN ROUND 5, by measurement, and one proposed widening was REJECTED by the
# same measurement. The narrow rule matched 5 of the 57 arm-adjacent figures, and an
# external review named three shapes it misses. Measured on this tree:
#
#   rule                                          checked   false positives
#   narrow (the round-4 rule)                        5            0
#   + parenthetical prefix, + table CELLS            7            0   <- shipped
#   + `**` as a connective                           9            1
#   naive "within 60 characters of an arm name"     38           21
#
# So `bart_m` (1.2 GB, 0.3367) and the exec-summary cells are now read, and
# `bert_base_ta` **0.9600 is still not: admitting bold-as-connective also admits
# `qwen_s` **0.7799**, which is a headroom figure and 0.06 from that arm's ndcg_10, so
# the "same metric" filter cannot exclude it. One false positive on a correct tree is
# how a check gets muted, and this repo has paid for that lesson once.
#
# TABLE ROWS ARE SCANNED PER CELL, not per row. Scanning the row let a tier row's AG
# News cell supply numbers for the DBpedia arm named in the next cell -- 3 of the 4
# false positives the first attempt produced. A cell is the unit the sentence is in.
#
# The `$` lookbehind is load-bearing: `anthropic_l at **$0.6897**` is that arm's COST
# beside its name, 0.0099 from its f1, which the "same metric" filter does not exclude.
_PROSE = re.compile(
    r"`([a-z0-9_]+)`\s*"
    r"(?:\((?:[^)]*?,\s*)?|at |scored |\u2014\s*)"
    r"\*{0,2}(?<![$\d.])(0\.[0-9]{4})\*{0,2}")
_prose_bad, _prose_checked = [], 0
for _rep, _dss in REPORT_DATASETS.items():
    if _rep == "REPORT_SYNTHESIS.md":
        continue                       # keyed by experiment, and spans five datasets
    _lines = (ROOT / "research" / _rep).read_text().splitlines()
    for _ds in _dss:
        _pref, _metric, _base = PRIMARY_BY_DATASET[_ds]
        _vals = {}
        for _arm, _dirs in _runs_for(_base, _ds, _pref).items():
            _v = (json.load(open(_dirs[0] / "metrics.json")).get("scores") or {}).get(_metric)
            if _v is not None:
                _vals[_arm] = _v
        _fenced = False
        for _i, _line in enumerate(_lines, 1):
            if _line.startswith("```"):
                _fenced = not _fenced
                continue
            if _fenced:
                continue               # code blocks have their own scan
            if _line.lstrip().startswith("|"):
                # EXEC-SUMMARY ROWS. The leaderboard scan reads the big per-arm tables,
                # keyed on the arm being the row's first cell. An exec-summary row's
                # first cell is a TIER ("**Self-host · small ML**") and the arm is
                # named inside the prose cell beside it, so 23 such rows across the
                # four reports were read by nothing. Here the arm is taken from
                # anywhere in the row and every 4-dp number in it is compared, under
                # the same "within 0.5 of the primary metric" rule the code-block scan
                # uses. Round 5, R5-M6.
                _cells = _line.split("|")
                if len(_cells) < 3 or _i > 60:
                    continue           # exec summaries live at the top of a report
                for _cell in _cells:
                    for _m in _PROSE.finditer(_cell):
                        _arm, _got = _m.group(1), float(_m.group(2))
                        if _arm not in _vals or abs(_got - _vals[_arm]) > 0.5:
                            continue   # not this metric; do not guess
                        _prose_checked += 1
                        if abs(_got - _vals[_arm]) > 0.0002:
                            _prose_bad.append(
                                f"{_rep}:{_i}: exec summary, {_arm} reads {_got:.4f}, "
                                f"the run says {_vals[_arm]:.4f}")
                continue
            for _m in _PROSE.finditer(_line):
                _arm, _got = _m.group(1), float(_m.group(2))
                if _arm not in _vals or abs(_got - _vals[_arm]) > 0.5:
                    continue           # not this metric; do not guess
                _prose_checked += 1
                if abs(_got - _vals[_arm]) > 0.0002:
                    _prose_bad.append(f"{_rep}:{_i}: {_arm} reads {_got:.4f}, "
                                      f"the run says {_vals[_arm]:.4f}")
check("prose figures that name an arm match the run", not _prose_bad,
      "; ".join(_prose_bad[:4]))
check(f"and prose figures were actually found to check ({_prose_checked})",
      _prose_checked >= 7,
      f"only {_prose_checked} matched")

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

#: THE TIE GROUP ITSELF, recomputed. The rows above lock onto "| … | 15 arms (13 paid) |"
#: and check only the ratio after it; the group size and the cheapest tied arm were
#: literals in this file, so when two arms joined AG News and the group went from 9 to 3,
#: nothing here could have noticed. Now: run the leader's Holm family test, count what it
#: does not separate from, split paid from free by the provider each run recorded, and
#: compare all three to what the synthesis row says. (leader, runs dir, dataset, metric,
#: prefix, the row's first cell)
TIE_GROUPS = [
    ("cnn_bart_l_n200_v1", DATA, "cnn_dailymail_200", "coverage", "cnn_", "| Summarisation · CNN/DM |"),
    ("db_qwen_m_n200_v1", DATA, "dbpedia_280", "correct", "db_", "| Classification · DBpedia |"),
    ("ag_bert_base_ta_n200_v1", DATA, "ag_news_200", "correct", "ag_", "| Classification · AG News |"),
]


def _not_separated(leader, runs_dir, dataset_id, metric):
    """Opponents the leader's Holm family test does not separate from, or None."""
    import subprocess  # noqa: PLC0415
    r = subprocess.run(
        [sys.executable, str(HERE / "family_test.py"), "--dataset-id", dataset_id,
         "--a", leader, "--against", "_n200_v1", "--metric", metric,
         "--runs-dir", str(runs_dir)],
        capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [ln.split()[0] for ln in r.stdout.splitlines()
            if ln.strip().endswith("--") and ln.split()[0].endswith("_n200_v1")]


def _provider(runs_dir, config_id):
    for f in sorted(glob.glob(str(runs_dir / f"{config_id}_2*" / "metrics.json"))):
        if "20260929" in Path(f).parent.name:
            continue
        return (json.load(open(f)).get("params") or {}).get("provider")
    return None


for leader, rdir, ds, metric, pref, cell in TIE_GROUPS:
    # The first cell repeats across the synthesis's tables; the tie row is the one that
    # says "N arms".
    _tie = re.compile(r"\|\s*(\d+) arms(?: \((\d+) paid\))?\s*\|\s*`([a-z0-9_]+)`")
    m = next((_tie.search(ln) for ln in SYNTH.splitlines()
              if ln.startswith(cell) and _tie.search(ln)), None)
    if not m:
        missing += 1
        print(f"  --   tie group {cell.strip('| ')}: row not found in the synthesis — skipped")
        continue
    tied = _not_separated(leader, rdir, ds, metric)
    if tied is None:
        missing += 1
        print(f"  --   tie group {cell.strip('| ')}: family test did not run — skipped")
        continue
    paid = [a for a in tied if _provider(rdir, a) == "litellm"]
    costs = _arm_costs(pref, ds)
    cheapest = min(paid, key=lambda a: costs.get(a.replace(pref, "").replace("_n200_v1", ""),
                                                 float("inf"))) if paid else None
    n, n_paid, named = int(m.group(1)), int(m.group(2) or m.group(1)), m.group(3)
    got_name = cheapest.replace(pref, "").replace("_n200_v1", "") if cheapest else None
    check(f"tie group {cell.strip('| ')}: {n} arms ({n_paid} paid), cheapest `{named}`",
          len(tied) == n and len(paid) == n_paid and got_name == named,
          f"the row says {n} ({n_paid} paid), cheapest {named}; the family test gives "
          f"{len(tied)} ({len(paid)} paid), cheapest {got_name}")

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

# ---- THE RE-TIMED LATENCY TABLE ------------------------------------------------
#
# `data/runs-linux/` holds the one-machine re-timing that three reports quote, and
# reviewing the merged ML-arm work found NOTHING read it -- `grep -n runs-linux
# scripts/*.py` returned nothing at all. Nine published figures, six documents citing
# the directory, zero checks. It is the same defect round 4 found one directory over,
# so it is closed the same way: the medians are recomputed here, and V9 now refuses to
# let the directory be deleted.
#
# MEDIANS, not means: a local arm's first one to three items pay a one-off
# initialisation the warm-up does not absorb, which is why the reports quote medians.
_LINUX = ROOT / "harness" / "data" / "runs-linux"
#: (config_id, the report that quotes it, the unit, decimals). The figure itself is
#: DERIVED from the runs and then looked for in the report -- it is deliberately not
#: written here. A literal here would make this check compare the runs to the checker,
#: which is round-3 M9: the check passes while the report says something else. I made
#: exactly that mistake once already in this file's ratio checks.
#: ...plus the arm as the reports name it, so each figure is sought in the paragraph
#: that is ABOUT that arm. Joining every citing paragraph made this an existence check
#: again, one scope wider: a figure was accepted if it appeared in any of them. It is
#: not exploitable on this tree -- each figure occurs in exactly one citing paragraph
#: per report -- but it becomes so the day a second paragraph repeats a number, which
#: is a check that works until it matters. Round 5, R5-L4.
_LATENCY = [
    ("cnn_bart_l_n200_v1",  "bart_l",  "REPORT_SUMMARIZATION.md", "s",  1000.0, 1),
    ("cnn_bart_m_n200_v1",  "bart_m",  "REPORT_SUMMARIZATION.md", "s",  1000.0, 1),
    ("cnn_bart_s_n200_v1",  "bart_s",  "REPORT_SUMMARIZATION.md", "s",  1000.0, 1),
    ("ag_bert_base_ta_n200_v1", "bert_base_ta", "REPORT_CLASSIFICATION.md", "ms", 1.0, 0),
    ("ag_bert_base_fy_n200_v1", "bert_base_fy", "REPORT_CLASSIFICATION.md", "ms", 1.0, 0),
    ("ag_bert_mini_n200_v1",    "bert_mini",    "REPORT_CLASSIFICATION.md", "ms", 1.0, 1),
]
if not _LINUX.is_dir():
    missing += 1
    print("  --   re-timed latency: data/runs-linux is absent — skipped")
else:
    # LAST WRITE WINS WAS THE BUG. This built `_medians[config_id]` over a sorted glob,
    # so a second run of one arm overwrote the first or did not, purely by how the two
    # directory names sorted -- the round-3 ext4 defect, which `runs_by_arm` exists to
    # refuse. V8 now also covers `runs-linux`, and this refuses independently, because
    # a checker that silently picks one of two measurements is the thing being fixed.
    _medians, _dupes = {}, []
    for _d in sorted(_LINUX.glob("*/predictions.jsonl")):
        _cid = json.load(open(_d.parent / "metrics.json")).get("config_id")
        _lat = [json.loads(_l)["latency_ms"] for _l in
                _d.read_text().splitlines() if _l.strip()]
        if not _lat:
            continue
        if _cid in _medians:
            _dupes.append(_cid)
        _medians[_cid] = statistics.median(_lat)
    check("runs-linux names each arm once (the medians depend on it)", not _dupes,
          f"{sorted(set(_dupes))} appear(s) twice — the median read below is whichever "
          f"directory sorted last")
    for _cid, _arm, _rep, _unit, _div, _places in _LATENCY:
        if _cid not in _medians:
            missing += 1
            print(f"  --   re-timed latency {_cid}: not in runs-linux — skipped")
            continue
        _want = f"{_medians[_cid] / _div:.{_places}f}"
        _text = (ROOT / "research" / _rep).read_text()
        # ONLY the lines that cite `runs-linux`, for every unit. Searching the whole
        # file made this an EXISTENCE check: planting "9.9 s" on the line that cites
        # the directory still passed, because an unrelated sentence elsewhere also
        # says 6.3 s. A check that passes when the sentence it is about is wrong is
        # not a check. (The copies of these figures in prose that does NOT cite the
        # directory remain unchecked -- KNOWN_ISSUES says so.)
        # PARAGRAPHS that cite `runs-linux`, not lines. Scoping to the line was too
        # tight the other way: the summarisation sentence wraps, and `bart_s`'s 3.4 s
        # sits on the continuation line while `runs-linux` sits on the first. Scoping
        # to the whole file was too loose -- it made this an EXISTENCE check that
        # passed with "9.9 s" planted on the citing line, because an unrelated
        # sentence elsewhere also says 6.3 s. The paragraph is the sentence's actual
        # extent. (Copies of these figures in prose that does NOT cite the directory
        # stay unchecked; KNOWN_ISSUES says so.)
        _paras = [_p for _p in _text.split("\n\n")
                  if "runs-linux" in _p and f"`{_arm}`" in _p]
        if not _paras:
            missing += 1
            print(f"  --   re-timed latency {_cid}: no paragraph of {_rep} cites "
                  f"runs-linux AND names `{_arm}` — skipped")
            continue
        _near = "\n\n".join(_paras)
        check(f"re-timed latency: {_rep} states {_want} {_unit} for {_cid}",
              re.search(rf"(?<![\d.]){re.escape(_want)}(?![\d])", _near) is not None,
              f"the runs-linux median is {_want} {_unit}; the report does not say it")
    # THE THREE CROSS-MACHINE FIGURES. The commit that added `runs-linux` listed nine
    # published numbers and checked six plus two ratios; these three were stated and
    # checked by nothing, and all three were falsifiable with 53/53 still printing.
    # They compare `data/runs` (the 12-core Mac) to `runs-linux` (the 4-core Linux
    # box), so they are derived from BOTH trees. Found by external review, round 5.
    _mac = {}
    for _d in sorted(DATA.glob("cnn_bart_*/predictions.jsonl")):
        _cid = json.load(open(_d.parent / "metrics.json")).get("config_id")
        _lat = [json.loads(_l)["latency_ms"] for _l in
                _d.read_text().splitlines() if _l.strip()]
        if _lat:
            _mac[_cid] = (statistics.fmean(_lat), statistics.median(_lat))
    if "cnn_bart_l_n200_v1" in _mac and "cnn_bart_l_n200_v1" in _medians:
        _ratio = _mac["cnn_bart_l_n200_v1"][1] / _medians["cnn_bart_l_n200_v1"]
        _r = f"{_ratio:.1f}"
        for _rep in ("REPORT_SUMMARIZATION.md", "REPORT_SYNTHESIS.md"):
            _t = (ROOT / "research" / _rep).read_text()
            check(f"cross-machine: {_rep} says the Linux box ran bart_l {_r}x faster",
                  re.search(rf"{re.escape(_r)}\u00d7 (?:\*)?faster", _t) is not None,
                  f"median/median is {_mac['cnn_bart_l_n200_v1'][1]:.1f} / "
                  f"{_medians['cnn_bart_l_n200_v1']:.1f} = {_r}x; the report says "
                  f"something else")
    if "cnn_bart_s_n200_v1" in _mac:
        _mean, _med = _mac["cnn_bart_s_n200_v1"]
        _summ = (ROOT / "research" / "REPORT_SUMMARIZATION.md").read_text()
        check(f"contaminated run: the report states bart_s's recorded mean "
              f"{_mean:.0f} ms",
              re.search(rf"(?<![\d,]){_mean:.0f}(?![\d])", _summ) is not None,
              f"data/runs cnn_bart_s mean is {_mean:.1f} ms; the report does not say it")
        _mfmt = f"{_med:,.0f}"
        check(f"contaminated run: the report states its own median {_mfmt} ms",
              _mfmt in _summ,
              f"data/runs cnn_bart_s median is {_med:.1f} ms; the report does not "
              f"say it")

    # And the two RATIOS the summarisation report draws from the same table, likewise
    # derived here and then looked for in the prose.
    if {"cnn_bart_l_n200_v1", "cnn_bart_m_n200_v1", "cnn_bart_s_n200_v1"} <= set(_medians):
        _bl = _medians["cnn_bart_l_n200_v1"]
        _sum = (ROOT / "research" / "REPORT_SUMMARIZATION.md").read_text()
        for _cid, _name in (("cnn_bart_m_n200_v1", "bart_m"), ("cnn_bart_s_n200_v1", "bart_s")):
            _got = f"{_medians[_cid] / _bl:.2f}"
            check(f"re-timed latency: the report states {_name} at {_got}x bart_l",
                  f"{_got}\u00d7" in _sum,
                  f"one-machine ratio is {_got}x; the report does not state it")

# ---- THE CONVERSION-PR EVIDENCE ------------------------------------------------
#
# `docs/evidence/conversion_pr_check.json` backs "byte-identical outputs on every item
# for all three" and the 5-of-6 story in two reports and KNOWN_ISSUES. Nothing read it:
# `grep -rn conversion_pr_check harness/scripts` returned nothing, and setting the first
# `byte_identical` from 200 to 150 left every check green. Found by external review,
# round 5. Each assertion below is DERIVED from the capture and then looked for in the
# report, never compared to a literal here.
_CPR = ROOT / "docs" / "evidence" / "conversion_pr_check.json"
if not _CPR.is_file():
    missing += 1
    print("  --   conversion PRs: the capture is absent — skipped")
else:
    _cpr = json.loads(_CPR.read_text())
    _arms = _cpr.get("arms") or {}
    _repro = {k: v for k, v in _arms.items() if v.get("error") is None}
    _failed = {k: v for k, v in _arms.items() if v.get("error") is not None}
    check(f"conversion PRs: the capture covers the 6 blocked arms "
          f"(found {len(_arms)})", len(_arms) == 6,
          "the reports' '5 of 6' is counted from this file")
    # Every arm the capture says reproduced must have done so on EVERY item it checked.
    _part = [f"{k}: {v.get('byte_identical')}/{v.get('items_checked')}"
             for k, v in sorted(_repro.items())
             if v.get("byte_identical") != v.get("items_checked")]
    check(f"conversion PRs: all {len(_repro)} loadable arms are byte-identical on "
          f"every item checked", not _part, "; ".join(_part))
    # ...and the one that did not load is the one the reports name, for the reason
    # they give.
    check("conversion PRs: exactly one arm failed to load, and it is bart_s",
          sorted(_failed) == ["cnn_bart_s_n200_v1"],
          f"the capture says {sorted(_failed)}; the reports say bart_s alone")
    _bs = _arms.get("cnn_bart_s_n200_v1") or {}
    check("conversion PRs: bart_s failed on fp16 LayerNorm, as the reports state",
          "LayerNormKernelImpl" in str(_bs.get("error")) and
          _bs.get("loaded_dtype") == "torch.float16",
          f"capture says dtype={_bs.get('loaded_dtype')} error={str(_bs.get('error'))[:60]}")
    # The three classification arms: the report says byte-identical on EVERY item, and
    # the item counts must be the whole run, not a sample.
    _cls = {k: v for k, v in _repro.items() if k.startswith(("ag_", "db_"))}
    _full = all(v.get("items_checked") == (280 if k.startswith("db_") else 200)
                for k, v in _cls.items())
    check(f"conversion PRs: the {len(_cls)} classification arms were checked on every "
          f"item of their run, not a sample", len(_cls) == 3 and _full,
          f"{ {k: v.get('items_checked') for k, v in sorted(_cls.items())} }")
    # And the reports must state the figure the capture supports.
    _n_bart = sorted({v.get("items_checked") for k, v in _repro.items()
                      if k.startswith("cnn_")})
    if len(_n_bart) == 1:
        _summ = (ROOT / "research" / "REPORT_SUMMARIZATION.md").read_text()
        check(f"conversion PRs: REPORT_SUMMARIZATION states {_n_bart[0]} of "
              f"{_n_bart[0]} items for the BART arms",
              f"{_n_bart[0]} of {_n_bart[0]} items" in _summ,
              f"the capture checked {_n_bart[0]} items per BART arm")
    # The torch version the whole story rests on.
    _ki = (ROOT / "research" / "KNOWN_ISSUES.md").read_text()
    _tv = str(_cpr.get("torch", "")).split("+")[0]
    check(f"conversion PRs: the capture ran on torch {_tv}, as the reports say",
          _tv and f"torch {_tv}" in _ki,
          f"the capture says torch {_cpr.get('torch')}; KNOWN_ISSUES says otherwise")

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
