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

# An `evh` command keeps its p's in the project's .cache/ unless told otherwise (PLAN_0.8.0 S2: every new process
# drew them again; `goals` right after `catalog` took as long again): EVH_P_CACHE names another file, an empty value
# turns it off. A library import (an adapter, a notebook) stores nothing, as above.
import contextlib  # noqa: E402
import io  # noqa: E402

from evaluation_harness import cli  # noqa: E402

proj = tmp / "proj"
(proj / "data").mkdir(parents=True)


def via_evh(value: str | None) -> str | None:
    saved = {k: os.environ.get(k) for k in ("EVH_P_CACHE", "EVAL_HOME")}
    os.environ["EVAL_HOME"] = str(proj)
    os.environ.pop("EVH_P_CACHE", None)
    if value is not None:
        os.environ["EVH_P_CACHE"] = value
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["licences"])
        return os.environ.get("EVH_P_CACHE")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


check(
    "an evh command keeps its p's in the project's .cache/evh-p.jsonl",
    via_evh(None) == str(proj / ".cache" / "evh-p.jsonl"),
    via_evh(None),
)
check("EVH_P_CACHE= (empty) turns it off", via_evh("") == "", via_evh(""))
check("EVH_P_CACHE names another file", via_evh(str(tmp / "mine.jsonl")) == str(tmp / "mine.jsonl"))
sys.exit(summary())
