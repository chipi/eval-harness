#!/usr/bin/env python3
"""V30 fails only a link the harness wrote and can resolve (RFC-041 F7, owner 2026-11-24, after the podcast project's beta run).

    EVAL_STORE=files  python tests/test_v30_links.py
    EVAL_STORE=sqlite python tests/test_v30_links.py

The podcast project passed validate on v0.8.0 and failed V30 on the candidate with nothing changed: its imported runs
name references by a bare name, kept in a folder of its own outside data/, and its goals' `datasets:` hold prose and
patterns. Here R2's imported look-alike (invented names, no data of the project) is given that shape, and:

  - a goal with a prose entry, a glob, a plain id that exists and a plain id that does not: validate exits 6 for the plain
    id that does not exist alone, and says the prose and the glob in a warning naming the goal and the entry;
  - imported runs whose reference is a bare name outside data/: one note each, no failure;
  - without the plain id that does not exist, validate exits 0.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _foreign  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-v30-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVH_ACTOR="person:fixture")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF", "EVAL_GOALS_DIR"):
    env.pop(k, None)
EXIT_PROBLEMS = 6
BARE = ("silver_dev_v1_paragraph", "silver_dev_v2_paragraph")
PROSE, GLOB = "5 personas", "prod_v3_*"
GONE = "never_imported_v1"


def validate() -> tuple[int, str]:
    """`evh validate` in the project: its exit code and output."""
    r = _cli.run(proj, env, "validate")
    return r.returncode, r.stdout + r.stderr


def goal(entries: list[str]) -> None:
    """The goal whose `datasets:` are `entries`, as the podcast project's are written."""
    put = _foreign.Build(proj, env).put
    put(
        "goals/podcast_like.yaml", _foreign._goal("podcast_like", "wer", "lower", [f"'{e}'" for e in entries])
    )


try:
    facts = _foreign.imported(proj, dict(env))
    ds = _foreign.IMPORTED_BIG
    for rid, ref in zip(facts["runs"][ds][:2], BARE):
        run = _runstore.read_json(proj, f"runs/{rid}/run.json")
        run["fingerprint"]["data"]["reference_id"] = ref
        _runstore.write_text(proj, f"runs/{rid}/run.json", json.dumps(run, indent=2) + "\n")
    outside = proj / "records" / "references" / "silver" / BARE[0]
    outside.mkdir(parents=True)
    (outside / "clip_01.txt").write_text("an invented reference text\n")

    goal([PROSE, GLOB, ds, GONE])
    code, out = validate()
    v30 = [ln for ln in out.splitlines() if re.match(r"\s+(ok|FAIL)\s+V30", ln)]
    check(
        "the plain id that names no dataset alone fails: exit 6, FAIL V30, one problem, naming the goal and the id",
        code == EXIT_PROBLEMS
        and v30
        and v30[0].lstrip().startswith("FAIL V30")
        and "1 problem(s)" in v30[0]
        and f"goals/podcast_like.yaml: dataset '{GONE}' does not exist" in out
        and "VALIDATION FAILED — 1 check(s): V30" in out,
        f"exit {code}: {out[-700:]}",
    )
    check(
        "a prose entry and a glob are warnings naming the goal and the entry, not failures",
        all(f"V30 goal podcast_like: datasets entry '{e}' is not a dataset id" in out for e in (PROSE, GLOB))
        and f"'{ds}'" not in " ".join(ln for ln in out.splitlines() if "V30 goal" in ln),
        out[-700:],
    )
    check(
        "an imported run's reference that is not under data/ is one note per reference, never a failure",
        all(
            re.search(
                rf"note: V16 references: 1 run\(s\) scored against {b}, which is not under data/references",
                out,
            )
            for b in BARE
        )
        and out.count(f"scored against {BARE[0]},") == 1,
        out[-900:],
    )

    goal([PROSE, GLOB, ds])
    code, out = validate()
    check(
        "without the plain id that names no dataset, validate exits 0 with the notes and warnings",
        code == 0 and "VALIDATION PASSED" in out and "datasets entry" in out and "scored against" in out,
        f"exit {code}: {out[-700:]}",
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
