#!/usr/bin/env python3
"""Check a judge scorer against human ratings of LLM-written news summaries.

    python scripts/validate_judge_zhang.py --scorer judge-summ-v1 [--dry-run | --no-calls]

SummEval validates judges on 2019-era summarisers. Zhang, Ladhak, Durmus, Liang, McKeown &
Hashimoto (2024, "Benchmarking Large Language Models for News Summarization", TACL 12)
released Likert ratings of 19 summarisers on 100 CNN/DailyMail articles: GPT-3-era LLMs
(davinci, text-davinci-002, Anthropic, Cohere, OPT, GLM, zero- and few-shot), the
fine-tunes BRIO and Pegasus, and the reference highlights. Three crowd ratings per summary:
coherence and relevance 1-5, faithfulness 0/1. This asks each judge of a scorer to score
an article's 19 summaries (the validated prompt, in blocks of at most 16: 10 + 9, order
seeded per article) and measures, per article, how well it ORDERS the summaries the way the
raters do:

  tau             Kendall tau-b per article between a judge's scores and the raters' mean,
                  per dimension: coherence~coherence, relevance~relevance, the judge's
                  consistency~faithfulness; averaged over articles, then over dimensions.
  reference       each summary's three ratings are held out one at a time (rotating, seeded
                  order): the held-out rating against the mean of the other two is the human
                  baseline, and the judge is scored against the same two-rater means.
  free metrics    ROUGE-1 F1 and this repository's `coverage` against the reference
                  highlights, on the 18 non-reference summaries; judges and raters are
                  reported on those 18 too, so all of them are compared like for like.

The ratings are downloaded to data/external/zhang2023/ (gitignored; the file's sha256 is
pinned) and never committed: the stored records under
data/judge-validation/<scorer>/zhang2023-cnndm/<judge>/ hold article ids, block orders, the
judge's reply and scores, and hashes. A reply that is not bare JSON scores, or repeats 8
consecutive words of the article or a summary, is not stored, only its hash. report.json holds the
aggregates and a hash of the records. CI has no ratings, so there report.json is checked only
against its records (their hash, count, bill, unparsed and withheld) and the scorer's hash;
rebuild it with --no-calls before a release (harness/docs/RELEASING.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _fetch  # noqa: E402
import judge_score as js  # noqa: E402
from _common import ModuleNotLoadable, die, load_module, write_bytes_atomic, write_text_atomic  # noqa: E402
from _retry import call_with_retries  # noqa: E402
from judging import (  # noqa: E402,F401
    DIMS,
    SHINGLE,
    kendall_tau_b,
    quotes_source,
    shingles,
    spearman,
    withheld_reason,
)

DATA = HERE.parent / "data"
EXT = DATA / "external" / "zhang2023"
FILE = EXT / "likert_evaluation_results.json"
#: The repository's commit when the file was fetched (2026-10-21), and the file's sha256.
COMMIT = "4e87890ed070c7db3dd5c1125adb5bde0ccd2eb1"
URL = f"https://raw.githubusercontent.com/Tiiiger/benchmark_llm_summarization/{COMMIT}/likert_evaluation_results.json"
REFERENCE = "reference"
#: Human dimension -> the judge dimension that orders the same property.
PAIRS = (("coherence", "coherence"), ("relevance", "relevance"), ("faithfulness", "consistency"))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load() -> dict[str, dict]:
    """{article_id: {"article": text, "systems": {model: {"summary", "ratings": [{dim: v}x3]}}}},
    CNN/DailyMail only. Downloads the pinned file if it is not present."""
    if not FILE.is_file():
        try:
            src, _ = _fetch.fetch(URL, PINNED)  # retried, checked against the pin
        except _fetch.FetchError as exc:
            die(str(exc))
        EXT.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(FILE, src.read_bytes())
    raw = FILE.read_bytes()
    if _sha(raw) != PINNED:
        die(f"{FILE} has sha256 {_sha(raw)}, not the pinned {PINNED}; refusing to use it")
    out: dict[str, dict] = {}
    for r in json.loads(raw):
        if r["dataset"] != "cnndm":
            continue
        aid = _sha(r["article"].encode())[:16]
        a = out.setdefault(aid, {"article": r["article"], "systems": {}})
        # 114 CNN/DM ratings are of summaries the model left empty (NaN in the file), rated
        # mostly 1, 1, 0: kept, as an empty summary, which a judge should also put last.
        text = r["summary"] if isinstance(r["summary"], str) else ""
        s = a["systems"].setdefault(r["model"], {"summary": text, "ratings": []})
        s["ratings"].append({d: float(r[d]) for d, _ in PAIRS})
    return out


#: sha256 of likert_evaluation_results.json at COMMIT (31,259,080 bytes), fetched 2026-10-21.
PINNED = "5f9936bb9c09877f758605a1767031d547db8edfd45ab1f93608a0fd6f56b56c"


def order(aid: str, systems: Sequence[str]) -> list[str]:
    """Deterministic (seeded by article_id) ordering of the systems."""
    return sorted(systems, key=lambda s: _sha(f"zhang-0:{aid}:{s}".encode()))


def blocks(aid: str, systems: Sequence[str], per_call: int) -> list[list[str]]:
    """Partition shuffled systems into balanced blocks (fewest blocks, roughly equal sizes)."""
    o = order(aid, systems)
    out, i = [], 0
    for n in js.block_sizes(len(o), per_call):
        out.append(o[i : i + n])
        i += n
    return out


def record_path(vdir: Path, aid: str, b: int) -> Path:
    """Path to a judge's stored verdict for one article's block."""
    return vdir / f"{aid}.b{b}.json"


def parse_dims(output: str, n: int) -> dict[str, list[float]] | None:
    """The judge's scores per dimension, or None. The same rule as judging.parse_block, kept
    per dimension: every dimension, exactly n numbers, each 1..5."""
    m = re.search(r"\{.*\}", output or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    out = {}
    for d in DIMS:
        v = obj.get(d)
        if not isinstance(v, list) or len(v) != n:
            return None
        # Numbers only, as judging.parse_block: `true` and "4" are not scores.
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in v):
            return None
        f = [float(x) for x in v]
        if any(not (1.0 <= x <= 5.0) for x in f):
            return None
        out[d] = f
    return out


def _mean(xs: Sequence[float | None]) -> float | None:
    v = [x for x in xs if x is not None]
    return round(statistics.fmean(v), 4) if v else None


def held_out(ratings: Sequence[dict], aid: str, model: str) -> list[tuple[dict, dict]]:
    """[(held-out rating, mean of the other two)] for each of the three, in a seeded order."""
    rs = sorted(
        ratings, key=lambda r: _sha(f"zhang-ho:{aid}:{model}:{json.dumps(r, sort_keys=True)}".encode())
    )
    out = []
    for k in range(len(rs)):
        rest = [r for i, r in enumerate(rs) if i != k]
        out.append((rs[k], {d: statistics.fmean(r[d] for r in rest) for d, _ in PAIRS}))
    return out


def human_and_refs(data: dict[str, dict], systems: Sequence[str]) -> tuple[dict, dict]:
    """Human baseline tau per dimension, and the two-rater reference means per article,
    held-out position and system (the judges are scored against the same references)."""
    refs: dict[str, list[dict[str, dict[str, float]]]] = {}
    hum: dict[str, list] = {h: [] for h, _ in PAIRS}
    for aid, a in data.items():
        per = {m: held_out(a["systems"][m]["ratings"], aid, m) for m in systems}
        refs[aid] = [{m: per[m][k][1] for m in systems} for k in range(3)]
        for k in range(3):
            for h, _ in PAIRS:
                hum[h].append(
                    kendall_tau_b([per[m][k][0][h] for m in systems], [refs[aid][k][m][h] for m in systems])
                )
    return {h: _mean(v) for h, v in hum.items()}, refs


def judge_tau(scores: dict[str, dict[str, dict[str, float]]], refs: dict, systems: Sequence[str]) -> dict:
    """Mean tau per human dimension, against the same two-rater references, over articles
    where every block parsed."""
    per: dict[str, list] = {h: [] for h, _ in PAIRS}
    for aid, s in scores.items():
        for k in range(3):
            for h, jd in PAIRS:
                per[h].append(
                    kendall_tau_b([s[m][jd] for m in systems], [refs[aid][k][m][h] for m in systems])
                )
    out = {h: _mean(v) for h, v in per.items()}
    out["mean"] = _mean(list(out.values()))
    return out


def metric_tau(data: dict[str, dict], refs: dict, systems: Sequence[str], fn) -> dict:
    """Kendall tau of a metric against human ratings, per dimension and overall mean."""
    per: dict[str, list] = {h: [] for h, _ in PAIRS}
    for aid, a in data.items():
        ref = a["systems"][REFERENCE]["summary"]
        vals = {m: fn(a["systems"][m]["summary"], ref) for m in systems}
        for k in range(3):
            for h, _ in PAIRS:
                per[h].append(
                    kendall_tau_b([vals[m] for m in systems], [refs[aid][k][m][h] for m in systems])
                )
    out = {h: _mean(v) for h, v in per.items()}
    out["mean"] = _mean(list(out.values()))
    return out


def article_taus(get, refs: dict, systems: Sequence[str], aids: Sequence[str]) -> dict[str, float]:
    """{article: tau averaged over the three held-out references and the three dimensions}.
    `get(aid, k, human_dim)` returns the instrument's value per system, in `systems` order."""
    out = {}
    for aid in aids:
        taus = [
            kendall_tau_b(get(aid, k, h), [refs[aid][k][m][h] for m in systems])
            for k in range(3)
            for h, _ in PAIRS
        ]
        known = [x for x in taus if x is not None]
        if known:
            out[aid] = statistics.fmean(known)
    return out


def paired_test(a: dict[str, float], b: dict[str, float], n: int = 20000, seed: int = 0) -> dict:
    """a minus b over the articles both have: mean difference, articles where a is ahead, and a
    two-sided sign-flip permutation p (seeded; the article is the unit)."""
    import random  # noqa: PLC0415

    ids = sorted(set(a) & set(b))
    d = [a[i] - b[i] for i in ids]
    obs = abs(statistics.fmean(d))
    rng = random.Random(seed)
    hits = sum(
        abs(statistics.fmean(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12 for _ in range(n)
    )
    return {
        "articles": len(ids),
        "mean_difference": round(statistics.fmean(d), 4),
        "a_ahead": sum(x > 0 for x in d),
        "b_ahead": sum(x < 0 for x in d),
        "p_two_sided": round((hits + 1) / (n + 1), 5),
    }


def system_means(data: dict[str, dict], systems: Sequence[str], scores: dict[str, dict]) -> dict:
    """Mean rating per system: the raters' (all three ratings) and each judge's, per dimension.
    A judge is ranked against the raters' means on the articles that judge scored."""

    def rater_means(aids) -> dict:
        return {
            m: {
                h: round(
                    statistics.fmean(r[h] for aid in aids for r in data[aid]["systems"][m]["ratings"]), 4
                )
                for h, _ in PAIRS
            }
            for m in systems
        }

    hum = rater_means(data)
    judges = {}
    for jid, s in scores.items():
        judges[jid] = {
            m: {jd: round(statistics.fmean(s[aid][m][jd] for aid in s), 4) for _, jd in PAIRS}
            for m in systems
        }

    # The system ranking: by the mean of coherence and relevance (the two 1-5 ratings; the
    # judge's coherence and relevance likewise), rank 1 the best.
    def ranks(means: dict, a: str, b: str) -> dict[str, int]:
        o = sorted(means, key=lambda m: (-(means[m][a] + means[m][b]), m))
        return {m: i + 1 for i, m in enumerate(o)}

    def key(means: dict) -> list[float]:
        return [means[m]["coherence"] + means[m]["relevance"] for m in systems]

    hr = ranks(hum, "coherence", "relevance")
    ranking: dict = {
        "basis": "the mean of coherence and relevance (faithfulness, 0/1, is not in it)",
        "raters": hr,
        "judges": {},
        "spearman_vs_raters": {},
    }
    for jid, s in judges.items():
        same = hum if len(scores[jid]) == len(data) else rater_means(scores[jid])
        ranking["judges"][jid] = ranks(s, "coherence", "relevance")
        # On the means themselves, tie-corrected (average ranks), not on the listed ranks,
        # which break ties by name.
        ranking["spearman_vs_raters"][jid] = round(spearman(key(s), key(same)), 4)
    return {"raters": hum, "judges": judges, "ranking": ranking}


def free_metrics() -> dict:
    """ROUGE-1 F1 and coverage metric functions."""
    from rouge_score import rouge_scorer  # noqa: PLC0415

    rs = rouge_scorer.RougeScorer(["rouge1"], use_stemmer=True)
    path = HERE.parents[1] / "examples" / "summarization-cnn-dailymail" / "adapter.py"
    try:
        mod = load_module(path, "_summ_adapter")
    except ModuleNotLoadable:
        raise SystemExit(f"cannot load {path}") from None
    return {
        "rouge1": lambda s, r: rs.score(r, s)["rouge1"].fmeasure,
        "coverage": lambda s, r: mod.score(s, r)["coverage"],
    }


def build_report(
    sc: dict, base: str, per_call: int, data: dict[str, dict], systems: list[str], vroot: Path
) -> dict[str, Any]:
    """Every figure the report states, recomputed from the stored records and the data;
    refuses records stored for another judge, prompt or order, or holding their text."""
    # Every record checked against the scorer and the data as they are now.
    problems, scores = [], {}
    for j in sc["judges"]:
        fp, s = js.judge_fingerprint(j), {}
        for aid, a in data.items():
            merged: dict[str, dict[str, float]] = {}
            ok = True
            src = shingles([a["article"], *(a["systems"][m]["summary"] for m in systems)])
            for b, ms in enumerate(blocks(aid, systems, per_call)):
                raw = record_path(vroot / j["id"], aid, b).read_text()
                rec = json.loads(raw)
                want = js._sha(js.build_message(base, a["article"], [a["systems"][m]["summary"] for m in ms]))
                if rec.get("judge_fp") != fp or rec.get("prompt_sha") != want or rec.get("order") != ms:
                    problems.append(f"{j['id']}/{aid}.b{b}: stored for a different judge, prompt or order")
                # The whole record as stored, and the reply decoded (JSON escapes can split a
                # quote in the raw file): none of the article's or the summaries' text may be
                # in what is committed.
                if quotes_source(raw, src) or quotes_source(rec.get("output") or "", src):
                    problems.append(f"{j['id']}/{aid}.b{b}: repeats 8 words of the article or a summary")
                if rec.get("dims") is None:
                    ok = False
                    continue
                for i, m in enumerate(ms):
                    merged[m] = {d: rec["dims"][d][i] for d in DIMS}
            if ok:
                s[aid] = merged
        scores[j["id"]] = s
    if problems:
        die("stored records refused:\n  " + "\n  ".join(problems[:20]))

    nonref = [m for m in systems if m != REFERENCE]
    hum19, refs19 = human_and_refs(data, systems)
    hum18, refs18 = human_and_refs(data, nonref)
    fm = free_metrics()
    report: dict[str, Any] = {
        "source": (
            "Zhang, Ladhak, Durmus, Liang, McKeown & Hashimoto (2024), Benchmarking Large "
            "Language Models for News Summarization, TACL 12; likert_evaluation_results.json, "
            "CNN/DailyMail rows"
        ),
        "scorer": sc["scorer_id"],
        "articles": len(data),
        "systems": len(systems),
        "empty_summaries": sum(1 for a in data.values() for s in a["systems"].values() if not s["summary"]),
        "blocks": js.block_sizes(len(systems), per_call),
        "inputs": {"commit": COMMIT, "file_sha256": PINNED, "scorer_sha256": sc["_sha256"]},
        "human_baseline": {
            "all_19": {**hum19, "mean": _mean(list(hum19.values()))},
            "non_reference_18": {**hum18, "mean": _mean(list(hum18.values()))},
        },
        "free_metrics_non_reference_18": {k: metric_tau(data, refs18, nonref, fn) for k, fn in fm.items()},
        "judges": {},
    }
    for j in sc["judges"]:
        jid = j["id"]
        recs = [json.loads(f.read_text()) for f in (vroot / jid).glob("*.json")]
        report["judges"][jid] = {
            "articles_scored": len(scores[jid]),
            "calls": len(recs),
            "unparsed": sum(1 for r in recs if r.get("dims") is None),
            "withheld_replies": sum(1 for r in recs if r.get("output_withheld")),
            "billed_usd": round(sum(float(r.get("cost_usd") or 0) for r in recs), 4),
            "records_sha256": js.records_sha256(vroot / jid),
            "all_19": judge_tau(scores[jid], {a: refs19[a] for a in scores[jid]}, systems),
            "non_reference_18": judge_tau(scores[jid], {a: refs18[a] for a in scores[jid]}, nonref),
        }
    # Paired over articles, on the 18 non-reference summaries: each judge against one rater
    # and against coverage, ROUGE-1. The article is the unit; refs are the same for all.
    aids = sorted(data)
    ho18 = {aid: {m: held_out(data[aid]["systems"][m]["ratings"], aid, m) for m in nonref} for aid in aids}
    human_t = article_taus(lambda aid, k, h: [ho18[aid][m][k][0][h] for m in nonref], refs18, nonref, aids)
    vals = {
        name: {
            aid: {
                m: fn(data[aid]["systems"][m]["summary"], data[aid]["systems"][REFERENCE]["summary"])
                for m in nonref
            }
            for aid in aids
        }
        for name, fn in fm.items()
    }
    metric_t = {
        name: article_taus(lambda aid, k, h, v=v: [v[aid][m] for m in nonref], refs18, nonref, aids)
        for name, v in vals.items()
    }
    jd_of = dict(PAIRS)
    report["paired_non_reference_18"] = {}
    for jid, s in scores.items():
        jt = article_taus(
            lambda aid, k, h, s=s: [s[aid][m][jd_of[h]] for m in nonref], refs18, nonref, sorted(s)
        )
        report["paired_non_reference_18"][jid] = {
            "vs_one_rater": paired_test(jt, human_t),
            **{f"vs_{name}": paired_test(jt, t) for name, t in metric_t.items()},
        }
    report["system_means"] = system_means(data, systems, scores)
    return report


def print_report(report: dict[str, Any]) -> None:
    """Print a summary of the judging results and human baseline."""
    for jid, r in report["judges"].items():
        print(
            f"{jid}: tau all-19 {r['all_19']}; non-reference {r['non_reference_18']}; "
            f"{r['articles_scored']} articles, unparsed {r['unparsed']}, withheld {r['withheld_replies']}, "
            f"billed ${r['billed_usd']:.4f}"
        )
        print(f"{jid} paired (non-reference 18): {report['paired_non_reference_18'][jid]}")
    print(
        f"humans (one rating vs the mean of the other two): all-19 {report['human_baseline']['all_19']}; "
        f"non-reference {report['human_baseline']['non_reference_18']}"
    )
    for k, v in report["free_metrics_non_reference_18"].items():
        print(f"{k} vs the reference highlights, non-reference 18: {v}")


def main() -> int:
    """Validate a judge on Zhang 2024 summaries; call or recompute from stored verdicts."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scorer", required=True)
    ap.add_argument("--dry-run", action="store_true", help="count calls and estimate cost; call nothing")
    ap.add_argument("--no-calls", action="store_true", help="recompute from stored records only")
    args = ap.parse_args()
    sc = js.load_scorer(DATA / "scorers" / f"{args.scorer}.yaml")
    base = js.prompt_text(sc)
    per_call = int(sc["protocol"]["outputs_per_call"])
    data = load()
    systems = sorted(next(iter(data.values()))["systems"])
    if any(sorted(a["systems"]) != systems for a in data.values()):
        die("not every article has the same systems")
    vroot = DATA / "judge-validation" / args.scorer / "zhang2023-cnndm"
    cap = js.effective_cap(sc)

    tasks = []
    for j in sc["judges"]:
        for aid in data:
            for b, ms in enumerate(blocks(aid, systems, per_call)):
                tasks.append((j, aid, b, ms))
    missing = [t for t in tasks if not record_path(vroot / t[0]["id"], t[1], t[2]).is_file()]
    if args.dry_run:
        est = 0.0
        for j, aid, _b, ms in missing:
            msg = js.build_message(
                base, data[aid]["article"], [data[aid]["systems"][m]["summary"] for m in ms]
            )
            tin, tout = (
                len(msg) / js.CHARS_PER_TOKEN,
                js.OUT_TOKENS_FIXED + js.OUT_TOKENS_PER_SUMMARY * len(ms),
            )
            est += tin / 1e6 * float(j["params"]["usd_per_mtok_in"]) + tout / 1e6 * float(
                j["params"]["usd_per_mtok_out"]
            )
        print(
            f"{len(data)} articles x {len(systems)} summaries, blocks {js.block_sizes(len(systems), per_call)}; "
            f"{len(tasks)} calls ({len(missing)} not stored), est ${est:.4f}; cap {cap}"
        )
        return 0
    if missing and args.no_calls:
        die(f"--no-calls but {len(missing)} record(s) are missing")
    if missing and cap is None:
        die("no cost cap: set cost_cap_usd in the scorer or EVAL_MAX_COST_USD")

    spent = sum(float(json.loads(f.read_text()).get("cost_usd") or 0.0) for f in vroot.glob("*/*.json"))
    stopped = None
    for j, aid, b, ms in missing:
        if stopped:
            break
        if cap is not None and spent >= cap:
            stopped = f"COST CAP: spent ${spent:.4f} of ${cap:.4f}"
            break
        a = data[aid]
        texts = [a["systems"][m]["summary"] for m in ms]
        msg = js.build_message(base, a["article"], texts)
        t0 = time.monotonic()
        try:
            res = call_with_retries(js.real_call, (msg, dict(j["params"])), label=f"{j['id']} {aid} b{b}")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — stop cleanly, as judge_score does
            stopped = f"JUDGE CALL FAILED after retries or refused: {j['id']}: {type(exc).__name__}: {str(exc)[:300]}"
            break
        cost, known = js.call_cost(res, j["params"])
        why = withheld_reason(res.output, shingles([a["article"], *texts]))
        rec: dict = {
            "article_id": aid,
            "block": b,
            "order": ms,
            "output": None if why else res.output,
            "output_sha256": _sha((res.output or "").encode()),
            "output_withheld": bool(why),
            **({"withheld_reason": why} if why else {}),
            "dims": parse_dims(res.output, len(ms)),
            "cost_usd": cost if cost is not None else 0.0,
            "cost_known": known,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "judge_fp": js.judge_fingerprint(j),
            "prompt_sha": js._sha(msg),
        }
        f = record_path(vroot / j["id"], aid, b)
        f.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(f, json.dumps(rec))
        spent += rec["cost_usd"]
        if cost is None:
            stopped = f"{j['id']}: no cost and no token counts; spend unknown"
    if stopped:
        print(f"  {stopped}\n  Stopping; every stored record is kept. Run the same command again to resume.")
        return 2

    report = build_report(sc, base, per_call, data, systems, vroot)
    print_report(report)
    write_text_atomic(vroot / "report.json", json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
