#!/usr/bin/env python3
"""The de-duplication example's checks: deterministic, and a changed key function is caught.

    TRIAGE_FLEET_SRC=/path/to/signal-fleet python examples/signal-fleet-dedup/test_dedup.py

Needs the fleet's code (TRIAGE_FLEET_SRC) and the fetched signals (fetch.py); skipped without either.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / "harness"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import adapter  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SIGNALS = ROOT / "data" / "sources" / "fleet_dedup_v1.hf" / "signals.jsonl"
SRC = os.environ.get("TRIAGE_FLEET_SRC", "")

check(
    "score: the same key and flags match",
    adapter.score('{"norm_key":"a","test":false}', '{"norm_key":"a","test":false}')
    == {"key_match": 1.0, "class_match": 1.0},
)
check(
    "score: another key does not", adapter.score('{"norm_key":"b"}', '{"norm_key":"a"}')["key_match"] == 0.0
)
check("score: no reference, nothing scored", adapter.score('{"norm_key":"a"}', None) == {})

if not SRC or not (Path(SRC) / "mvp" / "filing.py").is_file() or not SIGNALS.is_file():
    print("  --   the fleet's functions: skipped (needs TRIAGE_FLEET_SRC and fetch.py's signals)")
    sys.exit(summary())

RUN = """
import json, sys
sys.path.insert(0, sys.argv[1])
import adapter
rows = [json.loads(x) for x in open(sys.argv[2]) if x.strip()]
print(json.dumps([adapter.classify(r) for r in rows], sort_keys=True))
"""


def answers(src: str) -> list:
    """The filing stage's answers for every signal, from the fleet's code at `src` (a fresh process)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(RUN)
    try:
        out = subprocess.run(
            [sys.executable, f.name, str(HERE), str(SIGNALS)],
            env={**os.environ, "TRIAGE_FLEET_SRC": src},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    finally:
        os.unlink(f.name)
    return json.loads(out)


a, b = answers(SRC), answers(SRC)
check("the fleet's functions: 100 signals answered", len(a) == 100, len(a))
check("deterministic: two runs give the same answers", a == b)
check("the corpus de-duplicates: fewer keys than signals", len({x["norm_key"] for x in a}) < len(a))
with tempfile.TemporaryDirectory() as td:
    planted = Path(td) / "signal-fleet"
    shutil.copytree(SRC, planted, ignore=shutil.ignore_patterns("__pycache__"))
    f = planted / "mvp" / "filing.py"
    s = f.read_text()
    marker = "def normalized_key(signal, event_summary=None):"
    check("setup: the fleet's normalized_key is where the test expects it", marker in s)
    f.write_text(s.replace(marker, marker + "\n    return 'planted:' + str(signal.get('alertname'))\n", 1))
    c = answers(str(planted))
matched = sum(x["norm_key"] == y["norm_key"] for x, y in zip(a, c))
check(
    "a planted change to normalized_key is caught: key_match below 1", matched < len(a), f"{matched}/{len(a)}"
)
sys.exit(summary())
