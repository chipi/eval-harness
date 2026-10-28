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
  V11 judging sets   a frozen judging set whose stored hash is not its content's hash
  V12 verdicts       a stored judge verdict naming a set, item, pass or block that does not
                     exist, or whose `n` is not that block's size
  V13 judge scorers  a scorer yaml that does not load or fails judge_score's structure checks
  V14 goals          a goal that breaks its schema; a config, run or baseline naming a goal that
                     does not exist, or a format its goal does not accept; a run created on or
                     after data/goals/policy.yaml's `required_from` that names no goal
  V15 item fields    a field set that breaks its schema; a dataset naming a field set that does
                     not exist, or carrying fields without one; a value of an undeclared field,
                     of the wrong type or outside its choices; a required field with no value;
                     a fields_sha256 that is not the hash of the fields
  V16 references     a reference whose manifest breaks its schema, whose texts differ from the
                     checksums it records, or whose committed texts are missing (a manifest
                     with no texts and `redistributed: false` is a reference fetched elsewhere)

Exit 1 on any failure, so it can gate.

    python scripts/validate_tree.py
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from evaluation_harness._common import (
    BASELINES,
    CONFIGS,
    DATA,
    DATASETS,
    FIELDS,
    GOALS,
    MATERIALIZED,
    ROOT,
    RUNS,
    SCHEMAS,
    data_rel,
    goal_policy,
    load_goals,
    load_module,
    lower_is_better,
    no_options,
    read_json,
    sha256,
)
from evaluation_harness._runs import recorded_direction
from evaluation_harness.axes import axes_of

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]  # V1 is then skipped, and says why

problems: list[str] = []
notes: list[str] = []

#: The bundled demo: `demo_v1` on `smoke_v1` is run many times by `make demo` and by the
#: self-test, smoke_v1 is not an experiment, and no report cites it. A project adds its own
#: exceptions in `duplicate_ok`, each one a deliberate, justified edit.
_DEMO_DUPLICATE = ("smoke_v1", "demo_v1")


def policy() -> dict:
    """<data>/validate.json: what this project's validate holds it to (committed run
    directories, floors, scorer sources, duplicate exceptions). These were this
    repository's directory names and example paths written into the validator, so a pinned
    project's own `runs-adjudicated` was never checked while six names it does not have were.
    """
    f = DATA / "validate.json"
    return dict(read_json(f)) if f.is_file() else {}


def committed_dirs() -> list[str]:
    """The run directories that back the project's claims: `committed` in validate.json,
    else every git-tracked <data>/runs* directory holding a run."""
    declared = policy().get("committed")
    if declared:
        return list(declared)
    tracked = subprocess.run(
        ["git", "ls-files", data_rel(DATA)], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    prefix = data_rel(DATA).rstrip("/") + "/"
    names = set()
    for f in tracked:
        parts = f[len(prefix) :].split("/") if f.startswith(prefix) else []
        if len(parts) >= 3 and parts[0].startswith("runs") and parts[2] == "metrics.json":
            names.add(parts[0])
    return sorted(names)


def check(label: str, ok: object, detail: str = "") -> None:
    """Log a check result and append to problems if it failed."""
    if ok:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
        problems.append(label)


def v1_schemas() -> None:
    """V1: every document matches its schema."""
    if jsonschema is None:
        notes.append("V1 skipped: jsonschema not installed (pip install -r requirements.txt)")
        print("  --   V1 schemas (jsonschema not installed)")
        return
    import yaml  # noqa: PLC0415

    pairs = [
        (DATASETS.glob("*.json"), "dataset.schema.json"),
        (
            (r / "metrics.json" for _, r in all_runs() if (r / "metrics.json").is_file()),
            "metrics.schema.json",
        ),
        (BASELINES.glob("*.json"), "baseline.schema.json"),
        (CONFIGS.glob("*.yaml"), "config.schema.json"),
        ((DATA / "scorers").glob("*.yaml"), "scorer.schema.json"),
        ((DATA / "judging-sets").glob("*.json"), "judging-set.schema.json"),
        ((DATA / "judge-verdicts").glob("*/*/*/*.json"), "verdict.schema.json"),
        ([DATA / "models.yaml"], "models.schema.json"),
        ((DATA / "profiles").glob("*.json"), "profile.schema.json"),
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
                doc = yaml.safe_load(f.read_text(encoding="utf-8")) if f.suffix == ".yaml" else read_json(f)
                jsonschema.validate(doc, schema)
            except jsonschema.ValidationError as exc:
                bad += 1
                print(f"       {data_rel(f)}: {exc.message[:90]}")
            except (ValueError, yaml.YAMLError) as exc:
                bad += 1
                print(f"       {data_rel(f)}: does not parse ({type(exc).__name__})")
    check(f"V1 schemas — {n} document(s) validated", bad == 0, f"{bad} violation(s)")


def v2_dataset_ids() -> None:
    """V2: every run's dataset_id resolves to an existing dataset, and so does every dataset's
    `derived_from` (the version it was made from)."""
    known = {p.stem for p in DATASETS.glob("*.json")}
    dangling = []
    for label, run in all_runs():
        m = run / "metrics.json"
        if m.is_file():
            did = read_json(m).get("dataset_id")
            if did not in known:
                dangling.append(f"{label} -> {did}")
    for p in sorted(DATASETS.glob("*.json")):
        try:
            parent = (read_json(p).get("derived_from") or {}).get("dataset_id")
        except ValueError:
            continue  # V1 names a file that does not parse
        if parent and parent not in known:
            dangling.append(f"dataset {p.stem} derived from {parent}, which does not exist")
    for d in dangling:
        print(f"       {d}")
    check(
        f"V2 every run's dataset_id resolves ({len(known)} dataset(s) known)",
        not dangling,
        f"{len(dangling)} dangling",
    )


def v3_provenance() -> None:
    """V3: every run identifies its build ref."""
    missing = []
    for label, run in all_runs():
        m = run / "metrics.json"
        if m.is_file():
            b = read_json(m).get("build") or {}
            if b.get("ref", "unknown") == "unknown":
                missing.append(label)
    for r in missing:
        print(f"       {r}")
    check("V3 every run identifies its build", not missing, f"{len(missing)} without a ref")


def v4_materialized() -> None:
    """Every item of every materialized copy is there and has its frozen hash. A dataset with
    no copy here (materialized data is not committed, so CI has none) is not checked, and the
    output says so by name: the check used to print `ok` for it, and for a copy that had lost
    files, which is green for something never looked at."""
    drifted, missing, unchecked, checked = [], [], [], 0
    for ds_file in sorted(DATASETS.glob("*.json")):
        ds = read_json(ds_file)
        mat = MATERIALIZED / ds["dataset_id"]
        if not mat.is_dir():
            unchecked.append(ds["dataset_id"])
            continue
        checked += 1
        for item in ds["items"]:
            rel = item.get("source_path") or item["item_id"]
            f = mat / rel
            if not f.is_file():
                missing.append(f"{ds['dataset_id']}/{rel}")
            elif sha256(f) != item["source_sha256"]:
                drifted.append(f"{ds['dataset_id']}/{rel}")
    for d in drifted:
        print(f"       drifted: {d}")
    for d in missing:
        print(f"       missing: {d}")
    total = checked + len(unchecked)
    check(
        f"V4 materialized copies match their frozen hashes ({checked} of {total} datasets materialized here)",
        not drifted and not missing,
        f"{len(drifted)} drifted, {len(missing)} missing",
    )
    if unchecked:
        print(f"       not checked (no materialized copy here): {', '.join(unchecked)}")


#: Excluded from the V5 duplicate key: wall-clock and spend are properties of the RUN, not
#: of what the arm produced. Including them made the check unfireable — two arms agreeing to
#: full precision on every measured metric still keyed differently because their latencies
#: differed by microseconds. Measured on this tree: arm_a_v1 and arm_short_v1 both scored
#: overlap_f1 0.135256 and output_words 3.6, and V5 reported OK.
_V5_RUN_PROPERTIES = (
    "latency_ms",
    "cost_usd",
    "total_cost_usd",
    "tokens_in",
    "tokens_out",
    "total_tokens_in",
    "total_tokens_out",
)


def _outputs_signature(run: Path) -> str:
    """A digest of what a run wrote (outputs/<item>.txt, by name). Runs without outputs all
    share one value: what they wrote cannot tell them apart, so it excuses nothing."""
    outs = sorted((run / "outputs").glob("*.txt")) if (run / "outputs").is_dir() else []
    if not outs:
        return "<no-outputs>"
    h = hashlib.sha256()
    for f in outs:
        h.update(f.name.encode() + b"\0" + f.read_bytes() + b"\x1e")
    return h.hexdigest()


def _per_item_signature(run_name: str | Path) -> str:
    """A stable digest of one run's per-item scores, for telling ties from copies.

    Run-level properties are excluded for the same reason they are excluded from the key
    above: a fabricated result differs in latency like any other. A run with no readable
    predictions returns its own name, so it can never match another run -- an unreadable
    file is a reason to say nothing, not a reason to accuse.
    """
    path = (
        run_name / "predictions.jsonl"
        if isinstance(run_name, Path)
        else RUNS / run_name / "predictions.jsonl"
    )
    if not path.is_file():
        return f"<no-predictions:{run_name}>"
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            scored = {k: v for k, v in row.items() if k not in _V5_RUN_PROPERTIES and k != "_meta"}
            rows.append(json.dumps(scored, sort_keys=True))
    except (OSError, ValueError):
        return f"<unreadable:{run_name}>"
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def v5_duplicate_scores() -> None:
    """V5: no two runs in one directory report byte-identical scores and per-item results.
    Within a directory: a rescore that left a run's scores as they were is identical to its
    source in runs/ by design."""
    dupes: list[list] = []
    for base in run_bases():
        dupes += _v5_in(base)
    for group in dupes:
        print(
            f"       identical scores AND identical per-item results: {', '.join(str(n) for n, _, _ in group)}"
        )
    check(
        "V5 no two configs report byte-identical scores",
        not dupes,
        f"{len(dupes)} suspicious group(s) — differing params produced identical output",
    )


def _v5_in(base: Path) -> list[list]:
    by_key = defaultdict(list)
    for run in sorted(base.iterdir()):
        m = run / "metrics.json"
        if m.is_file():
            d = read_json(m)
            # Compare what the arm PRODUCED. A fabricated or copy-pasted result differs in
            # latency like any other, so keying on it let exactly the case this check exists
            # for slip through.
            produced = {k: v for k, v in (d.get("scores") or {}).items() if k not in _V5_RUN_PROPERTIES}
            key = (d.get("dataset_id"), json.dumps(produced, sort_keys=True))
            by_key[key].append((run, d.get("config_id"), json.dumps(d.get("params") or {}, sort_keys=True)))
    # Identical scores from identical params is not suspicious — it is what a deterministic
    # arm DOES, and two configs may legitimately request the same thing. What deserves a look
    # is DIFFERENT params landing on byte-identical output: either a result was not measured,
    # or the knobs that differ are inert.
    dupes: list[list] = []
    for group in by_key.values():
        known = group
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
            # A SATURATED METRIC AGREES ITEM BY ITEM TOO. Two different routers that both label
            # all 32 messages right score 1.0 on every item; what tells them apart is what they
            # wrote. Different outputs are two measurements; identical outputs from different
            # params are the copied result or the inert knob this check is for.
            if len({_outputs_signature(n) for n, _, _ in known}) > 1:
                continue
            dupes.append([(f"{base.name}/{n.name}", c, p) for n, c, p in known])
    return dupes


def v6_baselines() -> None:
    """V6: every baseline's promoted_from run still exists, and the baseline still says what
    it says: the tier, adapter, fingerprint, goal and format it carried from that run."""
    from evaluation_harness.promote_baseline import carried  # noqa: PLC0415

    broken = []
    for b in sorted(BASELINES.glob("*.json")):
        d = read_json(b)
        src = next(
            (
                base / d.get("promoted_from", "")
                for base in run_bases()
                if (base / d.get("promoted_from", "")).is_dir()
            ),
            None,
        )
        if src is None:
            broken.append(f"{b.name} -> {d.get('promoted_from')}: no such run")
            continue
        m = read_json(src / "metrics.json") if (src / "metrics.json").is_file() else {}
        for k, v in carried(m).items():
            if d.get(k) != v:
                broken.append(f"{b.name}: {k} is {d.get(k)!r}, its run records {v!r}")
    for x in broken:
        print(f"       {x}")
    check(
        "V6 every baseline's source run still exists and matches what the baseline carries",
        not broken,
        f"{len(broken)} broken",
    )


def run_bases() -> list[Path]:
    """The runs directory and every committed run directory, each once. V1-V3, V5 and V14
    read RUNS alone, so the derived directories reports cite (68 runs here) were never
    schema- or integrity-checked while the RUNBOOK said every run was."""
    out, seen = [], set()
    for base in [RUNS, *(DATA / d for d in committed_dirs())]:
        key = base.resolve()
        if base.is_dir() and key not in seen:
            seen.add(key)
            out.append(base)
    return out


def all_runs() -> list[tuple[str, Path]]:
    """(label, run directory) for every run in run_bases(), labelled `<dir>/<run>` outside RUNS."""
    out = []
    for base in run_bases():
        prefix = "" if base.resolve() == RUNS.resolve() else f"{base.name}/"
        out += [(f"{prefix}{r.name}", r) for r in sorted(base.iterdir()) if r.is_dir()]
    return out


def _tracked_runs(runs_dir: Path) -> dict:
    """{run id: names of its tracked top-level entries}, from the git INDEX, for a runs
    directory wherever the data root sits (<runs dir>/<run id>/<file...>)."""
    prefix = data_rel(runs_dir).rstrip("/") + "/"
    tracked = subprocess.run(
        ["git", "ls-files", prefix], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    out: dict = {}
    for f in tracked:
        if not f.startswith(prefix):
            continue
        parts = f[len(prefix) :].split("/")
        if len(parts) >= 2:
            out.setdefault(parts[0], set()).add(parts[1])
    return out


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
    have = _tracked_runs(RUNS)
    bad = sorted(r for r, files in have.items() if "metrics.json" not in files)

    # AND THE OTHER RUN DIRECTORIES, which V1 never looked at. Here `data/runs-rescored`,
    # `-reparsed`, `-pair` and `-repeats` are all committed and all cited by reports,
    # and nothing validated them at all. Found by external review.
    for extra in committed_dirs():
        base = DATA / extra
        if not base.is_dir() or base.resolve() == RUNS.resolve():
            continue
        seen = _tracked_runs(base)
        bad += [f"{extra}/{r}" for r, files in sorted(seen.items()) if "metrics.json" not in files]
    for x in bad[:10]:
        print(f"       {x}")
    if len(bad) > 10:
        print(f"       ... and {len(bad) - 10} more")
    check(
        "V7 every committed run has metrics.json",
        not bad,
        f"{len(bad)} run(s) stopped before they finished (outputs, no metrics.json): resume each with experiment-run --resume <run_id>, or delete it",
    )


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
    # The floors are PROJECT policy: how many runs each committed directory must keep is
    # a fact about one project's evidence, not about the harness. They are read from
    # <data>/validate.json (`policy`); a project without them has no floors (V9's
    # missing-file and empty-rows checks still apply).
    FLOORS = policy().get("floors") or {}

    listed = subprocess.run(
        [
            "git",
            "ls-files",
            *(data_rel(DATA / d) for d in committed_dirs()),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tracked = listed.stdout.split()
    missing, incomplete = [], []
    # A git that refuses (a path outside the repository) lists nothing, and nothing listed
    # read as nothing missing: V9 passed a run with no rows. Outside any repository nothing is
    # committed, and that is said, not passed.
    no_repo = False
    if listed.returncode != 0:
        no_repo = (
            subprocess.run(
                ["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True, text=True
            ).returncode
            != 0
        )
        if not no_repo:
            incomplete.append(
                f"git ls-files failed, so nothing committed was checked: {listed.stderr.strip()[:300]}"
            )
    seen: dict = {}
    data_prefix = data_rel(DATA).rstrip("/") + "/"
    for f in tracked:
        # <data root>/<runs dir>/<run id>/<file>, wherever the data root sits.
        if not f.startswith(data_prefix):
            continue
        parts = f[len(data_prefix) :].split("/")
        if len(parts) < 3:
            continue
        seen.setdefault(f"{parts[0]}/{parts[1]}", set()).add(parts[2])
        if not (ROOT / f).exists():
            missing.append(f)
    # PRESENCE IS NOT CONTENT. `: > predictions.jsonl` left the file tracked, present
    # and zero bytes, and V9 said "every committed run file is present on disk" while
    # the arm-row scan read `metrics.json` and reported 53/53. The evidence a run IS is
    # its rows; a run whose rows are gone is deleted whatever the directory listing
    # says. Found by external review, round 5.
    for key, files in sorted(seen.items()):
        if "metrics.json" not in files:
            continue  # V7's business, not this one
        if "predictions.jsonl" not in files:
            incomplete.append(f"{key} has no predictions.jsonl")
            continue
        _pj = DATA / key / "predictions.jsonl"
        _mj = DATA / key / "metrics.json"
        if not _pj.is_file() or not _mj.is_file():
            continue  # already counted as missing above
        try:
            _rows = sum(1 for _l in _pj.read_text(encoding="utf-8").splitlines() if _l.strip())
            _want = int(read_json(_mj).get("n_items") or 0)
        except (OSError, ValueError, TypeError):
            incomplete.append(f"{key} predictions.jsonl is unreadable")
            continue
        if _rows == 0:
            incomplete.append(f"{key} predictions.jsonl is empty")
        elif _want and _rows != _want:
            incomplete.append(f"{key} has {_rows} prediction rows, metrics.json says n_items={_want}")
    for x in missing[:5] + incomplete[:5]:
        print(f"       {x}")
    if len(missing) > 5:
        print(f"       ... and {len(missing) - 5} more missing files")
    if no_repo:
        print("  --   V9 committed run files (not a git repository: nothing is committed)")
    else:
        check(
            "V9 every committed run file is on disk, with its rows",
            not missing and not incomplete,
            f"{len(missing)} tracked file(s) missing, {len(incomplete)} run(s) incomplete",
        )

    short = []
    for name, floor in sorted(FLOORS.items()):
        base = DATA / name
        n = len(list(base.glob("*/metrics.json"))) if base.is_dir() else 0
        if n < floor:
            short.append(f"{name}: {n} runs, expected at least {floor}")
    for x in short:
        print(f"       {x}")
    check("V9 each committed runs directory meets its floor", not short, "; ".join(short))


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
    #: Declared per project in validate.json `scorer_sources`; a project without them has
    #: nothing for V10 to compare.
    SOURCES = [
        (src["dir"], src["glob"], tuple(src["path"]), src["module"], src["callable"])
        for src in policy().get("scorer_sources") or []
    ]

    def _dig(d, path):
        for k in path:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return d

    for directory, pat, path, modfile, fn in SOURCES:
        base = DATA / directory
        if not base.is_dir():
            continue
        runs = sorted(base.glob(f"{pat}/metrics.json"))
        if not runs:
            continue
        # By path, never by `import adapter`: every example's adapter is `adapter.py`, so a
        # name import returns whichever one this process loaded first.
        modpath = (ROOT / modfile).resolve()
        sys.path.insert(0, str(modpath.parent))  # the module's own siblings (_shared, ...)
        try:
            mod = load_module(
                modpath, f"validate_v10_{hashlib.sha256(str(modpath).encode()).hexdigest()[:12]}"
            )
            current = getattr(mod, fn)()
        except Exception as exc:  # noqa: BLE001 — an absent example dep is a named skip
            print(
                f"  skip V10 {directory}: {modpath.stem}.{fn} not importable "
                f"({type(exc).__name__}: {str(exc)[:60]})"
            )
            continue
        # A str at the end of `path` is one hash; a dict is a set of named ones. When
        # the run states a dict, compare every key it and the code have in common --
        # and refuse if they have none, because that is the same blindness by another
        # route.
        if isinstance(current, dict) and path[-1] in current:
            current = {path[-1]: current[path[-1]]}  # the run names ONE of them
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
                silent.append(f"{mj.parent.name} (states {sorted(pairs)}, code offers {sorted(want)})")
                continue
            for k in shared:
                if pairs[k] != want[k]:
                    stale.append(f"{mj.parent.name} {k} {pairs[k][:12]}")
        label = (
            f"V10 {directory}: {', '.join(sorted(keys))} match the code ({checked} run(s))"
            if keys
            else f"V10 {directory}: a scorer hash was compared at all"
        )

        # A DERIVED RUN THAT STATES NOTHING IS A FAILURE. Skipping here is how the
        # check disappears at the moment it matters.
        for x in silent[:5]:
            print(f"       {x} states no hash at {'.'.join(path)}")
        check(
            f"V10 {directory}: every run states its scorer",
            not silent,
            f"{len(silent)} of {len(runs)} run(s) record nothing at "
            f"{'.'.join(path)} — a derived run must say what derived it",
        )
        for x in stale[:5]:
            print(f"       {x} != the code")
        check(
            label,
            not stale and checked > 0,
            f"{len(stale)} mismatch(es) over {checked} derived run(s)"
            if stale
            else "no run was compared at all",
        )


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

    #: The directories whose runs back a report. Scratch dirs (runs-smoke, runs-tune)
    #: are gitignored working artifacts where repeats are normal.
    # `runs-linux` was omitted when it was added, so the sixth committed directory was
    # the one place a duplicate config_id could still land -- and the latency claims read
    # it by filesystem order, so a duplicate changed the answer depending on how the
    # names sorted. That is the round-3 ext4 defect in the sixth directory. Round 5.
    COMMITTED = committed_dirs()
    #: The bundled demo, plus the project's own `duplicate_ok`: named, never scoped away
    #: silently, so that adding an exception is a deliberate edit someone has to justify.
    ALLOWED = {_DEMO_DUPLICATE, *(tuple(x) for x in policy().get("duplicate_ok") or [])}

    bad = []
    for base in [(DATA / n) for n in COMMITTED]:
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
                notes.append(
                    f"{base.name}/: {len(names)} {cid!r} runs on {ds} "
                    f"(allowed: {'the bundled demo, cited by no report' if (ds, cid) == _DEMO_DUPLICATE else 'duplicate_ok in validate.json'})"
                )
                continue
            bad.append(f"{base.name}/: {len(names)} runs claim {cid!r} on {ds} — {', '.join(sorted(names))}")
    for x in bad[:6]:
        print(f"       {x}")
    if len(bad) > 6:
        print(f"       ... and {len(bad) - 6} more")
    check(
        "V8 no two runs share a config_id (outside a --repeat set)",
        not bad,
        f"{len(bad)} ambiguous config_id(s)",
    )


def judging_set_problems(sets_dir: Path) -> list[str]:
    """Every judging-set manifest: id matches its file name and the stored hash is the
    hash of the content. A set is frozen; an edit in place is what this catches."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    bad = []
    for f in sorted(sets_dir.glob("*.json")):
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            bad.append(f"{f.name}: unreadable ({exc})")
            continue
        if m.get("judging_set_id") != f.stem:
            bad.append(f"{f.name}: judging_set_id is {m.get('judging_set_id')!r}")
        want = js.manifest_hash(m)
        if m.get("judging_set_sha256") != want:
            bad.append(
                f"{f.name}: stored hash {str(m.get('judging_set_sha256'))[:12]} != recomputed {want[:12]}"
            )
        elif not f.stem.endswith(want[:12]):
            bad.append(f"{f.name}: id does not end in the content hash {want[:12]}")
    return bad


def verdict_problems(verdicts_dir: Path, sets_dir: Path) -> list[str]:
    """Every verdict file under <scorer>/<set>/<judge>/: it names an existing set, an item
    of it, a pass, and a block of that item and pass, and its `n` is that block's size."""
    bad = []
    sets: dict = {}
    for f in sorted(verdicts_dir.glob("*/*/*/*.json")):
        scorer_dir, set_id = f.parts[-4], f.parts[-3]
        label = f"{scorer_dir}/{set_id}/{f.parent.name}/{f.name}"
        if set_id not in sets:
            sp = sets_dir / f"{set_id}.json"
            try:
                sets[set_id] = json.loads(sp.read_text(encoding="utf-8")) if sp.is_file() else None
            except (OSError, ValueError):
                sets[set_id] = None
        m = sets[set_id]
        if m is None:
            bad.append(f"{label}: judging set {set_id} does not exist (or is unreadable)")
            continue
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(f"{label}: unreadable")
            continue
        if v.get("set_id") != set_id:
            bad.append(f"{label}: set_id is {v.get('set_id')!r}")
        item = next((i for i in m.get("items", []) if i.get("item_id") == v.get("item_id")), None)
        if item is None:
            bad.append(f"{label}: item {v.get('item_id')!r} is not in the set")
            continue
        p = v.get("pass")
        if p not in ("primary", "position", "noise"):
            bad.append(f"{label}: unknown pass {p!r}")
            continue
        if p != "primary" and v["item_id"] not in m.get(f"{p}_items", []):
            bad.append(f"{label}: item is not in the set's {p}_items")
            continue
        blocks = item["position" if p == "position" else "primary"]
        b = v.get("block")
        if not isinstance(b, int) or isinstance(b, bool) or not 0 <= b < len(blocks):
            bad.append(f"{label}: block {b!r} does not exist ({len(blocks)} blocks)")
            continue
        if v.get("n") != len(blocks[b]):
            bad.append(f"{label}: n is {v.get('n')!r}, the block has {len(blocks[b])}")
        if f.name != f"{v['item_id']}.{p}.b{b}.json" or f.parent.name != v.get("judge"):
            bad.append(f"{label}: file location does not match its judge/item/pass/block")
        bad.extend(f"{label}: {p_}" for p_ in reply_problems(v))
    return bad


def reply_problems(rec: dict) -> list[str]:
    """A committed judge reply is bare JSON scores, or withheld (no text, its hash kept).
    A reply that reasons aloud can copy the article or the outputs it scored; the writers
    withhold those (judging.withheld_reason), and this catches one that slipped through."""
    from evaluation_harness.judging import json_only  # noqa: PLC0415

    out = rec.get("output")
    if out is None:
        if not (rec.get("output_withheld") and len(str(rec.get("output_sha256") or "")) == 64):
            return ["no reply text and not marked withheld with its sha256"]
        return []
    if not json_only(out):
        return [f"reply is not bare JSON ({len(out)} chars): withhold it, keep its hash"]
    return []


def validation_record_problems(validation_dir: Path) -> list[str]:
    """The same rule for the judge-validation records (<scorer>/<set>/<judge>/*.json)."""
    bad = []
    for f in sorted(validation_dir.glob("*/*/*/*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(f"{f.relative_to(validation_dir)}: unreadable")
            continue
        bad.extend(f"{f.relative_to(validation_dir)}: {p}" for p in reply_problems(rec))
    return bad


def scorer_problems(scorers_dir: Path) -> list[str]:
    """Every scorer yaml loads and is structurally sound. Not the paid gate: whether a
    scorer is VALIDATED is judge_score's `validation_problems`, and an unvalidated
    experiment scorer is allowed to exist."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    bad = []
    from yaml import YAMLError as yaml_error  # noqa: PLC0415

    for f in sorted(scorers_dir.glob("*.yaml")):
        try:
            sc = js.load_scorer(f)
            if sc["scorer_id"] != f.stem:
                bad.append(f"{f.name}: scorer_id is {sc['scorer_id']!r}")
            n = sc["protocol"].get("outputs_per_call")
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                bad.append(f"{f.name}: protocol.outputs_per_call must be a positive integer")
            ids = [j.get("id") for j in sc["judges"]]
            if len(set(ids)) != len(ids) or not all(ids):
                bad.append(f"{f.name}: judge ids must be present and unique")
            for j in sc["judges"]:
                pr = j.get("params") or {}
                for k in ("model", "usd_per_mtok_in", "usd_per_mtok_out"):
                    if pr.get(k) in (None, ""):
                        bad.append(f"{f.name}: judge {j.get('id')!r} has no params.{k}")
            # The prompt must render for a call: `{n}`, or SummEval's own count phrases.
            # Size 2 exercises the rewrite: at 16 a SummEval prompt is returned unchanged, so a
            # prompt with neither `{n}` nor its phrases would pass and fail only at run time.
            js.render_prompt(js.prompt_text(sc), 2)
        except SystemExit as exc:
            bad.append(f"{f.name}: does not load ({exc})")
        except (KeyError, TypeError, AttributeError, ValueError, yaml_error) as exc:
            bad.append(f"{f.name}: malformed ({type(exc).__name__}: {exc})")
    return bad


def _report(bad: list[str], label: str, noun: str) -> None:
    for x in bad[:6]:
        print(f"       {x}")
    if len(bad) > 6:
        print(f"       ... and {len(bad) - 6} more")
    check(label, not bad, f"{len(bad)} {noun}")


def v11_judging_sets_match_their_hash() -> None:
    """V11: every frozen judging set's stored hash matches its content's hash."""
    _report(
        judging_set_problems(DATA / "judging-sets"),
        "V11 every judging set's stored hash is the hash of its content",
        "bad set(s)",
    )


def v12_verdicts_belong_to_their_set() -> None:
    """V12: every judge verdict names an existing set, item, pass and block."""
    _report(
        verdict_problems(DATA / "judge-verdicts", DATA / "judging-sets")
        + validation_record_problems(DATA / "judge-validation"),
        "V12 every judge verdict names a real set, item, pass and block, and its n; "
        "every committed reply is bare JSON or withheld",
        "bad verdict(s)",
    )


def v13_judge_scorers_are_well_formed() -> None:
    """V13: every judge scorer yaml loads and is structurally valid."""
    _report(
        scorer_problems(DATA / "scorers"),
        "V13 every judge scorer yaml loads and is structurally valid",
        "bad scorer(s)",
    )


def v14_goals() -> None:
    """Goals are what a number is FOR (ADR-0002). Optional until a project sets
    data/goals/policy.yaml `required_from`; from then on every new run must name one."""
    if not GOALS.is_dir():
        print("  --   V14 goals (no data/goals/: goals are optional until a project adds them)")
        return
    import yaml  # noqa: PLC0415

    goals, bad = load_goals(), []
    schema = json.loads((SCHEMAS / "goal.schema.json").read_text())
    # The file name is the goal's id; read from the files, since load_goals keys by goal_id.
    for f in sorted(GOALS.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) if f.name != "policy.yaml" else None
        if isinstance(doc, dict) and doc.get("goal_id") != f.stem:
            bad.append(f"goals/{f.name}: goal_id {doc.get('goal_id')!r} is not its file name")
    for gid, g in goals.items():
        if jsonschema is not None:
            try:
                jsonschema.validate(g, schema)
            except jsonschema.ValidationError as exc:
                bad.append(f"goals/{gid}.yaml: {exc.message[:90]}")
        # The tie-break names axes the goal weighs: quality, cost, speed or one of its own, not ignored.
        weighed = {a["name"] for a in axes_of(g) if a["role"] != "ignore"}
        for name in (g.get("success_criteria") or {}).get("tie_break") or []:
            if name not in weighed:
                bad.append(
                    f"goals/{gid}.yaml: tie_break names {name!r}, not an axis it weighs ({', '.join(sorted(weighed))})"
                )

    def named(where: str, doc: dict) -> None:
        gid, fmt = doc.get("goal"), doc.get("format")
        if not gid:
            return
        if gid not in goals:
            bad.append(f"{where}: goal {gid!r} does not exist")
            return
        ok = {c.get("format") for c in goals[gid].get("output_contract") or [] if c.get("format")}
        if fmt and ok and fmt not in ok:
            bad.append(f"{where}: format {fmt!r} is not one goal {gid!r} accepts ({', '.join(sorted(ok))})")

    for f in sorted(CONFIGS.glob("*.yaml")) if CONFIGS.is_dir() else []:
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        named(f"configs/{f.name}", doc if isinstance(doc, dict) else {})
    since = str(goal_policy().get("required_from") or "")
    unnamed, n_runs = [], 0
    filed: dict[str, list] = defaultdict(list)
    for label, run in all_runs():
        m = read_json(run / "metrics.json") if (run / "metrics.json").is_file() else None
        if not isinstance(m, dict):
            continue
        n_runs += 1
        named(f"runs/{label}", m)
        if m.get("goal"):
            filed[str(m["goal"])].append((run, m))
        if since and not m.get("goal") and str(m.get("created_at", ""))[:10] >= since:
            unnamed.append(label)
    for b in sorted(BASELINES.glob("*.json")):
        named(f"baselines/{b.name}", read_json(b))
    bad += [f"runs/{r}: created on or after {since} and names no goal" for r in unnamed]
    # THE GOAL DECIDES DIRECTION (_runs.lower_is_better_on), so it must not contradict what its
    # runs record (the adapter's METRIC_DIRECTIONS, import-run --asc) or a metric known to go
    # down (cost, latency, tokens): the goal page and the inspector would rank opposite ways.
    for gid, g in goals.items():
        primary = (g.get("success_criteria") or {}).get("primary") or {}
        measure, says = primary.get("measure"), primary.get("direction")
        if not measure or says not in ("lower", "higher"):
            continue
        recorded = recorded_direction(filed.get(gid, []), measure)
        if recorded and recorded != says:
            bad.append(
                f"goals/{gid}.yaml: {measure} is {says}-is-better, its runs record {recorded}-is-better"
            )
        elif not recorded and says == "higher" and lower_is_better(measure):
            bad.append(
                f"goals/{gid}.yaml: {measure} is a cost, speed or token count; higher-is-better contradicts it"
            )
    for x in bad:
        print(f"       {x}")
    # min_items: a note, not a failure. A dataset smaller than the goal's minimum can still
    # be measured; it cannot pick a winner, and the goal page says so.
    sizes = {p.stem: len((read_json(p) or {}).get("items") or []) for p in DATASETS.glob("*.json")}
    for gid, g in goals.items():
        need = (g.get("success_criteria") or {}).get("min_items")
        for d in g.get("datasets") or []:
            n = sizes.get(d.get("dataset_id"))
            if need and n is not None and n < need:
                notes.append(
                    f"V14 goal {gid}: dataset {d['dataset_id']} has {n} items, "
                    f"under its min_items {need}: it can measure, not pick a winner"
                )
    # Rounds (ADR-0004, optional) are part of a goal: their records, and the runs that name one.
    from evaluation_harness._rounds import load_rounds  # noqa: PLC0415
    from evaluation_harness._rounds import problems as round_problems  # noqa: PLC0415

    for p in round_problems():
        print(f"       {p}")
        bad.append(p)
    n_rounds = len(load_rounds())
    rounds = f", {n_rounds} round(s)" if n_rounds else ""
    rule = f"; runs from {since} must name one" if since else "; optional (no required_from set)"
    check(
        f"V14 goals — {len(goals)} goal(s){rounds}, every goal named resolves{rule}",
        not bad,
        f"{len(bad)} problem(s)",
    )


def v15_item_fields() -> None:
    """Item fields are declared, typed and hashed (ADR-0003). Undeclared means unchecked: a
    typo in a column name would be a new field nobody filters or groups by."""
    from evaluation_harness import _fields  # noqa: PLC0415

    fieldsets = {p.stem: p for p in sorted(FIELDS.glob("*.yaml"))} if FIELDS.is_dir() else {}
    with_fields = []
    for ds_file in sorted(DATASETS.glob("*.json")):
        ds = read_json(ds_file)
        if ds.get("fieldset") or any("fields" in it for it in ds.get("items") or []):
            with_fields.append(ds)
    if not fieldsets and not with_fields:
        print("  --   V15 item fields (no field set, no dataset with fields)")
        return
    bad: list[str] = []
    loaded: dict[str, dict] = {}
    for fid in fieldsets:
        fs = _fields.load_fieldset(fid) or {}
        problems = _fields.fieldset_problems(fid, fs)
        bad.extend(f"fields/{fid}.yaml: {p[:90]}" for p in problems)
        if not problems:
            loaded[fid] = fs
    for ds in with_fields:
        where, fid = f"datasets/{ds['dataset_id']}.json", ds.get("fieldset")
        if not fid:
            bad.append(f"{where}: items carry fields, but the dataset names no fieldset")
            continue
        if fid not in loaded:
            bad.append(
                f"{where}: field set {fid!r} " + ("is not valid" if fid in fieldsets else "does not exist")
            )
            continue
        for it in ds["items"]:
            bad += [
                f"{where}: {p}" for p in _fields.problems(loaded[fid], it["item_id"], it.get("fields") or {})
            ]
        if ds.get("fields_sha256") != _fields.digest(ds["items"]):
            bad.append(
                f"{where}: fields_sha256 is not the hash of the items' fields "
                "(edited by hand? `dataset-create --update-fields` records the change)"
            )
    for x in bad[:30]:
        print(f"       {x}")
    check(
        f"V15 item fields — {len(loaded)} field set(s), {len(with_fields)} dataset(s) with fields, "
        "every value declared and typed",
        not bad,
        f"{len(bad)} problem(s)",
    )


def v16_references() -> None:
    """A reference's texts match its manifest (schemas/reference.schema.json). The manifest is
    committed even when the text is not, so a rebuilt copy proves it is the same reference."""
    from evaluation_harness._references import drift  # noqa: PLC0415

    base = DATA / "references"
    dirs = [d for tier in ("gold", "silver") for d in sorted((base / tier).glob("*")) if d.is_dir()]
    if not dirs:
        print("  --   V16 references (none)")
        return
    schema = json.loads((SCHEMAS / "reference.schema.json").read_text()) if jsonschema else None
    bad: list[str] = []
    fetched = here = unchecked = 0
    for d in dirs:
        rel = d.relative_to(base).as_posix()
        mf_path = d / "manifest.json"
        texts = any(d.glob("*.txt"))
        if not mf_path.is_file():
            if texts:
                unchecked += 1
                notes.append(
                    f"V16: {rel} has no manifest, so a rebuilt copy cannot be checked "
                    f"(evh reference-manifest --reference-id {rel} --source <how it is built>)"
                )
            continue
        mf = read_json(mf_path)
        if schema is not None:
            bad += [
                f"{rel}/manifest.json: {e.message[:90]}"
                for e in jsonschema.Draft202012Validator(schema).iter_errors(mf)
            ]
        if not texts:
            if mf.get("redistributed", True):
                bad.append(f"{rel}: its texts are committed (redistributed), and none is here")
            else:
                fetched += 1
            continue
        here += 1
        for kind, ids in drift(d, mf).items():
            if ids:
                bad.append(f"{rel}: {len(ids)} item(s) {kind} against the manifest ({', '.join(ids[:3])})")
    for x in bad[:30]:
        print(f"       {x}")
    check(
        f"V16 references — {here} checked against their manifests, {fetched} fetched elsewhere"
        + (f", {unchecked} with no manifest" if unchecked else ""),
        not bad,
        f"{len(bad)} problem(s)",
    )


def main() -> int:
    """Run all integrity checks over the eval tree; exit 1 if any fails."""
    # `--help` prints help. It used to fall through and run the whole validation, which
    # made self_test's `validate_tree.py --help` check assert "the tree is valid" instead
    # of "the CLI responds" — so the one script whose failure matters most had a self-test
    # that could only pass when it had nothing to report.
    no_options(__doc__)
    problems.clear()
    notes.clear()
    print(f"eval tree: {DATA}\n")
    for fn in (
        v1_schemas,
        v2_dataset_ids,
        v3_provenance,
        v4_materialized,
        v5_duplicate_scores,
        v6_baselines,
        v7_committed_runs_are_readable,
        v8_no_duplicate_config_ids,
        v9_no_committed_evidence_is_missing,
        v10_derived_runs_carry_the_current_scorer,
        v11_judging_sets_match_their_hash,
        v12_verdicts_belong_to_their_set,
        v13_judge_scorers_are_well_formed,
        v14_goals,
        v15_item_fields,
        v16_references,
    ):
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
