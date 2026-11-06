"""The Workbench mockup's data, read from this project (never invented): the CNN goal, the project's measures and
datasets, the CNN dataset's source, its first items with their reference highlights, and its profile.

    python workbench/mock_data.py > workbench/mock.js   (from harness/)
"""

import json
import statistics
from pathlib import Path

import yaml

D = Path("/work/eval-harness/worktrees/080/harness/data")
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
first = sorted(rows["rows"].items(), key=lambda kv: kv[1]["row"])[:4]
items = []
for iid, r in first:
    art = (D / "materialized" / "cnn_dailymail_200" / f"{iid}.txt")
    ref = (D / "references" / "gold" / "cnn_dailymail_200" / f"{iid}.txt")
    items.append({
        "id": iid, "row": r["row"],
        "article": art.read_text()[:600].replace("\n", " ") if art.is_file() else None,
        "highlights": ref.read_text().replace("\n", " ") if ref.is_file() else None,
    })
prof = json.loads((D / "profiles" / "cnn_dailymail_200.json").read_text())
words = prof["items"].get("words") or {}
hist = words.get("histogram") or []
out = {
    "goal": {k: goal.get(k) for k in ("goal_id", "title", "statement", "decision")}
    | {"measure": goal["success_criteria"]["primary"]["measure"],
       "direction": goal["success_criteria"]["primary"]["direction"],
       "strategy": goal["success_criteria"].get("strategy", "balanced")},
    "measures": measures,
    "goals": sorted(f.stem for f in (D / "goals").glob("*.yaml") if f.name != "policy.yaml"),
    "datasets": datasets,
    "source": rows["source"] | {"rows": len(rows["rows"]), "licence": json.loads((D / "datasets" / "cnn_dailymail_200.json").read_text()).get("licence"),
               "split_rows": json.loads((D.parent.parent / "docs" / "evidence" / "calibration" / "summarization.json").read_text())["split_rows"]},
    "items": items,
    "profile": {"n": prof["items"]["n"], "words": {k: words.get(k) for k in ("min", "p25", "median", "p75", "max") if k in words},
                "reference": {"id": prof["references"][0]["id"], "items": prof["references"][0]["items"],
                              "words": prof["references"][0]["words"]},
                "items_sha256": prof["items_sha256"],
                "histogram": hist},
}
print("// The Workbench mockup's data, read from this project by its extractor (never invented).")
print("window.MOCK = " + json.dumps(out, indent=1, ensure_ascii=False) + ";")
