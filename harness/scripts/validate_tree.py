#!/usr/bin/env python3
"""Integrity checks over the eval tree. Run it before you trust any number.

Each check exists because its absence let a real defect through somewhere:

  V1  schemas        a document that violates its own contract
  V2  dataset_id     a run citing a dataset that does not exist — the number
                     cannot be attributed to any data
  V3  provenance     a run with no build ref — the number cannot be attributed
                     to any code
  V4  materialized   a dataset whose materialized copy drifted from its hashes
  V5  duplicates     two runs reporting byte-identical scores AND identical
                     per-item results on the same dataset. Agreeing MEANS are not
                     suspicious on a discrete metric; agreeing per item is
  V6  baselines      a baseline pointing at a run that no longer exists

Exit 1 on any failure, so it can gate.

    python scripts/validate_tree.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    BASELINES,
    DATASETS,
    MATERIALIZED,
    ROOT,
    RUNS,
    read_json,
    sha256,
)

try:
    import jsonschema
except ImportError:
    jsonschema = None

SCHEMAS = ROOT / "schemas"
problems: list[str] = []
notes: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    if ok:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
        problems.append(label)


def v1_schemas() -> None:
    if jsonschema is None:
        notes.append("V1 skipped: jsonschema not installed (pip install -r requirements.txt)")
        print("  --   V1 schemas (jsonschema not installed)")
        return
    pairs = [
        (DATASETS.glob("*.json"), "dataset.schema.json"),
        ((p / "metrics.json" for p in RUNS.iterdir()) if RUNS.is_dir() else [], "metrics.schema.json"),
        ((p for p in BASELINES.glob("*.json")), "baseline.schema.json"),
    ]
    bad = 0
    n = 0
    for files, schema_name in pairs:
        schema = json.loads((SCHEMAS / schema_name).read_text())
        for f in files:
            if not Path(f).is_file():
                continue
            n += 1
            try:
                jsonschema.validate(read_json(Path(f)), schema)
            except jsonschema.ValidationError as exc:
                bad += 1
                print(f"       {Path(f).name}: {exc.message[:90]}")
    check(bad == 0, f"V1 schemas — {n} document(s) validated", f"{bad} violation(s)")


def v2_dataset_ids() -> None:
    known = {p.stem for p in DATASETS.glob("*.json")}
    dangling = []
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            did = read_json(m).get("dataset_id")
            if did not in known:
                dangling.append(f"{run.name} -> {did}")
    for d in dangling:
        print(f"       {d}")
    check(not dangling, f"V2 every run's dataset_id resolves ({len(known)} dataset(s) known)",
          f"{len(dangling)} dangling")


def v3_provenance() -> None:
    missing = []
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            b = read_json(m).get("build") or {}
            if b.get("ref", "unknown") == "unknown":
                missing.append(run.name)
    for r in missing:
        print(f"       {r}")
    check(not missing, "V3 every run identifies its build", f"{len(missing)} without a ref")


def v4_materialized() -> None:
    drifted = []
    for ds_file in DATASETS.glob("*.json"):
        ds = read_json(ds_file)
        mat = MATERIALIZED / ds["dataset_id"]
        if not mat.is_dir():
            continue
        for item in ds["items"]:
            rel = item.get("source_path") or item["item_id"]
            f = mat / rel
            if f.is_file() and sha256(f) != item["source_sha256"]:
                drifted.append(f"{ds['dataset_id']}/{rel}")
    for d in drifted:
        print(f"       {d}")
    check(not drifted, "V4 materialized copies match their frozen hashes", f"{len(drifted)} drifted")


#: Excluded from the V5 duplicate key: wall-clock and spend are properties of the RUN, not
#: of what the arm produced. Including them made the check unfireable — two arms agreeing to
#: full precision on every measured metric still keyed differently because their latencies
#: differed by microseconds. Measured on this tree: arm_a_v1 and arm_short_v1 both scored
#: overlap_f1 0.135256 and output_words 3.6, and V5 reported OK.
_V5_RUN_PROPERTIES = ("latency_ms", "cost_usd", "total_cost_usd", "tokens_in", "tokens_out",
                      "total_tokens_in", "total_tokens_out")


def _per_item_signature(run_name: str) -> str:
    """A stable digest of one run's per-item scores, for telling ties from copies.

    Run-level properties are excluded for the same reason they are excluded from the key
    above: a fabricated result differs in latency like any other. A run with no readable
    predictions returns its own name, so it can never match another run -- an unreadable
    file is a reason to say nothing, not a reason to accuse.
    """
    path = RUNS / run_name / "predictions.jsonl"
    if not path.is_file():
        return f"<no-predictions:{run_name}>"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            scored = {k: v for k, v in row.items()
                      if k not in _V5_RUN_PROPERTIES and k != "_meta"}
            rows.append(json.dumps(scored, sort_keys=True))
    except (OSError, ValueError):
        return f"<unreadable:{run_name}>"
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def v5_duplicate_scores() -> None:
    by_key = defaultdict(list)
    for run in (RUNS.iterdir() if RUNS.is_dir() else []):
        m = run / "metrics.json"
        if m.is_file():
            d = read_json(m)
            # Compare what the arm PRODUCED. A fabricated or copy-pasted result differs in
            # latency like any other, so keying on it let exactly the case this check exists
            # for slip through.
            produced = {
                k: v for k, v in (d.get("scores") or {}).items() if k not in _V5_RUN_PROPERTIES
            }
            key = (d.get("dataset_id"), json.dumps(produced, sort_keys=True))
            # None (not {}) when the run predates params being recorded — kept distinct so
            # those runs can be EXCLUDED below rather than compared. Treating a missing
            # field as "different params" made every pre-existing run look suspicious
            # against every new one, which is a false alarm I walked straight into.
            params = json.dumps(d["params"], sort_keys=True) if "params" in d else None
            by_key[key].append((run.name, d.get("config_id"), params))
    # Identical scores from identical params is not suspicious — it is what a deterministic
    # arm DOES, and two configs may legitimately request the same thing. What deserves a look
    # is DIFFERENT params landing on byte-identical output: either a result was not measured,
    # or the knobs that differ are inert.
    dupes = []
    for group in by_key.values():
        known = [(n, c, p) for n, c, p in group if p is not None]
        if len({c for _, c, _ in known}) > 1 and len({p for _, _, p in known}) > 1:
            # AGREEING MEANS IS NOT AGREEING MEASUREMENT. The check's premise -- "independent
            # arms do not agree to full float precision" -- holds for a continuous metric and
            # FAILS for a discrete one. A classification run scores each item 1 or 0, so its
            # mean over 200 items takes one of 201 values; two genuinely different models
            # both getting 172 right produce byte-identical 0.86 with nothing wrong at all.
            # The AG News sweep tripped this four times in one run, on arms whose per-item
            # answers were nothing alike.
            #
            # So before flagging, compare what the runs actually DID: the per-item scores.
            # Two arms that agree on the mean but disagree on which items they got right are
            # two measurements. Two arms agreeing item by item are the case this check
            # exists for, and a low-cardinality metric cannot hide that.
            if len({_per_item_signature(n) for n, _, _ in known}) > 1:
                continue
            dupes.append(known)
    for group in dupes:
        print(f"       identical scores AND identical per-item results: "
              f"{', '.join(n for n, _, _ in group)}")
    check(
        not dupes,
        "V5 no two configs report byte-identical scores",
        f"{len(dupes)} suspicious group(s) — differing params produced identical output",
    )


def v6_baselines() -> None:
    broken = []
    for b in BASELINES.glob("*.json"):
        d = read_json(b)
        if not (RUNS / d.get("promoted_from", "")).is_dir():
            broken.append(f"{b.name} -> {d.get('promoted_from')}")
    for x in broken:
        print(f"       {x}")
    check(not broken, "V6 every baseline's source run still exists", f"{len(broken)} broken")


def v7_committed_runs_are_readable() -> None:
    """A run in the repo must carry `metrics.json`. Outputs alone are not a run.

    144 directories were committed as outputs ONLY -- 2,880 files of CNN/DailyMail
    paraphrases with nothing to say which arm produced them, on which dataset, under
    which fingerprint. No tool here can read them: `rescore`, `leaderboard`,
    `compare_runs` and every report script key off `metrics.json` and skip a directory
    without one.

    The cause was two rules interacting. Those dev runs are excluded BY NAME because
    they record an absolute username path; the exclusion named `metrics.json` and
    `predictions.jsonl`, and a later force-include of `outputs/**` reached underneath
    it. All of the copyright exposure and none of the reproducibility benefit.

    Checked against the INDEX rather than the working tree: an in-progress run on disk
    is fine and expected, a committed one is not.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "data/runs"], cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    have: dict[str, set] = {}
    for f in tracked:
        parts = f.split("/")
        if len(parts) >= 4:                      # data/runs/<id>/<file...>
            have.setdefault(parts[2], set()).add(parts[3])
    bad = sorted(r for r, files in have.items() if "metrics.json" not in files)

    # AND THE OTHER RUN DIRECTORIES, which V1 never looked at. `data/runs-rescored`,
    # `-reparsed`, `-pair` and `-repeats` are all committed and all cited by reports,
    # and nothing validated them at all. Found by external review.
    for extra in ("runs-rescored", "runs-reparsed", "runs-pair", "runs-repeats"):
        base = ROOT / "data" / extra
        if not base.is_dir():
            continue
        tracked_x = subprocess.run(
            ["git", "ls-files", f"data/{extra}"], cwd=ROOT, capture_output=True, text=True,
        ).stdout.split()
        seen: dict[str, set] = {}
        for f in tracked_x:
            parts = f.split("/")
            if len(parts) >= 4:
                seen.setdefault(parts[2], set()).add(parts[3])
        bad += [f"{extra}/{r}" for r, files in sorted(seen.items())
                if "metrics.json" not in files]
    for x in bad[:10]:
        print(f"       {x}")
    if len(bad) > 10:
        print(f"       ... and {len(bad) - 10} more")
    check(not bad, "V7 every committed run has metrics.json",
          f"{len(bad)} run(s) committed as outputs only")


def main() -> int:
    # `--help` prints help. It used to fall through and run the whole validation, which
    # made self_test's `validate_tree.py --help` check assert "the tree is valid" instead
    # of "the CLI responds" — so the one script whose failure matters most had a self-test
    # that could only pass when it had nothing to report.
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return 0
    print(f"eval tree: {ROOT / 'data'}\n")
    for fn in (v1_schemas, v2_dataset_ids, v3_provenance, v4_materialized,
               v5_duplicate_scores, v6_baselines, v7_committed_runs_are_readable):
        fn()
    for n in notes:
        print(f"\n  note: {n}")
    if problems:
        print(f"\nVALIDATION FAILED — {len(problems)} check(s): {', '.join(problems)}")
        return 1
    print("\nVALIDATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
