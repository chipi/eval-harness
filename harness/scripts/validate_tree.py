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
  V7  readable       a committed run with no metrics.json
  V8  config_ids     two run directories claiming the same (dataset_id, config_id)
  V9  present        a committed run deleted from disk, or a directory below its floor
  V10 scorer drift   a DERIVED run naming a scorer that is not the code in this tree

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


def v9_no_committed_evidence_is_missing() -> None:
    """Every run git has must still be on disk, with its files. Deleting evidence passed.

    V7 reads the git INDEX, V1 validates `data/runs` only, and the arm-row check skips
    arms it cannot find -- so `rm -rf data/runs/sf_mpnet_*` left `make ci` green and
    43/43 claims verified. A repo whose argument is "check the instrument" could lose a
    quarter of its evidence without a single red line. Found by external review.

    Floors as well as presence: a directory could be emptied one run at a time and each
    individual absence explained away.
    """
    #: What each committed runs directory must contain. Raising one of these is a
    #: deliberate edit; lowering one should need an argument.
    #: `runs-linux` is here because it was NOT, and nothing else reached it either: the
    #: re-timed latency figures in three reports come out of it, six documents cite it,
    #: and `grep -n runs-linux scripts/*.py` returned nothing. Deleting the directory
    #: that nine published latency numbers rest on passed every check. Found reviewing
    #: the merged ML-arm work, which is the same defect round 4 found one directory over.
    FLOORS = {"runs-reparsed": 19, "runs-rescored": 28, "runs-pair": 4, "runs-repeats": 3,
              "runs-linux": 9}

    tracked = subprocess.run(
        ["git", "ls-files", "data/runs", "data/runs-rescored", "data/runs-reparsed",
         "data/runs-pair", "data/runs-repeats", "data/runs-linux"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    missing, incomplete = [], []
    seen: dict = {}
    for f in tracked:
        parts = f.split("/")
        if len(parts) < 4:
            continue
        run_dir = ROOT / parts[0] / parts[1] / parts[2]
        seen.setdefault(f"{parts[1]}/{parts[2]}", set()).add(parts[3])
        if not (ROOT / f).exists():
            missing.append(f)
    # PRESENCE IS NOT CONTENT. `: > predictions.jsonl` left the file tracked, present
    # and zero bytes, and V9 said "every committed run file is present on disk" while
    # the arm-row scan read `metrics.json` and reported 53/53. The evidence a run IS is
    # its rows; a run whose rows are gone is deleted whatever the directory listing
    # says. Found by external review, round 5.
    for key, files in sorted(seen.items()):
        if "metrics.json" not in files:
            continue                       # V7's business, not this one
        if "predictions.jsonl" not in files:
            incomplete.append(f"{key} has no predictions.jsonl")
            continue
        _pj = ROOT / "data" / key / "predictions.jsonl"
        _mj = ROOT / "data" / key / "metrics.json"
        if not _pj.is_file() or not _mj.is_file():
            continue                       # already counted as missing above
        try:
            _rows = sum(1 for _l in _pj.read_text(encoding="utf-8").splitlines()
                        if _l.strip())
            _want = int(read_json(_mj).get("n_items") or 0)
        except (OSError, ValueError, TypeError):
            incomplete.append(f"{key} predictions.jsonl is unreadable")
            continue
        if _rows == 0:
            incomplete.append(f"{key} predictions.jsonl is empty")
        elif _want and _rows != _want:
            incomplete.append(f"{key} has {_rows} prediction rows, "
                              f"metrics.json says n_items={_want}")
    for x in (missing[:5] + incomplete[:5]):
        print(f"       {x}")
    if len(missing) > 5:
        print(f"       ... and {len(missing) - 5} more missing files")
    check(not missing and not incomplete,
          "V9 every committed run file is on disk, with its rows",
          f"{len(missing)} tracked file(s) missing, {len(incomplete)} run(s) incomplete")

    short = []
    for name, floor in sorted(FLOORS.items()):
        base = ROOT / "data" / name
        n = len([d for d in base.glob("*/metrics.json")]) if base.is_dir() else 0
        if n < floor:
            short.append(f"{name}: {n} runs, expected at least {floor}")
    for x in short:
        print(f"       {x}")
    check(not short, "V9 each committed runs directory meets its floor",
          "; ".join(short))


def v10_derived_runs_carry_the_current_scorer() -> None:
    """A run that CLAIMS to be a product of the current code must carry ALL its hashes.

    `runs-rescored` and `runs-reparsed` exist to be re-derivable for $0, and each run in
    them records the scorer it was derived with. Nothing ever compared those to the code
    in the tree, so a change to `_shared/extraction.py` or `_shared/retrieval.py` left
    every stored figure attributed to a scorer that no longer exists, with `make ci`
    green.

    THE FIRST VERSION OF THIS CHECK COMPARED ONE HASH OF THREE. A rescored run records
    `scorer_sha256`, `normalizer_sha256` AND `parser_sha256`; V10 read only the first,
    which is `extraction.scorer_sha256` -- the set-F1 rule. So changing the NER PARSER
    left V10 green, and the parser is the component that produced every number in
    `runs-rescored`, the component whose bugs rounds 2, 3 and 4 all found, and the
    component that changed in the very commit V10 shipped in. The can-fail guard planted
    `_ARTICLES`, a constant of the set scorer, so it proved V10 could see `extraction.py`
    and nothing whatever about the parser. Every key the run stores is now compared.
    Found by external review, round 5.

    AN ABSENT FIELD IS A FAILURE HERE, NOT A SKIP. It used to print `skip` and pass, so
    deleting `rescored_with` from all 27 runs left VALIDATION PASSED -- the check
    vanishing exactly when the thing it reads is gone, which is what its own docstring
    said it must not do. A derived directory with runs in it must state its provenance.
    Only `data/runs` may be silent. Also round 5.

    `data/runs` is a NOTE, never a failure. Those runs legitimately carry the hash they
    were measured with -- recording it is the entire point.

    An adapter whose dependencies are absent is a named skip, printed, not silence.
    """
    #: (directory, glob, where the run states its hashes, module, callable).
    #: The callable returns either a str (one hash) or a dict of named hashes, and
    #: EVERY key of that dict is compared -- naming one key here is how the parser went
    #: unwatched. `data/runs` predates `scorer_sha256` and states `parser_sha256` alone,
    #: under `system_under_test.model`, so that is what is compared there.
    SOURCES = (
        ("runs-rescored", "*", ("rescored_with", "scorer"),
         "examples/ner-few-nerd", "adapter", "scorer_id"),
        ("runs-reparsed", "*", ("reparsed_with", "scorer_sha256"),
         "examples/_shared", "retrieval", "scorer_sha256"),
        ("runs", "fn_*", ("fingerprint", "system_under_test", "model", "parser_sha256"),
         "examples/ner-few-nerd", "adapter", "scorer_id"),
    )

    def _dig(d, path):
        for k in path:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return d

    for directory, pat, path, modpath, modname, fn in SOURCES:
        base = ROOT / "data" / directory
        if not base.is_dir():
            continue
        runs = sorted(base.glob(f"{pat}/metrics.json"))
        if not runs:
            continue
        sys.path.insert(0, str(ROOT.parent / modpath))
        try:
            mod = __import__(modname)
            current = getattr(mod, fn)()
        except Exception as exc:  # noqa: BLE001 — an absent example dep is a named skip
            print(f"  skip V10 {directory}: {modname}.{fn} not importable "
                  f"({type(exc).__name__}: {str(exc)[:60]})")
            continue
        # A str at the end of `path` is one hash; a dict is a set of named ones. When
        # the run states a dict, compare every key it and the code have in common --
        # and refuse if they have none, because that is the same blindness by another
        # route.
        if isinstance(current, dict) and path[-1] in current:
            current = {path[-1]: current[path[-1]]}   # the run names ONE of them
        checked, stale, silent, keys = 0, [], [], set()
        for mj in runs:
            rec = _dig(read_json(mj), path)
            if rec is None:
                silent.append(mj.parent.name)
                continue
            checked += 1
            if isinstance(rec, str):
                pairs = {path[-1]: rec}
                want = current if isinstance(current, str) else current.get(path[-1])
                want = {path[-1]: want}
            else:
                pairs = {k: v for k, v in rec.items() if isinstance(v, str)}
                want = current if isinstance(current, dict) else {}
            shared = sorted(set(pairs) & set(want))
            keys.update(shared)
            if not shared:
                silent.append(f"{mj.parent.name} (states {sorted(pairs)}, code offers "
                              f"{sorted(want)})")
                continue
            for k in shared:
                if pairs[k] != want[k]:
                    stale.append(f"{mj.parent.name} {k} {pairs[k][:12]}")
        label = (f"V10 {directory}: {', '.join(sorted(keys))} match the code "
                 f"({checked} run(s))" if keys
                 else f"V10 {directory}: a scorer hash was compared at all")

        if directory == "runs":
            # Measurement runs SHOULD carry the hash of their own day. A note, not a gate.
            if stale:
                notes.append(f"{len(stale)} of {checked} run(s) in data/runs were "
                             f"measured with a scorer that is not the current one "
                             f"(expected; the hash is the record)")
            print(f"  ok   {label} — {checked - len(stale)} current, "
                  f"{len(stale)} historical")
            continue

        # A DERIVED RUN THAT STATES NOTHING IS A FAILURE. Skipping here is how the
        # check disappears at the moment it matters.
        for x in silent[:5]:
            print(f"       {x} states no hash at {'.'.join(path)}")
        check(not silent, f"V10 {directory}: every run states its scorer",
              f"{len(silent)} of {len(runs)} run(s) record nothing at "
              f"{'.'.join(path)} — a derived run must say what derived it")
        for x in stale[:5]:
            print(f"       {x} != the code")
        check(not stale and checked > 0, label,
              f"{len(stale)} mismatch(es) over {checked} derived run(s)"
              if stale else "no run was compared at all")


def v8_no_duplicate_config_ids() -> None:
    """No two run directories may claim the same (dataset_id, config_id).

    This is the round-3 ext4 failure made structural. `check_report_claims.py` globs
    for a run in SIX places and only one of them goes through `runs_by_arm`, which is
    the function that refuses ambiguity -- so copying a second SciFact run back into
    data/runs passes 33/33 in BOTH listing orders while two of its internal lookups
    silently disagree about which run they mean. Two defects were masking each other:
    the cost row that would have caught it was being skipped for an unrelated reason.

    Routing five more globs through `runs_by_arm` would fix those five. This forbids
    the situation instead, which is one rule in one place and covers every tool that
    has not been written yet.

    `--repeat N` writes `<id>_r1.._rN`: one arm measured N times, averaged on purpose,
    and not ambiguous.
    """
    import re as _re  # noqa: PLC0415

    #: The directories whose runs back a report. Scratch dirs (runs-smoke, runs-tune,
    #: runs-superseded) are gitignored working artifacts where repeats are normal.
    # `runs-linux` was omitted when it was added, so the sixth committed directory was
    # the one place a duplicate config_id could still land -- and the latency claims read
    # it by filesystem order, so a duplicate changed the answer depending on how the
    # names sorted. That is the round-3 ext4 defect in the sixth directory. Round 5.
    COMMITTED = ("runs", "runs-rescored", "runs-reparsed", "runs-pair", "runs-repeats",
                 "runs-linux")
    #: One documented exception. `demo_v1` on `smoke_v1` is the bundled demo, run many
    #: times by `make demo` and by the self-test; smoke_v1 is not an experiment and no
    #: report cites it. Named here rather than scoped away silently, so that adding a
    #: second exception is a deliberate edit someone has to justify.
    ALLOWED = {("smoke_v1", "demo_v1")}

    bad = []
    for base in [(ROOT / "data" / n) for n in COMMITTED]:
        if not base.is_dir():
            continue
        groups: dict = {}
        for mj in sorted(base.glob("*/metrics.json")):
            try:
                m = json.loads(mj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key = (m.get("dataset_id"), m.get("config_id"))
            if key[1]:
                groups.setdefault(key, []).append(mj.parent.name)
        for (ds, cid), names in sorted(groups.items()):
            if len(names) < 2:
                continue
            stems = {_re.sub(r"_r\d+$", "", n) for n in names}
            if len(stems) == 1 and all(_re.search(r"_r\d+$", n) for n in names):
                continue
            if (ds, cid) in ALLOWED:
                notes.append(f"{base.name}/: {len(names)} {cid!r} runs on {ds} "
                             f"(allowed: the bundled demo, cited by no report)")
                continue
            bad.append(f"{base.name}/: {len(names)} runs claim {cid!r} on {ds} "
                       f"— {', '.join(sorted(names))}")
    for x in bad[:6]:
        print(f"       {x}")
    if len(bad) > 6:
        print(f"       ... and {len(bad) - 6} more")
    check(not bad, "V8 no two runs share a config_id (outside a --repeat set)",
          f"{len(bad)} ambiguous config_id(s)")


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
               v5_duplicate_scores, v6_baselines, v7_committed_runs_are_readable,
               v8_no_duplicate_config_ids,
               v9_no_committed_evidence_is_missing,
               v10_derived_runs_carry_the_current_scorer):
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
