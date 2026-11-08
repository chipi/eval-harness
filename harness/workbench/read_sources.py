"""Read each dataset source the way `evh dataset-create --source NAME` would, with the example its module documents,
and keep what it describes and its first rows for the Workbench mockup: build/source_previews.json (a source read before with the same
query is kept, so a run retries only what failed). Nothing is written to the project.

    python workbench/read_sources.py          (from harness/; Zenodo, OpenML and Kaggle are read over the network)
"""

import itertools
import json
import sys
from pathlib import Path

H = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(H))

from evaluation_harness import _sources  # noqa: E402

QUERIES = {
    "folder": {"path": "data/sources/cnn_dailymail_20", "glob": "*.txt"},
    "zenodo": {"record": 10157504, "file": "sts_gold_tweet.csv", "text": "tweet", "id": "id", "fields": ["polarity"], "limit": 4},
    "openml": {"dataset": 61, "text": "class", "fields": ["sepallength"], "limit": 4},
    "kaggle": {"ref": "uciml/iris", "version": 2, "file": "Iris.csv", "text": "Species", "fields": ["SepalLengthCm"], "limit": 4},
    "croissant": {"path": "build/cnn_dailymail_20.croissant.json", "text": "text", "id": "item_id", "limit": 4},
}

KEPT = H / "build" / "source_previews.json"
out = json.loads(KEPT.read_text()) if KEPT.is_file() else {}
for name, query in QUERIES.items():
    if out.get(name, {}).get("rows") and out[name].get("query") == query:
        print(name, "kept from the last read")
        continue
    try:
        cls, _file = _sources.resolve(name)
        src = cls({})
        desc = src.describe(query)
        rows = []
        for it in itertools.islice(src.items(query), 4):
            text = it.get("text")
            if text is None and it.get("file"):
                text = Path(it["file"]).read_text(errors="replace")
            rows.append({"id": str(it.get("item_id")), "text": str(text or "")[:240], "fields": it.get("fields") or {}})
        out[name] = {"query": query, "describe": json.loads(json.dumps(desc, default=str)), "rows": rows}
        print(name, "ok", len(rows))
    except Exception as e:  # the mockup says what the source answered, whatever it was
        out[name] = {"query": query, "error": f"{type(e).__name__}: {e}"}
        print(name, "error", type(e).__name__, str(e)[:200])
KEPT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
