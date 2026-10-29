#!/usr/bin/env python3
"""stats' on-disk p cache (EVH_P_CACHE): the same p, bit for bit, read back by a fresh process.

python tests/test_p_cache.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary

ROOT = Path(__file__).resolve().parents[1]
SNIPPET = """
import sys, time
sys.path.insert(0, {root!r})
from evaluation_harness import stats
d = [((i * 37) % 11 - 5) / 7 for i in range(80)]   # 80 items: past the exact range, an estimate
t = time.monotonic()
p = stats.sign_flip_p(d, permutations=4000)
print(p.hex(), round(time.monotonic() - t, 3))
"""

tmp = Path(tempfile.mkdtemp(prefix="evh-pcache-"))
script = tmp / "p.py"
script.write_text(SNIPPET.format(root=str(ROOT)))


def run(cache: str | None) -> tuple[str, float]:
    env = dict(os.environ)
    env.pop("EVH_P_CACHE", None)
    if cache:
        env["EVH_P_CACHE"] = cache
    out = subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True, text=True, check=True
    ).stdout
    p, s = out.split()
    return p, float(s)


plain, _ = run(None)
cache = tmp / "c" / "p.jsonl"
first, _ = run(str(cache))
check("a stored p is the computed one", first == plain, (first, plain))
check(
    "the cache file is written (its directory made)",
    cache.is_file() and len(cache.read_text().splitlines()) == 1,
)
second, secs = run(str(cache))
check("a fresh process reads it back exactly", second == plain, (second, plain))
with cache.open("a") as fh:
    fh.write('{"k": "torn')  # an interrupted writer's last line
third, _ = run(str(cache))
check("a torn line is skipped, the stored p still read", third == plain)
check("unset, nothing is stored", not list(tmp.glob("*.jsonl")))
sys.exit(summary())
