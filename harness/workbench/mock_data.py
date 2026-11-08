"""The Workbench mockup's data, read from this project (never invented): the CNN goal, the project's measures,
datasets and models, the CNN dataset's source, items, reference highlights and profile, the goal's rounds, and its
arms on cnn_dailymail_200 with their scores, settings and first replies.

Two inputs are the harness's own printed answers, saved first (both slow to compute):

    evh models > build/models.txt
    evh goals --goal news_summary_cnn > build/goal_cnn.txt
    python workbench/mock_data.py > workbench/mock.js          (all from harness/)
"""

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
    for line in lines[start + 2:]:
        if not line.strip():
            break
        cells = [line[a:(spans[i + 1][0] if i + 1 < len(spans) else len(line))].strip() for i, (a, _b) in enumerate(spans)]
        rows.append(dict(zip(names, cells)))
    return rows


goal = yaml.safe_load((D / "goals" / "news_summary_cnn.yaml").read_text())
measures = sorted({
    (yaml.safe_load(f.read_text()) or {}).get("success_criteria", {}).get("primary", {}).get("measure")
    for f in (D / "goals").glob("*.yaml") if f.name != "policy.yaml"
} - {None} | {"coverage", "concision"})
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
    items.append({
        "id": iid, "row": r["row"],
        "article": art.read_text()[:600].replace("\n", " ") if art.is_file() else None,
        "highlights": ref.read_text().replace("\n", " ") if ref.is_file() else None,
    })
prof = json.loads((D / "profiles" / "cnn_dailymail_200.json").read_text())
words = prof["items"].get("words") or {}

# the models, as `evh models` prints them
mlines = (H / "build" / "models.txt").read_text().splitlines()
models = []
for r in table(mlines, next(i for i, x in enumerate(mlines) if x.strip().startswith("model "))):
    rank = re.search(r"news_summary_cnn #(\d+) of (\d+)", r.get("best result", ""))
    models.append({"id": r["model"], "kind": r["kind"], "weights": r["weights"], "where": r["where"],
                   "onboarding": r["onboarding"], "arms": int(r["arms"] or 0),
                   "cnn_rank": int(rank.group(1)) if rank else None})

# the goal's arms on cnn_dailymail_200 (gold), as `evh goals --goal news_summary_cnn` prints them
glines = (H / "build" / "goal_cnn.txt").read_text().splitlines()
g0 = next(i for i, x in enumerate(glines) if "scored against gold/cnn_dailymail_200" in x)
arm_rows = [r for r in table(glines, g0 + 1) if "retired" not in r["arm"]]
rec = next(i for i, x in enumerate(glines) if x.strip().startswith("recommended:"))
detect = " ".join(x.strip() for x in glines[rec + 1:rec + 4]).removeprefix("- ")
answer = " ".join(x.strip() for x in glines[glines.index("the answer so far:") + 2:glines.index("the answer so far:") + 5])


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
    arms.append({
        "config_id": cid, "arm": cid.removeprefix("cnn_").removesuffix("_n200_v1"), "rank": rank,
        "coverage": float(r["mean coverage"]), "rouge1": float(r["rouge1"]),
        "delta": float(m.group(1)) if m else None, "p": m.group(2) if m else None, "verdict": m.group(3) if m else None,
        "baseline": "[baseline]" in r["arm"], "recommended": "[recommended]" in r["arm"],
        "usd_per_item": float(r["cost per item"].split(" ")[0].lstrip("$")),
        "p50_ms": float(speed.group(1).replace(",", "")) if speed else None,
        "total_usd": met["scores"].get("total_cost_usd"),
        "model": p.get("model") or p.get("model_id") or p.get("hf_model"), "family": p.get("family"), "tier": p.get("price_tier"),
        "temperature": p.get("temperature"), "max_tokens": p.get("max_tokens"), "prompt_file": p.get("prompt_file"),
        "provider": p.get("provider"), "run_id": met["run_id"], "created_at": met["created_at"],
        "replies": [{"item": it["id"], "text": (outs.get(it["id"]) or "")[:420],
                     "coverage": (preds.get(it["id"]) or {}).get("coverage"),
                     "cost_usd": (preds.get(it["id"]) or {}).get("cost_usd"),
                     "latency_ms": (preds.get(it["id"]) or {}).get("latency_ms")} for it in items[:3]],
    })

rounds = []
for f in sorted((D / "rounds" / "news_summary_cnn").glob("r*.yaml")):
    rd = yaml.safe_load(f.read_text())
    rounds.append({"id": rd["round_id"], "status": rd["status"], "question": rd["hypothesis"],
                   "opened": rd.get("opened_at"), "closed": rd.get("closed_at"), "from": rd.get("from"),
                   "retired": len(rd.get("retired") or []), "conclusion": (rd.get("conclusion") or {}).get("text"),
                   "promoted": (rd.get("conclusion") or {}).get("promoted_run")})

out = {
    "goal": {k: goal.get(k) for k in ("goal_id", "title", "statement", "decision")}
    | {"measure": goal["success_criteria"]["primary"]["measure"],
       "direction": goal["success_criteria"]["primary"]["direction"],
       "strategy": goal["success_criteria"].get("strategy", "balanced")},
    "measures": measures,
    "goals": sorted(f.stem for f in (D / "goals").glob("*.yaml") if f.name != "policy.yaml"),
    "datasets": datasets,
    "source": rows["source"] | {"rows": len(rows["rows"]), "licence": json.loads((D / "datasets" / "cnn_dailymail_200.json").read_text()).get("licence"),
               "split_rows": json.loads((H.parent / "docs" / "evidence" / "calibration" / "summarization.json").read_text())["split_rows"]},
    "items": items,
    "profile": {"n": prof["items"]["n"], "words": {k: words.get(k) for k in ("min", "p25", "median", "p75", "max") if k in words},
                "reference": {"id": prof["references"][0]["id"], "items": prof["references"][0]["items"],
                              "words": prof["references"][0]["words"]},
                "items_sha256": prof["items_sha256"], "histogram": words.get("histogram") or []},
    "models": models,
    "prompt": (EX / "prompt.txt").read_text().strip(),
    "arms": arms,
    "rounds": rounds,
    "answer": answer,
    "detectable": detect,
}
print("// The Workbench mockup's data, read from this project by its extractor (never invented).")
print("window.MOCK = " + json.dumps(out, indent=1, ensure_ascii=False) + ";")
