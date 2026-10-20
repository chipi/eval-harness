#!/usr/bin/env python3
"""Check a judge scorer against human preferences on MODERN news summaries.

    python scripts/validate_judge_goyal.py --scorer judge-summ-v1 [--dry-run]

SummEval validates judges on 2019-era summarisers. Goyal, Li & Durrett (2022, "News
Summarization and Evaluation in the Era of GPT-3", CC BY 4.0) released, for 100 CNN
articles from 2022, summaries by GPT-3 (text-davinci-002), BRIO (a BART-based fine-tune)
and T0, each set judged best/worst by three annotators. This asks each judge of a scorer to
score the three summaries of every article (same validated prompt, rendered for three,
blinded, order seeded per article) and compares with the people:

  best-pick agreement  how often the judge's top summary is the annotators' majority best
  gpt3 vs brio         how often the judge prefers GPT-3 to BRIO, beside how often the
                       annotators did (each annotator's best > unranked > worst)

The data is downloaded to data/external/goyal2022/ (gitignored); raw verdicts are stored
under data/judge-validation/<scorer>/goyal2022-cnn/ and re-read for $0 on a rerun.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_score as js  # noqa: E402

DATA = HERE.parent / "data"
EXT = DATA / "external" / "goyal2022"
URL = "https://tagoyal.github.io/zero-shot-explorer/human_annotations.zip"
SYSTEMS = ("gpt3", "brio", "t0")
LABELS = "XYZ"


def load() -> dict:
    f = EXT / "human_annotations" / "cnn_human.json"
    if not f.is_file():
        EXT.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=60) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(EXT)
    return json.loads(f.read_text())


def order(article_id: str) -> list:
    return sorted(SYSTEMS, key=lambda s: hashlib.sha256(f"goyal-0:{article_id}:{s}".encode()).hexdigest())


def human_prefs(annotators: list) -> tuple:
    """(majority best or None, gpt3>brio count, brio>gpt3 count) over the annotators."""
    best = {}
    g, b = 0, 0
    for a in annotators:
        for s in a["best_summary"]:
            best[s] = best.get(s, 0) + 1
        rank = {s: (2 if s in a["best_summary"] else 0 if s in a["worst_summary"] else 1) for s in SYSTEMS}
        g += rank["gpt3"] > rank["brio"]
        b += rank["brio"] > rank["gpt3"]
    top = max(best.values()) if best else 0
    maj = [s for s, c in best.items() if c == top]
    return (maj[0] if len(maj) == 1 and top >= 2 else None), g, b


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scorer", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sc = js.load_scorer(DATA / "scorers" / f"{args.scorer}.yaml")
    base = js.prompt_text(sc)
    data = load()
    vroot = DATA / "judge-validation" / args.scorer / "goyal2022-cnn"
    if args.dry_run:
        print(f"{len(data)} articles x {len(sc['judges'])} judges = {len(data) * len(sc['judges'])} calls")
        return 0
    report = {"source": "Goyal, Li & Durrett 2022, cnn_human.json (CC BY 4.0)", "scorer": args.scorer,
              "articles": len(data), "judges": {}}
    for j in sc["judges"]:
        jid = j["id"]
        vdir = vroot / jid
        vdir.mkdir(parents=True, exist_ok=True)
        agree = n_maj = jg = jb = hg = hb = unparsed = 0
        billed = 0.0
        for aid, v in data.items():
            f = vdir / f"{hashlib.sha256(aid.encode()).hexdigest()[:16]}.json"
            sysorder = order(aid)
            if f.is_file():
                rec = json.loads(f.read_text())
            else:
                msg = js.build_message(base, v["article"],
                                       [v[s]["text"] for s in sysorder])
                t0 = time.monotonic()
                res = js.real_call(msg, j["params"])
                rec = {"article_id": aid, "order": sysorder, "output": res.output,
                       "cost_usd": res.cost_usd, "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
                rec["scores"] = js.parse_block(res.output, 3)
                f.write_text(json.dumps(rec))
            billed += rec.get("cost_usd") or 0.0
            maj, g, b = human_prefs(v["annotators"])
            hg += g
            hb += b
            if rec["scores"] is None:
                unparsed += 1
                continue
            s = dict(zip(rec["order"], rec["scores"]))
            top = max(s.values())
            judge_best = [k for k, x in s.items() if x == top]
            if maj is not None:
                n_maj += 1
                agree += judge_best == [maj]
            jg += s["gpt3"] > s["brio"]
            jb += s["brio"] > s["gpt3"]
        report["judges"][jid] = {
            "best_pick_agreement": f"{agree}/{n_maj}", "judge_gpt3_over_brio": jg,
            "judge_brio_over_gpt3": jb, "human_gpt3_over_brio": hg, "human_brio_over_gpt3": hb,
            "unparsed": unparsed, "billed_usd": round(billed, 4)}
        print(f"{jid}: best pick agrees with the annotators' majority on {agree}/{n_maj}; "
              f"GPT-3 over BRIO {jg}, BRIO over GPT-3 {jb} (humans: {hg} vs {hb}); "
              f"unparsed {unparsed}; billed ${billed:.4f}")
    agree_h = n_h = 0
    for v in data.values():
        anns = v["annotators"]
        for i, a in enumerate(anns):
            ob = [x["best_summary"] for j, x in enumerate(anns) if j != i]
            if len(ob) == 2 and ob[0] == ob[1] and len(ob[0]) == 1:
                n_h += 1
                agree_h += a["best_summary"] == ob[0]
    report["human_baseline"] = {"one_annotator_matches_other_two_best": f"{agree_h}/{n_h}"}
    print(f"humans: one annotator matches the other two's shared best on {agree_h}/{n_h}")
    (vroot / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
