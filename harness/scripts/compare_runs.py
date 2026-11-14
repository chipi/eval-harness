#!/usr/bin/env python3
"""Compare two runs — and REFUSE when the comparison would be meaningless.

The refusals are the feature. A tool that always produces a number teaches you
to trust numbers that mean nothing:

  * different `dataset_id`  -> refused outright. Two metrics measured on
    different data are not comparable; the result would be a coincidence
    wearing a delta's clothes.
  * same build on both sides -> reported. If the code did not change, the
    delta is instrument or noise, not an improvement.
  * a delta smaller than the arm's own spread -> flagged as noise, with the
    command that measures that spread.

    python scripts/compare_runs.py --baseline <run_id> --candidate <run_id>
    python scripts/compare_runs.py --baseline <run_id> --candidate <run_id> --noise 0.01
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
from pathlib import Path

from evaluation_harness import _jsonout, _store
from evaluation_harness._adapter import recorded_metric_kinds
from evaluation_harness._common import (
    RUNS,
    die,
    evh_prog,
    how,
    verdict_for,
)
from evaluation_harness.model import runs as model_runs


def _short(v: object, n: int = 40) -> str:
    text = "—" if v is None else str(v)
    return text if len(text) <= n else text[: n - 1] + "…"


def _paths_in(part: str, fa: dict, fb: dict) -> list[str]:
    from evaluation_harness._fingerprint import differing_paths  # noqa: PLC0415

    return differing_paths({part: fa.get(part)}, {part: fb.get(part)})


def _value(fp: dict, path: str) -> object:
    cur: object = fp
    for key in path.split("."):
        cur = cur.get(key) if isinstance(cur, dict) else None
    return cur


def _name(path: str) -> str:
    return path.partition(".")[2] or path


def _what_moved(part: str, fa: dict, fb: dict) -> str:
    """One line naming a moved part and how: the deployment by id, the settings by key and value."""
    paths = _paths_in(part, fa, fb)
    if part == "deployment":
        da, db = fa.get("deployment") or {}, fb.get("deployment") or {}
        return f"deployment differs: {_short(da.get('id'))} vs {_short(db.get('id'))}"
    if part == "settings":
        moved = [f"{_name(p)} ({_short(_value(fa, p))} vs {_short(_value(fb, p))})" for p in paths]
        return "settings differ: " + ", ".join(moved)
    if part == "data":
        return "data differs: " + ", ".join(_name(p) for p in paths)
    return "instrument differs: " + ", ".join(_name(p) for p in paths)


def _report_fingerprint_delta(a: dict, b: dict) -> None:
    """Say WHICH PART changed between the two runs, not just that something did.

    "The fingerprints differ" is true and useless. A comparison is only an experiment if
    exactly one thing moved, and this names the part (instrument, data, deployment, settings)
    and what in it - so a 3x latency win reads as "the deployment differs: dgx vs mac" rather
    than "the model got faster". The runner (where evh ran) is outside the hash: it is shown as
    a condition, never as a mismatch.
    """
    fa, fb = a.get("fingerprint"), b.get("fingerprint")
    if not (fa and fb):
        _jsonout.value(
            "fingerprint",
            {"comparable": False, "reason": "at least one run predates fingerprinting", "match": None},
        )
        print(
            "\n  NOTE: at least one run predates fingerprinting, so what else changed"
            "\n  between them cannot be checked — only asserted."
        )
        return
    if fa.get("version") != fb.get("version"):
        _jsonout.value(
            "fingerprint",
            {
                "comparable": False,
                "reason": f"fingerprint versions differ (v{fa.get('version')} vs v{fb.get('version')})",
                "match": None,
            },
        )
        print(
            f"\n  NOTE: fingerprint versions differ (v{fa.get('version')} vs v{fb.get('version')}):"
            "\n  they hash different things, so no part can be compared. Re-run the older arm to put"
            "\n  both on the same version."
        )
        return

    from evaluation_harness._fingerprint import PARTS, moved_parts  # noqa: PLC0415

    moved = moved_parts(fa, fb)
    ra, rb = fa.get("runner") or {}, fb.get("runner") or {}
    _jsonout.value(
        "fingerprint",
        {
            "comparable": True,
            "match": not moved,
            "moved": [p for p in PARTS if p in moved],
            "detail": [_what_moved(p, fa, fb) for p in PARTS if p in moved],
            "confounds": [p for p in PARTS if p in moved and p in ("instrument", "data")],
            "runner_differs": ra != rb,
        },
    )
    if not moved:
        print(
            "\n  Fingerprints MATCH: instrument, data, deployment and settings are identical,"
            "\n  so any delta above is the run-to-run noise."
        )
    else:
        print("\n  Fingerprints DIFFER. Parts that moved:")
        for part in PARTS:
            if part in moved:
                marker = "   " if part in ("deployment", "settings") else " ! "
                print(f"   {marker}{_what_moved(part, fa, fb)}")
        confounds = [p for p in moved if p in ("instrument", "data")]
        if confounds:
            print(
                f"\n  {len(confounds)} of those are NOT the arm (marked !). More than one thing"
                "\n  changed, so this is not a controlled comparison — it is two observations."
            )
        elif len(moved) > 1:
            print(
                "\n  The deployment and the settings both moved: two things were varied, so a delta"
                "\n  cannot be put on either alone."
            )
    if ra != rb:
        diff = [k for k in sorted(set(ra) | set(rb)) if k != "libraries" and ra.get(k) != rb.get(k)]
        libs = sorted(
            k
            for k in set(ra.get("libraries") or {}) | set(rb.get("libraries") or {})
            if (ra.get("libraries") or {}).get(k) != (rb.get("libraries") or {}).get(k)
        )
        print(
            "\n  Runner (where evh ran; a condition, outside the hash) differs: "
            + (", ".join(f"{k} {_short(ra.get(k))} vs {_short(rb.get(k))}" for k in diff) or "libraries")
            + (f"; libraries {', '.join(libs)}" if libs else "")
            + "\n  Latency is the deployment's, measured from the runner: speed across runners is not"
            "\n  the same measurement."
        )


def load(run_id: str) -> dict:
    """A run's record, as its first score reads it; die if there is no such run or it has no score."""
    # A run is a directory of the runs folder: an id that names a path ("../x") is not one (the MCP tool
    # takes ids from an agent).
    if run_id in ("", ".", "..") or run_id != Path(run_id).name:
        die(f"no run {run_id!r}: a run id names a directory of {RUNS.name}, not a path", "bad-argument")
    d = RUNS / run_id
    if not _store.is_file(d / model_runs.RUN):
        die(f"no run {run_id!r} (looked for {d / model_runs.RUN})", "not-found")
    sd = model_runs.first_score(d) or next(iter(model_runs.scores_of(d)), None)
    rec = model_runs.record(sd) if sd else None
    if rec is None:
        die(f"run {run_id!r} has no score to compare", "not-found")
    return rec


def main() -> int:
    """Load and summarize a single run."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument(
        "--noise",
        type=float,
        default=None,
        help="the arm's own spread; deltas at or below it are reported as noise. "
        "0 is a real answer — it means the arm is deterministic — so it is not "
        "the same as omitting the flag.",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="the same answer as one JSON object: the printed lines as blocks, the metric table as data, "
        "and the result by name under result.values (fingerprint, worth, ...)",
    )
    args = ap.parse_args()
    with _jsonout.collect("run-compare", args.json):
        return _run(args)


def _run(args: argparse.Namespace) -> int:
    a, b = load(args.baseline), load(args.candidate)

    if a["dataset_id"] != b["dataset_id"]:
        die(
            "REFUSED — different dataset_id:\n"
            f"    {args.baseline:32} {a['dataset_id']}\n"
            f"    {args.candidate:32} {b['dataset_id']}\n"
            "  A metric compared across two datasets is not a comparison, it is a\n"
            "  coincidence. Re-run one arm on the other's dataset_id. For two versions of one\n"
            "  dataset (same item ids, same reference), `evh pair-test --dataset-id D1 --a A --b B\n"
            "  --b-dataset D2` is the comparison.",
            "mismatch",
        )

    print(f"dataset_id : {a['dataset_id']}")
    print(f"baseline   : {args.baseline}  build={a['build']['ref'][:12]}")
    print(f"candidate  : {args.candidate}  build={b['build']['ref'][:12]}")
    if a["build"]["ref"] == b["build"]["ref"]:
        print("\n  NOTE: identical build on both sides — any delta here is the")
        print("  instrument or run-to-run noise, not a code change.")
    if a["build"].get("dirty") or b["build"].get("dirty"):
        print("\n  NOTE: a build was DIRTY — its ref does not identify what ran.")

    _report_fingerprint_delta(a, b)

    keys = sorted(set(a["scores"]) | set(b["scores"]))
    w = max([len(k) for k in keys] + [6])
    # THE KINDS THE RUNS THEMSELVES RECORDED. `verdict_for` otherwise consults only the
    # built-in table, which knows the bundled adapter's metrics and nothing else -- so
    # every example's own metrics were judged "better"/"worse" by sign alone. An arm
    # that hallucinated more document ids was reported as improved.
    # THE ADAPTER'S CURRENT DECLARATION WINS, as it does in `leaderboard`. A run
    # freezes the metric kinds declared when it was measured, so fixing a misdeclared
    # metric changed nothing for any comparison of runs made before the fix. Round 2
    # fixed this in leaderboard.py and not here. Found by external review.
    kinds = {**(a.get("metric_kinds") or {}), **(b.get("metric_kinds") or {})}
    for run in (a, b):
        kinds.update(recorded_metric_kinds(run.get("adapter")) or {})

    worth = 0
    shown: list[tuple] = []  # (metric, baseline, candidate, delta, verdict); None where a side has none
    for k in keys:
        if k not in a["scores"] or k not in b["scores"]:
            shown.append((k, a["scores"].get(k), b["scores"].get(k), None, "only on one side"))
            continue
        av, bv = a["scores"][k], b["scores"][k]
        d = bv - av
        # `is not None`, not truthiness: NOISE=0 is the correct floor for a
        # deterministic arm, and treating it as "not given" nagged the user for
        # doing exactly the right thing.
        if args.noise is not None and abs(d) <= args.noise:
            verdict = f"NOISE (<= {args.noise})"
        else:
            # Direction comes from _common, the same place leaderboard.py gets it.
            # This used to be `"better" if d > 0 else "worse"` for every metric, so a
            # run that got FASTER or CHEAPER was reported as worse.
            verdict = verdict_for(k, d, kinds=kinds)
            # Only a real regression or improvement counts toward "moved beyond the
            # noise floor". A descriptive metric moving is not a verdict, and counting
            # it inflated the number a reader uses to decide whether to care.
            if verdict in ("better", "worse"):
                worth += 1
        shown.append((k, av, bv, d, verdict))

    if not _jsonout.table(["metric", "baseline", "candidate", "delta", "verdict"], shown):
        print(f"\n  {'metric':{w}} {'baseline':>12} {'candidate':>12} {'delta':>12}   verdict")
        for k, av, bv, d, verdict in shown:
            if d is None:
                print(f"  {k:{w}} {'—':>12} {'—':>12} {'—':>12}   {verdict}")
            else:
                print(f"  {k:{w}} {av:12.6f} {bv:12.6f} {d:+12.6f}   {verdict}")
    _jsonout.values(
        {
            "dataset_id": a["dataset_id"],
            "baseline": args.baseline,
            "candidate": args.candidate,
            "baseline_build": a["build"]["ref"],
            "candidate_build": b["build"]["ref"],
            "same_build": a["build"]["ref"] == b["build"]["ref"],
            "dirty_build": bool(a["build"].get("dirty") or b["build"].get("dirty")),
            "noise": args.noise,
            "moved_beyond_noise": worth,
        }
    )

    if args.noise is None:
        print(
            "\n  --noise was not given, so nothing was judged against the arm's own\n"
            "  spread. Measure it first:  "
            + how(
                "evh run --system <id> --dataset <id> --repeat 3",
                "make run SYSTEM=<id> DATASET_ID=<id> REPEAT=3",
            )
        )
    print(f"\n  {worth} metric(s) moved beyond the stated noise floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
