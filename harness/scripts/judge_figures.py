#!/usr/bin/env python3
"""Every number the summarisation report states about the judge re-measurement, recomputed
from what is committed: the judging-set manifest, the stored verdicts, the committed runs
(for which arms are hosted) and the human-check record. data/runs-judged is gitignored and
is not read. The Goyal et al. comparison is recomputed from the stored per-article records
plus the human data when data/external/goyal2022 is present; otherwise it falls back to the
committed report.json and says so in `goyal_source`.

    python scripts/judge_figures.py          # print the figures as JSON
    python scripts/check_report_claims.py --print-judge-figures
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_score as js  # noqa: E402
import validate_judge_goyal as vg  # noqa: E402
import validate_judge_zhang as vz  # noqa: E402

REPO = HERE.parents[1]
DATA = HERE.parent / "data"
SCORER = "judge-summ-v1"
SET_GLOB = "cnn_dailymail_200-29arms-*.json"


def _range(xs):
    xs = list(xs)
    return [round(min(xs), 4), round(max(xs), 4)]


def goyal(scorer: str = SCORER) -> Dict[str, Any]:
    vroot = DATA / "judge-validation" / scorer / "goyal2022-cnn"
    jids = [j["id"] for j in js.load_scorer(DATA / "scorers" / f"{scorer}.yaml")["judges"]]
    human = vg.load_local()
    if human is None:
        rep = json.loads((vroot / "report.json").read_text())
        return {"source": "report.json (data/external/goyal2022 absent: not recomputed)",
                "judges": rep["judges"], "human_baseline": rep["human_baseline"]}
    out: Dict[str, Any] = {"source": "recomputed from the stored per-article records and the "
                                     "human annotations", "judges": {}}
    for jid in jids:
        st = vg.judge_stats(human, vg.read_records(vroot / jid, human))
        st["human_gpt3_over_brio"] = sum(vg.human_prefs(v["annotators"])[1] for v in human.values())
        st["human_brio_over_gpt3"] = sum(vg.human_prefs(v["annotators"])[2] for v in human.values())
        out["judges"][jid] = st
    out["human_baseline"] = vg.human_baseline(human)
    return out


def zhang(scorer: str = SCORER) -> Dict[str, Any]:
    """The Zhang et al. (2024) validation of a scorer's judges. Recomputed from the stored
    records when data/external/zhang2023 is present; otherwise the committed report.json,
    whose call counts and bill are checked against the committed records."""
    vroot = DATA / "judge-validation" / scorer / "zhang2023-cnndm"
    if vz.FILE.is_file():
        sc = js.load_scorer(DATA / "scorers" / f"{scorer}.yaml")
        data = vz.load()
        systems = sorted(next(iter(data.values()))["systems"])
        rep = vz.build_report(sc, js.prompt_text(sc), int(sc["protocol"]["outputs_per_call"]),
                              data, systems, vroot)
        rep["recomputed"] = "from the stored records and the ratings"
        return rep
    rep = json.loads((vroot / "report.json").read_text())
    for jid, r in rep["judges"].items():
        recs = [json.loads(f.read_text()) for f in (vroot / jid).glob("*.json")]
        if len(recs) != r["calls"] or round(sum(float(x.get("cost_usd") or 0) for x in recs), 4) != r["billed_usd"]:
            raise SystemExit(f"{vroot}/report.json disagrees with the stored records of {jid}")
    rep["recomputed"] = "report.json (data/external/zhang2023 absent: checked against the records only)"
    return rep


def pointwise() -> Dict[str, int]:
    man = sorted((DATA / "judging-sets").glob("cnn_dailymail_200-2arms-*.json"))
    assert len(man) == 1, man
    m = json.loads(man[0].read_text())
    per: Dict[str, Dict[str, list]] = {}
    for f in (DATA / "judge-verdicts" / "judge-summ-pointwise-v1" / m["judging_set_id"]).glob("*/*.json"):
        v = json.loads(f.read_text())
        if v.get("pass") != "primary" or v.get("scores") is None:
            continue
        it = next(x for x in m["items"] if x["item_id"] == v["item_id"])
        per.setdefault(v["item_id"], {}).setdefault(it["primary"][v["block"]][0], []).append(v["scores"][0])
    hi = lo = 0
    for a in per.values():
        b, d = a.get("cnn_bart_l_n200_v1"), a.get("cnn_deepseek_m_n200_v1")
        if b and d and len(b) == len(d) == 2:
            hi += sum(d) > sum(b)
            lo += sum(d) < sum(b)
    return {"deepseek_m_above_bart_l": hi, "deepseek_m_below_bart_l": lo, "articles": len(per)}


def compute(scorer: str = SCORER) -> Dict[str, Any]:
    sets = sorted((DATA / "judging-sets").glob(SET_GLOB))
    if len(sets) != 1:
        raise SystemExit(f"expected exactly one {SET_GLOB} in data/judging-sets, found "
                         f"{[p.name for p in sets]}")
    m = json.loads(sets[0].read_text())
    if len(m["arms"]) != 29:
        raise SystemExit(f"{sets[0].name} has {len(m['arms'])} arms, not 29")
    sc = js.load_scorer(DATA / "scorers" / f"{scorer}.yaml")
    vdir = DATA / "judge-verdicts" / scorer / m["judging_set_id"]
    item_ids = [i["item_id"] for i in m["items"]]
    scores = js.load_scores(m, sc, vdir)
    proj = js.project(sc, scores, item_ids)
    summ = js.summarise(m, sc, m["arms"], scores, proj, {}, "recomputed", True, vdir)

    files = [json.loads(f.read_text()) for f in vdir.glob("*/*.json")]
    hosted = []
    for a in m["arms"]:
        met = json.loads((DATA / "runs" / a["run"] / "metrics.json").read_text())
        if (met.get("params") or {}).get("provider") == "litellm":
            hosted.append(a["config_id"])
    pa = summ["per_arm"]
    hscores = [pa[c]["judge_score"] for c in hosted]
    hc = json.loads((REPO / "examples" / "summarization-cnn-dailymail" / "human_check_judge.json").read_text())
    h_bart = sum(x["preferred"] == "bart_l" for x in hc["pairs"])
    h_ds = sum(x["preferred"] == "deepseek_m" for x in hc["pairs"])
    j_ds = sum(proj[x["item_id"]]["cnn_deepseek_m_n200_v1"]["_mean"]
               > proj[x["item_id"]]["cnn_bart_l_n200_v1"]["_mean"] for x in hc["pairs"] if x["item_id"] in proj)
    n_pairs_judged = sum(1 for x in hc["pairs"] if x["item_id"] in proj)
    agr = next(iter(summ["judge_agreement"].values()))
    pos = [summ["controls"][j]["position"]["mean_abs_diff"] for j in summ["controls"]]
    noi = [summ["controls"][j]["noise"]["mean_abs_diff"] for j in summ["controls"]]
    return {
        "judging_set_id": m["judging_set_id"], "arms": len(m["arms"]), "hosted_arms": len(hosted),
        "calls": len(files), "billed_usd": round(sum(f.get("cost_usd") or 0.0 for f in files), 4),
        "items_total": len(item_ids), "items_scored": len(proj),
        "bart_l_judge_score": round(pa["cnn_bart_l_n200_v1"]["judge_score"], 4),
        "hosted_judge_score_range": _range(hscores),
        "hosted_all_above_every_bart": min(hscores) > max(
            pa[c]["judge_score"] for c in pa if "bart" in c),
        "hosted_leader": max(hosted, key=lambda c: pa[c]["judge_score"]),
        "agreement_arm_mean_spearman": round(agr["arm_mean_spearman"], 4),
        "agreement_mean_item_tau": round(agr["mean_item_tau"], 4),
        "position_mean_abs_diff_range": _range(pos), "noise_mean_abs_diff_range": _range(noi),
        "position_mean_tau": [summ["controls"][j]["position"]["mean_tau"] for j in summ["controls"]],
        "noise_mean_tau": [summ["controls"][j]["noise"]["mean_tau"] for j in summ["controls"]],
        "human_check": {"pairs": len(hc["pairs"]), "human_prefers_bart_l": h_bart,
                        "human_prefers_deepseek_m": h_ds,
                        "pairs_with_judge_scores": n_pairs_judged, "judge_prefers_deepseek_m": j_ds},
        "pointwise": pointwise(), "goyal": goyal(scorer),
    }


if __name__ == "__main__":
    print(json.dumps(compute(), indent=1, default=lambda o: None if isinstance(o, float) and math.isnan(o) else str(o)))
