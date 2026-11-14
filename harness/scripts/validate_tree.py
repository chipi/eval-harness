#!/usr/bin/env python3
"""Integrity checks over the eval tree. Run it before you trust any number.

Each check exists because its absence let a real defect through somewhere:

  V1  schemas        a document that violates its own contract
  V2  dataset_id     a run citing a dataset that does not exist — the number
                     cannot be attributed to any data; a dataset made from a capture or a version that
                     does not exist
  V3  provenance     a run with no build ref — the number cannot be attributed
                     to any code
  V4  materialized   a dataset whose materialized copy drifted from its hashes
  V5  duplicates     two runs reporting byte-identical scores AND identical
                     per-item results on the same dataset. Agreeing MEANS are not
                     suspicious on a discrete metric; agreeing per item is. A run
                     whose system says `expect_identical_to: <system>` (a regression
                     guard) is expected to agree, and fails V5 when it does not
  V6  baselines      a baseline pointing at a run that no longer exists; a version that no longer matches its run, a
                     line whose versions do not run 1..n, or the old one-per-dataset layout (RFC-027)
  V7  readable       a committed run that stopped before its first score (a run.json, nothing measured)
  V8  config_ids     two runs of one arm claiming the same (dataset_id, config_id)
  V9  present        a committed run or score file deleted from disk, or an arm below its floor
  V10 scorer drift   a DERIVED score naming a scorer that is not the code in this tree
  V11 judging sets   a frozen judging set whose stored hash is not its content's hash
  V12 verdicts       a stored judge verdict naming a set, item, pass or block that does not
                     exist, or whose `n` is not that block's size
  V13 judge scorers  a scorer yaml that does not load or fails judge_score's structure checks
  V14 goals          a goal that breaks its schema; a system, run or baseline naming a goal that
                     does not exist, or a format its goal does not accept; a run created on or
                     after data/goals/policy.yaml's `required_from` that names no goal
  V15 item fields    a field set that breaks its schema; a dataset naming a field set that does
                     not exist, or carrying fields without one; a value of an undeclared field,
                     of the wrong type or outside its choices; a required field with no value;
                     a fields_sha256 that is not the hash of the fields
  V16 references     a reference with no manifest (ADR-0022: made only by promoting labels), whose
                     manifest breaks its schema, whose texts differ from the checksums it
                     records, or whose committed texts are missing (a manifest with no texts and
                     `redistributed: false` is a reference fetched elsewhere)
  V17 captures       a capture whose record files are partly missing, or whose records differ from the
                     ids and sha256 it recorded (RFC-019)
  V18 model records  a model record not named by its id, an alias claimed twice, a deployment id used
                     twice, or a system naming a record or deployment that does not exist (RFC-020)
  V19 label sets     a label set that breaks its schema, whose labels differ from the sha256 it recorded,
                     whose label files are missing, whose dataset does not exist, or whose count is not its
                     labels' (RFC-023)
  V20 hypotheses     a system whose `hypothesis:` names no system that exists, a measure that is not one
                     of the arm's metrics, a direction that is not better, worse or no-worse, or a key
                     it lacks (ADR-0025)
  V21 failure modes  a failure-mode list that breaks its schema, is not named by its id or names a mode
                     twice (or `ok`, which a sheet reads as "nothing wrong"); a tag set that breaks its
                     schema, whose dataset or list does not exist, that names a mode not in its list or an
                     item not in its dataset, or whose count is not its tags' (PLAN_0.8.0 D1)
  V22 dataset records a dataset whose stored version is not the one its lineage gives (MAJOR.MINOR:
                     1.0 from nothing or a split, MINOR + 1 for added items, MAJOR + 1 for removed or
                     changed ones), a split side naming a parent version that is not its parent's, or
                     a licence not on evh licences' list (E2), a source block with a key or value
                     outside its form, item rows without an item_url to fill (E1), or a card key
                     that is not one of Croissant RAI's (E4); a sealed side whose open side changed
                     since it was sealed, or a run on it no unseal named (the fleet's feedback 29); an
                     exposure register that breaks its row schema or is of a dataset that is not a sealed
                     side (RFC-031); a line of the pick list that breaks its schema (RFC-023)
                     (PLAN_0.8.0 E3; `evh migrate` brings old records to the format)
  V23 run outputs    a run still in the old layout (an outputs/ folder, or a data/runs-* folder: `evh migrate`),
                     or a score derived from outputs its run does not have (RFC-024); a project in both stores
                     (RFC-025)
  V24 prompts        a prompt version whose bytes do not hash to its name, or a run naming one not recorded; a
                     run's deployment.code incomplete (RFC-028, RFC-030)
  V25 looks          a look number on a test set taken by two different questions (RFC-029)
  V26 faithfulness   a faithfulness record off its schema, of no code record, with exceptions that are not its own
                     disagreements; a code record keeping a summary of its own (RFC-030, RFC-032 step 7)
  V27 studies        a study's spec off its schema or under no goal, a log event a study does not write, a trial
                     with no system (RFC-029, RFC-032 step 7)

Exit 1 on any failure, so it can gate.

    evh validate
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
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _store
from evaluation_harness._common import (
    BASELINES,
    CAPTURES,
    DATA,
    DATASETS,
    EXIT_PROBLEMS,
    FIELDS,
    GOALS,
    MATERIALIZED,
    ROOT,
    RUNS,
    SCHEMAS,
    data_rel,
    die,
    goal_policy,
    load_goals,
    load_module,
    lower_is_better,
    no_options,
    read_json,
    sha256,
    system_files,
)
from evaluation_harness._runs import recorded_direction
from evaluation_harness.axes import axes_of
from evaluation_harness.model import runs as _mr

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]  # V1 is then skipped, and says why

problems: list[str] = []
notes: list[str] = []

#: The bundled demo: `demo_v1` on `smoke_v1` is run many times by `make demo` and by the
#: self-test, smoke_v1 is not an eval, and no report cites it. A project adds its own
#: exceptions in `duplicate_ok`, each one a deliberate, justified edit.
_DEMO_DUPLICATE = ("smoke_v1", "demo_v1")


def policy() -> dict:
    """<data>/validate.json: what this project's validate holds it to (committed arms, floors,
    scorer sources, duplicate exceptions). These were this repository's directory names and
    example paths written into the validator, so a pinned project's own `runs-adjudicated` was
    never checked while six names it does not have were. An arm is named by its label's prefix
    (`model.runs.arm_prefix`: `runs`, `pair`, `silver`, `judged-judge-summ-v1`, ...).
    """
    f = DATA / "validate.json"
    if not _store.is_file(f):
        return {}
    doc = parsed(f)
    if not isinstance(doc, dict):
        die(
            f"{data_rel(f)} does not parse as a JSON object: fix it, it says which checks this project runs",
            "invalid-file",
        )
    return dict(doc)


def arm_of(sd: Path, rec: dict) -> str:
    """The prefix of the arm a score is read in (`runs` for a plain run's own score)."""
    return _mr.arm_prefix(_mr.label(sd, rec))


def arms() -> dict[str, list[tuple[Path, dict]]]:
    """arm prefix -> its scores with their records, by run id then key. Every run is in data/runs (a throwaway pass is
    `evh run --scratch`, under .build/), so every score is the project's record."""
    out: dict[str, list[tuple[Path, dict]]] = {}
    for sd, rec in _mr.scored(label_is=None):
        out.setdefault(arm_of(sd, rec), []).append((sd, rec))
    return out


def committed_arms() -> list[str]:
    """The arms that back the project's claims: those `committed` in validate.json names (with their floors), then
    every other arm with a score git tracks. An arm someone committed is checked whether or not they also listed it
    here: a re-scored set's runs were committed and never checked because the list was not edited too."""
    declared = list(policy().get("committed") or [])
    return declared + [a for a in tracked_arms() if a not in declared]


def tracked_arms() -> list[str]:
    """Every arm one of whose scores git tracks (RFC-025: in the sqlite store, the database holds what git holds in the
    files store, so every score)."""
    from evaluation_harness import _common as _c  # noqa: PLC0415

    if _c.store() == "sqlite":
        tracked = {data_rel(p.parent) for p in _store.rglob(RUNS, "metrics.json")}
    else:
        tracked = {
            f.rsplit("/", 1)[0]
            for f in subprocess.run(
                ["git", "ls-files", data_rel(RUNS)], cwd=ROOT, capture_output=True, text=True
            ).stdout.split()
            if f.endswith("/metrics.json")
        }
    return sorted({a for a, scores in arms().items() if any(data_rel(sd) in tracked for sd, _r in scores)})


def check(label: str, ok: object, detail: str = "") -> None:
    """Log a check result and append to problems if it failed."""
    if ok:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
        problems.append(label)


def parsed(path: Path) -> Any:
    """The JSON at `path`, or None when it does not parse. V1 names every dataset, run, baseline and capture
    that does not; the checks after it skip such a file, and a check of any other kind of file reports it
    itself. Read directly, one broken file ended `validate` in a traceback and none of the later checks ran."""
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None


def v1_schemas() -> None:
    """V1: every document matches its schema."""
    if jsonschema is None:
        notes.append("V1 skipped: jsonschema not installed (pip install -r requirements.txt)")
        print("  --   V1 schemas (jsonschema not installed)")
        return
    import yaml  # noqa: PLC0415

    pairs = [
        (_store.glob(DATASETS, "*.json"), "dataset.schema.json"),
        (_store.glob(BASELINES, "*/*/*.json"), "baseline.schema.json"),
        (system_files(), "system.schema.json"),
        (_store.glob(DATA / "scorers", "*.yaml"), "scorer.schema.json"),
        (_store.glob(DATA / "judging-sets", "*.json"), "judging-set.schema.json"),
        (_store.glob(DATA / "judge-verdicts", "*/*/*/*.json"), "verdict.schema.json"),
        (_store.glob(DATA / "judge-validation", "*/*/report.json"), "judge-validation-report.schema.json"),
        (_store.glob(DATA / "judge-validation", "*/*/*/*.json"), "judge-validation-record.schema.json"),
        (_store.glob(DATA / "models", "*.yaml"), "model.schema.json"),
        (_store.glob(DATA / "deployments", "*/*.yaml"), "deployment.schema.json"),
        (_store.glob(DATA / "profiles", "*.json"), "profile.schema.json"),
        (_store.glob(CAPTURES, "*/capture.json"), "capture.schema.json"),
        (
            _store.rglob(DATA / "prompts", "*.json") if _store.is_dir(DATA / "prompts") else [],
            "prompt-version.schema.json",
        ),
    ]
    bad = 0
    n = 0
    # A run's files are read as their records (model/runs): the schema is of a score's whole record, the run's facts
    # with the score's over them. A file that does not parse is named; one run or score with none of its files is not.
    record_validator = jsonschema.Draft202012Validator(
        json.loads(_store.read_text(SCHEMAS / "metrics.schema.json"))
    )
    for rid in _mr.run_ids():
        if _mr.run(rid) is None:
            bad += 1
            print(f"       {data_rel(_mr.run_dir(rid))}/{_mr.RUN}: does not parse")
        for sd in _mr.scores_of(rid):
            for name, got in ((_mr.SCORE, _mr.meta(sd)), (_mr.METRICS, _mr._json(sd / _mr.METRICS))):
                if not got:
                    bad += 1
                    print(f"       {data_rel(sd)}/{name}: does not parse")
    for _label, sd, rec in all_scores():
        n += 1
        try:
            record_validator.validate(rec)
        except jsonschema.ValidationError as exc:
            bad += 1
            print(f"       {data_rel(sd)}: {exc.message[:90]}")
    for files, schema_name in pairs:
        schema = json.loads(_store.read_text(SCHEMAS / schema_name))
        for f in files:
            if not _store.is_file(Path(f)):
                continue
            n += 1
            try:
                doc = (
                    yaml.safe_load(_store.read_text(f, encoding="utf-8"))
                    if f.suffix == ".yaml"
                    else read_json(f)
                )
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
    `derived_from` (the version it was made from) and `made_from.capture` (the capture it was made from)."""
    from evaluation_harness.model import datasets as _datasets  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    known = {p.stem for p in _store.glob(DATASETS, "*.json")}
    dangling = []
    for rid in _mr.run_ids():
        did = (_mr.run(rid) or {}).get("dataset_id")
        if did not in known:
            dangling.append(f"{rid} -> {did}")
    for p in sorted(_store.glob(DATASETS, "*.json")):
        try:
            doc = read_json(p)
        except ValueError:
            continue  # V1 names a file that does not parse
        parent = (doc.get("derived_from") or {}).get("dataset_id")
        if parent and parent not in known:
            dangling.append(f"dataset {p.stem} derived from {parent}, which does not exist")
        cap = (doc.get("made_from") or {}).get("capture")
        if cap:
            try:
                there = _store.is_file(_datasets.CAPTURE.path(str(cap)))
            except Problem:  # not a capture id
                there = False
            if not there:
                dangling.append(f"dataset {p.stem} made from capture {cap}, which does not exist")
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
    for rid in _mr.run_ids():
        b = (_mr.run(rid) or {}).get("build") or {}
        if b.get("ref", "unknown") == "unknown":
            missing.append(rid)
    for r in missing:
        print(f"       {r}")
    check("V3 every run identifies its build", not missing, f"{len(missing)} without a ref")


def v4_materialized() -> None:
    """Every item of every materialized copy is there and has its frozen hash. A dataset with
    no copy here (materialized data is not committed, so CI has none) is not checked, and the
    output says so by name: the check used to print `ok` for it, and for a copy that had lost
    files, which is green for something never looked at."""
    drifted, missing, unchecked, checked = [], [], [], 0
    for ds_file in sorted(_store.glob(DATASETS, "*.json")):
        ds = parsed(ds_file)
        if not isinstance(ds, dict) or "dataset_id" not in ds:
            continue  # V1 names it
        mat = MATERIALIZED / ds["dataset_id"]
        if not _store.is_dir(mat):
            unchecked.append(ds["dataset_id"])
            continue
        checked += 1
        for item in ds["items"]:
            rel = item.get("source_path") or item["item_id"]
            f = mat / rel
            if not _store.is_file(f):
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


def _outputs_signature(score: Path) -> str:
    """A digest of what a score's run wrote (its outputs, by item: _outputs.signature). Runs without outputs all
    share one value: what they wrote cannot tell them apart, so it excuses nothing."""
    from evaluation_harness import _outputs  # noqa: PLC0415

    return _outputs.signature(score)


def _per_item_signature(score: Path) -> str:
    """A stable digest of one score's per-item rows, for telling ties from copies.

    Run-level properties are excluded for the same reason they are excluded from the key
    above: a fabricated result differs in latency like any other. A run with no readable
    predictions returns its own name, so it can never match another score -- an unreadable
    file is a reason to say nothing, not a reason to accuse.
    """
    from evaluation_harness import _outputs  # noqa: PLC0415

    rows = []
    try:
        text = _outputs.rows_text(score)
        if text is None:
            return f"<no-predictions:{score}>"
        for line in text.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            scored = {k: v for k, v in row.items() if k not in _V5_RUN_PROPERTIES and k != "_meta"}
            rows.append(json.dumps(scored, sort_keys=True))
    except (OSError, ValueError):
        return f"<unreadable:{score}>"
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def v5_duplicate_scores() -> None:
    """V5: no two runs in one arm report byte-identical scores and per-item results.
    Within an arm: a rescore that left a run's scores as they were is identical to its
    source in the `runs` arm by design."""
    global _DECLARED
    _DECLARED = None
    dupes: list[list] = []
    broken: list[str] = []
    guards = 0
    for arm, scores in arms().items():
        dupes += _v5_in(arm, scores)
        n, bad = _v5_guards(arm, scores)
        guards += n
        broken += bad
    for group in dupes:
        print(
            f"       identical scores AND identical per-item results: {', '.join(str(n) for n, _, _ in group)}"
        )
    for x in broken:
        print(f"       {x}")
    check(
        "V5 no two systems report byte-identical scores"
        + (f"; {guards} regression guard(s) reproduce what they must" if guards else ""),
        not dupes and not broken,
        f"{len(dupes)} suspicious group(s) — differing params produced identical output"
        if dupes
        else f"{len(broken)} regression guard(s) differ from the system they must reproduce",
    )


def _v5_in(arm: str, scores: list[tuple[Path, dict]]) -> list[list]:
    by_key = defaultdict(list)
    for run, d in scores:
        # Compare what the arm PRODUCED. A fabricated or copy-pasted result differs in
        # latency like any other, so keying on it let exactly the case this check exists
        # for slip through.
        produced = {k: v for k, v in (d.get("scores") or {}).items() if k not in _V5_RUN_PROPERTIES}
        key = (d.get("dataset_id"), json.dumps(produced, sort_keys=True))
        by_key[key].append((run, d.get("config_id"), json.dumps(d.get("params") or {}, sort_keys=True)))
    # Identical scores from identical params is not suspicious — it is what a deterministic
    # arm DOES, and two systems may legitimately request the same thing. What deserves a look
    # is DIFFERENT params landing on byte-identical output: either a result was not measured,
    # or the knobs that differ are inert.
    dupes: list[list] = []
    for group in by_key.values():
        known = group
        # A regression guard (fleet feedback 28): the same code at two commits MUST agree; a group joined by
        # `expect_identical_to` declarations is the agreement asked for, not an inert knob.
        if _declared_together(scores, {c for _, c, _ in known}):
            continue
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
            # A STUDY'S TRIAL THAT CHANGED NOTHING THE SYSTEM READS measures as the arm it came from: a finding of the
            # study (RFC-029), noted, not a copied result.
            study = _one_study({c for _, c, _ in known})
            if study:
                notes.append(
                    f"V5 study {study}: {', '.join(sorted({str(c) for _, c, _ in known}))} measured the same, item by "
                    "item: no effect"
                )
                continue
            dupes.append([(f"{arm}/{_mr.run_of(n).name}", c, p) for n, c, p in known])
    return dupes


def _one_study(configs: set) -> str | None:
    """The studies these systems belong to, when every one is a study's trial or the baseline a study started from
    (trials of several studies that land on the same settings measure the same too), or None."""
    from evaluation_harness.model import studies as model_studies  # noqa: PLC0415

    found: set[str] = set()
    covered: set = set()
    for rid in model_studies.ids(check_format=False):
        goal, sid = rid.split("/", 1)
        st = model_studies.state(goal, sid)
        members = ({t.get("config_id") for t in st["trials"]} | {st["baseline"]}) & configs
        if members - {st["baseline"]}:
            found.add(f"{goal}/{sid}")
            covered |= members
    return ", ".join(sorted(found)) if found and configs <= covered else None


def _declared_together(scores: list[tuple[Path, dict]], configs: set) -> bool:
    """Whether every system of a V5 group is joined to the others by `expect_identical_to` declarations."""
    if len(configs) < 2:
        return False
    edges = {(c, t) for c, t, _r in _guards_in(scores) if c in configs and t in configs}
    reach, todo = set(), [next(iter(configs))]
    while todo:
        c = todo.pop()
        if c in reach:
            continue
        reach.add(c)
        todo += [b for a, b in edges if a == c] + [a for a, b in edges if b == c]
    return reach == configs


#: What V5 read of the systems this run: each guard of every arm asks, and the systems are 300 files.
_DECLARED: dict[str, str] | None = None


def _declared_in_systems() -> dict[str, str]:
    """system id -> the system it must reproduce, as each system declares it today (every system of the project:
    data/systems and the folders validate.json's `systems` globs name)."""
    global _DECLARED
    if _DECLARED is None:
        _DECLARED = _read_declared()
    return _DECLARED


def _read_declared() -> dict[str, str]:
    import yaml  # noqa: PLC0415

    out: dict[str, str] = {}
    for f in system_files():
        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8"))
        except yaml.YAMLError:
            continue  # V1 reports the file
        if isinstance(doc, dict) and doc.get("system_id") and isinstance(doc.get("expect_identical_to"), str):
            out[str(doc["system_id"])] = doc["expect_identical_to"]
    return out


def _guards_in(scores: list[tuple[Path, dict]]) -> list[tuple]:
    """(system id, the system it must reproduce, its score directory) for every score of an arm that declares one: the
    run's own record, else its system's declaration (the fleet's beta: runs made before the system declared it are
    frozen, and the guard holds for them too)."""
    out = []
    by_config = _declared_in_systems()
    for run, d in scores:
        target = d.get("expect_identical_to") or by_config.get(str(d.get("config_id")))
        if target:
            out.append((d.get("config_id"), target, run))
    return out


def _v5_guards(arm: str, scores: list[tuple[Path, dict]]) -> tuple[int, list[str]]:
    """Every regression guard in an arm against the latest run of the system it names on the same dataset: the
    per-item results and the outputs must be the same. A guard whose system has no run there yet is not counted."""
    checked, bad = 0, []
    for cfg, target, run in _guards_in(scores):
        d = _mr.record(run) or {}
        theirs = sorted(
            r for r, m in scores
            if m.get("config_id") == target and m.get("dataset_id") == d.get("dataset_id")
        )  # fmt: skip
        if not theirs:
            continue
        checked += 1
        other = theirs[-1]
        mine, theirs_name = _mr.run_of(run).name, _mr.run_of(other).name
        if _per_item_signature(run) != _per_item_signature(other):
            bad.append(
                f"{arm}/{mine} ({cfg}) must reproduce {target}: its per-item results differ from {theirs_name}"
            )
        elif _outputs_signature(run) != _outputs_signature(other):
            bad.append(f"{arm}/{mine} ({cfg}) must reproduce {target}: its outputs differ from {theirs_name}")
    return checked, bad


def v6_baselines() -> None:
    """V6: every baseline version's promoted_from run still exists, and the version still says what it carried from
    it (the tier, adapter, fingerprint and format); each line's versions run 1..n, each replacing the one before
    and a rollback restoring an earlier one (RFC-027). A baseline still in the old layout (one file per dataset)
    fails it, with the command that moves it."""
    from evaluation_harness import _baselines  # noqa: PLC0415
    from evaluation_harness.promote_baseline import carried, run_record  # noqa: PLC0415

    broken = [
        f"{b.name}: the old layout, one baseline per dataset: evh migrate moves it"
        for b in sorted(_store.glob(BASELINES, "*.json"))
    ]
    for g, ds in _baselines.lines():
        vs = _baselines.versions(g, ds)
        line = f"{g or _baselines.NO_GOAL}/{ds}"
        if [v["version"] for v in vs] != list(range(1, len(vs) + 1)):
            broken.append(f"{line}: versions {[v['version'] for v in vs]}, not 1..{len(vs)}")
        for v in vs[1:]:
            if v.get("replaces") != v["version"] - 1:
                broken.append(
                    f"{line}/{v['version']}: replaces {v.get('replaces')!r}, not {v['version'] - 1}"
                )
            if v.get("restores") is not None and not (1 <= int(v["restores"]) < v["version"]):
                broken.append(
                    f"{line}/{v['version']}: restores {v.get('restores')!r}, not an earlier version"
                )
    for b in sorted(_store.glob(BASELINES, "*/*/*.json")):
        d = parsed(b)
        if not isinstance(d, dict):
            continue  # V1 names it
        name = b.relative_to(BASELINES).as_posix()
        if not d.get("promoted_from") or _mr.run(str(d["promoted_from"])) is None:
            broken.append(f"{name} -> {d.get('promoted_from')}: no such run")
            continue
        m = run_record(d["promoted_from"]) or {}
        # The goal is the line's, not the run's: a run may be promoted as another goal's baseline (--goal).
        for k, v in carried(m).items():
            if k != "goal" and d.get(k) != v:
                broken.append(f"{name}: {k} is {d.get(k)!r}, its run records {v!r}")
    for x in broken:
        print(f"       {x}")
    # WHO ACTED (RFC-027): a record from before 0.8.0 names nobody until `evh migrate` writes "before 0.8.0".
    # A note, not a failure: picks are append-only, and a record a test or a person wrote by hand is not wrong.
    from evaluation_harness.baselines_migrate import plan  # noqa: PLC0415

    missing = sum(1 for what, _f, _n in plan() if what.startswith("actor"))
    if missing:
        print(f"  note: {missing} record(s) name no actor (who made them): evh migrate writes one")
    check(
        "V6 every baseline's source run still exists and matches what the baseline carries",
        not broken,
        f"{len(broken)} broken",
    )


def all_scores() -> list[tuple[str, Path, dict]]:
    """(label, score directory, record) for every score, labelled by its run's id, `<arm>/<run id>` outside the `runs`
    arm."""
    out = []
    for sd, rec in _mr.scored(label_is=None):
        prefix = arm_of(sd, rec)
        rid = _mr.run_of(sd).name
        out.append((rid if prefix == "runs" else f"{prefix}/{rid}", sd, rec))
    return out


def _tracked_files() -> list[str]:
    """Every file of data/runs git tracks, as paths from the project root."""
    return subprocess.run(
        ["git", "ls-files", data_rel(RUNS)], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()


def v7_committed_runs_are_readable() -> None:
    """A run in the repo must have been scored. Outputs alone are not a measurement.

    144 directories were committed as outputs ONLY -- 2,880 files of CNN/DailyMail
    paraphrases with nothing to say which arm produced them, on which dataset, under
    which fingerprint. No tool here can read them: `rescore`, `leaderboard`,
    `compare_runs` and every report script key off a score and skip a run without one.

    The cause was two rules interacting. Those pilot runs are excluded BY NAME because
    they record an absolute username path; the exclusion named `metrics.json` and
    `predictions.jsonl`, and a later force-include of `outputs/**` reached underneath
    it. All of the copyright exposure and none of the reproducibility benefit. A run is now
    its `run.json` (committed from the first item) and its scores; one with no first score
    stopped before it finished.

    Checked against the INDEX rather than the working tree: an in-progress run on disk
    is fine and expected, a committed one is not.
    """
    from evaluation_harness import _common as _c  # noqa: PLC0415

    if _c.store() == "sqlite":  # RFC-025: nothing under data/ is in git; the database is the record
        print("  --   V7 committed runs (the sqlite store: nothing under data/ is in git)")
        return
    prefix = data_rel(RUNS).rstrip("/") + "/"
    committed = {f[len(prefix) :].split("/")[0] for f in _tracked_files() if f.startswith(prefix)}
    bad = sorted(r for r in committed if _mr.first_score(r) is None and _store.is_file(RUNS / r / _mr.RUN))
    for x in bad[:10]:
        print(f"       {x}")
    if len(bad) > 10:
        print(f"       ... and {len(bad) - 10} more")
    check(
        "V7 every committed run has its first score",
        not bad,
        f"{len(bad)} run(s) stopped before they finished (a run.json, nothing scored): resume each with evh run --resume <run_id>, or delete it",
    )


def v9_no_committed_evidence_is_missing() -> None:
    """Every run git has must still be on disk, with its files. Deleting evidence passed.

    V7 reads the git INDEX, V1 validates `data/runs` only, and the arm-row check skips
    arms it cannot find -- so `rm -rf data/runs/sf_mpnet_*` left `make ci` green and
    43/43 claims verified. A repo whose argument is "check the instrument" could lose a
    quarter of its evidence without a single red line. Found by external review.

    Floors as well as presence: an arm could be emptied one score at a time and each
    individual absence explained away.
    """
    from evaluation_harness import _common as _c  # noqa: PLC0415

    if _c.store() == "sqlite":  # RFC-025: nothing under data/ is in git; the database is the record
        print("  --   V9 committed run files (the sqlite store: nothing under data/ is in git)")
        return
    #: What each committed arm must contain. Raising one of these is a deliberate edit; lowering one should need an
    #: argument.
    #: The `linux` arm (the re-timed runs) is here because it was NOT, and nothing else reached it either: the
    #: re-timed latency figures in three reports come out of it, six documents cite it. Deleting what nine published
    #: latency numbers rest on passed every check. Found reviewing the merged ML-arm work, which is the same defect
    #: round 4 found one directory over.
    # The floors are PROJECT policy: how many scores each committed arm must keep is a fact about one project's
    # evidence, not about the harness. They are read from <data>/validate.json (`policy`); a project without them has
    # no floors (V9's missing-file and empty-rows checks still apply).
    FLOORS = policy().get("floors") or {}

    listed = subprocess.run(
        ["git", "ls-files", data_rel(RUNS)],
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
        # <data root>/runs/<run id>/scores/<key>/<file>, wherever the data root sits.
        if not f.startswith(data_prefix):
            continue
        parts = f[len(data_prefix) :].split("/")
        if len(parts) == 5 and parts[2] == "scores":
            seen.setdefault("/".join(parts[:4]), set()).add(parts[4])
        if not _store.exists(ROOT / f):
            missing.append(f)
    # PRESENCE IS NOT CONTENT. `: > predictions.jsonl` left the file tracked, present
    # and zero bytes, and V9 said "every committed run file is present on disk" while
    # the arm-row scan read `metrics.json` and reported 53/53. The evidence a score IS
    # is its rows; a score whose rows are gone is deleted whatever the directory listing
    # says. Found by external review, round 5.
    from evaluation_harness import _outputs  # noqa: PLC0415

    for key, files in sorted(seen.items()):
        if _mr.METRICS not in files:
            continue  # V7's business, not this one
        if _outputs.PREDICTIONS not in files:
            incomplete.append(f"{key} has no predictions.jsonl")
            continue
        sd = DATA / key
        try:
            _text = _outputs.rows_text(sd)
        except (OSError, ValueError):
            incomplete.append(f"{key} predictions.jsonl is unreadable")
            continue
        if _text is None or not _store.is_file(sd / _mr.METRICS):
            continue  # already counted as missing above
        try:
            _rows = sum(1 for _l in _text.splitlines() if _l.strip())
            _want = int((_mr.record(sd) or {}).get("n_items") or 0)
        except (OSError, ValueError, TypeError):
            incomplete.append(f"{key} predictions.jsonl is unreadable")
            continue
        if _rows == 0:
            incomplete.append(f"{key} predictions.jsonl is empty")
        elif _want and _rows != _want:
            incomplete.append(f"{key} has {_rows} prediction rows, its record says n_items={_want}")
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
    by_arm = arms()
    for name, floor in sorted(FLOORS.items()):
        n = len(by_arm.get(name, []))
        if n < floor:
            short.append(f"{name}: {n} scores, expected at least {floor}")
    for x in short:
        print(f"       {x}")
    check("V9 each committed arm meets its floor", not short, "; ".join(short))


def v10_derived_runs_carry_the_current_scorer() -> None:
    """A score that CLAIMS to be a product of the current code must carry ALL its hashes.

    Re-scores exist to be re-derivable for $0, and each records the scorer it was derived with. Nothing ever compared those to the code
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
    and nothing whatever about the parser. Every key the score stores is now compared.
    Found by external review, round 5.

    AN ABSENT FIELD IS A FAILURE HERE, NOT A SKIP. It used to print `skip` and pass, so
    deleting `rescored_with` from all 27 runs left VALIDATION PASSED -- the check
    vanishing exactly when the thing it reads is gone, which is what its own docstring
    said it must not do. A derived arm with scores in it must state its provenance.
    Only the `runs` arm may be silent. Also round 5.

    The `runs` arm is a NOTE, never a failure. Those scores legitimately carry the hash they
    were measured with -- recording it is the entire point.

    An adapter whose dependencies are absent is a named skip, printed, not silence.
    """
    #: (arm, glob of run ids, where the score states its hashes, module, callable).
    #: The callable returns either a str (one hash) or a dict of named hashes, and
    #: EVERY key of that dict is compared -- naming one key here is how the parser went
    #: unwatched. The `runs` arm predates `scorer_sha256` and states `parser_sha256` alone,
    #: under the fingerprint's `deployment.declared`, so that is what is compared there.
    #: Declared per project in validate.json `scorer_sources`; a project without them has
    #: nothing for V10 to compare.
    SOURCES = [
        (src["arms"], src["glob"], tuple(src["path"]), src["module"], src["callable"])
        for src in policy().get("scorer_sources") or []
    ]

    def _dig(d, path):
        for k in path:
            if not isinstance(d, dict):
                return None
            d = d.get(k)
        return d

    by_arm = arms()
    for directory, pat, path, modfile, fn in SOURCES:
        runs = [(sd, rec) for sd, rec in by_arm.get(directory, []) if fnmatch(_mr.run_of(sd).name, pat)]
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
        for sd, doc in runs:
            name = (
                f"{_mr.run_of(sd).name}/{sd.name}"
                if len(_mr.scores_of(_mr.run_of(sd))) > 1
                else _mr.run_of(sd).name
            )
            rec = _dig(doc, path)
            if rec is None:
                silent.append(name)
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
                silent.append(f"{name} (states {sorted(pairs)}, code offers {sorted(want)})")
                continue
            for k in shared:
                if pairs[k] != want[k]:
                    stale.append(f"{name} {k} {pairs[k][:12]}")
        label = (
            f"V10 {directory}: {', '.join(sorted(keys))} match the code ({checked} score(s))"
            if keys
            else f"V10 {directory}: a scorer hash was compared at all"
        )

        # A DERIVED RUN THAT STATES NOTHING IS A FAILURE. Skipping here is how the
        # check disappears at the moment it matters.
        for x in silent[:5]:
            print(f"       {x} states no hash at {'.'.join(path)}")
        check(
            f"V10 {directory}: every score states its scorer",
            not silent,
            f"{len(silent)} of {len(runs)} score(s) record nothing at "
            f"{'.'.join(path)} — a derived score must say what derived it",
        )
        for x in stale[:5]:
            print(f"       {x} != the code")
        check(
            label,
            not stale and checked > 0,
            f"{len(stale)} mismatch(es) over {checked} derived score(s)"
            if stale
            else "no run was compared at all",
        )


def v8_no_duplicate_config_ids() -> None:
    """No two runs of one arm may claim the same (dataset_id, config_id).

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

    #: The arms whose runs back a report. A throwaway pass (`evh run --scratch`) is outside the data.
    # The `linux` arm was omitted when it was added, so the sixth committed arm was the one place a duplicate
    # config_id could still land -- and the latency claims read it by filesystem order, so a duplicate changed the
    # answer depending on how the names sorted. That is the round-3 ext4 defect in the sixth arm. Round 5.
    COMMITTED = committed_arms()
    #: The bundled demo, plus the project's own `duplicate_ok`: named, never scoped away
    #: silently, so that adding an exception is a deliberate edit someone has to justify.
    ALLOWED = {_DEMO_DUPLICATE, *(tuple(x) for x in policy().get("duplicate_ok") or [])}

    bad = []
    by_arm = arms()
    for arm in COMMITTED:
        groups: dict = {}
        for sd, m in by_arm.get(arm, []):
            key = (m.get("dataset_id"), m.get("config_id"))
            rid = _mr.run_of(sd).name
            if key[1] and rid not in groups.setdefault(key, []):
                groups[key].append(rid)
        for (ds, cid), names in sorted(groups.items()):
            if len(names) < 2:
                continue
            stems = {_re.sub(r"_r\d+$", "", n) for n in names}
            if len(stems) == 1 and all(_re.search(r"_r\d+$", n) for n in names):
                continue
            if (ds, cid) in ALLOWED:
                notes.append(
                    f"{arm}: {len(names)} {cid!r} runs on {ds} "
                    f"(allowed: {'the bundled demo, cited by no report' if (ds, cid) == _DEMO_DUPLICATE else 'duplicate_ok in validate.json'})"
                )
                continue
            bad.append(f"{arm}: {len(names)} runs claim {cid!r} on {ds} — {', '.join(sorted(names))}")
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
    for f in sorted(_store.glob(sets_dir, "*.json")):
        try:
            m = json.loads(_store.read_text(f, encoding="utf-8"))
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
    for f in sorted(_store.glob(verdicts_dir, "*/*/*/*.json")):
        scorer_dir, set_id = f.parts[-4], f.parts[-3]
        label = f"{scorer_dir}/{set_id}/{f.parent.name}/{f.name}"
        if set_id not in sets:
            sp = sets_dir / f"{set_id}.json"
            try:
                sets[set_id] = (
                    json.loads(_store.read_text(sp, encoding="utf-8")) if _store.is_file(sp) else None
                )
            except (OSError, ValueError):
                sets[set_id] = None
        m = sets[set_id]
        if m is None:
            bad.append(f"{label}: judging set {set_id} does not exist (or is unreadable)")
            continue
        try:
            v = json.loads(_store.read_text(f, encoding="utf-8"))
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
        redo = f"evh judge-score --dataset-id {m.get('dataset_id')} --scorer {scorer_dir} --retry-unparsed"
        bad.extend(f"{label}: {p_}" for p_ in reply_problems(v, fix=redo))
    return bad


def reply_problems(rec: dict, fix: str = "") -> list[str]:
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
        how = f"; rewrite it with `{fix}`" if fix else ""
        return [f"reply is not bare JSON ({len(out)} chars): withhold it, keep its hash{how}"]
    return []


def validation_record_problems(validation_dir: Path) -> list[str]:
    """The same rule for the judge-validation records (<scorer>/<set>/<judge>/*.json)."""
    bad = []
    for f in sorted(_store.glob(validation_dir, "*/*/*/*.json")):
        try:
            rec = json.loads(_store.read_text(f, encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(f"{f.relative_to(validation_dir)}: unreadable")
            continue
        bad.extend(f"{f.relative_to(validation_dir)}: {p}" for p in reply_problems(rec))
    return bad


def scorer_problems(scorers_dir: Path) -> list[str]:
    """Every scorer yaml loads and is structurally sound. Not the paid gate: whether a
    scorer is VALIDATED is judge_score's `validation_problems`, and an unvalidated
    eval scorer is allowed to exist."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    bad = []
    from yaml import YAMLError as yaml_error  # noqa: PLC0415

    for f in sorted(_store.glob(scorers_dir, "*.yaml")):
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
            # A rubric that changed says what it replaced and why (C3): the scorer it supersedes exists, the reason
            # is a sentence, and a reason names what it supersedes.
            if sc.get("supersedes"):
                if not _store.is_file(scorers_dir / f"{sc['supersedes']}.yaml"):
                    bad.append(f"{f.name}: supersedes {sc['supersedes']!r}, which is not a scorer here")
                if len(str(sc.get("why") or "").split()) < 4:
                    bad.append(
                        f"{f.name}: supersedes {sc['supersedes']}: `why` must be a sentence, what changed and why"
                    )
            elif sc.get("why"):
                bad.append(f"{f.name}: `why` without `supersedes`: name the scorer this one replaces")
        except SystemExit as exc:
            bad.append(f"{f.name}: does not load ({exc})")
        except (KeyError, TypeError, AttributeError, ValueError, yaml_error) as exc:
            bad.append(f"{f.name}: malformed ({type(exc).__name__}: {exc})")
    return bad


def judged_score_problems(scorers_dir: Path) -> list[str]:
    """Every judged score was made with its scorer as it is: the hash it records is the content hash of the scorer's
    file now. A scorer changed after it judged is another scorer under the old id, and what it made (its summaries, its
    scores) no longer says which judges and prompt made it; the change belongs in a new scorer id (`supersedes`)."""
    import yaml  # noqa: PLC0415
    from evaluation_harness.model import scorers as _sc  # noqa: PLC0415

    now: dict[str, str | None] = {}
    bad = []
    for s in _sc.judged_scores():
        sid = str(s["scorer"])
        if sid not in now:
            f = scorers_dir / f"{sid}.yaml"
            try:
                now[sid] = (
                    _sc.content_hash(yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {})
                    if _store.is_file(f)
                    else None
                )
            except yaml.YAMLError:
                now[sid] = None
        cur = now[sid]
        where = data_rel(s["dir"])
        if cur is None:
            bad.append(f"{where}: made with scorer {sid}, which is not in data/scorers (or does not parse)")
        elif s["sha256"] != cur:
            bad.append(
                f"{where}: made with {sid} {str(s['sha256'] or 'with no hash recorded')[:12]}, "
                f"the scorer now is {cur[:12]}: restore it, or keep the change as a new scorer id (`supersedes`)"
            )
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
    """V13: every judge scorer yaml loads and is structurally valid, and every judged score was made with it as it is."""
    _report(
        scorer_problems(DATA / "scorers") + judged_score_problems(DATA / "scorers"),
        "V13 every judge scorer yaml loads and is structurally valid, and every judged score was made with it as it is",
        "bad scorer(s)",
    )


def v14_goals() -> None:
    """Goals are what a number is FOR (ADR-0002). Optional until a project sets
    data/goals/policy.yaml `required_from`; from then on every new run must name one."""
    if not _store.is_dir(GOALS):
        print("  --   V14 goals (no data/goals/: goals are optional until a project adds them)")
        return
    import yaml  # noqa: PLC0415

    goals, bad = load_goals(), []
    schema = json.loads(_store.read_text(SCHEMAS / "goal.schema.json"))
    # The file name is the goal's id; read from the files, since load_goals keys by goal_id.
    for f in sorted(_store.glob(GOALS, "*.yaml")):
        doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) if f.name != "policy.yaml" else None
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

    since = str(goal_policy().get("required_from") or "")
    unnamed, n_runs = [], 0
    filed: dict[str, list] = defaultdict(list)
    named_runs: set[str] = set()
    for _label, run, m in all_scores():
        rid = _mr.run_of(run).name
        if m.get("goal"):
            filed[str(m["goal"])].append((run, m))
        if rid in named_runs:  # a run's goal and format are its own, whatever it was scored as
            continue
        named_runs.add(rid)
        n_runs += 1
        named(f"runs/{rid}", m)
        if since and not m.get("goal") and str(m.get("created_at", ""))[:10] >= since:
            unnamed.append(rid)
    for b in sorted(_store.glob(BASELINES, "*/*/*.json")):
        if isinstance(doc := parsed(b), dict) and doc.get("goal"):
            named(f"baselines/{b.relative_to(BASELINES).as_posix()}", doc)
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
    # A goal's `cluster:` names a field the dataset's items carry: a typo would test item by item and say nothing.
    for gid, g in goals.items():
        for d in g.get("datasets") or []:
            field = d.get("cluster")
            if not field:
                continue
            ds = parsed(DATASETS / f"{d.get('dataset_id')}.json")
            if not isinstance(ds, dict):
                continue  # V2 or V1 names it
            have = sum(
                1 for it in ds.get("items") or [] if (it.get("fields") or {}).get(field) not in (None, "")
            )
            if not have:
                bad.append(
                    f"goals/{gid}.yaml: cluster {field!r} on {d['dataset_id']}: no item carries that field"
                )
    for x in bad:
        print(f"       {x}")
    # The margin decides who is a contender: on the strategy's default it is a choice nobody made for this goal.
    from evaluation_harness.axes import STRATEGY_MARGINS, strategy_of  # noqa: PLC0415

    for gid, g in goals.items():
        crit = g.get("success_criteria") or {}
        strategy = strategy_of(g)
        if (
            strategy != "quality_first"
            and ((crit.get("axes") or {}).get("quality") or {}).get("margin") is None
        ):
            notes.append(
                f"V14 goal {gid}: contenders are decided on {strategy}'s default margin, "
                f"{STRATEGY_MARGINS.get(strategy, 0):.0%} of the leader: set success_criteria.axes.quality.margin "
                "(in the measure's units) to choose it"
            )
    # min_items: a note, not a failure. A dataset smaller than the goal's minimum can still
    # be measured; it cannot pick a winner, and the goal page says so.
    sizes = {p.stem: len((parsed(p) or {}).get("items") or []) for p in _store.glob(DATASETS, "*.json")}
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

    fieldsets = {p.stem: p for p in sorted(_store.glob(FIELDS, "*.yaml"))} if _store.is_dir(FIELDS) else {}
    with_fields: list[Any] = []
    for ds_file in sorted(_store.glob(DATASETS, "*.json")):
        ds = parsed(ds_file)
        if not isinstance(ds, dict):
            continue  # V1 names it
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
    dirs = [
        d for tier in ("gold", "silver") for d in sorted(_store.glob(base / tier, "*")) if _store.is_dir(d)
    ]
    if not dirs:
        print("  --   V16 references (none)")
        return
    schema = json.loads(_store.read_text(SCHEMAS / "reference.schema.json")) if jsonschema else None
    bad: list[str] = []
    fetched = here = unchecked = 0
    for d in dirs:
        rel = d.relative_to(base).as_posix()
        mf_path = d / "manifest.json"
        texts = any(_store.glob(d, "*.txt"))
        if not _store.is_file(mf_path):
            if texts:
                # ADR-0022: a reference set is made only by promoting labels, with a record of where it came from.
                unchecked += 1
                tier, name = rel.split("/", 1)
                bad.append(
                    f"{rel}: no manifest, so nothing says where it came from. Make it a promoted reference where it "
                    f"is: evh label-import data/references/{rel} --dataset-id {name} --set {name}_hand --by WHO, then "
                    f"evh reference-promote --dataset-id {name} --labels {name}_hand --tier {tier} --reason … --by WHO "
                    f"(the promotion adopts the folder: its texts are the labels'). For gold a script builds: "
                    f"evh reference-manifest --reference-id {rel} --source <how it is built>"
                )
            continue
        mf = parsed(mf_path)
        if not isinstance(mf, dict):
            bad.append(f"{rel}: manifest.json does not parse")
            continue
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


def v17_captures() -> None:
    """V17: every capture's records are the ones it recorded (RFC-019): each record file present,
    its id the one listed, and its hash the capture's `sha256` (the whole record, outcome included,
    so an edited outcome is caught as surely as an edited body). A capture with no record file at all
    is not fetched yet (records are content a project may keep out of git, restored by its fetcher):
    named, not failed. One with some records and not others fails."""
    from evaluation_harness._importers import record_sha256  # noqa: PLC0415

    caps = sorted(_store.glob(CAPTURES, "*/capture.json")) if _store.is_dir(CAPTURES) else []
    if not caps:
        print("  --   V17 captures (none)")
        return
    bad: list[str] = []
    n = 0
    unfetched = []
    for c in caps:
        doc = parsed(c)
        if not isinstance(doc, dict):
            continue  # V1 names it
        if doc.get("records") and not any(_store.glob(c.parent / "records", "*.json")):
            unfetched.append(c.parent.name)
            continue
        for entry in doc.get("records") or []:
            n += 1
            rf = c.parent / "records" / f"{entry.get('id')}.json"
            if not _store.is_file(rf):
                bad.append(f"{c.parent.name}/{entry.get('id')}: record file missing")
                continue
            rec = parsed(rf)
            if not isinstance(rec, dict):
                bad.append(f"{c.parent.name}/{entry.get('id')}: record file does not parse")
                continue
            if rec.get("id") != entry.get("id") or record_sha256(rec) != entry.get("sha256"):
                bad.append(f"{c.parent.name}/{entry.get('id')}: does not match the hash the capture recorded")
        if doc.get("n_records") != len(doc.get("records") or []):
            bad.append(
                f"{c.parent.name}: n_records {doc.get('n_records')} but {len(doc.get('records') or [])} listed"
            )
    for b in bad[:10]:
        print(f"       {b}")
    if unfetched:
        print(f"  --   V17 captures not fetched here (no record files): {', '.join(unfetched)}")
    check(
        f"V17 captures — {len(caps) - len(unfetched)} capture(s), {n} record(s) match their hashes",
        not bad,
        f"{len(bad)} problem(s)",
    )


def v19_label_sets() -> None:
    """V19: every label set's labels are the ones it recorded (RFC-023): each label file present, its sha256 the
    set's, the set's dataset a dataset of the project, and its n_items the count. A set is never edited, so any
    difference is an edit or a loss."""
    import hashlib  # noqa: PLC0415

    from evaluation_harness import _common  # noqa: PLC0415

    found = sorted(_store.glob(_common.LABELS, "*/*/labels.json")) if _store.is_dir(_common.LABELS) else []
    if not found:
        print("  --   V19 label sets (none)")
        return
    schema = (
        jsonschema.Draft202012Validator(json.loads(_store.read_text(SCHEMAS / "label-set.schema.json")))
        if jsonschema
        else None
    )
    bad: list[str] = []
    n = 0
    for lj in found:
        doc = parsed(lj)
        rel = f"{lj.parent.parent.name}/{lj.parent.name}"
        if not isinstance(doc, dict):
            bad.append(f"{rel}: labels.json does not parse")
            continue
        if schema is not None and (err := next(iter(schema.iter_errors(doc)), None)):
            bad.append(f"{rel}: {err.message[:90]}")
            continue
        if not _store.is_file(_common.DATASETS / f"{doc.get('dataset_id')}.json"):
            bad.append(f"{rel}: its dataset {doc.get('dataset_id')!r} does not exist")
        items = doc.get("items") or {}
        if doc.get("n_items") != len(items):
            bad.append(f"{rel}: n_items {doc.get('n_items')} but {len(items)} listed")
        kept_out = doc.get("redistributed") is False and not any(_store.glob(lj.parent, "*.txt"))
        for iid, row in items.items():
            n += 1
            tf = lj.parent / f"{iid}.txt"
            if (
                kept_out
            ):  # its texts are kept out of git (labels.json says how to rebuild them): nothing to check
                continue
            if not _store.is_file(tf):
                bad.append(f"{rel}/{iid}: label file missing")
            elif hashlib.sha256(_store.read_bytes(tf)).hexdigest() != row.get("sha256"):
                bad.append(f"{rel}/{iid}: differs from the sha256 the set recorded (a set is never edited)")
    for b in bad[:10]:
        print(f"       {b}")
    check(
        f"V19 label sets — {len(found)} set(s), {n} label(s) match their hashes",
        not bad,
        f"{len(bad)} problem(s)",
    )


def v20_hypotheses() -> None:
    """V20: every `hypothesis:` in a system (ADR-0025) has its keys, a direction that is better, worse or
    no-worse, an `against` that is another system of the project, and a measure that is one of the system's metrics.
    The systems are system_files(); evh run refuses the same mistakes before it spends anything."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _hypothesis  # noqa: PLC0415

    found, bad = 0, []
    ids = None
    for c in system_files():
        try:
            cfg = yaml.safe_load(_store.read_text(c, encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue  # V1 names a system that does not parse
        if not isinstance(cfg, dict) or cfg.get("hypothesis") is None:
            continue
        found += 1
        ids = ids if ids is not None else _hypothesis.system_ids()
        bad += [f"{c.name}: {p}" for p in _hypothesis.problems(cfg, c, ids)]
    if not found:
        print("  --   V20 hypotheses (none)")
        return
    for b in bad[:10]:
        print(f"       {b}")
    check(f"V20 hypotheses — {found} system(s) with one, every one sound", not bad, f"{len(bad)} problem(s)")


def v21_failure_modes() -> None:
    """V21: the failure-mode lists are well formed, and every tag set names its dataset's items and its list's modes
    (PLAN_0.8.0 D1). A tag set is never edited, so a mode removed from its list later shows here."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _tags  # noqa: PLC0415

    lists = sorted(_store.glob(_tags.modes_root(), "*.yaml")) if _store.is_dir(_tags.modes_root()) else []
    sets = sorted(_store.glob(_tags.tags_root(), "*/*/tags.json")) if _store.is_dir(_tags.tags_root()) else []
    if not lists and not sets:
        print("  --   V21 failure modes (none)")
        return
    schema = json.loads(_store.read_text(SCHEMAS / "failure-modes.schema.json")) if jsonschema else None
    tag_schema = (
        jsonschema.Draft202012Validator(json.loads(_store.read_text(SCHEMAS / "tag-set.schema.json")))
        if jsonschema
        else None
    )
    bad: list[str] = []
    known: dict[str, set[str]] = {}
    for f in lists:
        rel = f"failure-modes/{f.name}"
        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            bad.append(f"{rel}: does not parse ({str(e).splitlines()[0]})")
            continue
        if schema is not None:
            errs = sorted(
                jsonschema.Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path)
            )
            if errs:
                bad.append(f"{rel}: {errs[0].message[:90]}")
                continue
        if not isinstance(doc, dict):
            bad.append(f"{rel}: not a mapping")
            continue
        if doc.get("failure_modes_id") != f.stem:
            bad.append(f"{rel}: failure_modes_id {doc.get('failure_modes_id')!r} is not its file name")
        ids = [str(m.get("id")) for m in doc.get("modes") or [] if isinstance(m, dict)]
        if len(set(ids)) != len(ids):
            bad.append(f"{rel}: a mode is named twice")
        if _tags.OK in ids:
            bad.append(f"{rel}: a mode named `{_tags.OK}`, which a sheet reads as nothing wrong")
        known[f.stem] = set(ids)
    n = 0
    for tj in sets:
        doc = parsed(tj)
        rel = f"tags/{tj.parent.parent.name}/{tj.parent.name}"
        if not isinstance(doc, dict):
            bad.append(f"{rel}: tags.json does not parse")
            continue
        if tag_schema is not None and (err := next(iter(tag_schema.iter_errors(doc)), None)):
            bad.append(f"{rel}: {err.message[:90]}")
            continue
        ds = parsed(DATASETS / f"{doc.get('dataset_id')}.json")
        if not isinstance(ds, dict):
            bad.append(f"{rel}: its dataset {doc.get('dataset_id')!r} does not exist")
            continue
        modes = known.get(doc.get("failure_modes") or "")
        if modes is None:
            bad.append(f"{rel}: its failure modes {doc.get('failure_modes')!r} do not exist")
            continue
        items = {it.get("item_id") for it in ds.get("items") or []}
        runs = doc.get("runs") or {}
        tagged = sum(len(v) for v in runs.values())
        n += tagged
        if doc.get("n_tagged") != tagged:
            bad.append(f"{rel}: n_tagged {doc.get('n_tagged')} but {tagged} listed")
        for run, by_item in runs.items():
            for iid, t in by_item.items():
                if iid not in items:
                    bad.append(f"{rel}/{run}/{iid}: not an item of {doc['dataset_id']}")
                off = [m for m in t.get("modes") or [] if m not in modes]
                if off:
                    bad.append(f"{rel}/{run}/{iid}: {', '.join(off)} not a mode of {doc['failure_modes']}")
    for b in bad[:10]:
        print(f"       {b}")
    check(
        f"V21 failure modes — {len(lists)} list(s), {len(sets)} tag set(s), {n} tag(s) name known modes and items",
        not bad,
        f"{len(bad)} problem(s)",
    )


def _lines_problems(f: Path, rel: str, schema: Any) -> list[str]:
    """What is wrong with each line of the JSON-lines file `f` against `schema` (named `rel`); [] when it is sound."""
    out = []
    for n, line in enumerate(_store.read_text(f, encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            out.append(f"{rel}: line {n} does not parse")
            continue
        if schema is not None and (err := next(iter(schema.iter_errors(row)), None)):
            out.append(f"{rel}: line {n}: {err.message[:90]}")
    return out


def _side_problems(docs: dict[str, dict]) -> list[str]:
    """V22's: each exposure register (data/exposure/<dataset>.jsonl) is of a sealed side and its rows fit their schema
    (RFC-031), and each line of the pick list (data/picks.jsonl) fits its own (RFC-023)."""
    schemas = {
        name: jsonschema.Draft202012Validator(json.loads(_store.read_text(SCHEMAS / f"{name}.schema.json")))
        if jsonschema
        else None
        for name in ("exposure", "pick")
    }
    out: list[str] = []
    reg = DATA / "exposure"
    for f in sorted(_store.glob(reg, "*.jsonl")) if _store.is_dir(reg) else []:
        rel = f"exposure/{f.name}"
        if not (docs.get(f.stem) or {}).get("sealed"):
            out.append(
                f"{rel}: {f.stem} is not a sealed side (a register is of a dataset dataset-split --seal made)"
            )
        out += _lines_problems(f, rel, schemas["exposure"])
    picks = DATA / "picks.jsonl"
    if _store.is_file(picks):
        out += _lines_problems(picks, "picks.jsonl", schemas["pick"])
    return out


def v22_dataset_records() -> None:
    """V22: each dataset's stored version is the one its lineage gives (PLAN_0.8.0 E3), so a hand-edited or
    pre-0.8.0 version is caught; `evh migrate` writes the right ones."""
    from evaluation_harness import _card, _dataset_version, _licences, _source  # noqa: PLC0415

    docs = (
        {f.stem: parsed(f) for f in sorted(_store.glob(DATASETS, "*.json"))}
        if _store.is_dir(DATASETS)
        else {}
    )
    docs = {k: v for k, v in docs.items() if isinstance(v, dict)}  # V1 names one that does not parse
    side = _side_problems(docs)
    if not docs and not side:
        print("  --   V22 dataset records (none)")
        return

    def version_of(i: str | None) -> str | None:
        return (docs.get(i) or {}).get("version") if i else None

    bad: list[str] = []
    for i, d in docs.items():
        want = _dataset_version.expected(d, version_of)
        if d.get("version") != want:
            bad.append(f"datasets/{i}.json: version {d.get('version')!r}, its lineage gives {want}")
        if "source" in d:
            bad += [f"datasets/{i}.json: {p}" for p in _source.problems(d["source"])]
        if "card" in d:
            bad += [f"datasets/{i}.json: {p}" for p in _card.problems(d["card"])]
        if any("source_row" in it for it in d.get("items") or []) and "{row}" not in str(
            (d.get("source") or {}).get("item_url") or ""
        ):
            bad.append(f"datasets/{i}.json: items carry source_row, but source.item_url has no {{row}}")
        if "licence" in d and _licences.problem(str(d["licence"])):
            bad.append(f"datasets/{i}.json: licence {d['licence']!r} is not on the list (evh licences)")
        sp = d.get("split") or {}
        if sp and sp.get("from") in docs and sp.get("from_version") != version_of(sp.get("from")):
            bad.append(
                f"datasets/{i}.json: split.from_version {sp.get('from_version')!r}, but {sp['from']} is "
                f"{version_of(sp['from'])}"
            )
    # A sealed side (the fleet's feedback 29): its open side unchanged since the seal, and no run on it by a system
    # no unseal named, or from before its unseal.
    from evaluation_harness import _seal  # noqa: PLC0415

    sealed = _seal.problems(docs)
    if any(d.get("sealed") for d in docs.values()):
        runs = [(_mr.run_dir(rid), m) for rid in _mr.run_ids() if isinstance(m := _mr.run(rid), dict)]
        sealed += _seal.runs_on_sealed(docs, runs)
    bad += sealed + side
    for b in bad[:10]:
        print(f"       {b}")
    if bad and len(bad) > len(sealed) + len(side):
        print("       evh migrate writes the versions the lineage gives (--dry-run shows them first)")
    check(
        f"V22 dataset records — {len(docs)} dataset(s), each version its lineage's"
        + (
            f", {sum(1 for d in docs.values() if d.get('sealed'))} sealed side(s) held"
            if any(d.get("sealed") for d in docs.values())
            else ""
        ),
        not bad,
        f"{len(bad)} problem(s)",
    )


def v24_prompt_versions() -> None:
    """V24 (RFC-028): every prompt version's bytes hash to its name and its record, its parent exists, and every
    run's `settings.prompts` names a recorded version; a run's `deployment.code` has its four keys (one checkout,
    RFC-028), or, for a replay (RFC-030), its code record, the record's versions' hash and the commits it ran."""
    from evaluation_harness import _prompts, _runs  # noqa: PLC0415

    bad: list[str] = []
    known: set[tuple[str, str]] = set()
    n = 0
    for name in _prompts.names():
        for v in _prompts.versions(name):
            n += 1
            sha16 = str(v.get("sha256", ""))[:16]
            try:
                data = _prompts.text_of(f"{name}/{sha16}")
            except (FileNotFoundError, ValueError):
                bad.append(f"{name}/{sha16}: its text file is missing")
                continue
            if _prompts.sha256(data) != v.get("sha256") or v.get("id") != f"{name}/{sha16}":
                bad.append(f"{name}/{sha16}: its bytes do not hash to its name and record")
            known.add((name, str(v.get("sha256"))))
            parent = v.get("parent")
            if parent:
                try:
                    _prompts.text_of(parent)
                except (FileNotFoundError, ValueError):
                    bad.append(f"{v.get('id')}: its parent {parent} is not recorded")
    runs = 0
    for d, m in _runs.runs_on():
        fp = m.get("fingerprint") or {}
        used = (fp.get("settings") or {}).get("prompts") or {}
        if used:
            runs += 1
        for name, sha in used.items() if isinstance(used, dict) else []:
            if (name, str(sha)) not in known:
                bad.append(f"{_mr.run_of(d).name}: prompt {name} {str(sha)[:16]} is not a recorded version")
        code = (fp.get("deployment") or {}).get("code")
        if code is None:
            continue
        if isinstance(code, dict) and code.get(
            "record"
        ):  # a replay's (RFC-030): many commits, from its record
            if not {"record", "versions_sha256", "commits"} <= set(code):
                bad.append(
                    f"{_mr.run_of(d).name}: a replay's deployment.code lacks record, versions_sha256 or commits"
                )
        elif not (isinstance(code, dict) and {"repo", "commit", "dirty", "path"} <= set(code)):
            bad.append(f"{_mr.run_of(d).name}: deployment.code lacks repo, commit, dirty or path")
    if bad:
        problems.append("V24")
        print(f"  FAIL V24 prompt versions — {len(bad)} problem(s):")
        for b in bad[:20]:
            print(f"       {b}")
    elif n or runs:
        print(f"  ok   V24 prompt versions — {n} version(s), {runs} run(s) naming them")
    else:
        print("  --   V24 prompt versions (none)")


def v25_looks() -> None:
    """V25 (RFC-029): no look number on a test set taken by two different questions (two clones deciding at once)."""
    from evaluation_harness import _looks  # noqa: PLC0415

    bad, sets = [], 0
    for p in _store.glob(DATASETS, "*.json") if _store.is_dir(DATASETS) else []:
        if not _looks.is_test_set(p.stem):
            continue
        sets += 1
        for n, keys in _looks.double_spent(p.stem):
            bad.append(
                f"{p.stem}: look {n} was taken by {len(keys)} questions ({', '.join(keys)}): a double spend"
            )
    if bad:
        problems.append("V25")
        print(f"  FAIL V25 test-set looks — {len(bad)} problem(s):")
        for b in bad:
            print(f"       {b}")
    elif sets:
        print(f"  ok   V25 test-set looks — {sets} test set(s), no look number taken twice")
    else:
        print("  --   V25 test-set looks (no test sets)")


def v26_faithfulness() -> None:
    """V26 (RFC-030, RFC-032 step 7): each faithfulness record is valid against its schema, of a code record (a model
    record of kind: code) that exists, and its exceptions name its own disagreements, once each, with a cause, by a
    person; a code record keeps no summary of its own (the records are the source of a version's faithfulness). A code
    record's deployed periods are V18's (no two versions at one moment)."""
    import json  # noqa: PLC0415

    import jsonschema  # noqa: PLC0415
    from evaluation_harness import _models  # noqa: PLC0415
    from evaluation_harness.model import faithfulness as model_faithfulness  # noqa: PLC0415

    bad: list[str] = []
    schema = model_faithfulness.FAITHFULNESS.schema_doc()
    n = 0
    for mid in model_faithfulness.model_ids():
        if (_models.find(DATA, mid) or {}).get("kind") != "code":
            bad.append(f"data/faithfulness/{mid}: no code record {mid!r} (data/models/, kind: code)")
        for k in model_faithfulness.numbers(mid):
            n += 1
            rec = json.loads(_store.read_text(model_faithfulness.record_file(mid, k), encoding="utf-8"))
            try:
                jsonschema.validate(rec, schema)
            except jsonschema.ValidationError as exc:
                bad.append(f"{mid}/{k}: {exc.message}")
                continue
            if rec["n"] != k or rec["model_id"] != mid:
                bad.append(f"{mid}/{k}: says it is {rec['model_id']}/{rec['n']}")
            mine = {x["item_id"] for x in rec["disagreements"]}
            seen: set = set()
            for e in model_faithfulness.exceptions(mid, k):
                iid = e.get("item_id")
                if iid not in mine:
                    bad.append(f"{mid}/{k}: an exception names {iid!r}, not one of its disagreements")
                elif iid in seen:
                    bad.append(f"{mid}/{k}: {iid} is named twice")
                elif not (e.get("cause") and (e.get("actor") or {}).get("type") == "person"):
                    bad.append(f"{mid}/{k}: the exception of {iid} has no cause or was not named by a person")
                seen.add(iid)
    for rec in _models.load(DATA):
        for v in rec.get("versions") or []:
            if isinstance(v, dict) and "faithfulness" in v:
                bad.append(
                    f"{rec.get('model_id')}: version {v.get('commit')} keeps a faithfulness summary; the records "
                    "(data/faithfulness/) say it, delete the copy"
                )
    if bad:
        problems.append("V26")
        print(f"  FAIL V26 faithfulness records — {len(bad)} problem(s):")
        for b in bad[:20]:
            print(f"       {b}")
    elif n:
        print(f"  ok   V26 faithfulness records — {n} record(s)")
    else:
        print("  --   V26 faithfulness records (none)")


def v27_studies() -> None:
    """V27 (RFC-029, RFC-032 step 7): each study's spec is valid against its schema, under a goal that exists, with an id
    a study may have; its log holds only the events a study writes, and each trial it logged has its system (an imported
    study's has none)."""
    from evaluation_harness import _common, _study  # noqa: PLC0415
    from evaluation_harness.model import studies as model_studies  # noqa: PLC0415

    bad: list[str] = []
    goals = _common.load_goals()
    ids = model_studies.ids(check_format=False)
    for rid in ids:
        goal, sid = rid.split("/", 1)
        if goal not in goals:
            bad.append(f"{rid}: no goal {goal!r} (data/goals/)")
        if not _study.STUDY_ID.fullmatch(sid):
            bad.append(f"{rid}: study id {sid!r}: lower-case letters, digits, '_' or '-'")
        bad += [
            f"{rid}: {'.'.join(map(str, p['path'])) or '(top)'}: {p['message']}"
            for p in model_studies.problems(rid)
        ]
        for ev in model_studies.events(goal, sid):
            if ev.get("event") not in model_studies.EVENTS:
                bad.append(f"{rid}: a log line of event {ev.get('event')!r}")
            elif ev["event"] == "trial" and ev.get("config_id") and not ev.get("imported"):
                path = model_studies.trial_path(goal, sid, int(ev.get("k") or 0))
                if not _store.is_file(path):
                    bad.append(f"{rid}: trial {ev.get('k')} has no system ({path.name})")
    if bad:
        problems.append("V27")
        print(f"  FAIL V27 studies — {len(bad)} problem(s):")
        for b in bad[:20]:
            print(f"       {b}")
    elif ids:
        print(f"  ok   V27 studies — {len(ids)} study(ies)")
    else:
        print("  --   V27 studies (none)")


def v23_run_outputs() -> None:
    """V23: every run's outputs can be read (RFC-024): none is left in the old layout (an outputs/ folder), and a
    score derived from them has them. And the project is files or its database, never both
    (RFC-025): with files no data/project.sqlite; with the database nothing under data/ on disk but it."""
    from evaluation_harness import _common, _outputs, _store  # noqa: PLC0415

    bad: list[str] = []
    db = DATA / _store.DB
    if _common.store() == "files":
        if _store.is_file(db):
            bad.append(
                f"{_store.DB} beside the files while the project's store is files: evh data-migrate --to files"
            )
    else:
        on_disk = _store.stray_files()
        if on_disk:
            bad.append(
                f"{len(on_disk)} file(s) under data/ on disk while the project's store is sqlite (first:"
                f" {on_disk[0].relative_to(DATA)}): evh data-migrate --to sqlite"
            )
    runs = [_mr.run_dir(rid) for rid in _mr.run_ids()]
    for old in sorted(_store.glob(DATA, "runs-*")):
        bad.append(f"{old.relative_to(DATA)}: a folder of runs of the layout before format 4: evh migrate")
    for d in runs:
        if _outputs.old_layout(d):
            bad.append(f"{d.relative_to(DATA)}: an outputs/ folder (the layout before 0.8.0): evh migrate")
    # A re-score reads its run's outputs: a score that says it was derived from them finds them.
    for sd, rec in _mr.scored(label_is=None):
        if rec.get("derived") and _outputs.source(sd) is None:
            bad.append(f"{sd.relative_to(DATA)}: derived from its run's outputs, and the run has none")
    if not runs and not bad:
        print("  --   V23 run outputs (no runs)")
        return
    for b in bad[:10]:
        print(f"       {b}")
    check(
        f"V23 run outputs — {len(runs)} run(s), every one's outputs readable; the project in one store",
        not bad,
        f"{len(bad)} problem(s)",
    )


def v18_model_records() -> None:
    """V18: the model records (RFC-020, optional; their schema is V1's): each file named by its id, no
    alias claimed by two records, a deployment id used twice in one record, every system that names a record
    (`model_record:`) naming one that exists, and `deployment:` only beside a `model_record:` that has it. The
    systems are system_files(): data/systems and the globs validate.json's `systems` adds."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _models  # noqa: PLC0415

    recs = {r.get("model_id") for r in _models.load(DATA)}
    if not recs and not _store.is_dir(DATA / "models"):
        print("  --   V18 model records (none)")
        return
    bad = _models.problems(DATA)
    for c in system_files():
        cfg = yaml.safe_load(_store.read_text(c, encoding="utf-8")) or {}
        rid = cfg.get("model_record") if isinstance(cfg, dict) else None
        dep = cfg.get("deployment") if isinstance(cfg, dict) else None
        if dep and not rid:
            bad.append(f"{c.name}: deployment {dep!r} is used without a model_record")
        if rid and rid not in recs:
            bad.append(f"{c.name}: model_record {rid!r} has no data/models/{rid}.yaml")
        elif rid:
            rec = _models.find(DATA, rid) or {}
            if dep and _models.deployment_of(rec, dep) is None:
                bad.append(f"{c.name}: deployment {dep!r} is not one of {rid}'s deployments")
                continue
            params = _models.resolve(cfg, DATA).get("params") or {}
            if cfg.get("system_id") not in (rec.get("smokes") or {}):
                notes.append(
                    f"{c.name}: never smoked (evh arm-smoke --system {cfg.get('system_id')} --dataset <id>)"
                )
            if (rec.get("capabilities") or {}).get("reasons") and "max_tokens" not in params:
                notes.append(f"{c.name}: {rid} reasons, and no max_tokens bounds its replies")
    for r in _models.load(DATA):
        by_tag: dict[str, set[str]] = {}
        for b in r.get("deployments") or []:
            if b.get("tag") and b.get("digest"):
                by_tag.setdefault(b["tag"], set()).add(b["digest"][:12])
        for tag, digests in by_tag.items():
            if len(digests) > 1:
                notes.append(
                    f"model {r.get('model_id')}: {tag} is a different build on different machines ({', '.join(sorted(digests))})"
                )
    for b in bad[:10]:
        print(f"       {b}")
    check(f"V18 model records — {len(recs)} record(s)", not bad, f"{len(bad)} problem(s)")


def note_uncommitted_runs() -> None:
    """A note, never a failure: finished runs whose run.json git ignores (a project that ignores data/runs). They are
    on this disk only; a fresh clone, CI and the published catalog never see them. A throwaway pass is `evh run
    --scratch`, which writes outside the data."""
    from evaluation_harness import _common as _c  # noqa: PLC0415

    if _c.store() == "sqlite":  # RFC-025: nothing under data/ is in git
        return
    finished = [rid for rid in _mr.run_ids() if _mr.first_score(rid) is not None]
    if not finished:
        return
    try:
        r = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            cwd=ROOT,
            input="\n".join(data_rel(_mr.run_dir(rid) / _mr.RUN) for rid in finished) + "\n",
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return
    n = len(r.stdout.split()) if r.returncode == 0 else 0
    if n:
        notes.append(
            f"{data_rel(RUNS)}: {n} finished run(s) that git ignores, so they are not committed and no catalog "
            "shows them. Stop ignoring data/runs in .gitignore (a throwaway pass is evh run --scratch)."
        )


def note_round_scorers() -> None:
    """A note, never a failure (RFC-022): a round whose arms through one adapter were scored by more than one version
    of it may compare them on different rules (the adapter's code is the scorer's identity, so an edit to its calling
    code alone counts too: score-preview says whether the scores move). Arms with different adapters (a hosted LLM's
    and a fine-tune's) are not that: each adapter is checked against itself."""
    from evaluation_harness import _rounds  # noqa: PLC0415
    from evaluation_harness import rescore as rs  # noqa: PLC0415

    for rnd in _rounds.load_rounds():
        by_adapter: dict[str, dict[str, set[str]]] = {}
        for d, m in rs.measured_runs(rnd["dataset_id"], set(_rounds.arms_of(rnd))):
            scorer, _from = rs.latest_scoring(d, m)
            by_adapter.setdefault(m.get("adapter") or "?", {}).setdefault(scorer or "?", set()).add(
                m["config_id"]
            )
        for adapter, seen in sorted(by_adapter.items()):
            if len(seen) > 1:
                parts = ", ".join(
                    f"{k} ({len(v)} arm(s))" for k, v in sorted(seen.items(), key=lambda kv: -len(kv[1]))
                )
                notes.append(
                    f"round {rnd['round_id']} of {rnd['goal']}: its arms through {adapter} were scored by {len(seen)} "
                    f"versions of that adapter, {parts}. An edit to its calling code alone makes a new version too: "
                    f"evh score-preview --goal {rnd['goal']} --round {rnd['round_id']} shows whether re-scoring moves "
                    f'anything; evh rescore --goal {rnd["goal"]} --round {rnd["round_id"]} --why "..." puts them on one'
                )


def main() -> int:
    """Run all integrity checks over the eval tree; exit 1 if any fails."""
    # `--help` prints help. It used to fall through and run the whole validation, which
    # made self_test's `validate_tree.py --help` check assert "the tree is valid" instead
    # of "the CLI responds" — so the one script whose failure matters most had a self-test
    # that could only pass when it had nothing to report.
    opts = no_options(__doc__, "--json")
    with _jsonout.collect("validate", opts.json, live=sys.stderr):
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
            v17_captures,
            v18_model_records,
            v19_label_sets,
            v20_hypotheses,
            v21_failure_modes,
            v22_dataset_records,
            v23_run_outputs,
            v24_prompt_versions,
            v25_looks,
            v26_faithfulness,
            v27_studies,
            note_uncommitted_runs,
            note_round_scorers,
        ):
            fn()
        for n in notes:
            print(f"\n  note: {n}")
        _jsonout.values({"passed": not problems, "failed": list(problems), "notes": list(notes)})
        if problems:
            print(f"\nVALIDATION FAILED — {len(problems)} check(s): {', '.join(problems)}")
            return EXIT_PROBLEMS
        print("\nVALIDATION PASSED")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
