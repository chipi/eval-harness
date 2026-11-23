#!/usr/bin/env python3
"""Each arm's scores read once per view and per build (scores_once).

    python tests/test_scores_once.py

On this repository's runs, `evh goal-list` read 1,054 arms' scores for 686 arms (the collect, the goals' groups and the
adapter's own `describe` asking again): 79% of its CPU, which the evals MCP server pays at cpus 0.5 on every fresh
call. With a counting adapter behind the views' loader: no arm's scores are read twice by a view or by a catalog
build, the adapter's own methods included (a wrapper around it missed those: arms read three times).
"""

import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

import yaml

# reads this repository's own committed runs (harness/data), which are files by definition
os.environ["EVAL_STORE"] = "files"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _ops
import _ops
from evaluation_harness import catalog_build as cb
from evaluation_harness._check import check, summary
from evaluation_harness.catalog_adapter import HarnessAdapter, scores_once

DATA = Path(__file__).resolve().parents[1] / "data"

READS: Counter = Counter()  # each arm's scores reads, by Counting


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _measured(rec: dict, root: dict) -> bool:
    """Whether a repeat joins the plain run it repeats, as the docs say: the same data, deployment, settings and
    adapter recorded in the two fingerprints (the harness's own code may differ)."""
    fa, fb = rec.get("fingerprint") or {}, root.get("fingerprint") or {}
    parts = [fa.get("version") and fa.get("version") == fb.get("version")]
    for part in ("data_sha256", "deployment_sha256", "settings_sha256"):
        parts.append(fa.get(part) and fa.get(part) == fb.get(part))
    adapters = [((f.get("instrument") or {}).get("adapter") or {}).get("sha256") for f in (fa, fb)]
    parts.append(adapters[0] and adapters[0] == adapters[1])
    return all(parts)


def narrowed() -> Counter:
    """How many rounds read each arm through only the runs they recorded, fewer than the arm has (a later run joined to
    it, a repeat of the same measurement, RFC-041 F2): each such round view reads the arm's scores once for itself.
    Counted from the files, not through the adapter: each round's yaml names its arms' runs, and an arm's runs are the
    run folders of its system and dataset with a score under the arm's label, a plain run and each repeat of it that
    is the same measurement (`_measured`); a repeat that is not is read as `repeats`."""
    runs = {
        d.name: json.loads((d / "run.json").read_text())
        for d in (DATA / "runs").iterdir()
        if (d / "run.json").is_file()
    }
    on_disk: dict[tuple[str, str, str], set[str]] = {}
    for name, rec in runs.items():
        d = DATA / "runs" / name
        root = rec
        while root.get("purpose") == "repeat" and root.get("of") in runs:
            root = runs[root["of"]]
        if rec.get("purpose") == "repeat" and (root is rec or not _measured(rec, root)):
            continue  # a --repeat set's member, or a repeat of something else: read as `repeats`
        labels = {json.loads(f.read_text()).get("label") or "" for f in (d / "scores").glob("*/score.json")}
        prefixes = {_slug(x) for x in labels if x} | (
            {"runs"} if root.get("purpose", "run") == "run" else set()
        )
        for prefix in prefixes:
            on_disk.setdefault((prefix, rec["dataset_id"], rec["system_id"]), set()).add(name)
    found: Counter = Counter()
    for f in sorted((DATA / "rounds").glob("*/r*.yaml")):
        rnd = yaml.safe_load(f.read_text())
        for a in rnd.get("arms") or []:
            prefix = _slug(a.get("label") or "") or "runs"
            key = (prefix, rnd["dataset_id"], a["system"])
            if a.get("runs") and on_disk.get(key, set()) - set(a["runs"]):
                found[f"{prefix}/{rnd['dataset_id']}/{a['system']}"] += 1
    return found


EXTRA = narrowed()


class Counting(HarnessAdapter):
    """The harness's adapter, counting each arm's scores reads."""

    def scores(self, arm, rescore=False):
        READS[arm] += 1
        return super().scores(arm, rescore)


# The memo itself: one read for two asks, the same dict back, the adapter's own methods reading it too.
inner = Counting()
arm = next(iter(inner.arms()))
READS.clear()
w = scores_once(inner)
first, again = w.scores(arm), w.scores(arm)
check(
    "scores_once: an arm asked twice is read once, the same answer both times, by the adapter's own methods too",
    READS[arm] == 1 and first is again and w is inner and w.describe(arm) is not None and READS[arm] == 1,
    dict(READS),
)

# A view: evh goal-list, in this process, with the counting adapter behind it (scores read once per arm, as the
# project's shared adapter does).
READS.clear()
_ops.result("goal-list", scores_once(Counting()))
twice = {
    a: n for a, n in READS.items() if n != 1
}  # goal-list shows no round: a view of a round reads its own
check(
    f"evh goal-list: every arm's scores read exactly once ({len(READS)} arms read)",
    READS and not twice,
    dict(list(twice.items())[:5]),
)

# A build: every page, each arm read once.
READS.clear()
with tempfile.TemporaryDirectory() as out:
    cb.build(Counting(), Path(out) / "catalog")
twice = {a: n for a, n in READS.items() if n != 1 + EXTRA[a]}
check(
    f"catalog build: every arm's scores read once, and once more for each round that reads it narrower ({len(READS)} arms read, {sum(EXTRA.values())} narrower round views)",
    READS and not twice,
    dict(list(twice.items())[:5]),
)

sys.exit(summary())
