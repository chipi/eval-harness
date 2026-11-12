"""The Workbench mockup's data, read from this project (never invented): the CNN goal, the project's measures,
datasets and models, the CNN dataset's source, items, reference highlights and profile, the goal's rounds, and its
arms on cnn_dailymail_200 with their scores, settings and first replies.

Two inputs are the harness's own printed answers, saved first (both slow to compute):

    evh models > build/models.txt
    evh goals --goal news_summary_cnn > build/goal_cnn.txt
    evh goals --goal triage_orrery > build/goal_triage.txt
    python workbench/read_sources.py                            (build/source_previews.json)
    evh pair-test --dataset-id cnn_dailymail_200 --a <arm> --b cnn_bart_l_n200_v1 --runs-dir data/runs-linux \
        --metric coverage, each local arm, after a "== <arm>" line   (build/pair_linux.txt)
    evh inspect --sheet --runs triage_baseline_pro_v2data_v1 --dataset-id orrery_triage_v1_labelled_v2 \
        --wrong-against gold_orrery_triage_v1_labelled_v2 --csv build/prod_wrong.csv --fill label
    evh label-sheet --dataset-id cnn_dailymail_200 --out build/label_sheet_cnn200.csv --items all
    python workbench/round5_inputs.py                          (build/round5/: round 5's screens, see that file)
    python workbench/mock_data.py > workbench/mock.js          (all from harness/)
"""

import csv
import json
import re
from pathlib import Path

import yaml

H = Path(__file__).resolve().parents[1]
D = H / "data"
EX = H.parent / "examples" / "summarization-cnn-dailymail"
N_ITEMS = 4


def table(lines: list[str], start: int) -> list[dict]:
    """The printed table whose header is at lines[start]: columns cut where the dashes line has its gaps."""
    head, dash = lines[start], lines[start + 1]
    spans = [m.span() for m in re.finditer(r"-+", dash)]
    names = [head[a:b].strip() for a, b in spans]
    rows = []
    for line in lines[start + 2 :]:
        if not line.strip():
            break
        cells = [
            line[a : (spans[i + 1][0] if i + 1 < len(spans) else len(line))].strip()
            for i, (a, _b) in enumerate(spans)
        ]
        rows.append(dict(zip(names, cells)))
    return rows


goal = yaml.safe_load((D / "goals" / "news_summary_cnn.yaml").read_text())
measures = sorted(
    {
        (yaml.safe_load(f.read_text()) or {}).get("success_criteria", {}).get("primary", {}).get("measure")
        for f in (D / "goals").glob("*.yaml")
        if f.name != "policy.yaml"
    }
    - {None}
    | {"coverage", "concision"}
)
datasets = []
for f in sorted((D / "datasets").glob("*.json")):
    doc = json.loads(f.read_text())
    datasets.append({"id": doc.get("dataset_id", f.stem), "items": len(doc.get("items") or [])})
rows = json.loads((D / "sources" / "cnn_dailymail_200.rows.json").read_text())
first = sorted(rows["rows"].items(), key=lambda kv: kv[1]["row"])[:N_ITEMS]
items = []
for iid, r in first:
    art = D / "materialized" / "cnn_dailymail_200" / f"{iid}.txt"
    ref = D / "references" / "gold" / "cnn_dailymail_200" / f"{iid}.txt"
    items.append(
        {
            "id": iid,
            "row": r["row"],
            "article": art.read_text()[:600].replace("\n", " ") if art.is_file() else None,
            "highlights": ref.read_text().replace("\n", " ") if ref.is_file() else None,
        }
    )
prof = json.loads((D / "profiles" / "cnn_dailymail_200.json").read_text())
words = prof["items"].get("words") or {}

# the models, as `evh models` prints them
mlines = (H / "build" / "models.txt").read_text().splitlines()
models = []
for r in table(mlines, next(i for i, x in enumerate(mlines) if x.strip().startswith("model "))):
    rank = re.search(r"news_summary_cnn #(\d+) of (\d+)", r.get("best result", ""))
    models.append(
        {
            "id": r["model"],
            "kind": r["kind"],
            "weights": r["weights"],
            "where": r["where"],
            "onboarding": r["onboarding"],
            "arms": int(r["arms"] or 0),
            "cnn_rank": int(rank.group(1)) if rank else None,
        }
    )

# the goal's arms on cnn_dailymail_200 (gold), as `evh goals --goal news_summary_cnn` prints them
glines = (H / "build" / "goal_cnn.txt").read_text().splitlines()
g0 = next(i for i, x in enumerate(glines) if "scored against gold/cnn_dailymail_200" in x)
arm_rows = [r for r in table(glines, g0 + 1) if "retired" not in r["arm"]]
rec = next(i for i, x in enumerate(glines) if x.strip().startswith("recommended:"))
detect = " ".join(x.strip() for x in glines[rec + 1 : rec + 4]).removeprefix("- ")
answer = " ".join(
    x.strip() for x in glines[glines.index("the answer so far:") + 2 : glines.index("the answer so far:") + 5]
)


def run_dir(config_id: str) -> Path:
    return sorted((D / "runs").glob(f"{config_id}_2*"))[0]


arms = []
for rank, r in enumerate(arm_rows, 1):
    cid = r["arm"].split(" ")[0]
    rd = run_dir(cid)
    met = json.loads((rd / "metrics.json").read_text())
    p = met["params"]
    outs = {o["item_id"]: o["text"] for o in map(json.loads, (rd / "outputs.jsonl").read_text().splitlines())}
    preds = {o["item_id"]: o for o in map(json.loads, (rd / "predictions.jsonl").read_text().splitlines())}
    vs = r["vs leader (paired test)"]
    m = re.match(r"(-?[\d.]+), p ([<\d.]+), (.*)", vs)
    speed = re.match(r"p50 ([\d,.]+)", r["speed per item"])
    arms.append(
        {
            "config_id": cid,
            "arm": cid.removeprefix("cnn_").removesuffix("_n200_v1"),
            "rank": rank,
            "coverage": float(r["mean coverage"]),
            "rouge1": float(r["rouge1"]),
            "delta": float(m.group(1)) if m else None,
            "p": m.group(2) if m else None,
            "verdict": m.group(3) if m else None,
            "baseline": "[baseline]" in r["arm"],
            "recommended": "[recommended]" in r["arm"],
            "usd_per_item": float(r["cost per item"].split(" ")[0].lstrip("$")),
            "p50_ms": float(speed.group(1).replace(",", "")) if speed else None,
            "total_usd": met["scores"].get("total_cost_usd"),
            "model": p.get("model") or p.get("model_id") or p.get("hf_model"),
            "family": p.get("family"),
            "tier": p.get("price_tier"),
            "temperature": p.get("temperature"),
            "max_tokens": p.get("max_tokens"),
            "prompt_file": p.get("prompt_file"),
            "provider": p.get("provider"),
            "run_id": met["run_id"],
            "created_at": met["created_at"],
            "replies": [
                {
                    "item": it["id"],
                    "text": (outs.get(it["id"]) or "")[:420],
                    "coverage": (preds.get(it["id"]) or {}).get("coverage"),
                    "cost_usd": (preds.get(it["id"]) or {}).get("cost_usd"),
                    "latency_ms": (preds.get(it["id"]) or {}).get("latency_ms"),
                }
                for it in items[:3]
            ],
        }
    )

rounds = []
for f in sorted((D / "rounds" / "news_summary_cnn").glob("r*.yaml")):
    rd = yaml.safe_load(f.read_text())
    rounds.append(
        {
            "id": rd["round_id"],
            "status": rd["status"],
            "question": rd["hypothesis"],
            "opened": rd.get("opened_at"),
            "closed": rd.get("closed_at"),
            "from": rd.get("from"),
            "retired": len(rd.get("retired") or []),
            "conclusion": (rd.get("conclusion") or {}).get("text"),
            "promoted": (rd.get("conclusion") or {}).get("promoted_run"),
        }
    )

# the home: every goal, where it stands
home = []
for f in sorted((D / "goals").glob("*.yaml")):
    if f.name == "policy.yaml":
        continue
    gd = yaml.safe_load(f.read_text())
    rs = [yaml.safe_load(x.read_text()) for x in sorted((D / "rounds" / f.stem).glob("r*.yaml"))]
    sc = gd.get("success_criteria") or {}
    home.append(
        {
            "id": gd["goal_id"],
            "title": gd.get("title"),
            "measure": sc.get("primary", {}).get("measure"),
            "direction": sc.get("primary", {}).get("direction"),
            "strategy": sc.get("strategy", "balanced"),
            "datasets": [x["dataset_id"] for x in gd.get("datasets") or []],
            "references": [x["reference_id"] for x in gd.get("references") or []],
            "rounds": len(rs),
            "open": [r["round_id"] for r in rs if r.get("status") == "open"],
            "last": rs[-1]["round_id"] if rs else None,
            "deployed": any(
                '"capture": "' in (D / "datasets" / f"{x['dataset_id']}.json").read_text()
                for x in gd.get("datasets") or []
                if (D / "datasets" / f"{x['dataset_id']}.json").is_file()
            ),
        }
    )


# W5: a model onboarded (pass) and one flagged (check), from their records
def record(mid: str) -> dict:
    r = yaml.safe_load((D / "models" / f"{mid}.yaml").read_text())
    return {
        "id": r["model_id"],
        "name": r.get("name"),
        "weights": r.get("weights"),
        "licence": r.get("licence"),
        "deployments": [
            {
                "id": d["id"],
                "where": d.get("where"),
                "endpoint": d.get("endpoint"),
                "onboarding": {
                    k: (d.get("onboarding") or {}).get(k) for k in ("status", "at", "flags", "report")
                },
            }
            for d in r.get("deployments") or []
        ],
        "settings": r.get("settings"),
        "settings_why": r.get("settings_why"),
        "accepted": (r.get("deployments") or [{}])[0].get("accepted"),
    }


onboard = {"pass": record("deepseek-4.1-flash"), "check": record("ministral-3-14b")}

# W6: the same arms scored against the silver reference, and who wrote it
s0 = next(i for i, x in enumerate(glines) if "scored against silver/cnn_dailymail_200" in x)
silver_rows = []
for k, r in enumerate(table(glines, s0 + 1), 1):
    m = re.match(r"(-?[\d.]+), p ([<\d.]+), (.*)", r["vs leader (paired test)"])
    silver_rows.append(
        {
            "arm": r["arm"].split(" ")[0].removeprefix("cnn_").removesuffix("_n200_v1"),
            "rank": k,
            "coverage": float(r["mean coverage"]),
            "verdict": m.group(3) if m else "leader",
            "p": m.group(2) if m else None,
        }
    )
sman = json.loads((D / "references" / "silver" / "cnn_dailymail_200" / "manifest.json").read_text())
silver = {
    "rows": silver_rows,
    "authored_by": sman["authored_by"].removeprefix("cnn_").removesuffix("_n200_v1"),
    "cost_usd": sman["from_run"]["cost_usd"],
    "caveat": sman["caveat"],
    "created_at": sman["created_at"],
}

# W7: the judge scorer and its validations
js = yaml.safe_load((D / "scorers" / "judge-summ-v2.yaml").read_text())
jv = {}
for src in ("goyal2022-cnn",):
    rep = json.loads((D / "judge-validation" / "judge-summ-v2" / src / "report.json").read_text())
    jv[src] = {
        "source": rep["source"],
        "articles": rep["articles"],
        "judges": {
            j: {k: v[k] for k in ("best_pick_agreement", "billed_usd") if k in v}
            | {
                "rate": v["best_pick_partial_credit"]["rate"],
                "ci95": v["best_pick_partial_credit"]["ci95"],
                "chance": v["best_pick_partial_credit"]["chance"],
            }
            for j, v in rep["judges"].items()
        },
    }
judge = {
    "id": js["scorer_id"],
    "judges": [
        {"id": j["id"], "model": j["params"]["model"], "family": j["params"]["family"]} for j in js["judges"]
    ],
    "protocol": js["protocol"],
    "cost_cap_usd": js["cost_cap_usd"],
    "prompt": js["prompt"]["file"],
    "validation": {
        "dataset": js["validation"]["dataset_id"],
        "metric": js["validation"]["metric"],
        "what": js["validation"]["what"],
        "runs": js["validation"]["runs"],
    },
    "checks": jv,
}

# W3: production on the deployed triage goal
cap = json.loads((D / "captures" / "orrery_2026_10_v2" / "capture.json").read_text())
tlines = (H / "build" / "goal_triage.txt").read_text().splitlines()
t0 = next(i for i, x in enumerate(tlines) if "scored against gold/orrery_triage_v1_labelled_v2" in x)
triage_rows = [
    {
        "arm": r["arm"].split(" ")[0],
        "triage_cost": float(r["mean triage_cost"]),
        "vs": r["vs leader (paired test)"],
        "usd_per_item": r["cost per item"].split(" ")[0],
    }
    for r in table(tlines, t0 + 1)
]
production = {
    "goal": "triage_orrery",
    "title": tlines[0],
    "capture": cap["capture_id"],
    "captured_at": cap["captured_at"],
    "records": cap["n_records"],
    "first": cap["records"][0]["created_at"],
    "last": max(r["created_at"] for r in cap["records"]),
    "dataset": "orrery_triage_v1_labelled_v2",
    "rows": triage_rows,
    "labels": sorted(p.name for p in (D / "labels" / "orrery_triage_v1_labelled").iterdir()),
    "decides": "triage_cost, lower is better",
}

# W2: the failure modes proposed from the CNN adapter's own format checks
src = (EX / "adapter.py").read_text()
modes = []
for key in (
    "fmt_narration",
    "fmt_label",
    "fmt_markdown",
    "fmt_bullets",
    "fmt_paragraphs",
    "fmt_overlong",
    "truncated",
):
    m = re.findall(rf'^\s*"{key}":\s*((?:"(?:[^"\\]|\\.)*"\s*)+),', src, re.M | re.S)[-1]
    text = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m)).replace('\\"', '"')
    modes.append({"id": key.removeprefix("fmt_"), "description": text})

# the other sources as they answered (workbench/read_sources.py)
sources = json.loads((H / "build" / "source_previews.json").read_text())

# a round's own runs: the local arms re-run on one Linux machine, and the paired test against bart_l re-run there
pairs, cur = {}, None
for line in (H / "build" / "pair_linux.txt").read_text().splitlines():
    if line.startswith("== "):
        cur = line[3:].strip()
    elif cur and "delta (A - B)" in line:
        pairs.setdefault(cur, {})["delta"] = float(line.split()[-1])
    elif cur and "sign-flip p" in line:
        pairs.setdefault(cur, {})["p"] = line.split("sign-flip p")[1].split("(")[0].strip()
reruns = {}
for rd in sorted((D / "runs-linux").glob("cnn_*")):
    met = json.loads((rd / "metrics.json").read_text())
    lat = sorted(
        o.get("latency_ms") or 0 for o in map(json.loads, (rd / "predictions.jsonl").read_text().splitlines())
    )
    reruns[met["config_id"]] = {
        "run_id": met["run_id"],
        "coverage": round(met["scores"]["coverage"], 4),
        "p50_ms": lat[len(lat) // 2],
        "created_at": met["created_at"],
        **pairs.get(met["config_id"], {}),
    }

# production's wrong decisions: `evh inspect --sheet --wrong-against` (build/prod_wrong.csv)
with (H / "build" / "prod_wrong.csv").open(encoding="utf-8-sig", newline="") as fh:
    wrong_rows = list(csv.DictReader(fh))
prod_arm = "triage_baseline_pro_v2data_v1"
wrong = [
    {
        "id": r["item_id"],
        "decided": r[prod_arm],
        "people": r["label: gold_orrery_triage_v1_labelled_v2 (person · owner)"],
        "cost": r[f"{prod_arm}: triage_cost"],
        "date": r.get("field: decision_date"),
        "stage": r.get("field: stage"),
    }
    for r in wrong_rows
]

# the label sheet `evh label-sheet --dataset-id cnn_dailymail_200 --items all` writes
sheet = (H / "build" / "label_sheet_cnn200.csv").read_text(encoding="utf-8-sig")


def r5(name: str) -> dict:
    """A round-5 input's values (a command's --json answer, saved by round5_inputs.py)."""
    doc = json.loads((H / "build" / "round5" / f"{name}.json").read_text())
    return (doc.get("result") or {}).get("values") or doc


def r5_lines(name: str) -> list[str]:
    doc = json.loads((H / "build" / "round5" / f"{name}.json").read_text())
    return [x for b in (doc.get("result") or {}).get("blocks") or [] for x in b.get("lines") or []]


replay_runs = json.loads((H / "build" / "round5" / "replay_runs.json").read_text())
label_doc = json.loads((H / "build" / "round5" / "label_set_doc.json").read_text())
code_rows = [
    row
    for b in json.loads((H / "build" / "round5" / "models_code.json").read_text())["result"]["blocks"]
    for row in b.get("rows") or []
    if row.get("kind") == "code"
]
this_baselines = json.loads((H / "build" / "round5" / "baselines.json").read_text())["baselines"]
cnn_base = next((b for b in this_baselines if b.get("goal") == "news_summary_cnn"), None)
round5 = {
    "baseline": {
        k: cnn_base.get(k)
        for k in (
            "goal",
            "dataset",
            "current",
            "promoted_from",
            "promoted_at",
            "reason",
            "actor",
            "history",
            "migrated",
        )
    }
    if cnn_base
    else None,
    "baselines": len(this_baselines),
    "study": r5("study").get("study"),
    "confirm": r5("study_confirm").get("confirm"),
    "looks": r5("looks").get("sets"),
    "prompts": r5("prompts").get("prompts"),
    "jobs": r5("jobs").get("jobs"),
    "job_started": r5("job_start").get("job"),  # the job as started: its cap and the locks it holds
    "sealed_counts": r5("sealed_counts"),
    "exposure": (r5("exposure").get("exposure") or [None])[0],
    "exposure_check": r5("exposure_check"),
    "unseal": r5_lines("unseal"),
    "heldout_pair": {
        k: r5("heldout_pair").get(k)
        for k in (
            "a",
            "b",
            "metric",
            "n",
            "delta",
            "p",
            "verdict",
            "left_out_exposed",
            "with_exposed",
            "look",
        )
    },
    "faithfulness": {
        k: (r5("faithfulness").get("faithfulness") or {}).get(k)
        for k in ("n", "counts", "commits", "adapter", "coverage")
    },
    "replay_scores": {
        "replay": (replay_runs["replay_metrics"].get("scores") or {}).get("exact"),
        "candidate": (replay_runs["candidate_metrics"].get("scores") or {}).get("exact"),
        "confound": replay_runs["candidate_metrics"].get("history_confound"),
        "replay_confound": replay_runs["replay_metrics"].get("history_confound"),
    },
    "periods": r5("periods").get("periods"),
    "period_compare": [r5(f"period_compare_{n}") for n in (1, 2, 3)],
    "code_records": code_rows,
    "label_coverage": {k: r5("label_coverage").get(k) for k in ("counts", "rules", "by_item", "captured_at")},
    "label_set": {
        "source": label_doc.get("source"),
        # the label texts are files beside labels.json; label-coverage's answer names each labelled item's label
        "items": {
            i: {
                **row,
                "label": " | ".join(
                    next(
                        (x.get("label") or [] for x in r5("label_coverage")["by_item"] if x["item_id"] == i),
                        [],
                    )
                ),
            }
            for i, row in (label_doc.get("items") or {}).items()
        },
        "gone": label_doc.get("gone"),
    },
    "label_mutants": r5("label_mutants"),
}

out = {
    "goal": {k: goal.get(k) for k in ("goal_id", "title", "statement", "decision")}
    | {
        "measure": goal["success_criteria"]["primary"]["measure"],
        "direction": goal["success_criteria"]["primary"]["direction"],
        "strategy": goal["success_criteria"].get("strategy", "balanced"),
    },
    "measures": measures,
    "goals": sorted(f.stem for f in (D / "goals").glob("*.yaml") if f.name != "policy.yaml"),
    "datasets": datasets,
    "source": rows["source"]
    | {
        "rows": len(rows["rows"]),
        "licence": json.loads((D / "datasets" / "cnn_dailymail_200.json").read_text()).get("licence"),
        "split_rows": json.loads(
            (H.parent / "docs" / "evidence" / "calibration" / "summarization.json").read_text()
        )["split_rows"],
    },
    "items": items,
    "profile": {
        "n": prof["items"]["n"],
        "words": {k: words.get(k) for k in ("min", "p25", "median", "p75", "max") if k in words},
        "reference": {
            "id": prof["references"][0]["id"],
            "items": prof["references"][0]["items"],
            "words": prof["references"][0]["words"],
        },
        "items_sha256": prof["items_sha256"],
        "histogram": words.get("histogram") or [],
    },
    "models": models,
    "prompt": (EX / "prompt.txt").read_text().strip(),
    "arms": arms,
    "rounds": rounds,
    "answer": answer,
    "detectable": detect,
    "home": home,
    "onboard": onboard,
    "silver": silver,
    "judge": judge,
    "production": production,
    "modes": modes,
    "axes": goal["success_criteria"].get("axes") or {},
    "sources": sources,
    "reruns": reruns,
    "wrong": wrong,
    "sheet": sheet,
    "round5": round5,
}
print("// The Workbench mockup's data, read from this project by its extractor (never invented).")
print("window.MOCK = " + json.dumps(out, indent=1, ensure_ascii=False) + ";")
