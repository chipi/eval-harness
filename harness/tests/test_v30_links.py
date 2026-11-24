#!/usr/bin/env python3
"""V30 fails only a reference the harness scored a run against; goal entries are notes (RFC-041 F7, owner 2026-11-24).

    EVAL_STORE=files  python tests/test_v30_links.py
    EVAL_STORE=sqlite python tests/test_v30_links.py

The podcast project passed validate on v0.8.0 and failed V30 on the candidate with nothing changed: its imported runs
name references by a bare name, kept in a folder of its own outside data/, and its goals' `datasets:` hold prose and
patterns. Here R2's imported look-alike (invented names, no data of the project) is given that shape, and:

  - a goal with a prose entry, a glob, a range (`_v1..v3_`, the podcast project's), a plain id that exists and a plain id
    that does not: validate exits 0, and says each of the prose, the glob, the range and the missing id in a note naming the
    goal and the entry (only the id's says it fails from 0.9: a range is no id);
  - imported runs whose reference is a bare name outside data/: one note each, no failure, which says the harness cannot
    find it, not that it cannot be re-checked (the importer keeps it where it likes);
  - a harness-scored run's missing reference stays a FAIL: test_writers_refuse.py.
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
PROSE, GLOB, RANGE = "5 personas", "prod_v3_*", "prod_like_2x10_v1..v3_cleaned"
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
    (outside / "clip_01.txt").write_text("an invented reference text\n", encoding="utf-8")

    goal([PROSE, GLOB, RANGE, ds, GONE])
    code, out = validate()
    v30 = [ln for ln in out.splitlines() if re.match(r"\s+(ok|FAIL)\s+V30", ln)]
    check(
        "the plain id that names no dataset is a note naming the goal and the entry, saying it fails from 0.9; exit 0",
        code == 0
        and v30
        and v30[0].lstrip().startswith("ok   V30")
        and f"V30 goal podcast_like: datasets entry '{GONE}' names no dataset of this project" in out
        and out.count("FAIL from 0.9") == 1
        and "VALIDATION PASSED" in out,
        f"exit {code}: {out[-700:]}",
    )
    check(
        "a prose entry, a glob and a range are notes naming the goal and the entry, not failures, and never 'FAIL from 0.9'",
        all(
            f"V30 goal podcast_like: datasets entry '{e}' is not a dataset id" in out
            for e in (PROSE, GLOB, RANGE)
        )
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
        and out.count(f"scored against {BARE[0]},") == 1
        and "the harness cannot find it" in out
        and "cannot be re-checked" not in out,
        out[-900:],
    )

    goal([PROSE, GLOB, ds])
    code, out = validate()
    check(
        "without that id, the notes for the prose and the glob remain and none names it",
        code == 0 and "datasets entry" in out and GONE not in out and "scored against" in out,
        f"exit {code}: {out[-700:]}",
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
