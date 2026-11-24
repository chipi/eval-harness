#!/usr/bin/env python3
"""`make site` never leaves site/public deleted (0.8.1 P3).

    python tests/test_site_build_atomic.py

An agent saw `make -C harness site` without EVAL_STORE delete most of site/public. The store is not the cause (the
repository's harness/config.yaml names `store: files`, and a project that names none is refused with
`ERROR (not-configured)` before anything is written); the cause is that `build()` removed the live site first and wrote
the new one in place, a build of about two minutes, so a failure or an interrupt anywhere in it, for any reason, left the
site half-deleted. The build is now written beside the output and swapped in only when it is whole.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

PY = sys.executable
FAIL_LATE = """
import sys
from pathlib import Path
sys.path.insert(0, {site!r})
import build

def boom(*a, **k):
    raise RuntimeError("a page failed to render")

# The figures take about a minute to compute, and `make site-check` builds the whole site on every change; here they are a
# stand-in, and the first page fails after the stage has its assets: a failure part-way, with something written.
build.figures.compute = lambda: dict()
build.home = boom
out = Path({out!r})
try:
    build.build(out)
except RuntimeError:
    pass
"""
NO_STORE = """
import sys
from pathlib import Path
sys.path.insert(0, {site!r})
import build
build.build(Path({out!r}))
"""


def run(code: str, env_extra: dict, drop=()) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(env_extra)
    return subprocess.run(
        [PY, "-c", code], env=env, capture_output=True, text=True, check=False, encoding="utf-8"
    )


with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "public"
    out.mkdir()
    (out / "marker.html").write_text("the live site", encoding="utf-8")
    p = run(FAIL_LATE.format(site=str(ROOT / "site"), out=str(out)), {}, drop=("EVAL_STORE",))
    check(
        "a build that fails part-way leaves the live output as it was",
        (out / "marker.html").is_file()
        and (out / "marker.html").read_text(encoding="utf-8") == "the live site",
        (p.stderr or p.stdout)[-300:],
    )
    check(
        "and leaves no half-built directory beside it",
        sorted(x.name for x in Path(tmp).iterdir()) == ["public"],
        str(sorted(x.name for x in Path(tmp).iterdir())),
    )

with tempfile.TemporaryDirectory() as tmp:
    proj = Path(tmp) / "proj"
    (proj / "data").mkdir(parents=True)
    (proj / "config.yaml").write_text("name: x\n", encoding="utf-8")
    out = Path(tmp) / "public"
    out.mkdir()
    (out / "marker.html").write_text("the live site", encoding="utf-8")
    p = run(
        NO_STORE.format(site=str(ROOT / "site"), out=str(out)), {"EVAL_HOME": str(proj)}, drop=("EVAL_STORE",)
    )
    check(
        "a project naming no store is refused as not-configured, and the output is untouched",
        "ERROR (not-configured)" in p.stderr + p.stdout and (out / "marker.html").is_file(),
        (p.stderr or p.stdout)[-300:],
    )

cfg = (ROOT / "harness" / "config.yaml").read_text(encoding="utf-8")
check(
    "the repository's own harness/config.yaml names its store, so `make site` needs no EVAL_STORE",
    any(line.strip() in ("store: files", "store: sqlite") for line in cfg.splitlines()),
    cfg[:200],
)

sys.exit(summary())
