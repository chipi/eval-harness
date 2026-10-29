#!/usr/bin/env python3
"""stats' on-disk p cache (EVH_P_CACHE): the same p, bit for bit, read back by a fresh process.

python tests/test_p_cache.py
"""

import json
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
shift = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
d = [((i * 37) % 11 - 5) / 7 + shift for i in range(80)]   # 80 items: past the exact range, an estimate
t = time.monotonic()
p = stats.sign_flip_p(d, permutations=4000)
print(p.hex(), round(time.monotonic() - t, 3), stats._disk_key((tuple(d), 4000, stats.SEED)))
"""

tmp = Path(tempfile.mkdtemp(prefix="evh-pcache-"))
script = tmp / "p.py"
script.write_text(SNIPPET.format(root=str(ROOT)))


def run(cache: str | None, shift: float = 0.0) -> tuple[str, float, str]:
    env = dict(os.environ)
    env.pop("EVH_P_CACHE", None)
    if cache:
        env["EVH_P_CACHE"] = cache
    out = subprocess.run(
        [sys.executable, str(script), str(shift)], env=env, capture_output=True, text=True, check=True
    ).stdout
    p, s, k = out.split()
    return p, float(s), k


plain, _secs, key = run(None)
cache = tmp / "c" / "p.jsonl"
first = run(str(cache))[0]
check("a stored p is the computed one", first == plain, (first, plain))
check(
    "the cache file is written (its directory made)",
    cache.is_file() and len(cache.read_text().splitlines()) == 1,
)
second = run(str(cache))[0]
check("a fresh process reads it back exactly", second == plain, (second, plain))
with cache.open("a") as fh:
    fh.write('{"k": "torn')  # an interrupted writer's last line
third = run(str(cache))[0]
check("a torn line is skipped, the stored p still read", third == plain)
other, _secs, okey = run(str(cache), 0.25)
lines = cache.read_text().splitlines()
check(
    "other deltas are another key; after a torn line the next record starts a line of its own",
    okey != key and other != plain and any(okey in ln and ln.startswith("{") for ln in lines),
    lines,
)
# The read path, proven: a p planted under the key is what a fresh process answers.
cache.write_text(json.dumps({"k": key, "p": (0.123).hex()}) + "\n")
planted = run(str(cache))[0]
check("the stored p is read, not recomputed", planted == (0.123).hex(), planted)
cache.write_bytes(b"\xff\xfe not utf-8\n")
bad = run(str(cache))[0]
check("a file that is not UTF-8 is no cache: the p is computed", bad == plain, bad)
cache.write_text("")
cache.chmod(0)
if not os.access(cache, os.R_OK):  # (as root every file is readable)
    unread = run(str(cache))[0]
    check("an unreadable file is no cache: the p is computed", unread == plain, unread)
cache.chmod(0o600)
check("unset, nothing is stored", not list(tmp.glob("*.jsonl")))
sys.exit(summary())
