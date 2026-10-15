"""Time each SciFact first-stage arm's one-off index build, uncached, through the adapter's own
warmup() -- the code path the harness records as warmup_ms -- with the model revisions the runs
measured (examples/local_models.json). Prints one JSON line per arm; warmup() writes each index
cache as a real run would.

Move harness/data/corpora/scifact/.index aside first, or every dense arm loads its cache in
seconds. Run from examples/retrieval-scifact with that example's venv:
    .venv/bin/python ../../docs/evidence/index_build_times.py bm25 minilm bge_small mpnet e5_base
"""
import json, sys, time, yaml
from pathlib import Path
sys.path.insert(0, ".")
import adapter
pins = json.load(open("../local_models.json"))["revisions"]  # the revisions the runs measured
for arm in sys.argv[1:]:
    p = yaml.safe_load(open(f"configs/arm_{arm}_n200.yaml"))["params"]
    rev = pins.get(p.get("model", ""))
    if isinstance(rev, dict):
        rev = rev.get("revision")
    if rev and p.get("provider") == "dense":
        p["revision"] = rev
    t = time.perf_counter(); adapter.warmup(p); s = time.perf_counter() - t
    print(json.dumps({"arm": arm, "model": p.get("model", "bm25"), "revision": p.get("revision"),
                      "build_s": round(s, 1)}), flush=True)
