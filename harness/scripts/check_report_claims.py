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
import glob
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "runs"
RESCORED = HERE.parent / "data" / "runs-rescored"

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
    ("NER glm_l parsed",          RESCORED, "fn_glm_l_n200_v1",       "parsed",    0.8357),
    ("SciFact glm_s ndcg@10",     DATA,     "sf_glm_s_n200_v1",       "ndcg_10",   0.7437),
    ("SciFact e5_base ndcg@10",   DATA,     "sf_e5_base_n200_v1",     "ndcg_10",   0.7191),
    ("SciFact bm25 ndcg@10",      DATA,     "sf_bm25_n200_v1",        "ndcg_10",   0.6451),
    ("SciFact rerank recall@100", DATA,     "sf_glm_s_n200_v1",       "recall_100",0.8586),
    ("AG News bert_mini",         DATA,     "ag_bert_mini_n200_v1",   "correct",   0.9450),
    ("DBpedia qwen_m",            DATA,     "db_qwen_m_n200_v1",      "correct",   0.9929),
    ("Summarisation bart_l",      DATA,     "cnn_bart_l_n200_v1",     "coverage",  0.3461),
]

#: (label, claimed, a - b) — the DIFFERENCES the reports lead with.
DELTAS = [
    ("NER fine-tuning is worth +0.3134", 0.3134,
     (RESCORED, "fn_span_marker_n200_v1", "f1"), (RESCORED, "fn_gliner_n200_v1", "f1")),
    ("SciFact BM25 -> e5_base = +0.0740", 0.0740,
     (DATA, "sf_e5_base_n200_v1", "ndcg_10"), (DATA, "sf_bm25_n200_v1", "ndcg_10")),
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

print(f"\n{sum(ok)}/{len(ok)} claims verified against the committed runs"
      + (f", {missing} skipped (runs absent)" if missing else ""))
sys.exit(0 if all(ok) else 1)
