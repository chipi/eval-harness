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
#: is every free scorer but BARTScore and UniEval: ROUGE, `coverage` and length are rules, not models.
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


def hardware() -> list:
    """The machines behind the experiments (docs/evidence/hardware.json), each with the
    committed runs whose fingerprint names it. Every run must match exactly one machine,
    or the build stops: a run measured somewhere undocumented is a gap, not a footnote."""
    hw = json.loads((ROOT / "docs" / "evidence" / "hardware.json").read_text())["machines"]
    machines = [{**m, "hosted": 0, "local": 0} for m in hw]
    for exp in EXPERIMENTS:
        for arm, d in _runs("runs", exp["dataset"], exp["prefix"], exp["suffix"]).items():
            fp = json.loads((d / "metrics.json").read_text()).get("fingerprint") or {}
            host = fp.get("host") or {}
            hits = [m for m in machines if m["fingerprint"]
                    and host.get("platform") == m["fingerprint"]["platform"]
                    and host.get("cpu_count") == m["fingerprint"]["cpu_count"]]
            if len(hits) != 1:
                raise SystemExit(f"{d.name}: host {host.get('platform')}/{host.get('cpu_count')} "
                                 f"matches {len(hits)} machines in docs/evidence/hardware.json")
            prov = (json.loads((d / "metrics.json").read_text()).get("params") or {}).get("provider")
            hits[0]["hosted" if prov in ("litellm", "rerank") else "local"] += 1
    return machines


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


def _ranks(scores: dict) -> dict:
    """arm -> 1-based position by score, highest first (ties by name, as the tables print)."""
    return {a: i for i, a in enumerate(sorted(scores, key=lambda a: (-scores[a], a)), 1)}


def adjudicated(slug: str, exps: list) -> dict:
    """Accuracy per arm on the dataset's gold (v1) and on the adjudicated gold (v2), from the
    committed predictions and the committed adjudication record: an adjudicated item's
    verdict replaces its gold, every other item keeps the correctness the run recorded. The
    same rule check_report_claims verifies the report's table with."""
    x = next(e for e in exps if e["slug"] == slug)
    adj = json.loads((ROOT / "examples" / x["example"] / "adjudication.json").read_text())
    verdict = {i["item_id"]: i["adjudicated"] for i in adj["items"]}
    v1, v2 = {}, {}
    for arm, d in _runs(x["base"], x["dataset"], x["prefix"], x["suffix"]).items():
        rows = [json.loads(line) for line in (d / "predictions.jsonl").open() if line.strip()]
        v1[arm] = sum(r["correct"] for r in rows) / len(rows)
        v2[arm] = sum((r["_meta"].get("predicted") == verdict[r["item_id"]])
                      if r["item_id"] in verdict else r["correct"] for r in rows) / len(rows)
    kind = {a["arm"]: a["kind"] for a in x["arms"]}
    wts = {a["arm"]: a["weights"] for a in x["arms"]}
    r1, r2 = _ranks(v1), _ranks(v2)
    return {"arms": [{"arm": a, "kind": kind[a], "weights": wts[a], "v1": v1[a], "v2": v2[a], "r1": r1[a],
                      "r2": r2[a]} for a in sorted(v1, key=lambda a: r1[a])],
            "n_items": len(adj["items"]),
            "changed": sum(i["verdict"] == "gold wrong" for i in adj["items"]),
            "n_arms": len(v1)}


def judged_summarisation(exps: list, scorer: str = "") -> dict:
    """The summarisation arms on coverage (the primary) and on a judge scorer's score,
    projected from its stored verdicts exactly as judge_figures does, with
    judge_figures' own figures (human check, Goyal, pointwise, agreement)."""
    sys.path.insert(0, str(HARNESS / "scripts"))
    import judge_figures as jf  # noqa: PLC0415
    import judge_score as js  # noqa: PLC0415
    scorer = scorer or jf.SCORER
    jfig = jf.compute(scorer)
    m = json.loads(next((DATA / "judging-sets").glob(jf.SET_GLOB)).read_text())
    sc = js.load_scorer(DATA / "scorers" / f"{scorer}.yaml")
    vdir = DATA / "judge-verdicts" / scorer / m["judging_set_id"]
    ids = [i["item_id"] for i in m["items"]]
    scores = js.load_scores(m, sc, vdir)
    proj = js.project(sc, scores, ids)
    summ = js.summarise(m, sc, m["arms"], scores, proj, {}, "recomputed", True, vdir)
    files = [json.loads(p.read_text()) for p in vdir.glob("*/*.json")]
    hc = json.loads((ROOT / "examples" / "summarization-cnn-dailymail" / "human_check_judge.json").read_text())
    pairs = [p for p in hc["pairs"] if p["item_id"] in proj]
    ctrl = summ["controls"]
    x = next(e for e in exps if e["slug"] == "summarization")
    judged = {a["config_id"][len(x["prefix"]):-len(x["suffix"])]:
              sum(proj[i][a["config_id"]]["_mean"] for i in proj) / len(proj) for a in m["arms"]}
    cov = {a["arm"]: a["score"] for a in x["arms"]}
    kind = {a["arm"]: a["kind"] for a in x["arms"]}
    wts = {a["arm"]: a["weights"] for a in x["arms"]}
    if set(cov) != set(judged):
        raise SystemExit(f"judged arms differ from the summarisation arms: {set(cov) ^ set(judged)}")
    rc, rj = _ranks(cov), _ranks(judged)
    return {"arms": [{"arm": a, "kind": kind[a], "weights": wts[a], "v1": cov[a], "v2": judged[a], "r1": rc[a],
                      "r2": rj[a]} for a in sorted(cov, key=lambda a: rc[a])],
            "n_arms": len(cov), "items_scored": len(proj), "items_total": len(ids), "fig": jfig,
            "scorer": scorer, "judges": [j["id"] for j in sc["judges"]],
            "calls": len(files), "billed_usd": round(sum(f.get("cost_usd") or 0.0 for f in files), 4),
            "unparsed": sum(1 for f in files if f.get("scores") is None),
            "spearman": next(iter(summ["judge_agreement"].values()))["arm_mean_spearman"],
            "position": [ctrl[j]["position"]["mean_abs_diff"] for j in ctrl],
            "noise": [ctrl[j]["noise"]["mean_abs_diff"] for j in ctrl],
            "self_family_gap": {j: v["own_minus_others"] for j, v in summ["self_family_gap"].items()},
            "human_pairs": len(pairs),
            "prefers_deepseek_m": sum(proj[p["item_id"]]["cnn_deepseek_m_n200_v1"]["_mean"]
                                      > proj[p["item_id"]]["cnn_bart_l_n200_v1"]["_mean"] for p in pairs),
            "prefers_bart_l": sum(proj[p["item_id"]]["cnn_deepseek_m_n200_v1"]["_mean"]
                                  < proj[p["item_id"]]["cnn_bart_l_n200_v1"]["_mean"] for p in pairs)}


def validation_spend() -> float:
    """Billed for checking the judges against published human ratings (Goyal et al., Zhang et
    al.), from the committed records: spent beside the re-measurement, not part of it."""
    files = [p for p in (DATA / "judge-validation").glob("*/*/*/*.json")]
    return round(sum(json.loads(p.read_text()).get("cost_usd") or 0.0 for p in files), 4)


def zhang_figures() -> dict:
    """Both scorers' judges against Zhang et al.'s crowd ratings of LLM-era summaries, through
    judge_figures.zhang: recomputed from the stored records when the ratings are downloaded,
    the committed report.json (checked against the records) when not."""
    sys.path.insert(0, str(HARNESS / "scripts"))
    import judge_figures as jf  # noqa: PLC0415
    return {s: jf.zhang(s) for s in ("judge-summ-v1", "judge-summ-v2")}


def instrument_check(exps: list) -> dict:
    """How well each instrument agrees with SummEval's experts (mean Kendall tau): the
    summarisation experiment's own metric, ROUGE-1, the best free scorer, the best judge."""
    x = next(e for e in exps if e["slug"] == "summeval")
    s = {a["arm"]: a["score"] for a in x["arms"]}
    local = [a for a in x["arms"] if a["kind"] == "local"]
    return {"coverage": s["coverage"], "rouge1": s["rouge1"], "best_judge": x["top"]["arm"],
            "best_judge_tau": x["top"]["score"], "best_free": max(local, key=lambda a: a["score"])["arm"],
            "best_free_tau": max(a["score"] for a in local),
            "gemma_l": s["gemma_l"], "qwen_s": s["qwen_s"]}


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
        # SciFact ran only the twelve cheapest hosted models, so its dearest arm is not a
        # frontier model; the headline stat counts only experiments where one ran.
        "frontier_exps": sum(_has_frontier(e) for e in exps),
        "dearest_not_best_frontier": sum(_has_frontier(e) and e["dearest"]["arm"] != e["top"]["arm"]
                                         for e in exps),
        "local_first_or_tied": sum(e["top"]["kind"] == "local" or
                                   any(a["kind"] == "local" for a in e["arms"] if a["arm"] in e["tied"])
                                   for e in exps),
        "calibration": cal,
        "calibration_consistent": sum(r["consistent"] for r in cal),
        "calibration_inside": sum(abs(r["delta"]) <= r["ci"] for r in cal),
        "dailymail": dailymail(),
        "hardware": hardware(),
        "remeasure": {"ag": adjudicated("ag-news", exps), "db": adjudicated("dbpedia", exps),
                      "summ": judged_summarisation(exps), "summeval": instrument_check(exps),
                      "summ_v2": judged_summarisation(exps, "judge-summ-v2"), "zhang": zhang_figures(),
                      "validation_usd": validation_spend()},
    }


def _has_frontier(e) -> bool:
    return any(a["arm"].startswith(("anthropic_", "openai_")) for a in e["arms"])


if __name__ == "__main__":
    f = compute()
    for e in f["experiments"]:
        print(f"{e['bench']:14s} n={e['n_items']} arms={e['n_arms']} top={e['top']['arm']} "
              f"{e['top']['score']:.4f} dearest={e['dearest']['arm']} rank {e['dearest']['rank']}"
              f"/{e['n_arms']} tied={e['n_tied']} ({e['n_tied_paid']} paid) cheapest_tied="
              f"{e['cheapest_tied']['arm'] if e['cheapest_tied'] else '-'} ${e['billed_total']:.2f}")
    print("total arms", f["total_arms"], "billed", round(f["total_billed"], 2),
          "dearest never best", f["dearest_never_best"],
          "| with frontier models", f["dearest_not_best_frontier"], "/", f["frontier_exps"], "calibration consistent",
          f["calibration_consistent"], "/", len(f["calibration"]))
