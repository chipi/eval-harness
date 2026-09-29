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
            _m = re.fullmatch(r"\$?([0-9]+\.[0-9]{3,4})", _c.replace("**", ""))
            if not _m:
                continue
            _v = float(_m.group(1))
            if abs(_v - _bil) < 0.0002:
                _checked_cost += 1
            elif abs(_v - _rec) < 0.0002:
                _stale_cost.append(f"{_rep}: {_arm} shows ${_v:.4f} (price table); "
                                   f"billed ${_bil:.4f}")
check("report cost cells quote the BILL, not the price table", not _stale_cost,
      "; ".join(_stale_cost[:4]) + (f" (+{len(_stale_cost)-4} more)"
                                    if len(_stale_cost) > 4 else ""))
check("and cost cells were actually found to check", _checked_cost >= 20,
      f"only {_checked_cost} matched a billed figure")

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
