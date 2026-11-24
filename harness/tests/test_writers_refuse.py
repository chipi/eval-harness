#!/usr/bin/env python3
"""Every writer records the fact explicitly or refuses by name, and validate names each broken link (RFC-041 F7, PLAN
0.8.1 R4).

    EVAL_STORE=files  python tests/test_writers_refuse.py
    EVAL_STORE=sqlite python tests/test_writers_refuse.py

Why: readers kept assuming what no writer guaranteed (a missing cost read as $0, a repeat known by its `_rN` name,
`dirty: null`, a NaN score). Here each writer is fed what the readers assume away, on a copy of R2's fleet-shaped project
($0, offline, the echo provider and a stub adapter), and must either refuse with a kind of RUNBOOK's Refusals table,
writing nothing (a `refused:` check), or record the fact where a reader finds it (a `recorded:` check).

The inventory (what each writer does with each shape) is in the commit that added this file; the checks below are the
shapes a writer used to take silently:

  - an id with unicode, a space or a path in it (evh run and import-run `--run-id`, import-run `--system-id`, a reference
    promoted `--name`);
  - a repeat with no `of`, and an `of` that names another system's run (a retime or a pair as well);
  - a reference named in import-run that is not there, a tier with no reference, a tier the reference's id contradicts;
  - a run with no goal after the project's policy says every run names one (evh run, import-run);
  - a smoke test of a goal or a round that is not there;
  - a cost no item reported (unknown), one every item reported as 0 (zero), and one only some items reported;
  - a goal whose measure no run records, or whose direction is no direction, and a baseline promoted for one.

Then validate: one broken link at a time (a score's reference, a score's label set, a baseline's run, a repeat's `of`, a
goal's dataset, a round's run), and the check must name the link and the file that holds it.
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

PROJECTS: list[Path] = []
LIMITS = ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF", "EVAL_GOALS_DIR")
REFUSAL = re.compile(r"^ERROR \(([a-z-]+)\)", re.M)
REASON = "The hand-written answers decide this queue, and I say so."


def new_project() -> tuple[Path, dict[str, str]]:
    """An empty temporary project and the environment `evh` runs in there."""
    proj = Path(tempfile.mkdtemp(prefix="evh-writers-"))
    PROJECTS.append(proj)
    env = dict(os.environ, EVAL_HOME=str(proj), EVH_ACTOR="person:fixture")
    for k in LIMITS:
        env.pop(k, None)
    return proj, env


BASE, BASE_ENV = new_project()
F = _foreign.fleet(BASE, dict(BASE_ENV))
DS, SET_RUN, FIRST_Y, NO_GOAL = F["dataset"], F["set"][0], F["first_y"], F["no_goal"]
REF = f"gold/{DS}"


def fresh() -> tuple[Path, dict[str, str]]:
    """A copy of the built project, to write into."""
    proj, env = new_project()
    shutil.rmtree(proj)
    shutil.copytree(BASE, proj, symlinks=True)
    return proj, {**env, "EVAL_HOME": str(proj)}


def evh(proj: Path, env: dict[str, str], *args: object, **extra: str):
    """`evh <args>` in the project; `extra` adds environment variables."""
    return _cli.run(proj, {**env, **extra}, *args)


def snapshot(proj: Path) -> frozenset[str]:
    """Every file of the project's data, by name: what a refusal must leave as it was."""
    return frozenset(_runstore.files_under(proj, ""))


def put(proj: Path, rel: str, text: str) -> None:
    """A file of the project's data, written through its store."""
    _runstore.write_text(proj, rel, text)


def refused(label: str, proj: Path, env: dict[str, str], args: tuple, kind: str, names: str = "") -> None:
    """`evh <args>` refuses with `kind`, names what is wrong (`names`, when given), and writes nothing."""
    before = snapshot(proj)
    r = evh(proj, env, *args)
    out = r.stdout + r.stderr
    got = REFUSAL.search(r.stderr)
    check(
        f"refused: {label}: exit 1, ERROR ({kind}){f', names {names!r}' if names else ''}",
        r.returncode == 1
        and got is not None
        and got.group(1) == kind
        and "Traceback" not in out
        and (not names or names in out),
        f"exit {r.returncode}: {out[-400:]}",
    )
    after = snapshot(proj)
    check(f"refused: {label}: nothing written", after == before, sorted(after ^ before)[:4])


def score_record(proj: Path, run_id: str) -> dict:
    """A run's record as a reader has it: run.json with its first score's metrics over it."""
    return _runstore.record_of(proj, run_id)


SCORES = '{"item_id": "t01_login", "wer": 0.1}\n'


def import_args(**more: object) -> tuple:
    """import-run's arguments for the one-row scores file, with `more` (option name: value; None leaves it out)."""
    given = {
        "dataset-id": DS,
        "system-id": "ext_v1",
        "scores": "s.jsonl",
        "primary-metric": "wer",
        "build-ref": "abc123",
        "source": "elsewhere",
        "scorer-id": "ext",
        **{k.replace("_", "-"): v for k, v in more.items()},
    }
    out: list[object] = ["import-run", "--allow-subset"]
    for k, v in given.items():
        if v is not None:
            out += [f"--{k}", v]
    return tuple(out)


# ── the writers refuse what no reader can read ───────────────────────────────────────────────────────────────────
P, E = fresh()
(P / "s.jsonl").write_text(SCORES, encoding="utf-8")
RUN = ("run", "--system", "arm_z_v1", "--dataset", DS)

print("\n-- an id with unicode, a space or a path in it")
for what, bad in (("unicode", "café_run"), ("a path", "../evil"), ("a slash", "a/b"), ("a space", "a b")):
    refused(f"evh run --run-id with {what}", P, E, (*RUN, "--run-id", bad), "bad-argument", "--run-id")
    refused(f"import-run --run-id with {what}", P, E, import_args(run_id=bad), "bad-argument", "--run-id")
refused(
    "import-run --system-id with unicode", P, E, import_args(system_id="sysé"), "bad-argument", "--system-id"
)
refused(
    "import-run --system-id with a slash", P, E, import_args(system_id="a/b"), "bad-argument", "--system-id"
)
for what, bad in (("unicode", "café"), ("a space", "up per")):
    refused(
        f"reference-promote --name with {what}",
        P, E,
        ("reference-promote", "--dataset-id", DS, "--labels", "g", "--tier", "silver", "--reason", REASON,
         "--name", bad),
        "bad-argument", "--name",
    )  # fmt: skip

print("\n-- a repeat names the run it repeats, and a re-run names a run of its own system")
refused("--purpose repeat with no --of", P, E, (*RUN, "--purpose", "repeat"), "bad-argument", "--of")
for purpose in ("retime", "pair"):
    refused(
        f"--purpose {purpose} --of another system's run",
        P, E,
        (*RUN, "--purpose", purpose, "--of", FIRST_Y),
        "mismatch", "system differ",
    )  # fmt: skip

print("\n-- a reference import-run names is there, and its tier is the reference's")
refused(
    "import-run --reference-id that is not there",
    P, E, import_args(reference_id="gold/nope", reference_tier="gold"), "not-found", "gold/nope",
)  # fmt: skip
refused(
    "import-run --reference-tier with no --reference-id",
    P, E, import_args(reference_tier="gold"), "bad-argument", "--reference-id",
)  # fmt: skip
refused(
    "import-run --reference-tier the reference's id contradicts",
    P, E, import_args(reference_id=REF, reference_tier="silver"), "mismatch", "silver",
)  # fmt: skip

print("\n-- a smoke test names a goal and a round that are there")
SMOKE = ("arm-smoke", "--system", "arm_z_v1", "--dataset", DS, "--no-record")
refused("arm-smoke --goal that is not there", P, E, (*SMOKE, "--goal", "nope"), "not-found", "nope")
refused("arm-smoke --round with no --goal", P, E, (*SMOKE, "--round", "r1"), "bad-argument", "--goal")
refused(
    "arm-smoke --round that is not there",
    P,
    E,
    (*SMOKE, "--goal", "triage_a", "--round", "r9"),
    "not-found",
    "r9",
)

print("\n-- already refused by name, held here so a writer that stops refusing is seen")
(P / "nan.jsonl").write_text('{"item_id": "t01_login", "wer": NaN}\n', encoding="utf-8")
(P / "inf.jsonl").write_text('{"item_id": "t01_login", "wer": Infinity}\n', encoding="utf-8")
(P / "str.jsonl").write_text('{"item_id": "t01_login", "wer": 0.1, "cost_usd": "free"}\n', encoding="utf-8")
for what, name in (("NaN", "nan"), ("infinity", "inf"), ("a text cost", "str")):
    refused(
        f"import-run row with {what}",
        P,
        E,
        import_args(scores=f"{name}.jsonl"),
        "invalid-file",
        "not a number",
    )
put(
    P, "goals/elsewhere.yaml",
    "goal_id: elsewhere\nschema_version: '0.1'\ntitle: t\nstatement: s\ndecision: d\nstatus: active\n"
    "success_criteria:\n  primary:\n    measure: overlap_f1\n    direction: higher\n"
    "datasets:\n  - {dataset_id: nowhere_v1, role: validation}\n",
)  # fmt: skip
PROMOTE = ("run-promote", "--run", FIRST_Y, "--allow-dirty", "--reason", REASON)
refused(
    "run-promote for a goal on a dataset the goal does not list",
    P,
    E,
    (*PROMOTE, "--goal", "elsewhere"),
    "mismatch",
    DS,
)
refused("run-promote for a goal that is not there", P, E, (*PROMOTE, "--goal", "nope"), "not-found", "nope")
refused("evh run --goal that is not there", P, E, (*RUN, "--goal", "nope"), "not-found", "nope")
refused("evh run --labels that are not there", P, E, (*RUN, "--labels", "nope"), "not-found", "nope")
refused(
    "rescore --reference-id that is not there",
    P,
    E,
    ("rescore", "--dataset-id", DS, "--reference-id", "gold/nope"),
    "not-found",
    "nope",
)
refused(
    "rescore --labels that are not there",
    P,
    E,
    ("rescore", "--dataset-id", DS, "--labels", "nope"),
    "not-found",
    "nope",
)
refused(
    "reference-promote of labels that are not there", P, E,
    ("reference-promote", "--dataset-id", DS, "--labels", "nope", "--tier", "silver", "--reason", REASON),
    "not-found", "nope",
)  # fmt: skip
refused(
    "label-from-run of a run that is not there",
    P,
    E,
    ("label-from-run", "--run", "nope", "--set", "s1"),
    "not-found",
    "nope",
)
refused(
    "label-from-run --set with unicode", P, E, ("label-from-run", "--run", FIRST_Y, "--set", "café", "--allow-dirty"),
    "bad-argument", "label set",
)  # fmt: skip
refused(
    "goal-new naming a dataset that is not there", P, E,
    (
        "goal-new", "g_lost", "--set", "title=t", "--set", "statement=s", "--set", "decision=d", "--set", "status=active",
        "--set", "success_criteria.primary.measure=overlap_f1", "--set", "success_criteria.primary.direction=higher",
        "--set", 'datasets=[{"dataset_id":"ghost_v1","role":"validation"}]',
    ),
    "invalid-file", "ghost_v1",
)  # fmt: skip

# ── a run with no goal, after the project says every run names one ──────────────────────────────────────────────
print("\n-- a run with no goal, once goals/policy.yaml says every run names one")
P2, E2 = fresh()
(P2 / "s.jsonl").write_text(SCORES, encoding="utf-8")
put(P2, "goals/policy.yaml", "required_from: 2026-01-01\n")
refused("evh run with no goal under the policy", P2, E2, RUN, "bad-argument", "--goal")
refused("import-run with no goal under the policy", P2, E2, import_args(), "bad-argument", "--goal")
refused("import-run --goal that is not there", P2, E2, import_args(goal="nope"), "not-found", "nope")
r = evh(P2, E2, *import_args(goal="triage_a", run_id="named_run"))
check("recorded: import-run --goal names the goal the run answers", r.returncode == 0 and (
    _runstore.record_of(P2, "named_run").get("goal") == "triage_a"), (r.stdout + r.stderr)[-300:])  # fmt: skip
r = evh(P2, E2, *RUN, "--goal", "triage_a", "--run-id", "named_evh_run")
check(
    "recorded: evh run --goal names the goal, and the policy accepts it",
    r.returncode == 0 and _runstore.record_of(P2, "named_evh_run").get("goal") == "triage_a",
    (r.stdout + r.stderr)[-300:],
)

# ── a reference the run is scored against is the one it names; a tier follows the id ───────────────────────────
print("\n-- import-run records the tier of the reference it names")
P3, E3 = fresh()
(P3 / "s.jsonl").write_text(SCORES, encoding="utf-8")
r = evh(P3, E3, *import_args(reference_id=REF, run_id="with_ref"))
rec = score_record(P3, "with_ref")
check(
    "recorded: import-run --reference-id alone records its tier (gold), not a reference with no tier",
    r.returncode == 0 and rec.get("reference_tier") == "gold",
    f"exit {r.returncode}, reference_tier {rec.get('reference_tier')!r}: {(r.stdout + r.stderr)[-200:]}",
)
r = evh(P3, E3, *import_args(run_id="no_ref"))
check(
    "recorded: import-run with no reference records none (no tier either)",
    r.returncode == 0 and "reference_tier" not in score_record(P3, "no_ref"),
    score_record(P3, "no_ref").get("reference_tier"),
)

# ── cost: unknown, zero, and known for some items ───────────────────────────────────────────────────────────────
print("\n-- cost: unknown is not zero, and a total that some items did not report says so")
COST_ADAPTER = '''"""A stub adapter: the cost it reports by the system's `cost_mode`."""
from evaluation_harness.adapter import Result

PRIMARY_METRIC = "n"
_calls = [0]


def call_system(text, params):
    _calls[0] += 1
    mode = params.get("cost_mode")
    cost = {"zero": 0.0, "none": None, "mixed": 0.0 if _calls[0] % 2 else None}[mode]
    return Result(output=text[:20], tokens_in=10, tokens_out=3, cost_usd=cost)


def score(output, reference=None):
    return {"n": 1.0}
'''
P4, E4 = fresh()
(P4 / "adapter.py").write_text(COST_ADAPTER, encoding="utf-8")
for mode in ("zero", "none", "mixed"):
    put(
        P4,
        f"systems/cost_{mode}_v1.yaml",
        f"system_id: cost_{mode}_v1\nparams:\n  provider: stub\n  model: m\n  cost_mode: {mode}\n",
    )
    r = evh(P4, E4, "run", "--system", f"cost_{mode}_v1", "--dataset", DS, "--run-id", f"cost_{mode}")
    check(f"cost {mode}: the run is written", r.returncode == 0, (r.stdout + r.stderr)[-300:])
zero, none, mixed = (score_record(P4, f"cost_{m}") for m in ("zero", "none", "mixed"))
check(
    "recorded: every item reported 0.0: total_cost_usd is 0.0, a zero and not an absence",
    zero.get("scores", {}).get("total_cost_usd") == 0.0 and "cost_coverage" not in zero,
    zero.get("scores"),
)
check(
    "recorded: no item reported a cost: no total_cost_usd, no cost_usd (unknown is not zero), and no coverage to state",
    "total_cost_usd" not in none.get("scores", {})
    and "cost_usd" not in none.get("scores", {})
    and "cost_coverage" not in none,
    none.get("scores"),
)
check(
    "recorded: some items reported a cost: cost_coverage says how many (the total is of those)",
    mixed.get("cost_coverage") == {"items_with_cost": 3, "items": 6}
    and "total_cost_usd" in mixed.get("scores", {}),
    f"{mixed.get('cost_coverage')} {mixed.get('scores')}",
)

# ── a goal whose measure no run records, or whose direction is no direction ─────────────────────────────────────
print("\n-- a goal the runs cannot answer is said, where it is written")
P5, E5 = fresh()
GOAL = (
    "goal-new", "g_prose", "--set", "title=t", "--set", "statement=s", "--set", "decision=d", "--set", "status=active",
    "--set", "success_criteria.primary.measure=Prose measure", "--set", "success_criteria.primary.direction=non_inferior",
    "--set", f'datasets=[{{"dataset_id":"{DS}","role":"validation"}}]',
)  # fmt: skip
r = evh(P5, E5, *GOAL)
out = r.stdout + r.stderr
check(
    "recorded: goal-new says the primary measure is recorded by no run on its dataset, naming the measure and what is",
    r.returncode == 0 and "Prose measure" in out and "overlap_f1" in out and "WARNING" in out,
    out[-400:],
)
check(
    "recorded: goal-new says a direction that is neither lower nor higher is not one",
    "non_inferior" in out and "neither lower nor higher" in out,
    out[-400:],
)
r = evh(P5, E5, "run-promote", "--run", FIRST_Y, "--goal", "g_prose", "--allow-dirty", "--reason", REASON)
out = r.stdout + r.stderr
check(
    "recorded: run-promote names that the run records no value of the goal's primary measure",
    r.returncode == 0 and "WARNING" in out and "Prose measure" in out,
    out[-400:],
)
r = evh(
    P5, E5, "goal-set", "g_prose",
    "--set", "success_criteria.primary.measure=overlap_f1", "--set", "success_criteria.primary.direction=higher",
)  # fmt: skip
check(
    "goal-set to a measure the runs record and a real direction says nothing",
    r.returncode == 0 and "WARNING" not in r.stdout + r.stderr,
    (r.stdout + r.stderr)[-300:],
)

# ── validate names each broken link, with its file ──────────────────────────────────────────────────────────────
print("\n-- validate: one broken link at a time")


def validate(proj: Path, env: dict[str, str]) -> str:
    """`evh validate` in the project: its output."""
    r = evh(proj, env, "validate")
    return r.stdout + r.stderr


def line_of(out: str, tag: str) -> list[str]:
    """The lines a check printed: its details, then its result line (ok, FAIL or --)."""
    pending = []
    for ln in out.splitlines():
        pending.append(ln)
        if re.match(r"\s+(ok|FAIL|--)\s+V\d+\b", ln):
            if ln.split()[1] == tag:
                return pending
            pending = []
    return []


def broken(label: str, mutate, tag: str, names: list[str], fails: bool = True) -> None:
    """On a copy of the project, `mutate` breaks one link; check `tag` fails (or, with `fails` False, only notes: no
    `FAIL tag`, exit 0, and a `note:` line) and names every string of `names`."""
    proj, env = fresh()
    mutate(proj, env)
    r = evh(proj, env, "validate")
    out = r.stdout + r.stderr
    shown = (
        " ".join(line_of(out, tag))
        if fails
        else " ".join(ln for ln in out.splitlines() if ln.lstrip().startswith("note:"))
    )
    check(
        f"validate: {label}: {tag + ' fails' if fails else 'a note'}, naming {', '.join(names)}",
        (f"FAIL {tag}" in out if fails else f"FAIL {tag}" not in out)
        and all(n in shown for n in names)
        and "Traceback" not in out,
        shown[-600:],
    )
    if fails:
        check(f"validate: {label}: the run exits non-zero", "VALIDATION FAILED" in out, out[-200:])
    else:
        check(f"validate: {label}: the run exits 0", r.returncode == 0, f"exit {r.returncode}: {out[-300:]}")


def scored_run(proj: Path, run_id: str = FIRST_Y) -> str:
    """The folder under runs/ of a run's first score."""
    return next(
        p.rsplit("/", 1)[0]
        for p in _runstore.files_under(proj, f"runs/{run_id}/scores")
        if p.endswith("score.json")
    )


def lose_reference(proj: Path, env: dict[str, str]) -> None:
    """The reference a run was scored against, removed."""
    _runstore.rmtree(proj, f"references/gold/{DS}")


def lose_label_set(proj: Path, env: dict[str, str]) -> None:
    """The label set a re-score read, removed."""
    evh(proj, env, "rescore", "--dataset-id", DS, "--labels", "g")
    _runstore.rmtree(proj, f"labels/{DS}/g")


def lose_baseline_run(proj: Path, env: dict[str, str]) -> None:
    """The run a baseline was promoted from, removed."""
    _runstore.rmtree(proj, f"runs/{FIRST_Y}")


def lose_of(proj: Path, env: dict[str, str]) -> None:
    """A repeat's `of`, made to name a run that is not there."""
    rec = _runstore.record_of(proj, F["joined"])
    rec["of"] = "ghost_run"
    put(proj, f"runs/{F['joined']}/run.json", json.dumps(rec, indent=2) + "\n")


def lose_goal_dataset(proj: Path, env: dict[str, str]) -> None:
    """A goal's dataset, made to name one that is not there."""
    text = _runstore.read_text(proj, "goals/triage_a.yaml")
    put(proj, "goals/triage_a.yaml", text.replace(DS, "ghost_v1"))


def lose_round_run(proj: Path, env: dict[str, str]) -> None:
    """A round's run, made to name one that is not there."""
    f = "rounds/triage_a/r1.yaml"
    put(proj, f, _runstore.read_text(proj, f).replace(SET_RUN, "ghost_run"))


broken(
    "a run's reference that is not there",
    lose_reference, "V30", [f"runs/{FIRST_Y}/run.json", f"reference {REF!r}"],
)  # fmt: skip
broken(
    "a run's label set that is not there",
    lose_label_set, "V30", [f"runs/{FIRST_Y}/scores/", "metrics.json", f"label set 'labels/{DS}/g'"],
)  # fmt: skip
broken(
    "a baseline's run that is not there",
    lose_baseline_run, "V6", [f"triage_b/{DS}/1.json", FIRST_Y, "no such run"],
)  # fmt: skip
broken(
    "a repeat's `of` that is not there",
    lose_of, "V29", [f"runs/{F['joined']}/run.json", "ghost_run"], fails=False,
)  # fmt: skip
broken(
    "a goal's dataset that is not there",
    lose_goal_dataset, "V30", ["V30 goal triage_a", "ghost_v1", "names no dataset", "FAIL from 0.9"], fails=False,
)  # fmt: skip
broken(
    "a round's run that is not there",
    lose_round_run, "V14", ["rounds/triage_a/r1.yaml", "ghost_run"],
)  # fmt: skip

print("\n-- and a project whose links all resolve passes them")
out = validate(P3, E3)
check(
    "validate: the sound project passes V30, V6, V14 and V29",
    all(line_of(out, t) and "FAIL" not in " ".join(line_of(out, t)) for t in ("V30", "V6", "V14", "V29")),
    out[-600:],
)

for p in PROJECTS:
    shutil.rmtree(p, ignore_errors=True)
sys.exit(summary())
