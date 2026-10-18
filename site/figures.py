"""Every number the site shows, computed from the committed runs and evidence.

The site is generated, never hand-edited, so no figure on it can drift from the data:
`build.py` renders only what this module returns, and `make site-check` rebuilds and
fails on any difference. The sources are the same ones `check_report_claims.py` uses —
rescored NER runs, reparsed SciFact runs, billed cost from `_meta.usage.cost`, tie groups
from the leader's Holm family test — so the site and the reports cannot disagree.

Stdlib only; the family tests run as subprocesses of the harness's own script.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "harness"
DATA = HARNESS / "data"

#: The measurement slices on the site, from the registry `make reproduce` uses too -- so the site
#: and a stranger's rerun cannot mean different experiments. `base` is the directory the
#: REPORT is computed from; billed cost always comes from data/runs, where the provider's
#: response was recorded.
EXPERIMENTS = [e for e in json.loads((ROOT / "examples" / "experiments.json").read_text())
               ["experiments"] if e.get("site")]

#: Arms that are not models at all — calibration floors for the scorer. On SummEval that
#: is every free scorer but BARTScore: ROUGE, `coverage` and length are rules, not models.
BASELINES = {"lead3", "keyword", "constant", "capitalized", "nothing", "random", "first_k",
             "random_rank", "first20", "length", "rouge1", "rouge2", "rougeL", "coverage"}


def _runs(base: str, dataset: str, prefix: str, suffix: str) -> dict:
    """{arm: run_dir} for one slice. Two runs sharing an arm is an error, as in V8."""
    out: dict = {}
    for f in sorted((DATA / base).glob(f"{prefix}*/metrics.json")):
        m = json.loads(f.read_text())
        cid = m.get("config_id", "")
        if m.get("dataset_id") != dataset or not cid.endswith(suffix):
            continue
        arm = cid[len(prefix):-len(suffix)]
        if arm in out:
            raise SystemExit(f"two runs for {cid} under {base}: {out[arm].name}, {f.parent.name}")
        out[arm] = f.parent
    return out


def _billed(run_dir: Path) -> float:
    total = 0.0
    pj = run_dir / "predictions.jsonl"
    if pj.is_file():
        for line in pj.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                total += float((((r.get("_meta") or {}).get("usage") or {}).get("cost") or 0))
    return total


def _weights() -> dict:
    """arm -> 'open' | 'proprietary', from REFERENCE.md's hosted table."""
    ref = (ROOT / "docs" / "REFERENCE.md").read_text()
    out = {}
    for arm, w in re.findall(r"^\| `([a-z]+_[sml])` \| `eval-[^`]+` \| .*\| (\*\*open\*\*|proprietary)", ref, re.M):
        out[arm] = "open" if "open" in w else "proprietary"
    # A replacement arm is described in a note, not a table row: the row count is the
    # 24-model field other checks derive from.
    for arm, w in re.findall(r"`([a-z0-9_]+)` \(alias `eval-[^`]+` → .*?, weights: (open|proprietary)\)", ref):
        out[arm] = w
    return out


def _not_separated(exp: dict) -> list:
    """Opponents the leader's Holm family test does not separate from."""
    r = subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "family_test.py"), "--dataset-id",
         exp["dataset"], "--a", f"{exp['prefix']}{exp['leader']}{exp['suffix']}", "--against",
         exp["suffix"], "--metric", exp["metric"], "--runs-dir", str(DATA / exp["base"])],
        capture_output=True, text=True, cwd=HARNESS)
    if r.returncode != 0:
        raise SystemExit(f"family test failed for {exp['slug']}:\n{r.stderr[-800:]}")
    return [ln.split()[0][len(exp["prefix"]):-len(exp["suffix"])] for ln in r.stdout.splitlines()
            if ln.strip().endswith("--") and ln.split()[0].endswith(exp["suffix"])]


def experiment(exp: dict, weights: dict) -> dict:
    scored = _runs(exp["base"], exp["dataset"], exp["prefix"], exp["suffix"])
    billed = _runs("runs", exp["dataset"], exp["prefix"], exp["suffix"])
    arms = []
    for arm, d in scored.items():
        m = json.loads((d / "metrics.json").read_text())
        provider = (m.get("params") or {}).get("provider")
        kind = ("baseline" if arm in BASELINES else
                "hosted" if provider in ("litellm", "rerank") else "local")
        arms.append({"arm": arm, "score": m["scores"][exp["metric"]], "kind": kind,
                     "weights": weights.get(arm) if kind == "hosted" else None,
                     "cost": _billed(billed[arm]) if arm in billed else 0.0,
                     "model": (m.get("params") or {}).get("model")})
    arms.sort(key=lambda a: -a["score"])
    for i, a in enumerate(arms, 1):
        a["rank"] = i
    hosted = [a for a in arms if a["kind"] == "hosted"]
    paid = sorted(hosted, key=lambda a: a["cost"])
    dearest = max(hosted, key=lambda a: a["cost"])
    tied = _not_separated(exp)
    tied_paid = [a for a in hosted if a["arm"] in tied]
    cheapest_tied = min(tied_paid, key=lambda a: a["cost"]) if tied_paid else None
    leader = next(a for a in arms if a["arm"] == exp["leader"])
    n_items = json.loads((next(iter(scored.values())) / "metrics.json").read_text())["n_items"]
    return {
        **exp, "n_items": n_items, "arms": arms, "n_arms": len(arms),
        "n_hosted": len(hosted), "leader_row": leader, "top": arms[0],
        "dearest": dearest, "cheapest_paid": paid[0],
        "best_hosted": hosted[0] if hosted else None,
        "tied": tied, "n_tied": len(tied), "n_tied_paid": len(tied_paid),
        "cheapest_tied": cheapest_tied,
        "tied_ratio": (dearest["cost"] / cheapest_tied["cost"]) if cheapest_tied else None,
        "dearest_ratio": dearest["cost"] / paid[0]["cost"],
        "billed_total": sum(a["cost"] for a in arms),
    }


def calibration() -> list:
    """One row per calibration figure, in percentage points, for the forest plot."""
    cal = ROOT / "docs" / "evidence" / "calibration"
    rows = []
    s = json.loads((cal / "summarization.json").read_text())
    ft, pub = s["full_test"], s["published"]["lead3"]
    rows.append({"bench": "CNN/DailyMail", "what": "LEAD-3, ROUGE-1", "ours": ft["rouge1"],
                 "ci": ft["rouge1_ci95"], "published": pub["rouge1"], "n": ft["n"],
                 "scale": 1})
    names = {"ag_news": "AG News", "dbpedia": "DBpedia-14", "few_nerd": "Few-NERD",
             "scifact": "SciFact", "summeval": "SummEval"}
    for exp, label in names.items():
        c = json.loads((cal / f"{exp}.json").read_text())
        for arm, r in c["arms"].items():
            rows.append({"bench": label, "what": arm, "ours": 100 * r["value"],
                         "ci": 100 * r["ci95"], "published": 100 * r["published"],
                         "n": r.get("n") or r.get("n_sentences"), "scale": 100})
    for r in rows:
        r["delta"] = r["ours"] - r["published"]
        r["consistent"] = abs(r["delta"]) <= r["ci"] + 2.0
    return rows


def dailymail() -> list:
    """The five local summarisation arms on the CNN slice and on the DailyMail slice."""
    out = []
    cnn = _runs("runs", "cnn_dailymail_200", "cnn_", "_n200_v1")
    dm = _runs("runs", "cnn_dailymail_dm200", "cnn_", "_dm200_v1")
    for arm in ("bart_l", "bart_m", "bart_s", "lead3", "bart_l_xsum"):
        c = json.loads((cnn[arm] / "metrics.json").read_text())["scores"]["coverage"]
        d = json.loads((dm[arm] / "metrics.json").read_text())["scores"]["coverage"]
        out.append({"arm": arm, "cnn": c, "dm": d})
    return out


def compute() -> dict:
    weights = _weights()
    exps = [experiment(e, weights) for e in EXPERIMENTS]
    all_arms = sum(e["n_arms"] for e in exps)
    billed = sum(e["billed_total"] for e in exps)
    cal = calibration()
    claims = subprocess.run([sys.executable, str(HARNESS / "scripts" / "check_report_claims.py")],
                            capture_output=True, text=True, cwd=HARNESS).stdout
    m = re.search(r"(\d+)/(\d+) claims verified", claims)
    if not m or m.group(1) != m.group(2):
        raise SystemExit("check_report_claims is not green; the site will not claim it is")
    return {
        "claims_checked": int(m.group(2)),
        "experiments": exps,
        "total_arms": all_arms,
        "total_billed": billed,
        "dearest_never_best": sum(e["dearest"]["arm"] != e["top"]["arm"] for e in exps),
        "local_first_or_tied": sum(e["top"]["kind"] == "local" or
                                   any(a["kind"] == "local" for a in e["arms"] if a["arm"] in e["tied"])
                                   for e in exps),
        "calibration": cal,
        "calibration_consistent": sum(r["consistent"] for r in cal),
        "dailymail": dailymail(),
    }


if __name__ == "__main__":
    f = compute()
    for e in f["experiments"]:
        print(f"{e['bench']:14s} n={e['n_items']} arms={e['n_arms']} top={e['top']['arm']} "
              f"{e['top']['score']:.4f} dearest={e['dearest']['arm']} rank {e['dearest']['rank']}"
              f"/{e['n_arms']} tied={e['n_tied']} ({e['n_tied_paid']} paid) cheapest_tied="
              f"{e['cheapest_tied']['arm'] if e['cheapest_tied'] else '-'} ${e['billed_total']:.2f}")
    print("total arms", f["total_arms"], "billed", round(f["total_billed"], 2),
          "dearest never best", f["dearest_never_best"], "calibration consistent",
          f["calibration_consistent"], "/", len(f["calibration"]))
