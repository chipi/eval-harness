#!/usr/bin/env python3
"""Check a judge scorer against human preferences on MODERN news summaries.

    python scripts/validate_judge_goyal.py --scorer judge-summ-v1 [--dry-run | --no-calls]
    python scripts/validate_judge_goyal.py --scorer judge-summ-v1 --backfill-provenance --no-calls

SummEval validates judges on 2019-era summarisers. Goyal, Li & Durrett (2022, "News
Summarization and Evaluation in the Era of GPT-3", CC BY 4.0) released, for 100 CNN
articles from 2022, summaries by GPT-3 (text-davinci-002), BRIO (a BART-based fine-tune)
and T0, each set judged best/worst by three annotators. This asks each judge of a scorer to
score the three summaries of every article (same validated prompt, rendered for three,
blinded, order seeded per article) and compares with the people, per article:

  best pick            the judge's top summary against the annotators' majority best (at
                       least 2 of 3 name the same system). A tie for top earns 1/k when the
                       human best is among the k tied; chance is 1/3.
  gpt3 vs brio         per article, the judge's preference against the MAJORITY of the three
                       annotators' implied orderings (best > unranked > worst; ties skipped),
                       as an agreement rate with a Wilson 95% interval, beside each side's
                       own GPT-3 rate on the same articles.
  human baseline       leave-one-annotator-out: each annotator's best against the best of the
                       other two, with the same partial-credit rule, over ALL articles. The
                       judge is scored against the same leave-one-out references.

Everything is recomputed from the stored verdicts. The data is downloaded to
data/external/goyal2022/ (gitignored; the zip's sha256 is pinned below); raw verdicts are
stored under data/judge-validation/<scorer>/goyal2022-cnn/<judge>/ and re-read for $0.
Each record carries judge_fp (the judge's fingerprint) and prompt_sha (the sha256 of the
message sent); a record that disagrees with the scorer as it is now is refused, not reused.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import math
import sys
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _fetch  # noqa: E402
import judge_score as js  # noqa: E402
from _common import die, write_bytes_atomic, write_text_atomic  # noqa: E402
from _retry import call_with_retries  # noqa: E402
from judging import shingles, withheld_reason  # noqa: E402

DATA = HERE.parent / "data"
EXT = DATA / "external" / "goyal2022"
ZIP_PATH = EXT / "human_annotations.zip"
URL = "https://tagoyal.github.io/zero-shot-explorer/human_annotations.zip"
#: sha256 of the zip served at URL on 2026-10-20 (327,103 bytes), and of its cnn_human.json.
ZIP_SHA256 = "0139228dd09f652865015495551685caf886e540f816f06d4fc7961b82124cf6"
CNN_JSON_SHA256 = "4e13a6eeb2aeb2c300b32e870360f0118d4855bcbb1ade8d8946976c4b203fe4"
SYSTEMS = ("gpt3", "brio", "t0")
CHANCE_BEST = 1 / 3


def _file_sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_local() -> dict | None:
    """The human annotations if already on disk (both pins checked), else None. Never downloads."""
    f = EXT / "human_annotations" / "cnn_human.json"
    if ZIP_PATH.is_file() and _file_sha(ZIP_PATH.read_bytes()) != ZIP_SHA256:
        die(f"{ZIP_PATH} does not match the pinned sha256 {ZIP_SHA256}; refusing to use it")
    if not f.is_file():
        return None
    raw = f.read_bytes()
    if _file_sha(raw) != CNN_JSON_SHA256:
        die(f"{f} has sha256 {_file_sha(raw)}, not the pinned {CNN_JSON_SHA256}")
    return json.loads(raw)


def load() -> dict:
    """Download and extract the Goyal data if not already on disk; validate both pins."""
    data = load_local()
    if data is None:
        if not ZIP_PATH.is_file():
            # Retried, checked against the pin, and only a whole file ever lands: a download cut
            # short used to leave a partial zip that every later run refused.
            try:
                src, _ = _fetch.fetch(URL, ZIP_SHA256)
            except _fetch.FetchError as exc:
                die(f"{exc}; refusing to extract it")
            EXT.mkdir(parents=True, exist_ok=True)
            write_bytes_atomic(ZIP_PATH, src.read_bytes())
        zipfile.ZipFile(io.BytesIO(ZIP_PATH.read_bytes())).extractall(EXT)
        data = load_local()
        if data is None:
            die(f"{ZIP_PATH} extracted, but it holds no human_annotations/cnn_human.json")
    return data


def order(article_id: str) -> list:
    """Deterministic (seeded by article_id) ordering of the three summaries."""
    return sorted(SYSTEMS, key=lambda s: hashlib.sha256(f"goyal-0:{article_id}:{s}".encode()).hexdigest())


def record_path(vdir: Path, aid: str) -> Path:
    """Path to a judge's stored verdict for an article, hashed to a short filename."""
    return vdir / f"{hashlib.sha256(aid.encode()).hexdigest()[:16]}.json"


# ── human side ───────────────────────────────────────────────────────────────
def best_counts(annotators: Sequence[dict]) -> collections.Counter:
    """Vote counts for systems named best by the annotators."""
    c: collections.Counter = collections.Counter()
    for a in annotators:
        c.update(a["best_summary"])
    return c


def majority_best(annotators: Sequence[dict]) -> str | None:
    """The one system at least 2 of the annotators name best, else None."""
    c = best_counts(annotators)
    if not c:
        return None
    top = max(c.values())
    tied = [s for s, n in c.items() if n == top]
    return tied[0] if len(tied) == 1 and top >= 2 else None


def human_prefs(annotators: Sequence[dict]) -> tuple:
    """(majority best or None, annotators preferring gpt3 to brio, brio to gpt3)."""
    g = b = 0
    for a in annotators:
        r = ranks(a)
        g += r["gpt3"] > r["brio"]
        b += r["brio"] > r["gpt3"]
    return majority_best(annotators), g, b


def ranks(a: dict) -> dict[str, int]:
    """Rank of each system in one annotator: 2=best, 1=unranked, 0=worst."""
    return {s: (2 if s in a["best_summary"] else 0 if s in a["worst_summary"] else 1) for s in SYSTEMS}


def human_pair_pref(annotators: Sequence[dict]) -> str | None:
    """Majority of the annotators' implied gpt3-vs-brio orderings; None on a tie."""
    net = 0
    for a in annotators:
        r = ranks(a)
        net += (r["gpt3"] > r["brio"]) - (r["brio"] > r["gpt3"])
    return "gpt3" if net > 0 else "brio" if net < 0 else None


def top_set(counts: collections.Counter) -> list[str]:
    """All systems tied for the highest count; empty list if counts is empty."""
    if not counts:
        return []
    top = max(counts.values())
    return sorted(s for s, n in counts.items() if n == top)


def credit(picks: Sequence[str], ref: Sequence[str]) -> float:
    """Expected agreement of one system drawn uniformly from `picks` with one drawn
    uniformly from `ref`. With a single reference system this is 1/k if it is among the k
    tied picks; with two annotators' split best it is the same rule applied both ways."""
    if not picks or not ref:
        return 0.0
    return len(set(picks) & set(ref)) / (len(picks) * len(ref))


def wilson(k: float, n: int, z: float = 1.959964) -> list[float] | None:
    """Wilson 95% interval for k successes in n. k may be fractional (partial credit): the
    interval then treats the mean credit as a proportion of n, an approximation."""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k: float, n: int) -> dict:
    """Score k out of n with the rate, Wilson 95% CI, and raw counts."""
    return {"k": round(k, 4), "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def loo_refs(annotators: Sequence[dict]) -> list[tuple[dict, list[str]]]:
    """(held-out annotator, the other annotators' top-voted best systems) for each annotator."""
    out = []
    for i, a in enumerate(annotators):
        rest = best_counts([x for j, x in enumerate(annotators) if j != i])
        out.append((a, top_set(rest)))
    return out


def human_baseline(data: dict) -> dict:
    """Leave-one-annotator-out baseline stats for all articles."""
    tot = n = n_skip = 0.0
    tot_agree = n_agree = 0.0
    for v in data.values():
        for a, ref in loo_refs(v["annotators"]):
            picks = sorted(a["best_summary"])
            if not picks or not ref:
                n_skip += 1
                continue
            c = credit(picks, ref)
            tot += c
            n += 1
            if len(ref) == 1:
                tot_agree += c
                n_agree += 1
    old_k = old_n = 0
    for v in data.values():
        anns = v["annotators"]
        for i, a in enumerate(anns):
            ob = [x["best_summary"] for j, x in enumerate(anns) if j != i]
            if len(ob) == 2 and ob[0] == ob[1] and len(ob[0]) == 1:
                old_n += 1
                old_k += a["best_summary"] == ob[0]
    return {
        "definition": (
            "Leave-one-annotator-out over ALL articles: for each article and each of its three "
            "annotators, that annotator's best set P is scored against R, the system(s) with the "
            "most best-votes among the OTHER two annotators (one system when they agree, two "
            "when they name different ones). Credit = |P and R| / (|P| x |R|): the chance that "
            "a system drawn at random from P equals one drawn from R, which is the judge's 1/k "
            "rule when R has one system. Pairs where P or R is empty are skipped. This is one "
            "annotator against two others, the judge's score is against three: the judge is "
            "also scored against these same leave-one-out references (best_pick_vs_loo_reference)."
        ),
        "leave_one_annotator_out": rate(tot, int(n)),
        "pairs_skipped_empty": int(n_skip),
        "leave_one_annotator_out_agreeing_others_only": rate(tot_agree, int(n_agree)),
        "one_annotator_matches_other_two_best": f"{old_k}/{old_n}",
    }


# ── judge side ───────────────────────────────────────────────────────────────
def judge_top(rec: dict) -> tuple[dict[str, float], list[str]]:
    """(score dict, all systems with the top score)."""
    s = dict(zip(rec["order"], rec["scores"]))
    top = max(s.values())
    return s, sorted(k for k, x in s.items() if x == top)


def judge_stats(data: dict, recs: dict[str, dict]) -> dict:
    """Comprehensive stats comparing judge to human preferences."""
    per_article = []
    cred: float = 0
    n_maj = exact = tied_hit = miss = 0
    unparsed = 0
    jg = jb = 0  # the old, all-articles counts
    pw_n = pw_agree = 0
    pw_j_g = pw_h_g = 0  # GPT-3 preferred, on the articles both sides decided
    pw_j_tied = pw_h_tied = 0
    loo_cred = loo_n = 0.0
    for aid, v in data.items():
        rec = recs[aid]
        if rec["scores"] is None:
            unparsed += 1
            continue
        s, top = judge_top(rec)
        jg += s["gpt3"] > s["brio"]
        jb += s["brio"] > s["gpt3"]
        maj = majority_best(v["annotators"])
        if maj is not None:
            c = credit(top, [maj])
            n_maj += 1
            cred += c
            exact += c == 1
            tied_hit += 0 < c < 1
            miss += c == 0
            per_article.append(
                {"article_id": aid, "human_best": maj, "judge_top": top, "credit": round(c, 4)}
            )
        for a, ref in loo_refs(v["annotators"]):
            if a["best_summary"] and ref:
                loo_cred += credit(top, ref)
                loo_n += 1
        hp = human_pair_pref(v["annotators"])
        jp = "gpt3" if s["gpt3"] > s["brio"] else "brio" if s["brio"] > s["gpt3"] else None
        pw_j_tied += jp is None
        pw_h_tied += hp is None
        if hp is not None and jp is not None:
            pw_n += 1
            pw_agree += hp == jp
            pw_j_g += jp == "gpt3"
            pw_h_g += hp == "gpt3"
    strict = sum(1 for p in per_article if p["credit"] == 1.0 and len(p["judge_top"]) == 1)
    return {
        "unparsed": unparsed,
        "judge_gpt3_over_brio": jg,
        "judge_brio_over_gpt3": jb,
        "best_pick_agreement": f"{strict}/{n_maj}",
        "best_pick_partial_credit": {
            **rate(cred, n_maj),
            "chance": round(CHANCE_BEST, 4),
            "exact_unique": strict,
            "tied_with_human_best": int(tied_hit),
            "miss": int(miss),
            "rule": "1/k when the human majority best is among the judge's k tied top summaries",
        },
        "best_pick_per_article": per_article,
        "best_pick_vs_loo_reference": {
            **rate(loo_cred, int(loo_n)),
            "rule": "the judge's top set against the other-two-annotators reference of each "
            "(article, held-out annotator) pair; the same pairs as the human baseline",
        },
        "pairwise_gpt3_vs_brio_per_article": {
            "human_preference": "majority of the three annotators' implied orderings "
            "(best > unranked > worst), ties skipped",
            "articles_both_decided": pw_n,
            "judge_tied": pw_j_tied,
            "human_tied": pw_h_tied,
            "agreement": rate(pw_agree, pw_n),
            "judge_prefers_gpt3": rate(pw_j_g, pw_n),
            "human_prefers_gpt3": rate(pw_h_g, pw_n),
        },
    }


def read_records(vdir: Path, data: dict) -> dict[str, dict]:
    """Load all judge verdicts for the articles in data; keyed by article_id."""
    return {aid: json.loads(record_path(vdir, aid).read_text()) for aid in data}


# ── stored-record integrity ──────────────────────────────────────────────────
def expected(base: str, aid: str, v: dict) -> tuple[list[str], str]:
    """(summary order for this article, sha256 of the message sent to the judge)."""
    so = order(aid)
    msg = js.build_message(base, v["article"], [v[s]["text"] for s in so])
    return so, js._sha(msg)


def record_problem(rec: dict, so: list[str], sha: str, fp: str) -> str | None:
    """Error message if the stored record is inconsistent with the scorer as it is now, else None."""
    if "judge_fp" not in rec or "prompt_sha" not in rec:
        return "has no judge_fp/prompt_sha (run --backfill-provenance --no-calls once)"
    if rec["judge_fp"] != fp:
        return f"was stored by judge {rec['judge_fp']}, the scorer's is now {fp}"
    if rec["prompt_sha"] != sha:
        return f"was stored for prompt {rec['prompt_sha'][:12]}, the scorer now sends {sha[:12]}"
    if rec.get("order") != so:
        return "was stored with a different summary order"
    return None


def main() -> int:
    """Validate a judge on Goyal 2022 summaries; call or recompute from stored verdicts."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scorer", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--no-calls",
        action="store_true",
        help="recompute from the stored records; error, listing them, if any is missing",
    )
    ap.add_argument(
        "--backfill-provenance",
        action="store_true",
        help="stamp judge_fp and prompt_sha, from the scorer as it is now, on stored "
        "records that lack them (one-off; records the fact in the report)",
    )
    args = ap.parse_args()
    sc = js.load_scorer(DATA / "scorers" / f"{args.scorer}.yaml")
    base = js.prompt_text(sc)
    data = load()
    vroot = DATA / "judge-validation" / args.scorer / "goyal2022-cnn"
    cap = js.effective_cap(sc)

    backfilled = {j["id"]: 0 for j in sc["judges"]}
    missing, problems = [], []
    exp: dict[tuple[str, str], tuple[list[str], str]] = {}
    for j in sc["judges"]:
        fp = js.judge_fingerprint(j)
        for aid, v in data.items():
            so, sha = exp[(j["id"], aid)] = expected(base, aid, v)
            f = record_path(vroot / j["id"], aid)
            if not f.is_file():
                missing.append(f"{j['id']}/{f.name} (article {aid})")
                continue
            rec = json.loads(f.read_text())
            if args.backfill_provenance and "judge_fp" not in rec and "prompt_sha" not in rec:
                if rec.get("order") != so:
                    problems.append(
                        f"{j['id']}/{f.name}: order differs from the seeded order; not backfilled"
                    )
                    continue
                rec.update({"judge_fp": fp, "prompt_sha": sha, "provenance_backfilled": True})
                write_text_atomic(f, json.dumps(rec))
                backfilled[j["id"]] += 1
            p = record_problem(rec, so, sha, fp)
            if p:
                problems.append(f"{j['id']}/{f.name}: {p}")
    if args.backfill_provenance:
        print(f"backfilled: {backfilled}")
    if problems:
        die(
            "stored records refused:\n  "
            + "\n  ".join(problems[:20])
            + (f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else "")
        )
    if args.dry_run:
        print(
            f"{len(data)} articles x {len(sc['judges'])} judges = {len(data) * len(sc['judges'])} "
            f"calls, {len(missing)} not stored; cap {cap}"
        )
        return 0
    if missing:
        if args.no_calls:
            die(f"--no-calls but {len(missing)} record(s) are missing:\n  " + "\n  ".join(missing))
        if cap is None:
            die("no cost cap: set cost_cap_usd in the scorer or EVAL_MAX_COST_USD")

    spent = sum(
        float(json.loads(f.read_text()).get("cost_usd") or 0.0)
        for j in sc["judges"]
        for f in (vroot / j["id"]).glob("*.json")
    )
    report: dict[str, Any] = {
        "source": "Goyal, Li & Durrett 2022, cnn_human.json (CC BY 4.0)",
        "scorer": args.scorer,
        "articles": len(data),
        "judges": {},
        "inputs": {
            "zip_sha256": ZIP_SHA256,
            "cnn_human_sha256": CNN_JSON_SHA256,
            "scorer_sha256": sc["_sha256"],
            "chance_best_pick": round(CHANCE_BEST, 4),
        },
    }
    aborted = False
    for j in sc["judges"]:
        jid, fp = j["id"], js.judge_fingerprint(j)
        vdir = vroot / jid
        vdir.mkdir(parents=True, exist_ok=True)
        billed = 0.0
        for aid, v in data.items():
            f = record_path(vdir, aid)
            if f.is_file():
                continue
            if aborted:
                continue
            if cap is not None and spent >= cap:
                print(f"COST CAP: spent ${spent:.4f} of ${cap:.4f}; stopping")
                aborted = True
                continue
            sysorder, sha = exp[(jid, aid)]
            msg = js.build_message(base, v["article"], [v[s]["text"] for s in sysorder])
            t0 = time.monotonic()
            try:
                res = call_with_retries(js.real_call, (msg, dict(j["params"])), label=f"{jid} {aid}")
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001 — stop cleanly, as judge_score does
                print(
                    f"  JUDGE CALL FAILED after retries or refused: {jid}: {type(exc).__name__}: "
                    f"{str(exc)[:300]}\n  Stopping; every stored record is kept. Run the same "
                    "command again to resume."
                )
                aborted = True
                continue
            cost, known = js.call_cost(res, j["params"])
            why = withheld_reason(res.output, shingles([v["article"], *(v[s]["text"] for s in sysorder)]))
            rec = {
                "article_id": aid,
                "order": sysorder,
                "output": None if why else res.output,
                "output_sha256": hashlib.sha256((res.output or "").encode()).hexdigest(),
                "output_withheld": bool(why),
                **({"withheld_reason": why} if why else {}),
                "cost_usd": cost if cost is not None else 0.0,
                "cost_known": known,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "scores": js.parse_block(res.output, 3),
                "judge_fp": fp,
                "prompt_sha": sha,
            }
            write_text_atomic(f, json.dumps(rec))
            spent += rec["cost_usd"]
            if cost is None:
                print(f"{jid}: no cost and no token counts; spend unknown, stopping")
                aborted = True
        billed = sum(float(json.loads(f.read_text()).get("cost_usd") or 0.0) for f in vdir.glob("*.json"))
        if aborted:
            die(f"stopped before every record of {jid} was stored; nothing reported")
        recs = read_records(vdir, data)
        st = judge_stats(data, recs)
        st["human_gpt3_over_brio"] = sum(human_prefs(v["annotators"])[1] for v in data.values())
        st["human_brio_over_gpt3"] = sum(human_prefs(v["annotators"])[2] for v in data.values())
        st["billed_usd"] = round(billed, 4)
        st["records_sha256"] = js.records_sha256(vdir)
        st["records_backfilled"] = sum(1 for r in recs.values() if r.get("provenance_backfilled"))
        st["records_cost_unknown"] = sum(1 for r in recs.values() if r.get("cost_known") is False)
        report["judges"][jid] = {
            k: st[k]
            for k in (
                "best_pick_agreement",
                "judge_gpt3_over_brio",
                "judge_brio_over_gpt3",
                "human_gpt3_over_brio",
                "human_brio_over_gpt3",
                "unparsed",
                "billed_usd",
            )
        }
        report["judges"][jid].update({k: v for k, v in st.items() if k not in report["judges"][jid]})
        bp, pw, lo = (
            st["best_pick_partial_credit"],
            st["pairwise_gpt3_vs_brio_per_article"],
            st["best_pick_vs_loo_reference"],
        )
        print(
            f"{jid}: best pick, partial credit {bp['k']}/{bp['n']} = {bp['rate']} {bp['ci95']} "
            f"(chance {bp['chance']}; unique-and-right {bp['exact_unique']}, tied-with-best "
            f"{bp['tied_with_human_best']}, miss {bp['miss']}); vs leave-one-out refs {lo['rate']} {lo['ci95']}"
        )
        print(
            f"{jid}: GPT-3 vs BRIO per article, {pw['articles_both_decided']} articles both decided "
            f"(judge tied {pw['judge_tied']}, humans tied {pw['human_tied']}): agreement "
            f"{pw['agreement']['k']:.0f}/{pw['agreement']['n']} = {pw['agreement']['rate']} {pw['agreement']['ci95']}; "
            f"judge prefers GPT-3 {pw['judge_prefers_gpt3']['rate']} {pw['judge_prefers_gpt3']['ci95']}, "
            f"humans {pw['human_prefers_gpt3']['rate']} {pw['human_prefers_gpt3']['ci95']}; "
            f"unparsed {st['unparsed']}; billed ${billed:.4f}; backfilled records {st['records_backfilled']}"
        )
    hb = human_baseline(data)
    report["human_baseline"] = hb
    lo = hb["leave_one_annotator_out"]
    print(
        f"humans, leave-one-annotator-out partial credit {lo['k']}/{lo['n']} = {lo['rate']} {lo['ci95']} "
        f"(others agreeing only: {hb['leave_one_annotator_out_agreeing_others_only']['rate']} on "
        f"{hb['leave_one_annotator_out_agreeing_others_only']['n']}); old strict figure "
        f"{hb['one_annotator_matches_other_two_best']}"
    )
    n_back = sum(r["records_backfilled"] for r in report["judges"].values())
    if n_back:
        report["provenance_note"] = (
            f"{n_back} stored records predate judge_fp/prompt_sha. They were stamped once, "
            "deterministically, from the scorer as it was at that moment (--backfill-provenance), after "
            "checking each record's summary order against the seeded order; they are marked "
            "provenance_backfilled. The stamp attests the scorer at backfill time, not what "
            "was sent at the time."
        )
        print(report["provenance_note"])
    write_text_atomic(vroot / "report.json", json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
