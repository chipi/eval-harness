#!/usr/bin/env python3
"""Prove the instrument before scoring any model: every canonical solution must pass, and a
function that returns None must fail.

    examples/code-mbpp-plus/.venv/bin/python examples/code-mbpp-plus/canonical_check.py

Three things are checked through exactly the path a model's reply takes (extract, sanitise,
sandboxed base and plus execution -- adapter.score), on every task:
  1. the canonical solution passes base AND plus      -> the tests, the sandbox and the
                                                        sanitiser agree with the dataset
  2. a stub returning None fails base                 -> no test is vacuous
  3. the slowest execution fits well inside the limits -> a timeout means slow code, not a
                                                        slow machine
It writes canonical_check.json beside this file: the evidence behind the timeouts in
adapter.py and the sandbox row of the report.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter  # noqa: E402
import sandbox  # noqa: E402

ROOT = HERE.parents[1] / "harness"


def _check(path: Path) -> dict:
    gold_text = path.read_text(encoding="utf-8")
    gold = json.loads(gold_text)
    started = time.perf_counter()
    right = adapter.score(f"```python\n{gold['canonical']}\n```", gold_text)
    took = time.perf_counter() - started
    stub = f"```python\ndef {gold['entry_point']}(*args, **kwargs):\n    return None\n```"
    wrong = adapter.score(stub, gold_text)
    return {"item": path.stem, "canonical": right, "stub": wrong, "seconds": round(took, 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", default="mbppplus_378")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel executions (1 for honest timings)")
    args = ap.parse_args()
    golds = sorted((ROOT / "data" / "references" / "gold" / args.dataset_id).glob("*.txt"))
    if not golds:
        sys.exit(f"no gold for {args.dataset_id} -- run examples/code-mbpp-plus/fetch.py first")
    probe = sandbox.probe(sentinel_dir=HERE)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_check, golds))
    fails = [r["item"] for r in rows if r["canonical"]["pass_plus"] != 1.0]
    vacuous = [r["item"] for r in rows if r["stub"]["pass_base"] != 0.0]
    slow = sorted(rows, key=lambda r: -r["seconds"])[:5]
    report = {
        "dataset_id": args.dataset_id, "tasks": len(rows),
        "canonical_pass_plus": sum(r["canonical"]["pass_plus"] for r in rows),
        "canonical_failures": fails, "stub_passes_base": vacuous,
        "slowest_seconds": [{"item": r["item"], "seconds": r["seconds"]} for r in slow],
        "limits_s": {"base": adapter.BASE_TIMEOUT_S, "plus": adapter.PLUS_TIMEOUT_S},
        "sandbox": sandbox.backend(), "probe": probe, "workers": args.workers,
        "machine": f"{platform.system()} {platform.machine()}, python {platform.python_version()}",
        "scorer_sha256": adapter.scorer_sha256(),
    }
    (HERE / "canonical_check.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"canonical solutions passing base+plus: {report['canonical_pass_plus']:.0f}/{len(rows)}")
    print(f"stubs passing base (vacuous tests):   {len(vacuous)}")
    print(f"slowest (canonical, base+plus):       {slow[0]['seconds']}s  ({slow[0]['item']})")
    for item in fails:
        r = next(x for x in rows if x["item"] == item)
        print(f"  FAIL {item}: {r['canonical']}")
    return 0 if not fails and not vacuous else 1


if __name__ == "__main__":
    raise SystemExit(main())
