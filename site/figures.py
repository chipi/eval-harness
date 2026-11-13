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
sys.path.insert(
    0, str(HARNESS)
)  # the evaluation_harness package: every read of the data goes through its store
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._runs import read_metrics, runs_on  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

sys.path.insert(0, str(ROOT / "examples" / "_shared"))
from eval_arms import arm_of  # noqa: E402
from evaluation_harness._common import system_now  # noqa: E402

#: The test slices on the site, from the registry `make reproduce` uses too -- so the site
#: and a stranger's rerun cannot mean different evals. `base` is the arm prefix (model.runs.arm_prefix) of
#: the label the REPORT is computed from; billed cost always comes from the plain label's runs, where the
#: provider's response was recorded.
EVALS = [e for e in json.loads(_store.read_text(ROOT / "examples" / "evals.json"))["evals"] if e.get("site")]

#: Arms that are not models at all — calibration floors for the scorer. On SummEval that
#: is every free scorer but BARTScore and UniEval: ROUGE, `coverage` and length are rules, not models.
BASELINES = {
    "lead3",
    "keyword",
    "constant",
    "capitalized",
    "nothing",
    "random",
    "first_k",
    "random_rank",
    "first20",
    "length",
    "rouge1",
    "rouge2",
    "rougeL",
    "coverage",
}


def label_of(base: str) -> str:
    """The label whose arm prefix is `base` ("runs": the plain label, a run's own score)."""
    for lbl in model_runs.labels():
        if model_runs.arm_prefix(lbl) == base:
            return lbl
    raise SystemExit(f"no scores read under {base!r}")


def _runs(base: str, dataset: str, prefix: str) -> dict:
    """{arm: score dir} for one slice: the scores read under `base`'s label of the runs whose id starts with
    `prefix`. Two runs sharing an arm is an error, as in V8."""
    out: dict = {}
    for d, m in runs_on(dataset, label=label_of(base)):
        if not m["run_id"].startswith(prefix):
            continue
        arm = arm_of(prefix, m["config_id"])
        if arm is None:
            continue
        if arm in out:
            raise SystemExit(
                f"two runs for {m['config_id']} under {base}: {m['run_id']}, {model_runs.run_of(out[arm]).name}"
            )
        out[arm] = d
    return out


def system_id(exp: dict, arm: str) -> str:
    """The id of the system behind an arm of an eval, as its run records it."""
    return read_metrics(_runs(exp["base"], exp["dataset"], exp["prefix"])[arm])["config_id"]


def _billed(run_dir: Path) -> float:
    """What the provider billed for one run (cost_report's sum, the one the reports use)."""
    sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
    from evaluation_harness.cost_report import billed_and_recorded  # noqa: PLC0415

    return billed_and_recorded(run_dir)[0]


def _weights() -> dict:
    """arm -> 'open' | 'proprietary', from REFERENCE.md's hosted table."""
    ref = _store.read_text(ROOT / "docs" / "REFERENCE.md")
    out = {}
    for arm, w in re.findall(
        r"^\| `([a-z]+_[sml])` \| `eval-[^`]+` \| .*\| (\*\*open\*\*|proprietary)", ref, re.M
    ):
        out[arm] = "open" if "open" in w else "proprietary"
    # A replacement arm is described in a note, not a table row: the row count is the
    # 24-model field other checks derive from.
    for arm, w in re.findall(
        r"`([a-z0-9_]+)` \(alias `eval-[^`]+` → .*?, weights: (open|proprietary)\)", ref
    ):
        out[arm] = w
    return out


def _not_significant(exp: dict) -> list:
    """Opponents the leader's Holm family test finds not significantly different."""
    cids = {
        read_metrics(d)["config_id"]: arm
        for arm, d in _runs(exp["base"], exp["dataset"], exp["prefix"]).items()
    }
    leader = next(c for c, arm in cids.items() if arm == exp["leader"])
    r = subprocess.run(
        [
            sys.executable,
            str(HARNESS / "scripts" / "family_test.py"),
            "--dataset-id",
            exp["dataset"],
            "--a",
            leader,
            "--against",
            ",".join(cids),
            "--metric",
            exp["metric"],
            "--label",
            label_of(exp["base"]),
        ],
        capture_output=True,
        text=True,
        cwd=HARNESS,
    )
    if r.returncode != 0:
        raise SystemExit(f"family test failed for {exp['slug']}:\n{r.stderr[-800:]}")
    return [
        cids[ln.split()[0]]
        for ln in r.stdout.splitlines()
        if ln.strip().endswith("--") and ln.split()[0] in cids and ln.split()[0] != leader
    ]


def eval_figures(exp: dict, weights: dict) -> dict:
    scored = _runs(exp["base"], exp["dataset"], exp["prefix"])
    billed = _runs("runs", exp["dataset"], exp["prefix"])
    arms = []
    for arm, d in scored.items():
        m = read_metrics(d)
        provider = (m.get("params") or {}).get("provider")
        kind = "baseline" if arm in BASELINES else "hosted" if provider in ("litellm", "rerank") else "local"
        arms.append(
            {
                "arm": arm,
                "score": m["scores"][exp["metric"]],
                "kind": kind,
                "weights": weights.get(arm) if kind == "hosted" else None,
                "cost": _billed(billed[arm]) if arm in billed else 0.0,
                "model": (m.get("params") or {}).get("model"),
            }
        )
    arms.sort(key=lambda a: -a["score"])
    for i, a in enumerate(arms, 1):
        a["rank"] = i
    hosted = [a for a in arms if a["kind"] == "hosted"]
    paid = sorted(hosted, key=lambda a: a["cost"])
    dearest = max(hosted, key=lambda a: a["cost"])
    contenders = _not_significant(exp)
    contenders_paid = [a for a in hosted if a["arm"] in contenders]
    cheapest_contender = min(contenders_paid, key=lambda a: a["cost"]) if contenders_paid else None
    leader = next(a for a in arms if a["arm"] == exp["leader"])
    n_items = read_metrics(next(iter(scored.values())))["n_items"]
    return {
        **exp,
        "n_items": n_items,
        "arms": arms,
        "n_arms": len(arms),
        "n_hosted": len(hosted),
        "leader_row": leader,
        "top": arms[0],
        "dearest": dearest,
        "cheapest_paid": paid[0],
        "best_hosted": hosted[0] if hosted else None,
        "contenders": contenders,
        "n_contenders": len(contenders),
        "n_contenders_paid": len(contenders_paid),
        "cheapest_contender": cheapest_contender,
        "contender_ratio": (dearest["cost"] / cheapest_contender["cost"]) if cheapest_contender else None,
        "dearest_ratio": dearest["cost"] / paid[0]["cost"],
        "billed_total": sum(a["cost"] for a in arms),
    }


def calibration() -> list:
    """One row per calibration figure, in percentage points, for the forest plot."""
    cal = ROOT / "docs" / "evidence" / "calibration"
    rows = []
    s = json.loads(_store.read_text(cal / "summarization.json"))
    ft, pub = s["full_test"], s["published"]["lead3"]
    rows.append(
        {
            "bench": "CNN/DailyMail",
            "what": "LEAD-3, ROUGE-1",
            "ours": ft["rouge1"],
            "ci": ft["rouge1_ci95"],
            "published": pub["rouge1"],
            "n": ft["n"],
            "scale": 1,
        }
    )
    names = {
        "ag_news": "AG News",
        "dbpedia": "DBpedia-14",
        "few_nerd": "Few-NERD",
        "scifact": "SciFact",
        "summeval": "SummEval",
    }
    for exp, label in names.items():
        c = json.loads(_store.read_text(cal / f"{exp}.json"))
        for arm, r in c["arms"].items():
            rows.append(
                {
                    "bench": label,
                    "what": arm,
                    "ours": 100 * r["value"],
                    "ci": 100 * r["ci95"],
                    "published": 100 * r["published"],
                    "n": r.get("n") or r.get("n_sentences"),
                    "scale": 100,
                }
            )
    for r in rows:
        r["delta"] = r["ours"] - r["published"]
        r["consistent"] = abs(r["delta"]) <= r["ci"] + 2.0
    return rows


def hardware() -> list:
    """The machines behind the evals (docs/evidence/hardware.json), each with the
    committed runs whose fingerprint names it. Every run must match exactly one machine,
    or the build stops: a run measured somewhere undocumented is a gap, not a footnote."""
    hw = json.loads(_store.read_text(ROOT / "docs" / "evidence" / "hardware.json"))["machines"]
    machines = [{**m, "hosted": 0, "local": 0} for m in hw]
    for exp in EVALS:
        for _arm, d in _runs("runs", exp["dataset"], exp["prefix"]).items():
            fp = read_metrics(d).get("fingerprint") or {}
            host = fp.get("runner") or {}
            hits = [
                m
                for m in machines
                if m["fingerprint"]
                and host.get("platform") == m["fingerprint"]["platform"]
                and host.get("cpu_count") == m["fingerprint"]["cpu_count"]
            ]
            if len(hits) != 1:
                raise SystemExit(
                    f"{model_runs.run_of(d).name}: host {host.get('platform')}/{host.get('cpu_count')} "
                    f"matches {len(hits)} machines in docs/evidence/hardware.json"
                )
            prov = (read_metrics(d).get("params") or {}).get("provider")
            hits[0]["hosted" if prov in ("litellm", "rerank") else "local"] += 1
    return machines


def dailymail() -> list:
    """The five local summarisation arms on the CNN slice and on the DailyMail slice."""
    out = []
    cnn = _runs("runs", "cnn_dailymail_200", "cnn_")
    dm = _runs("runs", "cnn_dailymail_dm200", "cnn_")
    for arm in ("bart_l", "bart_m", "bart_s", "lead3", "bart_l_xsum"):
        c = read_metrics(cnn[arm])["scores"]["coverage"]
        d = read_metrics(dm[arm])["scores"]["coverage"]
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
    adj = json.loads(_store.read_text(ROOT / "examples" / x["example"] / "adjudication.json"))
    verdict = {i["item_id"]: i["adjudicated"] for i in adj["items"]}
    sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
    from evaluation_harness._runs import item_rows  # noqa: PLC0415

    v1, v2 = {}, {}
    for arm, d in _runs(x["base"], x["dataset"], x["prefix"]).items():
        rows = list(item_rows(d))
        v1[arm] = sum(r["correct"] for r in rows) / len(rows)
        v2[arm] = sum(
            (r["_meta"].get("predicted") == verdict[r["item_id"]])
            if r["item_id"] in verdict
            else r["correct"]
            for r in rows
        ) / len(rows)
    kind = {a["arm"]: a["kind"] for a in x["arms"]}
    wts = {a["arm"]: a["weights"] for a in x["arms"]}
    r1, r2 = _ranks(v1), _ranks(v2)
    return {
        "arms": [
            {"arm": a, "kind": kind[a], "weights": wts[a], "v1": v1[a], "v2": v2[a], "r1": r1[a], "r2": r2[a]}
            for a in sorted(v1, key=lambda a: r1[a])
        ],
        "n_items": len(adj["items"]),
        "changed": sum(i["verdict"] == "gold wrong" for i in adj["items"]),
        "n_arms": len(v1),
    }


def judged_summarisation(exps: list, scorer: str = "") -> dict:
    """The summarisation arms on coverage (the primary) and on a judge scorer's score,
    projected from its stored verdicts exactly as judge_figures does, with
    judge_figures' own figures (human check, Goyal, pointwise, agreement)."""
    sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
    sys.path.insert(0, str(HARNESS / "tools"))  # judge_figures: the repository's, not the package's
    import judge_figures as jf  # noqa: PLC0415
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    scorer = scorer or jf.SCORER
    jfig = jf.compute(scorer)
    m = json.loads(_store.read_text(jf.grading_set()))
    sc = js.load_scorer(DATA / "scorers" / f"{scorer}.yaml")
    vdir = DATA / "judge-verdicts" / scorer / m["judging_set_id"]
    ids = [i["item_id"] for i in m["items"]]
    scores = js.load_scores(m, sc, vdir)
    proj = js.project(sc, scores, ids)
    summ = js.summarise(m, sc, m["arms"], scores, proj, {}, "recomputed", True, vdir)
    files = [json.loads(_store.read_text(p)) for p in _store.glob(vdir, "*/*.json")]
    hc = json.loads(
        _store.read_text(ROOT / "examples" / "summarization-cnn-dailymail" / "human_check_judge.json")
    )
    pairs = [p for p in hc["pairs"] if p["item_id"] in proj]
    ctrl = summ["controls"]
    x = next(e for e in exps if e["slug"] == "summarization")
    judged = {
        arm_of(x["prefix"], system_now(a["config_id"])): sum(proj[i][a["config_id"]]["_mean"] for i in proj)
        / len(proj)
        for a in m["arms"]
    }
    cov = {a["arm"]: a["score"] for a in x["arms"]}
    kind = {a["arm"]: a["kind"] for a in x["arms"]}
    wts = {a["arm"]: a["weights"] for a in x["arms"]}
    if set(cov) != set(judged):
        raise SystemExit(f"judged arms differ from the summarisation arms: {set(cov) ^ set(judged)}")
    rc, rj = _ranks(cov), _ranks(judged)
    return {
        "arms": [
            {
                "arm": a,
                "kind": kind[a],
                "weights": wts[a],
                "v1": cov[a],
                "v2": judged[a],
                "r1": rc[a],
                "r2": rj[a],
            }
            for a in sorted(cov, key=lambda a: rc[a])
        ],
        "n_arms": len(cov),
        "items_scored": len(proj),
        "items_total": len(ids),
        "fig": jfig,
        "scorer": scorer,
        "judges": [j["id"] for j in sc["judges"]],
        "calls": len(files),
        "billed_usd": round(sum(f.get("cost_usd") or 0.0 for f in files), 4),
        "unparsed": sum(1 for f in files if f.get("scores") is None),
        "spearman": next(iter(summ["judge_agreement"].values()))["arm_mean_spearman"],
        "position": [ctrl[j]["position"]["mean_abs_diff"] for j in ctrl],
        "noise": [ctrl[j]["noise"]["mean_abs_diff"] for j in ctrl],
        "self_family_gap": {j: v["own_minus_others"] for j, v in summ["self_family_gap"].items()},
        "human_pairs": len(pairs),
        "prefers_deepseek_m": sum(
            proj[p["item_id"]]["cnn_deepseek_m_n200_v1"]["_mean"]
            > proj[p["item_id"]]["cnn_bart_l_n200_v1"]["_mean"]
            for p in pairs
        ),
        "prefers_bart_l": sum(
            proj[p["item_id"]]["cnn_deepseek_m_n200_v1"]["_mean"]
            < proj[p["item_id"]]["cnn_bart_l_n200_v1"]["_mean"]
            for p in pairs
        ),
    }


def validation_spend() -> float:
    """Billed for checking the judges against published human ratings (Goyal et al., Zhang et
    al.), from the committed records: spent beside the re-measurement, not part of it."""
    files = list(_store.glob(DATA / "judge-validation", "*/*/*/*.json"))
    return round(sum(json.loads(_store.read_text(p)).get("cost_usd") or 0.0 for p in files), 4)


def zhang_figures() -> dict:
    """Both scorers' judges against Zhang et al.'s crowd ratings of LLM-era summaries, through
    judge_figures.zhang: recomputed from the stored records when the ratings are downloaded,
    the committed report.json (checked against the records) when not."""
    sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
    sys.path.insert(0, str(HARNESS / "tools"))  # judge_figures: the repository's, not the package's
    import judge_figures as jf  # noqa: PLC0415

    return {s: jf.zhang(s) for s in ("judge-summ-v1", "judge-summ-v2")}


def instrument_check(exps: list) -> dict:
    """How well each instrument agrees with SummEval's experts (mean Kendall tau): the
    summarisation eval's own metric, ROUGE-1, the best free scorer, the best judge."""
    x = next(e for e in exps if e["slug"] == "summeval")
    s = {a["arm"]: a["score"] for a in x["arms"]}
    local = [a for a in x["arms"] if a["kind"] == "local"]
    return {
        "coverage": s["coverage"],
        "rouge1": s["rouge1"],
        "best_judge": x["top"]["arm"],
        "best_judge_tau": x["top"]["score"],
        "best_free": max(local, key=lambda a: a["score"])["arm"],
        "best_free_tau": max(a["score"] for a in local),
        "gemma_l": s["gemma_l"],
        "qwen_s": s["qwen_s"],
    }


def goal_decisions(exps: list) -> None:
    """Each eval's goal decision, as the catalog computes it (tools/goal_decisions.py): the
    gold leader, the promoted baseline and its reason, the recommendation and its reasons, with
    arm ids shortened to the site's arm names. Added to each eval as `goal`."""
    rows = json.loads(
        subprocess.run(
            [sys.executable, str(HARNESS / "tools" / "goal_decisions.py")],
            capture_output=True,
            text=True,
            cwd=HARNESS,
            check=True,
        ).stdout
    )
    by_ds = {r["dataset"]: r for r in rows}
    for x in exps:
        r = by_ds.get(x["dataset"])
        if r is None:
            raise SystemExit(
                f"no goal decides on {x['dataset']}: the catalog has nothing to say for {x['slug']}"
            )

        def short(arm, x=x):
            config = (arm or "").rsplit("/", 1)[-1]
            return arm_of(x["prefix"], config) or config

        x["goal"] = {
            **r,
            "leader": short(r["leader"]),
            "baseline": short(r["baseline"]),
            "recommended": short(r["recommended"]) if r["recommended"] else None,
        }


def compute() -> dict:
    weights = _weights()
    exps = [eval_figures(e, weights) for e in EVALS]
    goal_decisions(exps)
    all_arms = sum(e["n_arms"] for e in exps)
    billed = sum(e["billed_total"] for e in exps)
    cal = calibration()
    claims = subprocess.run(
        [sys.executable, str(HARNESS / "tools" / "check_report_claims.py")],
        capture_output=True,
        text=True,
        cwd=HARNESS,
    ).stdout
    m = re.search(r"(\d+)/(\d+) claims verified", claims)
    if not m or m.group(1) != m.group(2):
        raise SystemExit("check_report_claims is not green; the site will not claim it is")
    return {
        "claims_checked": int(m.group(2)),
        "evals": exps,
        "total_arms": all_arms,
        "total_billed": billed,
        "dearest_never_best": sum(e["dearest"]["arm"] != e["top"]["arm"] for e in exps),
        # SciFact ran only the twelve cheapest hosted models, so its dearest arm is not a
        # frontier model; the headline stat counts only evals where one ran.
        "frontier_exps": sum(_has_frontier(e) for e in exps),
        "dearest_not_best_frontier": sum(
            _has_frontier(e) and e["dearest"]["arm"] != e["top"]["arm"] for e in exps
        ),
        "local_first_or_contender": sum(
            e["top"]["kind"] == "local"
            or any(a["kind"] == "local" for a in e["arms"] if a["arm"] in e["contenders"])
            for e in exps
        ),
        "calibration": cal,
        "calibration_consistent": sum(r["consistent"] for r in cal),
        "calibration_inside": sum(abs(r["delta"]) <= r["ci"] for r in cal),
        "dailymail": dailymail(),
        "hardware": hardware(),
        "remeasure": {
            "ag": adjudicated("ag-news", exps),
            "db": adjudicated("dbpedia", exps),
            "summ": judged_summarisation(exps),
            "summeval": instrument_check(exps),
            "summ_v2": judged_summarisation(exps, "judge-summ-v2"),
            "zhang": zhang_figures(),
            "validation_usd": validation_spend(),
        },
    }


def _has_frontier(e) -> bool:
    return any(a["arm"].startswith(("anthropic_", "openai_")) for a in e["arms"])


if __name__ == "__main__":
    f = compute()
    for e in f["evals"]:
        print(
            f"{e['bench']:14s} n={e['n_items']} arms={e['n_arms']} top={e['top']['arm']} "
            f"{e['top']['score']:.4f} dearest={e['dearest']['arm']} rank {e['dearest']['rank']}"
            f"/{e['n_arms']} contenders={e['n_contenders']} ({e['n_contenders_paid']} paid) cheapest_contender="
            f"{e['cheapest_contender']['arm'] if e['cheapest_contender'] else '-'} ${e['billed_total']:.2f}"
        )
    print(
        "total arms",
        f["total_arms"],
        "billed",
        round(f["total_billed"], 2),
        "dearest never best",
        f["dearest_never_best"],
        "| with frontier models",
        f["dearest_not_best_frontier"],
        "/",
        f["frontier_exps"],
        "calibration consistent",
        f["calibration_consistent"],
        "/",
        len(f["calibration"]),
    )
