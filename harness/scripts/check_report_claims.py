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
FP32 = HERE.parent / "data" / "runs-fp32"
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
    # The arm that was blocked for five review rounds, measured 2026-10-01. Pinned
    # because adding it moved every Holm threshold in the NER family from 26 to 27.
    ("NER mistral_l f1",          RESCORED, "fn_mistral_l_n200_v1",   "f1",        0.5979),
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
    # The DailyMail slice (2026-10-14): the summarisation sample was all CNN, so the five
    # local arms re-ran on 200 DailyMail articles. REPORT_SUMMARIZATION §3.7 quotes these.
    ("DailyMail bart_l",          DATA,     "cnn_bart_l_dm200_v1",      "coverage", 0.4430),
    ("DailyMail bart_m",          DATA,     "cnn_bart_m_dm200_v1",      "coverage", 0.4430),
    ("DailyMail bart_s",          DATA,     "cnn_bart_s_dm200_v1",      "coverage", 0.4039),
    ("DailyMail lead3",           DATA,     "cnn_lead3_dm200_v1",       "coverage", 0.3697),
    ("DailyMail bart_l_xsum",     DATA,     "cnn_bart_l_xsum_dm200_v1", "coverage", 0.1522),
    # bart_s at the precision its config declared (data/runs-fp32, 2026-10-15): the
    # committed runs above are fp16 measurements, and REPORT_SUMMARIZATION says so.
    ("Summarisation bart_s at fp32", FP32,  "cnn_bart_s_n200_v1",      "coverage", 0.3274),
    ("DailyMail bart_s at fp32",  FP32,     "cnn_bart_s_dm200_v1",      "coverage", 0.4048),
    # SummEval judging (2026-10-18): tau against the expert means, REPORT_SUMMEVAL §3.1.
    ("SummEval openai_l tau",     DATA,     "se_openai_l_n100_v1",      "tau",      0.5398),
    ("SummEval gemma_l tau",      DATA,     "se_gemma_l_n100_v1",       "tau",      0.5384),
    ("SummEval qwen37max tau",    DATA,     "se_qwen37max_n100_v1",     "tau",      0.5204),
    ("SummEval llama_s tau",      DATA,     "se_llama_s_n100_v1",       "tau",      0.3533),
    ("SummEval unievalpub tau",   DATA,     "se_unievalpub_n100_v1",    "tau",      0.3717),
    ("SummEval unieval tau",      DATA,     "se_unieval_n100_v1",       "tau",      0.3476),
    ("SummEval bartscore tau",    DATA,     "se_bartscore_n100_v1",     "tau",      0.2562),
    ("SummEval rouge1 tau",       DATA,     "se_rouge1_n100_v1",        "tau",      0.1487),
    ("SummEval coverage tau",     DATA,     "se_coverage_n100_v1",      "tau",      0.1011),
]

#: Which report states each CLAIM. A claim here is a copy of a number in a report, and a
#: copy verified only against the run proves the copy, not the report: change the report's
#: figure and this file still passes. So every claim must also appear, to four decimals,
#: in the report it came from.
CLAIM_REPORT = {"fn_": "REPORT_NER.md", "sf_": "REPORT_RETRIEVAL.md",
                "ag_": "REPORT_CLASSIFICATION.md", "db_": "REPORT_CLASSIFICATION.md",
                "cnn_": "REPORT_SUMMARIZATION.md", "se_": "REPORT_SUMMEVAL.md"}

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
    ("SciFact BM25 -> best reranker (glm_s) = +0.0986", 0.0986,
     (DATA, "sf_glm_s_n200_v1", "ndcg_10"), (DATA, "sf_bm25_n200_v1", "ndcg_10")),
    ("SciFact BM25 -> worst reranker (gemma_s) = +0.0566", 0.0566,
     (DATA, "sf_gemma_s_n200_v1", "ndcg_10"), (DATA, "sf_bm25_n200_v1", "ndcg_10")),
    ("SciFact glm_s on e5_base over main-table BM25 = +0.1441", 0.1441,
     (PAIR, "sf_glm_s_e5first_n200_v1", "ndcg_10"), (DATA, "sf_bm25_n200_v1", "ndcg_10")),
    ("SciFact glm_s on e5_base over e5_base alone = +0.0700", 0.0700,
     (PAIR, "sf_glm_s_e5first_n200_v1", "ndcg_10"), (DATA, "sf_e5_base_n200_v1", "ndcg_10")),
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
    "REPORT_SUMMEVAL.md": ("se_", "summeval_100"),
}

#: The size suffix every config_id ends with. It was a literal "_n200_v1" at each call
#: site, which is right for the five 200-item datasets and silently wrong for SummEval's
#: 100 articles: "se_openai_l_n100_v1" kept its suffix, matched no arm name, and every
#: SummEval row would have been skipped rather than checked.
_SIZE_SUFFIX = re.compile(r"_n\d+_v1$")


def _arm_name(config_id, prefix):
    return _SIZE_SUFFIX.sub("", config_id.replace(prefix, "", 1))


def _first_arm_cell(cells):
    """Index of the arm cell: 0, or 1 when the table leads with a rank column."""
    return 1 if len(cells) > 1 and cells[0].isdigit() else 0


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
        out[_arm_name(m["config_id"], prefix)] = (bil, rec)
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
        _a = _first_arm_cell(_cells)
        _arm = re.sub(r"[`*\u27f3 ]", "", _cells[_a])
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
        for _c in _cells[_a + 1:]:
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
    "summeval_100": ("se_", "tau", DATA),
}
REPORT_DATASETS = {
    "REPORT_NER.md": ["few_nerd_280"],
    "REPORT_RETRIEVAL.md": ["scifact_200"],
    "REPORT_CLASSIFICATION.md": ["ag_news_200", "dbpedia_280"],
    "REPORT_SUMMARIZATION.md": ["cnn_dailymail_200"],
    "REPORT_SUMMEVAL.md": ["summeval_100"],
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
        return runs_by_arm(base, dataset_id, prefix=prefix,
                           strip="_n100_v1" if dataset_id == "summeval_100" else "_n200_v1")
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
    "tau": {"τ", "tau"},
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
                _vals[_arm_name(_m["config_id"], _pref)] = _v
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
            _arm = re.sub(r"[`*\u27f3 ]", "", _cells[_first_arm_cell(_cells)])
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
    "summeval_100": ("summeval",),
}
_METRIC_COLUMN = {"correct": "accuracy", "f1": "f1",
                  "ndcg_10": "ndcg", "coverage": "coverage", "tau": "τ"}

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
        out[_arm_name(m["config_id"], prefix)] = bil or rec
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
    ("SummEval cheapest-tied vs dearest", "se_", "summeval_100",
     "gemma_l", "| Judging · SummEval | 5 arms (5 paid) |"),
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
    ("se_openai_l_n100_v1", DATA, "summeval_100", "tau", "se_", "| Judging · SummEval |"),
]


def _not_separated(leader, runs_dir, dataset_id, metric):
    """Opponents the leader's Holm family test does not separate from, or None."""
    import subprocess  # noqa: PLC0415
    suffix = _SIZE_SUFFIX.search(leader).group(0)
    r = subprocess.run(
        [sys.executable, str(HERE / "family_test.py"), "--dataset-id", dataset_id,
         "--a", leader, "--against", suffix, "--metric", metric,
         "--runs-dir", str(runs_dir)],
        capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [ln.split()[0] for ln in r.stdout.splitlines()
            if ln.strip().endswith("--") and ln.split()[0].endswith(suffix)]


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
    cheapest = min(paid, key=lambda a: costs.get(_arm_name(a, pref), float("inf"))) if paid else None
    n, n_paid, named = int(m.group(1)), int(m.group(2) or m.group(1)), m.group(3)
    got_name = _arm_name(cheapest, pref) if cheapest else None
    check(f"tie group {cell.strip('| ')}: {n} arms ({n_paid} paid), cheapest `{named}`",
          len(tied) == n and len(paid) == n_paid and got_name == named,
          f"the row says {n} ({n_paid} paid), cheapest {named}; the family test gives "
          f"{len(tied)} ({len(paid)} paid), cheapest {got_name}")

# ---- THE CLASSIFICATION REPORT'S "NOT SEPARATED" AND LABEL-NOISE FIGURES --------------
#
# Review 2026-10-19: the report called all three AG News fine-tunes "clearly separated
# from all but one" hosted arm. That is true of the leader only. The per-arm separation
# counts, the 17-item set and the "other 183" comparison below are DERIVED from the
# committed runs and then looked for in the report, so a sentence that drifts from them
# fails here instead of surviving on the tie-group row alone.
import math as _math  # noqa: E402

_CLS = " ".join((ROOT / "research" / "REPORT_CLASSIFICATION.md").read_text().split())
_AG_FAMILY = 29
for _arm, _name in (("ag_bert_base_ta_n200_v1", "bert_base_ta"),
                    ("ag_bert_base_fy_n200_v1", "bert_base_fy"),
                    ("ag_bert_mini_n200_v1", "bert_mini")):
    _tied = _not_separated(_arm, DATA, "ag_news_200", "correct")
    if _tied is None:
        missing += 1
        print(f"  --   classification: family test for {_name} did not run — skipped")
        continue
    _sep = _AG_FAMILY - len(_tied)
    check(f"classification: {_name} is separated from {_sep} of {_AG_FAMILY} and the report says so",
          f"separated from **{_sep}**" in _CLS or f"separated from {_sep} of" in _CLS
          or f"(separated from {_sep}" in _CLS,
          f"family_test gives {_sep} of {_AG_FAMILY}; the report does not state it")


def _cls_correct(prefix, ds_glob_suffix="_n200_v1"):
    out = {}
    for _d in sorted(DATA.glob(f"{prefix}_*{ds_glob_suffix}_2*")):
        _arm = _d.name.rsplit("_2026", 1)[0][len(prefix) + 1:-len(ds_glob_suffix)]
        out[_arm] = {(_r := json.loads(_l))["item_id"]: _r
                     for _l in (_d / "predictions.jsonl").read_text().splitlines() if _l.strip()}
    return out


_AG = _cls_correct("ag")
_NOT_HOSTED = {"bert_base_ta", "bert_base_fy", "bert_mini", "bart_mnli", "keyword", "constant"}
_HOSTED = [_a for _a in _AG if _a not in _NOT_HOSTED]
if len(_HOSTED) == 24:
    _ids = list(_AG["bert_mini"])
    _ok = lambda a, i: _AG[a][i]["correct"] == 1.0  # noqa: E731
    _cut = {_t: [_i for _i in _ids if sum(not _ok(_h, _i) for _h in _HOSTED) / 24 >= _t]
            for _t in (0.8, 0.75, 0.7)}
    check("classification: the 17 / 19 / 20 items at 80% / 75% / 70% of hosted arms wrong",
          f"{len(_cut[0.8])} items at ≥80%" in _CLS or f"{len(_cut[0.8])} items are missed by ≥80%" in _CLS,
          f"derived {[len(_cut[t]) for t in (0.8, 0.75, 0.7)]}")
    check("classification: the 75% and 70% cuts are stated",
          f"{len(_cut[0.75])} at 75%, {len(_cut[0.7])} at 70%" in _CLS,
          f"derived {len(_cut[0.75])} at 75%, {len(_cut[0.7])} at 70%")
    _rest = [_i for _i in _ids if _i not in set(_cut[0.8])]
    _rows = []
    for _o in ("anthropic_l", "anthropic_m"):
        _b = sum(_ok("bert_base_ta", _i) and not _ok(_o, _i) for _i in _rest)
        _c = sum(not _ok("bert_base_ta", _i) and _ok(_o, _i) for _i in _rest)
        _n = _b + _c
        _p = min(1.0, 2 * sum(_math.comb(_n, _k) for _k in range(min(_b, _c) + 1)) / 2 ** _n) if _n else 1.0
        _rows.append((_o, _b, _c, _p))
    _o, _b, _c, _p = _rows[0]
    check(f"classification: on the other {len(_rest)} items {_o} wins {_c} to {_b}, sign p = {_p:.3f}",
          f"discordant items {_c} vs {_b}, exact sign p = {_p:.3f}" in _CLS
          and f"{len(_rest)} items" in _CLS,
          f"derived {_c} vs {_b}, p = {_p:.3f}")
    _o, _b, _c, _p = _rows[1]
    check(f"classification: against {_o} on the other {len(_rest)}: {_b} vs {_c}, p = {_p:.1f}",
          f"`anthropic_m` {_b} vs {_c} (p = {_p:.1f})" in _CLS,
          f"derived {_b} vs {_c}, p = {_p:.1f}")
    _conf = [(_AG["bert_mini"][_i]["confidence"], _ok("bert_mini", _i)) for _i in _ids]
    _hi = [_k for _c_, _k in _conf if _c_ >= 0.8]
    _errs = [_c_ for _c_, _k in _conf if not _k]
    _low_err = sum(_c_ < 0.8 for _c_ in _errs)
    check("classification: bert_mini's confidence buckets and errors above 0.8",
          f"{len(_hi)} items above 0.8 confidence were {sum(_hi) / len(_hi):.1%} correct ({sum(_hi)})" in _CLS
          and f"Of its {len(_errs)} errors, {len(_errs) - _low_err} sit above 0.8" in _CLS
          and f"catch {_low_err} of the {len(_errs)} errors" in _CLS,
          f"derived {len(_hi)} above 0.8 with {sum(_hi)} correct; {len(_errs)} errors, "
          f"{_low_err} below 0.8")

_DB = _cls_correct("db")
if "qwen_m" in _DB and "anthropic_l" in _DB:
    _dids = list(_DB["qwen_m"])
    _learned = [_a for _a in _DB if _a not in ("constant", "keyword")]
    _dok = lambda a, i: _DB[a][i]["correct"] == 1.0  # noqa: E731
    _dis = [_i for _i in _dids if sum(not _dok(_a, _i) for _a in _learned) / len(_learned) >= 0.8]
    _diff = [_i for _i in _dids if _dok("qwen_m", _i) != _dok("anthropic_l", _i)]
    check("classification: qwen_m's one-item lead over anthropic_l is a disputed item, "
          "its only errors are the other disputed items, anthropic_l misses all three",
          len(_dis) == 3 and _diff == [_i for _i in _diff if _i in _dis] and len(_diff) == 1
          and _dok("qwen_m", _diff[0]) and sum(not _dok("qwen_m", _i) for _i in _dids) == 2
          and all(not _dok("qwen_m", _i) for _i in _dis if _i != _diff[0])
          and all(not _dok("anthropic_l", _i) for _i in _dis)
          and "`qwen_m` leads `anthropic_l` by exactly one disputed item" in _CLS,
          f"disputed {len(_dis)}, qwen_m/anthropic_l differ on {len(_diff)}")

# ---- THE CLASSIFICATION SUMMARY'S RENTED-API PICKS, MINIMUM GAP AND PILOT FIGURES --------
#
# Stage-two review 2026-10-19. The summary names the cheapest HOSTED arm the best paid arm
# cannot be separated from, the smallest gap Holm separated on DBpedia, and the pilot's
# tie-aware rho. None of those had a producer. Each is derived here and then looked for
# in the report. The rho is Pearson on midranks (ties share a rank), dev-slice accuracy
# against 200-item accuracy over every arm, which is what the report's footnote states.
import subprocess as _clsp  # noqa: E402


def _cl_midranks(v):
    o = sorted(range(len(v)), key=lambda i: -v[i])
    r, i = [0.0] * len(v), 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _cl_pearson(a, b):
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    return (sum((x - ma) * (y - mb) for x, y in zip(a, b))
            / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5)


def _cl_pilot(runs, dev_file, drop=()):
    _ids = {(_i if isinstance(_i, str) else (_i.get("item_id") or _i.get("id")))
            for _i in json.loads((ROOT / "harness" / "data" / "datasets" / dev_file)
                                 .read_text())["items"]}
    _arms = sorted(a for a in runs if a not in drop)
    _dev = [statistics.fmean(runs[a][i]["correct"] for i in _ids) for a in _arms]
    _all = [statistics.fmean(r["correct"] for r in runs[a].values()) for a in _arms]
    _top = max(_dev)
    _tied = [a for a, m in zip(_arms, _dev) if m == _top]
    return _cl_pearson(_cl_midranks(_dev), _cl_midranks(_all)), _tied, len(_arms)


if "bert_mini" in _AG and "qwen_m" in _DB:
    _r28, _t28, _n28 = _cl_pilot(_AG, "ag_news_20.json", drop=("bert_base_ta", "bert_base_fy"))
    _r30, _t30, _n30 = _cl_pilot(_AG, "ag_news_20.json")
    _d27, _dt27, _dn27 = _cl_pilot(_DB, "dbpedia_56.json", drop=("bert_base_fy",))
    _d28, _dt28, _dn28 = _cl_pilot(_DB, "dbpedia_56.json")
    check("classification: pilot rho (midranks) and the tie at the top of the dev slice",
          (_n28, _n30, _dn27, _dn28) == (28, 30, 27, 28)
          and f"AG News {_r28:.3f} at the 28 arms that existed then, {_r30:.3f} at today's 30"
          in _CLS
          and f"DBpedia {_d27:.3f} at 27, {_d28:.3f} at 28" in _CLS
          and f"{len(_t28)} of 28 arms ({len(_t30)} of 30)" in _CLS
          and f"{len(_dt27)} of 27 arms tied at the top of the 56-item dev slice" in _CLS
          and sorted(_t28)[0] == sorted(_dt27)[0] == "anthropic_l",
          f"derived AG {_r28:.3f}/{_r30:.3f}, ties {len(_t28)}/{len(_t30)}; "
          f"DB {_d27:.3f}/{_d28:.3f}, tie {len(_dt27)}, first {sorted(_dt27)[0]}")

    # AG News: the best paid arm's own family test, not the leader's.
    _am = _not_separated("ag_anthropic_m_n200_v1", DATA, "ag_news_200", "correct")
    if _am is None or len(_HOSTED) != 24:
        missing += 1
        print("  --   classification: anthropic_m family test did not run — skipped")
    else:
        _am_ns = {_arm_name(_a, "ag_") for _a in _am}
        _hosted_ns = [_h for _h in _HOSTED if _h != "anthropic_m" and _h in _am_ns]
        _ag_cost = _arm_costs("ag_", "ag_news_200")
        _cheap = min(_hosted_ns, key=lambda h: _ag_cost[h])
        _acc = lambda a: statistics.fmean(r["correct"] for r in _AG[a].values())  # noqa: E731
        _sep_h = 23 - len(_hosted_ns)
        _per_m = lambda a: round(_ag_cost[a] / 200 * 1e6)  # noqa: E731
        check("classification: anthropic_m is separated from 3 of the 23 other hosted arms; "
              "the cheapest hosted arm it is not separated from, with its gap",
              f"separated from {_sep_h} of the 23 other hosted arms" in _CLS
              and f"is `{_cheap}`, at ${_per_m(_cheap)} and {_acc(_cheap):.4f}, "
                  f"{_acc('anthropic_m') - _acc(_cheap):.4f} behind" in _CLS
              and f"`qwen_m`, at ${_per_m('qwen_m')} and {_acc('qwen_m'):.4f}" in _CLS
              and f"`anthropic_m`, at ${_per_m('anthropic_m')} per 1M items and "
                  f"{_acc('anthropic_m'):.4f}" in _CLS,
              f"derived: separated from {_sep_h}, cheapest not separated {_cheap} "
              f"${_per_m(_cheap)} {_acc(_cheap):.4f}")

    # DBpedia: the smallest gap the leader's Holm test separated.
    _fo = _clsp.run([sys.executable, str(HERE / "family_test.py"), "--dataset-id", "dbpedia_280",
                     "--a", "db_qwen_m_n200_v1", "--against", "_n200_v1", "--metric", "correct",
                     "--runs-dir", str(DATA)], capture_output=True, text=True)
    _rows_f = [ln.split() for ln in _fo.stdout.splitlines()
               if ln.strip().startswith("db_") and ln.split()[-1] in ("SEPARATED", "--")]
    if _fo.returncode != 0 or not _rows_f:
        missing += 1
        print("  --   classification: qwen_m family test did not run — skipped")
    else:
        _lo_sep = min(abs(float(r[1])) for r in _rows_f if r[-1] == "SEPARATED")
        _hi_ns = max(abs(float(r[1])) for r in _rows_f
                     if r[-1] == "--" and r[0] not in ("db_bert_base_fy_n200_v1",))
        check("classification: DBpedia, no gap under 10 items separated; 8 items are not",
              round(_lo_sep * 280) == 10 and round(_hi_ns * 280) == 8
              and "smallest gap Holm separated from `qwen_m` is 10 items" in _CLS
              and "8 items (+0.0286" in _CLS and "10 items (+0.0357" in _CLS,
              f"derived smallest separated {round(_lo_sep * 280)} items, "
              f"largest not separated {round(_hi_ns * 280)}")

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

# ---- SUMMARISATION: PRICE AGAINST QUALITY, PROVIDER MIX, THE PILOT OVERLAP ------------
#
# Review 2026-10-19: "price carried no information" and "demonstrably" rested on r = -0.07
# over 24 arms, which cannot exclude a moderate effect, and nothing here computed the
# correlation, so the report's figures were checked against nothing. Derived from the
# committed runs and looked for in the report: the correlation and its interval, how many
# arms were served by several providers, the pilot-overlap rho, and the cost gap of the
# three dominated arms whose dominator's quality lead is not separated.
import math as _pqm  # noqa: E402


def _pq_ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pq_pearson(x, y):
    mx, my = statistics.fmean(x), statistics.fmean(y)
    return (sum((a - mx) * (b - my) for a, b in zip(x, y))
            / _pqm.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)))


def _pq_sg(x, nd=2):
    return f"+{x:.{nd}f}" if x >= 0 else f"−{-x:.{nd}f}"


_PQ = " ".join(SUMM.split())
if len(_hosted) == 24 and all(CNN.get(_a) for _a in _hosted):
    _pn = sorted(_hosted)
    _cov = [_hosted[_a][0] for _a in _pn]
    _lcost = [_pqm.log10(CNN[_a]) for _a in _pn]
    _r = _pq_pearson(_lcost, _cov)
    _z, _se = _pqm.atanh(_r), 1 / _pqm.sqrt(len(_pn) - 3)
    _lo, _hi = _pqm.tanh(_z - 1.96 * _se), _pqm.tanh(_z + 1.96 * _se)
    _sp = _pq_pearson(_pq_ranks(_lcost), _pq_ranks(_cov))
    _slope = (sum((a - statistics.fmean(_lcost)) * (b - statistics.fmean(_cov))
                  for a, b in zip(_lcost, _cov))
              / sum((a - statistics.fmean(_lcost)) ** 2 for a in _lcost))
    _pct = 100 * _slope / statistics.fmean(_cov)
    _stated = (f"r = {_pq_sg(_r)} (95% CI {_pq_sg(_lo)} to {_pq_sg(_hi)}, "
               f"Spearman {_pq_sg(_sp)}")
    check(f"Summarisation price vs coverage: {_stated.replace('(', '').strip()}, "
          f"{_pq_sg(_pct, 1)}% per 10x, stated in the exec row and in section 4",
          _PQ.count(_stated) >= 2 and f"{_pq_sg(_pct, 1)}%** quality per 10× cost" in _PQ,
          f"derived {_stated}), {_pq_sg(_pct, 1)}% per 10x cost")

    _prov = {}
    for _a, _dirs in _runs_for(DATA, "cnn_dailymail_200", "cnn_").items():
        if _a in _hosted:
            _prov[_a] = len(json.load(open(_dirs[0] / "metrics.json")).get("providers_seen") or {})
    _multi = [_a for _a in _prov if _prov[_a] > 1]
    _one = [_a for _a in _prov if _prov[_a] == 1]
    _dear7 = sorted(_hosted, key=lambda a: -CNN[a])[:7]
    _maxmulti = max(CNN[_a] for _a in _multi) if _multi else 0
    _want = (f"{len(_multi)} of the 24 hosted arms were served by {min(_prov[_a] for _a in _multi)} "
             f"to {max(_prov.values())} providers within one run (`deepseek_m` {_prov['deepseek_m']}, "
             f"`llama_m` {_prov['llama_m']}, `deepseek_l` {_prov['deepseek_l']}, "
             f"`gemma_m` {_prov['gemma_m']}); the other {len(_one)}")
    check(f"Summarisation provider mix: {len(_multi)} multi-provider arms, the seven dearest "
          f"all single-provider, multi-provider arms cost at most ${_maxmulti:.4f}",
          _want in _PQ and all(_prov[_a] == 1 for _a in _dear7)
          and _PQ.count(f"${_maxmulti:.4f} or less") >= 2,
          f"derived: {_want}; seven dearest providers {[_prov[_a] for _a in _dear7]}; "
          f"multi-provider max ${_maxmulti:.4f}")

    # The three dominated arms whose dominator's quality lead is not separated (p in the
    # report comes from pair_test.py; here only that the dominance holds and the cost gap).
    _dom_ok, _dom_say = True, []
    for _a, _b in (("llama_l", "deepseek_m"), ("mistral_s", "deepseek_s"), ("gemma_l", "llama_s")):
        _holds = (_hosted[_b][0] > _hosted[_a][0] and CNN[_b] < CNN[_a]
                  and _hosted[_b][2] < _hosted[_a][2])
        _gap = 100 * (CNN[_a] / CNN[_b] - 1)
        _dom_ok = _dom_ok and _holds and f"(+{_gap:.0f}%)" in _PQ
        _dom_say.append(f"{_a} by {_b} +{_gap:.0f}%")
    check("Summarisation dominated arms: llama_l, mistral_s and gemma_l are dominated, at the "
          "cost gaps the report states", _dom_ok, "; ".join(_dom_say))

    _d20f = ROOT / "harness" / "data" / "datasets" / "cnn_dailymail_20.json"
    if _d20f.is_file():
        _ids20 = {(_i if isinstance(_i, str) else (_i.get("item_id") or _i.get("id")))
                  for _i in json.loads(_d20f.read_text())["items"]}
        _pi = {}
        for _a, _dirs in _runs_for(DATA, "cnn_dailymail_200", "cnn_").items():
            if _a in _hosted:
                _pi[_a] = {(_row := json.loads(_l))["item_id"]: float(_row["coverage"])
                           for _l in (_dirs[0] / "predictions.jsonl").read_text().splitlines()
                           if _l.strip()}
        _m20 = [statistics.fmean(_pi[_a][_i] for _i in _ids20) for _a in _pn]
        _m180 = [statistics.fmean(v for _i, v in _pi[_a].items() if _i not in _ids20) for _a in _pn]
        _m200 = [statistics.fmean(_pi[_a].values()) for _a in _pn]
        _r180 = _pq_pearson(_pq_ranks(_m20), _pq_ranks(_m180))
        _r200 = _pq_pearson(_pq_ranks(_m20), _pq_ranks(_m200))
        check(f"Summarisation pilot overlap: rho {_r180:.3f} on the 180 other articles, "
              f"{_r200:.3f} with the overlap",
              f"ρ = {_r180:.3f} over the 24 hosted arms, against all 200 at {_r200:.3f}" in _PQ
              and f"ρ = {_r180:.3f} ({_r200:.3f} with the overlap)" in _PQ,
              f"derived {_r180:.3f} and {_r200:.3f}")
    else:
        missing += 1
        print("  --   Summarisation pilot overlap: cnn_dailymail_20.json absent — skipped")
else:
    missing += 1
    print("  --   Summarisation price vs coverage: not 24 hosted arms with a bill — skipped")

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

# ---- THE SYNTHESIS HEADLINE: ARM COUNT AND BILLED TOTAL ------------------------
#
# "133 measured arms · $12.01 billed" went stale the moment `fn_mistral_l` landed, and
# nothing noticed -- 66/66 claims passed with the headline wrong, because no check
# counted the runs. It is the first line of the top-level report. Both figures are
# derived here and then looked for in the document, so adding or removing any arm
# fails until the headline is updated.
_SLICES = ("cnn_dailymail_200", "ag_news_200", "dbpedia_280", "few_nerd_280", "scifact_200",
           "summeval_100")
_arm_n, _billed = 0, 0.0
for _d in sorted(DATA.glob("*/metrics.json")):
    if json.load(open(_d)).get("dataset_id") not in _SLICES:
        continue
    _arm_n += 1
    _billed += _billed_of(_d.parent)
_syn = (ROOT / "research" / "REPORT_SYNTHESIS.md").read_text()
# EVERY statement of each, not the first. The synthesis says "N measured arms" twice --
# the headline and the executive summary -- and an `in` test passed with the headline
# reverted because the other copy still matched. That is the existence-check defect
# round 5 found in the latency scope and the open-weight count, for the third time.
_stated_arms = [int(_x) for _x in re.findall(r"(\d+) measured arms", _syn)]
_wrong_arms = [_x for _x in _stated_arms if _x != _arm_n]
check(f"the synthesis states {_arm_n} measured arms, everywhere it says so "
      f"({len(_stated_arms)} place(s))",
      bool(_stated_arms) and not _wrong_arms,
      f"data/runs holds {_arm_n} arms across the {len(_SLICES)} measurement slices; the "
      f"synthesis says {_wrong_arms or 'nothing'}")
# ANCHORED TO THE CLAIM, not the phrase. A bare "$N billed" also matches "that
# sweep's $1.94 billed" -- a true sentence about SciFact alone -- which the first
# version flagged as a wrong repo total. A check that cries wolf on correct text gets
# muted. These are the two places the synthesis states the REPO-WIDE bill.
_stated_bill = (re.findall(r"\$([0-9]+\.[0-9]{2}) billed \u00b7 one harness", _syn)
                + re.findall(r"\*\$([0-9]+\.[0-9]{2}) is the \d+ arms", _syn))
_wrong_bill = [_x for _x in _stated_bill if abs(float(_x) - _billed) > 0.005]
check(f"...and ${_billed:.2f} billed, everywhere it says so "
      f"({len(_stated_bill)} place(s))",
      bool(_stated_bill) and not _wrong_bill,
      f"the provider bill over those arms sums to ${_billed:.2f}; the synthesis says "
      f"{_wrong_bill or 'nothing'}")

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
    _ki = (ROOT / "research" / "internal" / "KNOWN_ISSUES.md").read_text()
    _tv = str(_cpr.get("torch", "")).split("+")[0]
    check(f"conversion PRs: the capture ran on torch {_tv}, as the reports say",
          _tv and f"torch {_tv}" in _ki,
          f"the capture says torch {_cpr.get('torch')}; KNOWN_ISSUES says otherwise")

# ---- CALIBRATION ROWS: THE INSTRUMENT AGAINST THE LITERATURE -------------------
#
# Each example's `calibrate.py` runs one known model or baseline on the benchmark's full
# test set (or a large seeded sample) and writes docs/evidence/calibration/<exp>.json.
# docs/PROTOCOL.md quotes every one of those figures. Derived from the capture and looked
# for in the page, so a re-calibration that moves a number fails until the page follows.
# A MISSING CAPTURE IS A FAILURE, not a skip: these files are committed, and a check that
# vanishes when its evidence does is the defect round 5 found in V10.
_CAL = ROOT / "docs" / "evidence" / "calibration"
_proto = (ROOT / "docs" / "PROTOCOL.md").read_text() if (ROOT / "docs" / "PROTOCOL.md").is_file() else ""
_rows = [ln for ln in _proto.splitlines() if ln.startswith("|")]
for _exp in ("summarization", "ag_news", "dbpedia", "few_nerd", "scifact", "summeval"):
    _f = _CAL / f"{_exp}.json"
    if not _f.is_file():
        check(f"calibration {_exp}: the capture exists", False,
              f"{_f.relative_to(ROOT)} is missing; PROTOCOL.md quotes it")
        continue
    _c = json.loads(_f.read_text())
    if _exp == "summarization":
        _ft, _pub = _c["full_test"], _c["published"]["lead3"]
        _want = [f"{_ft['rouge1']:.2f}", f"{_ft['rouge2']:.2f}",
                 f"{_pub['rouge1']:.2f}", f"{_pub['rouge2']:.2f}"]
        _miss = [w for w in _want if w not in _proto]
        check(f"calibration summarization: PROTOCOL.md states LEAD-3 R1/R2 "
              f"{_want[0]}/{_want[1]} vs published {_want[2]}/{_want[3]}",
              not _miss, f"not found in PROTOCOL.md: {_miss}")
        continue
    for _arm, _r in (_c.get("arms") or {}).items():
        _v = f"{_r['value']:.4f}"
        _p = _r["published"]
        _pubs = {f"{_p:.4f}", f"{_p:.3f}"}
        _row = next((ln for ln in _rows if _v in ln), None)
        _ok = _row is not None and any(p in _row for p in _pubs)
        if _ok and _r.get("verdict") == "differs":
            # A calibration that disagrees with the literature is a finding; the row that
            # quotes it must say so rather than present it as agreement.
            _ok = "differs" in _row
        check(f"calibration {_exp}/{_arm}: PROTOCOL.md states {_v} vs {_p} "
              f"({_r.get('verdict')}) in one row",
              _ok, f"no PROTOCOL.md table row carries both {_v} and the published {_p}"
                   + (" and the word 'differs'" if _r.get("verdict") == "differs" else ""))

# ---- SUMMEVAL: THE FIGURES THAT ARE NOT ONE RUN'S OWN METRIC ---------------------
#
# The scans above read a run's primary metric wherever an arm names it. Everything else
# REPORT_SUMMEVAL states -- the split-half table, price against quality, the family
# ladders, the per-dimension leaders, the tie table -- was first computed by a scratch
# script outside the repo, so a reader could not reproduce it and nothing here could
# notice it drift. `summeval_analysis.py` computes all of it from the committed runs,
# seeded, and every figure below is looked for in the document that states it.
import summeval_analysis as _sea  # noqa: E402
import subprocess as _sp  # noqa: E402

_SE = _sea.compute()
_SEV = (ROOT / "research" / "REPORT_SUMMEVAL.md").read_text()
_SER = (ROOT / "examples" / "summeval-judging" / "README.md").read_text()
_MINUS = "−"


def _signed(x, nd=4):
    return (f"{x:.{nd}f}" if x >= 0 else f"{_MINUS}{-x:.{nd}f}")


for _n, _st in _SE["stability"].items():
    _row = f"| {_n} | {_st['rho']:.3f} | {_st['p5']:.3f} | {_st['same_winner']:.0%} |"
    check(f"SummEval split-half at {_n} per half: {_row}", _row in _SEV,
          "that row is not in REPORT_SUMMEVAL §3.5")
_st20 = _SE["stability"][20]
check("SummEval decision table states the 20-per-half rho and same-winner rate",
      f"ρ = **{_st20['rho']:.2f}**" in _SEV and f"**{_st20['same_winner']:.0%}**" in _SEV,
      f"expected ρ = **{_st20['rho']:.2f}** and **{_st20['same_winner']:.0%}**")
_sh = f"{_SE['summarisation_hosted_20']['rho']:.3f}"
check(f"SummEval compares like for like: summarisation's 24 hosted arms at {_sh}, twice",
      _SEV.count(_sh) >= 2, f"{_sh} appears {_SEV.count(_sh)} time(s)")
_m443 = re.search(r"^\| 20 \| \*\*(0\.\d{3})\*\*", SUMM, re.M)
check("SummEval cites the summarisation report's own 20-per-half rho as it stands there",
      bool(_m443) and f"is {_m443.group(1)}" in _SEV,
      f"REPORT_SUMMARIZATION §3.6 says {_m443.group(1) if _m443 else '?'}")
_sc = f"{_SE['spearman_cost_tau']:+.3f}"
check(f"SummEval Spearman(billed cost, tau) = {_sc}, everywhere it is stated",
      _SEV.count(_sc) >= 2 and f"{round(_SE['price_range'])}×" in _SEV,
      f"{_sc} appears {_SEV.count(_sc)} time(s); range {_SE['price_range']:.1f}x")
_tr = f"Spearman {_SE['spearman_tie_rate_tau']:+.2f}"
check(f"SummEval tie rate vs quality: {_tr}", _tr in _SEV, "not stated as computed")

_FAM = {"anthropic": "Anthropic", "deepseek": "DeepSeek", "gemma": "Gemma", "glm": "GLM",
        "llama": "Llama", "mistral": "Mistral", "openai": "OpenAI", "qwen": "Qwen"}
_bad_lad = []
for _fam, _lad in _SE["ladders"].items():
    _want = f"| {_FAM[_fam]} | {_lad['s']:.4f} | {_lad['m']:.4f} | {_lad['l']:.4f}"
    if not any(ln.startswith(_want) for ln in _SEV.splitlines()):
        _bad_lad.append(_want)
check("SummEval family ladders (§3.4) match the runs", not _bad_lad, "; ".join(_bad_lad[:3]))
_bad_dim = []
for _d, _r in _SE["dimensions"].items():
    _want = (f"| {_d} | `{_r['best']}` | {_r['best_tau']:.4f} | "
             f"`{_r['worst']}` | {_r['worst_tau']:.4f} |")
    if _want not in _SEV:
        _bad_dim.append(_want)
check("SummEval per-dimension leaders (§3.6) match the runs", not _bad_dim, "; ".join(_bad_dim))

_se_arms = _SE["arms"]
_lead = max((a for a in _se_arms if a not in _sea.FREE), key=lambda a: _se_arms[a]["scores"]["tau"])
_ft = _sp.run([sys.executable, str(HERE / "family_test.py"), "--dataset-id", _sea.DATASET,
               "--a", f"se_{_lead}_n100_v1", "--against", "_n100_v1", "--metric", "tau",
               "--runs-dir", str(DATA)], capture_output=True, text=True)
_tied_rows = [ln.split() for ln in _ft.stdout.splitlines() if ln.strip().endswith("--")
              and ln.split()[0].endswith("_n100_v1")]
_bad_tie = []
for _t in _tied_rows:
    _arm = _t[0][len("se_"):-len("_n100_v1")]
    _wins = _t[2].split("/")[0]
    _want = (f"| `{_arm}` | {_signed(-float(_t[1]))} | {_wins} of 100 | "
             f"{float(_t[3]):.4f} | {float(_t[4]):.4f} |")
    if _want not in _SEV:
        _bad_tie.append(_want)
check(f"SummEval tie table (§3.2): the {len(_tied_rows)} arms {_lead} cannot separate from, "
      "with delta, wins, p and threshold", bool(_tied_rows) and not _bad_tie,
      "; ".join(_bad_tie[:3]) or "the family test returned no tied rows")

_judges = sorted(a for a in _se_arms if a not in _sea.FREE)
_bft = _sp.run([sys.executable, str(HERE / "family_test.py"), "--dataset-id", _sea.DATASET,
                "--a", "se_bartscore_n100_v1", "--against", "_n100_v1", "--metric", "tau",
                "--runs-dir", str(DATA)], capture_output=True, text=True)
_bart = {ln.split()[0][3:-8]: (float(ln.split()[1]), ln.split()[-1], ln.split()[2])
         for ln in _bft.stdout.splitlines()
         if ln.strip().endswith(("SEPARATED", "--")) and ln.split()[0].endswith("_n100_v1")}
_not_sep = [a for a in _judges if a not in _bart or _bart[a][1] != "SEPARATED" or _bart[a][0] >= 0]
check(f"SummEval: BARTScore is separated from all {len(_judges)} judges, every one ahead of it",
      len(_judges) == 24 and not _not_sep
      and "Every judge is separated from, and ahead of, BARTScore" in " ".join(_SEV.split()),
      f"not separated, or not behind: {_not_sep}")
_weakest = min(_judges, key=lambda a: _se_arms[a]["scores"]["tau"])
_bw = _bart.get(_weakest, (0, "", "?/100"))[2].split("/")[0]
check(f"SummEval: against the weakest judge, {_weakest}, BARTScore wins {_bw} of 100 articles",
      f"`{_weakest}`" in _SEV and f"BARTScore wins only {_bw} of 100 articles" in _SEV,
      f"the family test gives {_bw}/100 against {_weakest}")
# UniEval, the free evaluator trained for the task, on both sets of inputs (§3.3): separated
# from every judge but the weakest, and the §3.3 table row against that one as the test gives it.
_ue = {}
for _u in ("unievalpub", "unieval"):
    _uft = _sp.run([sys.executable, str(HERE / "family_test.py"), "--dataset-id", _sea.DATASET,
                    "--a", f"se_{_u}_n100_v1", "--against", "_n100_v1", "--metric", "tau",
                    "--runs-dir", str(DATA)], capture_output=True, text=True)
    _ue[_u] = {ln.split()[0][3:-8]: (float(ln.split()[1]), ln.split()[-1], ln.split()[2], float(ln.split()[3]))
               for ln in _uft.stdout.splitlines()
               if ln.strip().endswith(("SEPARATED", "--")) and ln.split()[0].endswith("_n100_v1")}
    _unsep = sorted(a for a, v in _ue[_u].items() if v[1] != "SEPARATED")
    _behind = [a for a in _judges if a != _weakest and (_ue[_u].get(a, (1,))[0] >= 0)]
    _d, _, _w, _pv = _ue[_u].get(_weakest, (0, "", "?/100", 1))
    _row = (f"| `{_u}` | {_se_arms[_u]['scores']['tau']:.4f} | {'+' if _d > 0 else ''}{_signed(_d)} | {_w.split('/')[0]} of 100 "
            f"| {_pv:.4f} | {len(_ue[_u]) - len(_unsep)} of {len(_ue[_u])}, all but `{_weakest}` |")
    check(f"SummEval: {_u} is separated from every arm but the weakest judge, {_weakest}, and §3.3 says so",
          _unsep == [_weakest] and not _behind and _row in _SEV,
          f"not separated from {_unsep}; ahead of {_behind}; or §3.3 lacks {_row}")
_dpub = _ue["unievalpub"].get("unieval", (0, "", "?/100", 1))
check(f"SummEval: the inputs move UniEval by {_dpub[0]:.4f}, p {_dpub[3]:.4f}, "
      f"{_dpub[2].split('/')[0]} of 100 articles",
      _dpub[1] == "SEPARATED" and f"worth {_dpub[0]:.4f} τ, separated (p {_dpub[3]:.4f}; `unievalpub`"
      f" wins {_dpub[2].split('/')[0]} of 100 articles)" in " ".join(_SEV.split()),
      "§3.3 does not state the paired difference between the two UniEval arms")

_per_m = lambda a: f"${_se_arms[a]['billed'] / _SE['n_items'] * 1e6:,.0f}"  # noqa: E731
_cheap_tie = min((_t[0][3:-8] for _t in _tied_rows), key=lambda a: _se_arms[a]["billed"])
check(f"SummEval cheapest tied judge {_cheap_tie} at {_per_m(_cheap_tie)} per million, "
      f"the leader at {_per_m(_lead)}, 1/{round(_se_arms[_lead]['billed'] / _se_arms[_cheap_tie]['billed'])}",
      f"**{_per_m(_cheap_tie)} per million articles**" in _SEV and _per_m(_lead) in _SEV
      and f"1/{round(_se_arms[_lead]['billed'] / _se_arms[_cheap_tie]['billed'])}" in _SEV,
      "the decision table's per-million figures or the ratio do not match the bills")
_bill = f"${_SE['total_billed']:.2f}"
check(f"SummEval states {_bill} billed in the report and the example README",
      f"**{_bill} billed**" in _SEV and f"({_bill} billed)" in _SER,
      f"the 24 judges' bills sum to {_bill}")

_bad_free = []
for _ln in _SER.splitlines():
    _c = [c.strip() for c in _ln.strip().strip("|").split("|")]
    _a = _c[0].strip("`") if _c else ""
    if not _ln.startswith("| `") or _a not in _sea.FREE or len(_c) < 5:
        continue
    _sc4 = _se_arms[_a]["scores"]
    for _k, _cell in zip(("tau", "rho", "tau_relevance", "tau_consistency"), _c[1:5]):
        if abs(float(_cell.replace(_MINUS, "-")) - _sc4[_k]) > 0.0005 + 1e-9:
            _bad_free.append(f"{_a} {_k} {_cell} vs {_sc4[_k]:.4f}")
check("SummEval README's free-arm table (3 decimals) matches the runs",
      not _bad_free and sum(1 for ln in _SER.splitlines() if ln.startswith("| `")) >= 7,
      "; ".join(_bad_free[:4]))

_cal_se = json.loads((_CAL / "summeval.json").read_text())
_r1 = _cal_se["arms"]["rouge1"]
_combo = _cal_se["rouge1_reference_combination"]
check("SummEval calibration in the README: rho/tau mean, max and first-reference variants",
      f"ρ {_combo['mean']['rho']:.3f}, τ {_combo['mean']['tau']:.3f}" in _SER
      and f"ρ {_combo['max']['rho']:.3f}" in _SER
      and f"alone {_combo['first']['rho']:.3f}" in _SER,
      f"mean {_combo['mean']}, max {_combo['max']}, first {_combo['first']}")
check("SummEval 'within 0.01 of the published value on every dimension' holds for ROUGE-1",
      all(abs(x["value"] - x["published"]) <= 0.01 for x in _r1["by_dimension"].values()),
      str(_r1["by_dimension"]))
_rl = _cal_se["arms"]["rougeL"]["by_dimension"]["coherence"]
check("SummEval names ROUGE-L's coherence gap where it calls ROUGE-L not quite reproduced",
      f"{_rl['value']:.4f} against {_rl['published']:.3f}" in _SEV
      and f"{_rl['value']:.3f} against {_rl['published']:.3f}" in _SER,
      f"coherence {_rl['value']:.4f} vs {_rl['published']}")

# The human ceiling (REPORT_SUMMEVAL §3.7), from the original release's per-expert scores.
# The evidence file is written by examples/summeval-judging/human_ceiling.py, which
# refuses to write it unless the experts' means reproduce the gold and every arm re-scores
# to its committed tau -- so those two flags are part of the claim, not decoration.
_hc_path = ROOT / "docs" / "evidence" / "summeval_human_ceiling.json"
_hc = json.loads(_hc_path.read_text()) if _hc_path.is_file() else {}
check("SummEval human ceiling: the evidence exists, reproduced the gold and re-scored every arm",
      bool(_hc) and _hc.get("gold_reproduced") and _hc.get("arms_rescored_exactly")
      and _hc.get("duplicate_groups_with_more_than_one_fitting_assignment") == 0
      and set(_hc.get("arms", {})) == set(_se_arms),
      f"{_hc_path.relative_to(ROOT)} missing, or its arms differ from the runs")
if _hc:
    _ceil = _hc["tau_mean"]
    _bad_hc = []
    for _ln in _SEV.splitlines():
        _m = re.match(r"^\| `([a-z0-9_]+)`(?: \([^)]*\))? \| (0\.\d{4}) \| \*{0,2}(\d+)%\*{0,2} \|$", _ln)
        if not _m:
            continue
        _a, _v, _pct = _m.group(1), float(_m.group(2)), int(_m.group(3))
        _want = _hc["arms"].get(_a, {}).get("tau_vs_two_experts")
        if _want is None or abs(_v - _want) > 0.00005 or _pct != round(100 * _want / _ceil):
            _bad_hc.append(f"{_a} {_v} {_pct}% vs {_want} {round(100 * (_want or 0) / _ceil)}%")
    _n_hc = sum(1 for _ln in _SEV.splitlines()
                if re.match(r"^\| `[a-z0-9_]+`(?: \([^)]*\))? \| 0\.\d{4} \| \*{0,2}\d+%", _ln))
    check(f"SummEval §3.7: the {_n_hc} arm rows against two experts match the evidence",
          _n_hc >= 5 and not _bad_hc, "; ".join(_bad_hc[:3]))
    _best = max((a for a in _hc["arms"] if a not in _sea.FREE),
                key=lambda a: _hc["arms"][a]["tau_vs_two_experts"])
    _bv = _hc["arms"][_best]["tau_vs_two_experts"]
    _bp = round(100 * _bv / _ceil)
    _ue_pub_p = round(100 * _hc["arms"]["unievalpub"]["tau_vs_two_experts"] / _ceil)
    _ue_p = round(100 * _hc["arms"]["unieval"]["tau_vs_two_experts"] / _ceil)
    _bs_p = round(100 * _hc["arms"]["bartscore"]["tau_vs_two_experts"] / _ceil)
    check(f"SummEval decision table: the best judge {_bv:.4f}, {_bp}% of one expert's {_ceil:.4f}, "
          f"UniEval {_ue_pub_p}% ({_ue_p}% on this experiment's inputs), BARTScore {_bs_p}%",
          f"**{_bv:.4f}**, **{_bp}%** (95% interval "
          f"{round(100 * _hc['arms'][_best]['share_ci95'][0])}–{round(100 * _hc['arms'][_best]['share_ci95'][1])}%) "
          f"of one expert's agreement with the other two (**{_ceil:.4f}**)" in _SEV
          and f"UniEval reaches {_ue_pub_p}% ({_ue_p}% on this experiment's inputs), BARTScore {_bs_p}%" in _SEV
          and f"| **{_ceil:.4f}** |" in _SEV,
          "the decision table or §3.7 does not state the evidence's figures")
    # The same two figures, repeated where the conclusions are drawn. A copy is checked
    # where it is stated, or it drifts from the report it was copied from.
    _copies = {"research/REPORT_SYNTHESIS.md": f"reached {_bp}% of a human expert's agreement",
               "README.md": f"reach {_bp}% of a human expert's",
               "examples/README.md": f"reach {_bp}% of a\nhuman expert's agreement"}
    _stale_copy = [f for f, t in _copies.items()
                   if " ".join(t.split()) not in " ".join((ROOT / f).read_text().split())
                   or not re.findall(r"UniEval,? (\d+)%", " ".join((ROOT / f).read_text().split()))
                   or any(int(x) not in (_ue_pub_p, _ue_p) for x in re.findall(r"UniEval,? (\d+)%", " ".join((ROOT / f).read_text().split())))]
    check(f"SummEval's {_bp}% / {_ue_pub_p}% stated the same in the synthesis and both READMEs",
          not _stale_copy, f"stale or missing in {_stale_copy}")
    _gap = _hc["arms"][_best]["gap_ci95"]
    check(f"SummEval §3.7: the gap to one expert, {_gap[0]:.4f} to {_gap[1]:.4f}, as the evidence says",
          f"({_gap[0]:.4f} to\n{_gap[1]:.4f} for `{_best}`)" in _SEV
          or f"({_gap[0]:.4f} to {_gap[1]:.4f} for `{_best}`)" in " ".join(_SEV.split()),
          "§3.7 does not state the bootstrap interval of the gap")
    _pos = _hc["tau_per_position"]
    check(f"SummEval §3.7: positions {min(_pos):.4f}-{max(_pos):.4f}; {_hc['duplicate_summary_groups']} "
          f"identical-text groups in {_hc['duplicate_articles']} articles, "
          f"{_hc['duplicate_groups_scored_differently']} scored differently",
          f"give {min(_pos):.4f}–{max(_pos):.4f}" in _SEV
          and f"{_hc['duplicate_summary_groups']} groups of identical texts" in _SEV
          and f"In {_hc['duplicate_articles']} of the 100 articles" in _SEV
          and " ".join(_SEV.split()).count(f"{_hc['duplicate_groups_scored_differently']} of those") >= 2
          and f"in {_hc['duplicate_articles']} articles two or more systems" in _SEV,
          "a count in §3.7 or the findings does not match the evidence")
    # The system-identity prior on the two-expert footing (leave-one-article-out lookup).
    _pp = _hc.get("position_prior") or {}
    _pp_v, _pp_p = _pp.get("tau_vs_two_experts"), round(100 * _pp.get("share_of_one_expert", 0))
    _sev_n = " ".join(_SEV.split())
    check(f"SummEval §3.7: the position prior {_pp_v}, {_pp_p}% of one expert, in the table and the summary",
          bool(_pp) and _pp_p == round(100 * _pp_v / _ceil)
          and f"| position prior (no model: other 99 articles' mean per position) | {_pp_v:.4f} | {_pp_p}% |" in _SEV
          and f"reaches {_pp_p}% of one expert" in _sev_n
          and f"lookup of which system wrote each summary reaches {_pp_p}% of an expert" in _sev_n,
          f"evidence says {_pp}")

# UniEval's derived figures (REPORT_SUMMEVAL §3.3, §5; the synthesis' tables), each computed
# here from the runs, the family tests above and the evidence, so a copied figure cannot drift.
_SYN = " ".join((ROOT / "research" / "REPORT_SYNTHESIS.md").read_text().split())
_SEVn = " ".join(_SEV.split())
_tau = {a: v["scores"]["tau"] for a, v in _se_arms.items()}
_order = sorted(_tau, key=lambda a: -_tau[a])
_ord = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"  # noqa: E731
_bad_rank = [a for a in ("unievalpub", "unieval", "bartscore")
             if f"{_ord(_order.index(a) + 1)} of {len(_order)}" not in _SYN]
check("SummEval ranks of the free learned arms in the synthesis' exposure table", not _bad_rank,
      f"{_bad_rank}: {[(a, _order.index(a) + 1) for a in _bad_rank]}")
_n_above = sum(1 for a in _judges if _ue["unievalpub"].get(a, (0, ""))[1] == "SEPARATED"
               and _ue["unievalpub"][a][0] < 0)
_pw = (_ue["unievalpub"][_weakest][3], _ue["unieval"][_weakest][3])
check(f"SummEval: {_n_above} of the {len(_judges)} judges are separated above UniEval; "
      f"p {_pw[0]:.2f} and {_pw[1]:.2f} against {_weakest}",
      f"below {_n_above} of the {len(_judges)} judges" in _SEVn
      and f"p {_pw[0]:.2f} and {_pw[1]:.2f}" in _SEVn and f"{_n_above} of 24 judges" in _SYN,
      "the headline counts or p-values do not match the family tests")
check(f"SummEval: both UniEval arms are separated above BARTScore, by "
      f"{-_bart['unieval'][0]:.4f} and {-_bart['unievalpub'][0]:.4f}",
      _bart["unieval"][1] == _bart["unievalpub"][1] == "SEPARATED"
      and f"(by {-_bart['unieval'][0]:.4f} and {-_bart['unievalpub'][0]:.4f})" in _SEVn, "")
_lt, _pt = _tau[_lead], _tau["unievalpub"]
check(f"SummEval: UniEval {_lt - _pt:.3f} below the leader; free vs paid "
      f"−{100 * (1 - _pt / _lt):.1f}% and +{100 * (_lt / _pt - 1):.1f}%; gemma_l by {_tau['gemma_l'] - _pt:.4f}",
      f"{_lt - _pt:.3f} below the leader" in _SEVn
      and _SYN.count(f"**−{100 * (1 - _pt / _lt):.1f}%**") == 2
      and f"**paid wins +{100 * (_lt / _pt - 1):.1f}%**" in _SYN
      and f"**LLM wins by {_tau['gemma_l'] - _pt:.4f}, separated**" in _SYN
      and f"by {_tau['gemma_l'] - _pt:.4f}, scored on UniEval's" in _SYN, "")
_sep_lead = sum(1 for ln in _ft.stdout.splitlines() if ln.strip().endswith("SEPARATED"))
_m_lead = sum(1 for ln in _ft.stdout.splitlines() if ln.strip().endswith(("SEPARATED", "--"))
              and ln.split()[0].endswith("_n100_v1"))
check(f"SummEval leader separated from {_sep_lead} of {_m_lead} in the synthesis' table",
      f"| {_m_lead} of {_m_lead} | {_sep_lead} of {_m_lead} ({round(100 * _sep_lead / _m_lead)}%) |" in _SYN, "")
_lat = sorted(_se_arms[a]["scores"]["latency_ms"] / 1000 for a in ("unieval", "unievalpub"))
check(f"SummEval: UniEval latency {_lat[0]:.2f}–{_lat[1]:.2f} s in the synthesis",
      f"UniEval {_lat[0]:.2f}–{_lat[1]:.2f} s" in _SYN, "")
_ued = _cal_se["arms"]["unievalpub"]["by_dimension"]
_worst = max(_ued, key=lambda d: abs(_ued[d]["value"] - _ued[d]["published"]))
check(f"SummEval calibration: UniEval's largest dimension gap is {_worst}'s "
      f"{abs(_ued[_worst]['value'] - _ued[_worst]['published']):.4f}, every dimension inside its interval",
      f"{_worst}'s {abs(_ued[_worst]['value'] - _ued[_worst]['published']):.4f}" in _SEVn
      and all(abs(x["value"] - x["published"]) <= x["ci95"] for x in _ued.values()), str(_ued))
_gp = score(PAIR, "se_gemma_l_pubtextcw_n100_v1", "tau")
_gs, _go = score(PAIR, "se_gemma_l_pubtext_n100_v1", "tau"), _tau["gemma_l"]
check(f"SummEval §3.3: gemma_l on UniEval's text {_gp:.4f} (CoreWeave) and {_gs:.4f} (SambaNova) vs "
      f"{_go:.4f}; its lead over UniEval {_go - _tau['unieval']:.4f} and {_gp - _tau['unievalpub']:.4f}",
      None not in (_gp, _gs)
      and f"scores {_gp:.4f} against its {_go:.4f} here: +{_gp - _go:.4f}" in _SEVn
      and f"to SambaNova, scored {_gs:.4f}; on the same text the two providers differ by {_gs - _gp:.4f}" in _SEVn
      and f"{_go - _tau['unieval']:.4f} on this experiment's text and {_gp - _tau['unievalpub']:.4f} on" in _SEVn,
      f"pair run taus {_gp} {_gs}")
_pl = _cal_se.get("position_lookup") or {}
_plt = _pl.get("tau_leave_one_article_out") or 0.0
check(f"SummEval §7: a system-identity prior (position lookup) reaches {_plt}",
      _pl.get("each_position_one_system_on_every_article") is True
      and f"reaches τ {_plt:.4f}" in _SEVn
      and f"reaches τ {_plt:.3f}" in " ".join(_SER.split())
      and _tau["llama_s"] < _plt < _tau["unievalpub"], str(_pl))
_rank_pl = 1 + sum(v > _plt for v in _tau.values())
check(f"SummEval §3.1: the identity prior would rank {_ord(_rank_pl)} of the field",
      f"would rank {_ord(_rank_pl)} here" in _SEVn, f"rank {_rank_pl}")
_tt = _SE["tier_tests"]
_sep_t = sorted(f for f, v in _tt.items() if v["separated"])
_not_t = sorted(f for f, v in _tt.items() if not v["separated"])
check(f"SummEval §3.4: large tier separated above small in {len(_sep_t)} of {len(_tt)} families, "
      f"not in {', '.join(_not_t)}",
      ("separated in " + "zero one two three four five six seven eight".split()[len(_sep_t)]) in _SEVn
      and all(f"{f.capitalize() if f != 'openai' else 'OpenAI'} +{_tt[f]['delta']:.4f}" in _SEVn
              for f in _sep_t if f not in ("glm",))
      and all(f"+{_tt[f]['delta']:.4f} (p {_tt[f]['p']:.4f})" in _SEVn for f in _not_t),
      str({f: (round(v["delta"], 4), round(v["p"], 4), v["separated"]) for f, v in _tt.items()}))
_sel = _hc.get("selection_corrected_best_judge") or {}
check(f"SummEval §3.7: best judge held out {_sel.get('share_held_out')} vs in sample {_sel.get('share_in_sample')}",
      bool(_sel) and f"gives {round(100 * _sel['share_held_out'])}% held out against "
      f"{round(100 * _sel['share_in_sample'])}% in sample" in _SEVn, str(_sel))
_ui = _cal_se.get("unievalpub_inputs_vs_ours") or {}
check("SummEval §3.3: how UniEval's published inputs differ from ours, as calibrate.py counted it",
      bool(_ui) and _ui["summaries"] - _ui["same_ignoring_case_and_punctuation"] == _ui["differ_only_in_bracket_tokens"]
      and _ui["reference_is_the_first_of_11"] == _ui["article_same_ignoring_case_and_punctuation"] == _ui["summaries"]
      and f"{_ui['same_ignoring_case_and_punctuation']:,} of the {_ui['summaries']:,} summaries match" in _SEVn
      and f"the other {_ui['differ_only_in_bracket_tokens']} differ only in how brackets" in _SEVn,
      str(_ui))
_rs = _sp.run([sys.executable, str(HERE / "rank_stability.py"), "--dataset-id", _sea.DATASET,
               "--metric", "tau"], capture_output=True, text=True, cwd=str(HERE.parent))
_rs20 = [ln.split() for ln in _rs.stdout.splitlines() if ln.split()[:1] == ["20"]]
check("SummEval: all-arm split-half rho at 20 per half, as rank_stability gives it",
      bool(_rs20) and f"({float(_rs20[0][1]):.3f} at 20" in _SEVn,
      f"rank_stability gives {_rs20[:1]}; stderr {_rs.stderr[-200:]}")

# NER: how often each arm emitted the `other` type. The report rests its reading of gliner's
# 0.0000 on `other` on this count, and it needs no gold, so it runs wherever the runs do.
_NERT = " ".join((ROOT / "research" / "REPORT_NER.md").read_text().split())
_oth = {}
for _a in ("gliner", "openai_m", "anthropic_l", "span_marker"):
    _d = glob.glob(str(RESCORED / f"fn_{_a}_n200_v1_*"))
    _oth[_a] = sum(1 for _ln in open(Path(_d[0]) / "predictions.jsonl") if _ln.strip()
                   for _e in (json.loads(_ln).get("_meta", {}).get("predicted") or [])
                   if (_e.get("type") or "").lower() == "other") if _d else None
check("NER: emitted-`other` counts (gliner 3, openai_m 93, anthropic_l 131, span_marker 97) match the report",
      _oth == {"gliner": 3, "openai_m": 93, "anthropic_l": 131, "span_marker": 97}
      and "emitted `other` 3 times in 280 sentences (`openai_m` 93, `anthropic_l` 131, "
          "`span_marker` 97)" in _NERT,
      str(_oth))

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
