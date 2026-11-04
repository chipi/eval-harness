#!/usr/bin/env python3
"""pair-test --b-dataset: one arm on two versions of a dataset, paired by item id.

    python tests/test_pair_versions.py

In a throwaway project built from the tutorial ($0, offline, the echo provider): tickets_v1 and tickets_v2 hold
the same six item ids with the same gold; an arm on each is tested against the other (allowed, and says it is a
cross-version comparison). Then the refusals: a version whose gold differs on one item (named), one that shares
no item id, one whose arm records another metric direction, and the flag next to --round. The command without
the flag is covered by test_stat_commands.py.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-pair-versions-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-pair-versions")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def version(ds: str, tickets: Path, gold: Path, arm: str = "lead1") -> subprocess.CompletedProcess:
    """A dataset of these tickets, gold from this directory, and the tutorial's arm on it."""
    r = evh("dataset-create", "--dataset-id", ds, "--source-dir", str(tickets.relative_to(proj)))
    for step in (
        ("dataset-materialize", "--dataset-id", ds),
        ("label-import", str(gold), "--dataset-id", ds, "--set", "owner_gold", "--by", "owner"),
        (
            "reference-promote", "--dataset-id", ds, "--labels", "owner_gold", "--tier", "gold",
            "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
        ),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    if r.returncode:
        return r
    goal = (KIT / "goals" / "tickets_summary.yaml").read_text().replace("tickets_v1", ds)
    (proj / "data" / "goals" / f"{ds}.yaml").write_text(
        goal.replace("goal_id: tickets_summary", f"goal_id: {ds}")
    )
    return arm_on(ds, arm)


def arm_on(ds: str, arm: str) -> subprocess.CompletedProcess:
    """The tutorial's arm run on this dataset, as tickets_<arm>_<its suffix>."""
    cfg = (KIT / "configs" / f"tickets_{arm}.yaml").read_text()
    cfg = cfg.replace("tickets_v1", ds).replace(f"tickets_{arm}_v1", f"tickets_{arm}_{ds.split('_')[-1]}")
    path = proj / "data" / "configs" / f"{ds}_{arm}.yaml"
    path.write_text(cfg + f"goal: {ds}\n")
    return evh("run", "--config", str(path.relative_to(proj)))


try:
    (proj / "data" / "configs").mkdir(parents=True)
    (proj / "data" / "goals").mkdir()
    t1 = proj / "tutorial" / "tickets"
    shutil.copytree(KIT / "tickets", t1)
    # v2 corrects the evidence of one ticket; the item ids and the gold are v1's.
    t2 = proj / "tutorial" / "tickets_v2"
    shutil.copytree(t1, t2)
    fixed = t2 / "t03_export.txt"
    fixed.write_text("The export was started from the admin panel. " + fixed.read_text())
    # v3: the same ids, but the owner reworded one summary.
    gold3 = proj / "tutorial" / "gold_v3"
    shutil.copytree(KIT / "gold", gold3)
    (gold3 / "t05_delete.txt").write_text("Deleting an account is refused while a subscription is active.\n")
    # v4: no id in common with v1.
    t4 = proj / "tutorial" / "tickets_v4"
    t4.mkdir()
    gold4 = proj / "tutorial" / "gold_v4"
    gold4.mkdir()
    for f in sorted(t1.glob("*.txt")):
        (t4 / f"x_{f.name}").write_text(f.read_text())
        (gold4 / f"x_{f.name}").write_text((KIT / "gold" / f.name).read_text())

    for ds, tickets, gold in (
        ("tickets_v1", t1, KIT / "gold"),
        ("tickets_v2", t2, KIT / "gold"),
        ("tickets_v3", t1, gold3),
        ("tickets_v4", t4, gold4),
    ):
        r = version(ds, tickets, gold)
        check(f"setup: {ds} with its gold and an arm on it", r.returncode == 0, out(r)[-300:])
    base = [
        "pair-test",
        "--dataset-id",
        "tickets_v1",
        "--metric",
        "overlap_f1",
        "--a",
        "tickets_lead1_v1",
        "--b",
    ]

    # An arm on each version.
    r = evh(*base, "tickets_lead1_v2", "--b-dataset", "tickets_v2")
    check(
        "two versions: allowed; says it is cross-version, names both datasets, what it does and does not establish",
        r.returncode == 0
        and "CROSS-VERSION comparison: tickets_lead1_v1 on tickets_v1  vs  tickets_lead1_v2 on tickets_v2"
        in r.stdout
        and "item ids shared    6 of 6 / 6; 6 used" in r.stdout
        and "same reference     gold/tickets_v1 / gold/tickets_v2" in r.stdout
        and "establishes        the effect of the dataset change plus the arms' run-to-run noise" in r.stdout
        and "does not" in r.stdout
        and "an arm's repeats are averaged per item" in r.stdout
        and "N=6" in r.stdout,
        out(r),
    )
    j = evh(*base, "tickets_lead1_v2", "--b-dataset", "tickets_v2", "--json")
    v = json.loads(j.stdout)["result"]["values"] if j.returncode == 0 else {}
    check(
        "--json: cross_version, both dataset ids, the shared count, the establishes/does-not words",
        v.get("cross_version") is True
        and (v["dataset_id"], v["b_dataset_id"], v["items_shared"], v["n"])
        == ("tickets_v1", "tickets_v2", 6, 6)
        and (v["runs_a"], v["runs_b"]) == (1, 1)
        and "run-to-run noise" in v["establishes"]
        and v["does_not_establish"]
        and v["reference_checked"] is True,
        j.stdout[:400] + j.stderr[-200:],
    )
    ids_a, ids_b = v.get("run_ids_a") or [], v.get("run_ids_b") or []
    check(
        "the runs of each side are named, in the text and as run_ids_a / run_ids_b, with where they were read",
        len(ids_a) == 1
        and len(ids_b) == 1
        and ids_a[0].startswith("tickets_lead1_v1_")
        and ids_b[0].startswith("tickets_lead1_v2_")
        and f"runs of A          {ids_a[0]}" in r.stdout
        and f"runs of B          {ids_b[0]}" in r.stdout
        and "read from          " in r.stdout
        and "--runs-dir" in r.stdout,
        (ids_a, ids_b, r.stdout[-600:]),
    )
    missing = [a if a != "overlap_f1" else "no_such_measure" for a in base]
    r = evh(*missing, "tickets_lead1_v2", "--b-dataset", "tickets_v2", "--desc")
    check(
        "a measure not stored per item: refused as a missing metric, naming the side, what is stored, and rescore",
        r.returncode != 0
        and "no_such_measure is not stored per item in tickets_lead1_v1's runs on tickets_v1" in r.stderr
        and "overlap_f1" in r.stderr
        and "evh rescore" in r.stderr
        and "share no item id" not in r.stderr,
        out(r),
    )
    arm_on("tickets_v1", "lead2")
    plain = json.loads(evh(*base, "tickets_lead2_v1", "--json").stdout)["result"]["values"]
    check(
        "without the flag the values carry no cross-version key",
        not {"cross_version", "b_dataset_id", "establishes"} & set(plain),
        sorted(plain),
    )

    # The same item ids, the same gold except one item.
    r = evh(*base, "tickets_lead1_v3", "--b-dataset", "tickets_v3")
    check(
        "a reference that differs on one item: refused, naming the item and the count",
        r.returncode != 0
        and "ERROR" in r.stderr
        and "differs between tickets_v1" in r.stderr
        and "1 of 6 item(s), e.g. t05_delete" in r.stderr
        and "CROSS-VERSION" not in r.stdout,
        out(r),
    )
    j = evh(*base, "tickets_lead1_v3", "--b-dataset", "tickets_v3", "--json")
    check(
        "the same refusal under --json: nothing on stdout, non-zero",
        j.returncode != 0 and j.stdout == "",
        out(j),
    )

    # No item id in common.
    r = evh(*base, "tickets_lead1_v4", "--b-dataset", "tickets_v4")
    check(
        "a dataset sharing no item id: refused",
        r.returncode != 0 and "share no item id" in r.stderr and r.stdout == "",
        out(r),
    )

    # A reference whose text is gone still compares by its recorded checksums.
    ref2 = proj / "data" / "references" / "gold" / "tickets_v2"
    kept = {f.name: f.read_text() for f in ref2.glob("*.txt")}
    for f in ref2.glob("*.txt"):
        f.unlink()
    r = evh(*base, "tickets_lead1_v2", "--b-dataset", "tickets_v2")
    check(
        "reference texts not on this machine: compared by the checksums the manifest records",
        r.returncode == 0 and "the same text for each of the 6 items" in r.stdout,
        out(r),
    )
    for name, text in kept.items():
        (ref2 / name).write_text(text)

    # Other refusals.
    r = evh(*base, "tickets_lead1_v1", "--b-dataset", "tickets_v1")
    check(
        "--b-dataset naming the dataset itself: refused", r.returncode != 0 and "itself" in r.stderr, out(r)
    )
    r = evh(*base, "tickets_lead1_v2", "--b-dataset", "../x")
    check(
        "--b-dataset that is not a plain name: refused",
        r.returncode != 0 and "not a dataset id" in r.stderr,
        out(r),
    )
    r = evh(*base, "tickets_lead1_v2", "--b-dataset", "tickets_v2", "--asc")
    check(
        "--asc applies to both sides (one direction), the test runs",
        r.returncode == 0 and "(lower is better)" in r.stdout,
        out(r),
    )
    r = evh(*base, "tickets_lead1_v2", "--b-dataset", "tickets_v2", "--round", "r1")
    check("--b-dataset with --round: refused", r.returncode == 2 and "cannot be combined" in r.stderr, out(r))
    r = evh("pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_lead1_v1", "--b-dataset", "tickets_v2")
    check("--b-dataset without --b: refused", r.returncode == 2 and "needs --a and --b" in r.stderr, out(r))

    # An arm scored against a different metric direction on each side.
    goal2 = proj / "data" / "goals" / "tickets_v2.yaml"
    goal2.write_text(goal2.read_text().replace("direction: higher", "direction: lower"))
    r = evh(*base, "tickets_lead1_v2", "--b-dataset", "tickets_v2")
    check(
        "a metric that is higher-is-better for one arm and lower-is-better for the other: refused",
        r.returncode != 0 and "not one metric" in r.stderr and r.stdout == "",
        out(r),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
