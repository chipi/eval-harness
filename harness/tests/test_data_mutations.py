#!/usr/bin/env python3
"""Real-looking data, changed the way a hand, an older release or another tool changes it, read by every reader (RFC-041,
PLAN 0.8.1 R5).

    EVAL_STORE=files  python tests/test_data_mutations.py [MUTATION ...]
    EVAL_STORE=sqlite python tests/test_data_mutations.py [MUTATION ...]

Why: R2's look-alike projects and R3's cross-reader check read the data the harness made and the shapes the beta projects
had. The data a project really holds drifts from both: a run with no goal beside runs that name one, a cost of 0 beside a
cost nobody recorded, `dirty: null`, ids in other scripts, a `_r1` name that is no repeat set, a field an older release did
not write and one a newer one does, two goals on one dataset with two baselines, a stamp near a UTC midnight read in a zone
a day away, a public environment with no hosts, a reference that is gone, a goal measure no run records.

Each mutation of the table (`MUTATIONS` below, applied by `_mutations.py`) is applied to a fresh copy of the tutorial
project and of R2's three look-alikes (`_agree_projects.py`, built once in the store EVAL_STORE names); a control row, the
four projects unchanged, is read the same way. Of each copy it asks:

  - every read command (the CLI, the catalog build, `validate`): no traceback, and exit 0 or a refusal that names its kind;
  - every reader of R3 (the CLI, the API, the MCP reads, the export, the inspector): no traceback, and they agree;
  - the facts the files say (`_mutations.oracle`): each arm's cost state, the UTC day of its latest run, each run's `dirty`;
  - `evh validate` names the mutation (a FAIL or a note that mentions it) where the data is wrong, and says nothing new where
    it is legal data (a run that names no goal): the same failing checks as the control, no traceback;
  - what the mutation is about, by hand (`HAND`): the unicode arms are in every reader, three plain runs are one arm of
    three runs, two goals promote two baselines, a public environment shows no text of a hidden dataset.

A disagreement or a traceback this finds is a bug: it is fixed where it is made (RFC-041), never listed here.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _mutations as MUT  # noqa: E402
import _serve  # noqa: E402
import test_reader_agreement as RA  # noqa: E402
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

FD = RA.FD
STORE = RA.STORE
PROJECTS = ("tutorial", "imported", "fleet", "bakeoff")
TRACEBACK = "Traceback"
REFUSAL = re.compile(r"^ERROR \(([a-z-]+)\)", re.M)
COPIES: list[Path] = []
JOBS = max(2, min(8, (os.cpu_count() or 4) // 3))
KIRITIMATI, PAGO_PAGO = "Pacific/Kiritimati", "Pacific/Pago_Pago"


@dataclass(frozen=True)
class Mutation:
    """One row of the table: what is done to a copy, and what a reader may and must say of it."""

    name: str
    what: str
    data: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    #: a regex `evh validate`'s output must match: the check or note that names the mutation, for every project or for the
    #: projects it lists. Where it is None the data is legal, and validate must fail the same checks as on the control and
    #: print no traceback.
    names: str | dict[str, str] | None = None
    #: what `evh validate` says of it (RUNBOOK exit codes): exit 6 and a `FAIL <check>` line, or exit 0 and no new FAIL
    #: line (the `names` match is a `note:`; the bakeoff control fails V5 on its own). None: either exit is taken (no document says which).
    verdict: tuple[int, str] | None = None


MUTATIONS: tuple[Mutation, ...] = (
    Mutation("control", "the four projects unchanged"),
    Mutation("no_goal", "runs that name no goal beside runs that do", "no_goal"),
    Mutation(
        "cost_zero_and_missing",
        "a run that records a cost of 0 beside one that records none",
        "cost_zero_and_missing",
    ),
    Mutation("dirty_null", "build.dirty is null on every run", "dirty_null"),
    Mutation(
        "unicode_ids",
        "a system, a dataset and run ids in other scripts",
        "unicode_ids",
        names=rf"(?s){re.escape(MUT.UNICODE_DATASET)}[^\n]*\n.*FAIL V1 ",
        verdict=(6, "V1"),
    ),
    Mutation(
        "underscore_r_not_a_set",
        "<id>_r1 and <id>_r2 made by hand, no repeat_index",
        "underscore_r_not_a_set",
        names=r"(?s)\d+ runs claim '[^']+' on \S+ — [^\n]*_r1[^\n]*\n.*FAIL V8 ",
        verdict=(6, "V8"),
    ),
    Mutation(
        "missing_optional_fields",
        "fields the run schema does not require are missing",
        "missing_optional_fields",
    ),
    Mutation(
        "n_items_missing",
        "n_items, which the run schema requires, is missing",
        "n_items_missing",
        names=r"'n_items' is a required property",
        verdict=(6, "V1"),
    ),
    Mutation(
        "extra_unknown_fields",
        "fields no release defines, in the record, build and fingerprint",
        "extra_unknown_fields",
        names=r"Additional properties are not allowed \('future', 'tags', 'x_ticket' were unexpected\)",
        verdict=(6, "V1"),
    ),
    Mutation(
        "two_goals_two_baselines",
        "two goals on one dataset, each with its own baseline",
        "two_goals_two_baselines",
    ),
    Mutation(
        "tz_kiritimati", "stamps near a UTC midnight, read in UTC+14", "utc_day_boundary", {"TZ": KIRITIMATI}
    ),
    Mutation(
        "tz_pago_pago", "stamps near a UTC midnight, read in UTC-11", "utc_day_boundary", {"TZ": PAGO_PAGO}
    ),
    Mutation(
        "public_env",
        "EVH_PUBLIC set, no public hosts, a hidden dataset",
        "hide_a_dataset",
        {"EVH_PUBLIC": "1"},
    ),
    Mutation(
        "reference_gone",
        "the reference a run was scored against no longer exists",
        "reference_gone",
        names=r"note: V16 references: \d+ run\(s\) scored against (gold|silver)/\S+, which is not under data/references",
        verdict=(6, "V30"),
    ),
    Mutation(
        "goal_measure_unrecorded",
        "a goal's primary measure no run records",
        "goal_measure_unrecorded",
        names=rf"primary measure '{MUT.NO_SUCH_MEASURE}' is recorded by no run",
        verdict=(0, ""),
    ),
    Mutation(
        "no_fingerprint",
        "every second run has no fingerprint (a repeat that joined its run through it joins no more)",
        "no_fingerprint",
        names={"fleet": r"where it is no longer read: it is a repeat of \S+, which is not the run it joined"},
    ),
)
BY_NAME = {m.name: m for m in MUTATIONS}


# ── one copy of one project, mutated ─────────────────────────────────────────────────────────────────────────────────
class Copy(RA.Project):
    """A copy of a built project, read by the readers of `test_reader_agreement` as the project itself is (name, proj, env,
    evh); it is not built again, so `Project.__init__` is not run."""

    def __init__(self, mutation: Mutation, base: RA.Project) -> None:
        self.mutation = mutation
        self.name = f"{mutation.name}@{base.name}"
        self.project = base.name
        self.proj = Path(tempfile.mkdtemp(prefix=f"evh-mut-{mutation.name}-{base.name}-"))
        COPIES.append(self.proj)
        shutil.copytree(base.proj, self.proj, symlinks=True, dirs_exist_ok=True)
        self.env = {**dict(base.env, EVAL_HOME=str(self.proj)), **mutation.env}
        RA.SPENT[self.name] = {}

    def helper(self, *args: str) -> str:
        """`_mutations.py <args>` in a process of its own, with this copy's environment but not its time zone or public
        flag (the data is made the same wherever it is read); its output, or RuntimeError with its tail."""
        env = {k: v for k, v in self.env.items() if k not in ("TZ", "EVH_PUBLIC")}
        env["EVAL_BUILD_REF"] = "mutation-fixture"
        r = subprocess.run(  # nosec B603 - this interpreter and the test's own helper
            [sys.executable, str(HERE / "_mutations.py"), *args, str(self.proj)],
            cwd=self.proj, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900, check=False, encoding="utf-8",
        )  # fmt: skip
        if r.returncode != 0:
            raise RuntimeError(f"_mutations.py {' '.join(args)} failed: {(r.stdout + r.stderr)[-700:]}")
        return r.stdout


@dataclass
class Outcome:
    """What reading one mutated copy gave."""

    copy: Copy
    seconds: float = 0.0
    oracle: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, RA.FactMap] = field(default_factory=dict)
    why: dict[str, list[str]] = field(default_factory=dict)
    reader_errors: dict[str, str] = field(default_factory=dict)
    reads: list[tuple[str, int, str, str]] = field(default_factory=list)
    validate: str = ""
    validate_exit: int = -1
    runs_json: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def evh(c: Copy, *args: str, public: bool | None = None) -> subprocess.CompletedProcess:
    """`evh <args>` in the copy, with its environment; `public` True or False sets or clears EVH_PUBLIC for this call."""
    env = dict(c.env)
    if public is not None:
        env.pop("EVH_PUBLIC", None)
        if public:
            env["EVH_PUBLIC"] = "1"
    return _cli.run(c.proj, env, *args)


def inventory(c: Copy, o: Outcome) -> dict[str, Any]:
    """What to ask the read commands about: the datasets, systems, arms, metrics and goals this copy has."""
    runs = o.oracle["runs"]
    cli = {k: v for r, d in o.facts.items() if r.startswith("cli:") for k, v in d.items()}
    datasets = sorted({r["dataset"] for r in runs.values()} | {k[1][0] for k in cli if k[0] == "arms"})
    arms = sorted({k[1][0] for k in cli if k[0] == "n_runs"})
    metrics = sorted({k[1][1] for k in cli if k[0] == "direction"})
    goals: list[str] = []
    r = evh(c, "goal-list", "--json")
    if r.returncode == 0:
        goals = [g["goal"] for g in (json.loads(r.stdout).get("result") or {}).get("goals") or []]
    return {
        "datasets": datasets,
        "arms": arms,
        "metrics": metrics,
        "goals": goals,
        "systems": sorted({r["system"] for r in runs.values()}),
    }


def read_commands(inv: dict[str, Any], oracle: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Every read command, with the arguments this copy gives it: the global ones, then one per dataset, metric, goal,
    system and arm (the first few of each, so the project of 64 arms does not take a minute a mutation)."""
    cmds: list[list[str]] = [
        ["runs-list"], ["arm-list"], ["arm-list", "--systems", "1"], ["metric-list"], ["goal-list"], ["overview-show"],
        ["baselines"], ["cost-report"], ["dataset-list"], ["system-list"], ["model-list"], ["activity-show"],
        ["reference-list"], ["picks"], ["looks"], ["prompt-list"], ["scorer-list"], ["env-check"], ["migrate", "--check"],
    ]  # fmt: skip
    datasets = inv["datasets"]
    if datasets:
        cmds.append(["search", datasets[0]])
    first_items = oracle.get("first_items") or {}
    runs = oracle["runs"]
    for ds in datasets:
        cmds += [
            ["leaderboard", ds], ["dataset-show", ds], ["dataset-items", ds], ["dataset-arm-list", ds],
            ["cost-report", "--dataset-id", ds], ["dataset-card", ds], ["label-set-list", ds],
        ]  # fmt: skip
        if first_items.get(ds):
            cmds.append(["dataset-items", ds, "--item", first_items[ds]])
        systems = sorted({r["system"] for r in runs.values() if r["dataset"] == ds})
        if len(systems) > 1:
            cmds.append(["pair-test", ds, "--a", systems[0], "--b", systems[1], "--json"])
        ids = sorted(i for i, r in runs.items() if r["dataset"] == ds)
        if len(ids) > 1:
            cmds.append(["run-compare", "--baseline", ids[0], "--candidate", ids[-1]])
        on = [a for a in inv["arms"] if f"/{ds}/" in a][:2]
        for a in on:
            label, _d, system = FD.split_arm(a, set(datasets))
            cmds.append(["arm-show", label or "runs", ds, system])
            if first_items.get(ds):
                cmds.append(["comparison-item", "--runs", a, "--item", first_items[ds]])
        if on:
            cmds.append(["sheet-show", ds, "--runs", on[0]])
            cmds.append(
                ["comparison-show", "--runs", ",".join(on)]
                + (["--metric", inv["metrics"][0]] if inv["metrics"] else [])
            )
    cmds += [["metric-show", m] for m in inv["metrics"][:8]]
    for g in inv["goals"]:
        cmds += [
            ["goal-show", g],
            ["goal-status", g],
            ["goal-leaderboard", g],
            ["goal-history", g],
            ["round-list", g],
        ]
    cmds += [["system-show", s] for s in inv["systems"][:6]]
    return [(" ".join(c), c) for c in cmds]


def run_reads(c: Copy, cmds: list[tuple[str, list[str]]]) -> list[tuple[str, int, str, str]]:
    """(label, exit code, the refusal's kind or '', a traceback marker or '') of each command run in the copy."""

    def one(item: tuple[str, list[str]]) -> tuple[str, int, str, str]:
        label, args = item
        r = evh(c, *args)
        out = r.stdout + r.stderr
        refused = REFUSAL.search(r.stderr)
        return (
            label,
            r.returncode,
            refused.group(1) if refused else "",
            (out[out.find(TRACEBACK) :][:300] if TRACEBACK in out else ""),
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(one, cmds))


def read_all(c: Copy) -> tuple[dict[str, RA.FactMap], dict[str, list[str]], dict[str, str], Any]:
    """R3's readers on the copy, each on its own so one that fails does not hide the others: (facts, why, errors, the CLI's
    collection)."""
    facts: dict[str, RA.FactMap] = {}
    why: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    collected: Any = None

    def add(got: tuple[dict[str, RA.FactMap], dict[str, list[str]]]) -> None:
        facts.update(got[0])
        why.update(got[1])

    for name, fn in (
        ("cli", lambda: RA.cli_reader(c)),
        ("api", lambda: RA.api_reader(c)),
        ("mcp", lambda: RA.mcp_reader(c)),
        ("catalog", lambda: RA.catalog_reader(c)),
    ):
        try:
            got = fn()
        except Exception as exc:  # noqa: BLE001 - a reader that fails is a finding the check names
            errors[name] = f"{type(exc).__name__}: {str(exc)[-500:]}"
            continue
        if name in ("cli", "api"):
            if name == "cli":
                collected = got
            add(RA.prefixed(name, got))
        else:
            add(got)
    if collected is not None:
        try:
            add(RA.api_inspector(c, {k: v for d in collected.facts.values() for k, v in d.items()}))
        except Exception as exc:  # noqa: BLE001
            errors["inspector"] = f"{type(exc).__name__}: {str(exc)[-500:]}"
    return facts, why, errors, collected


def public_pass(c: Copy, o: Outcome) -> dict[str, Any]:
    """In a public environment with no hosts: what the commands and a local server say of a hidden dataset's items. Returns
    {dataset: [the stretches of its items' text that appear in an answer]}, and under "seen" whether the same item
    command shows that text where it may (a probe that cannot see the text finds no leak)."""
    leaks: dict[str, Any] = {"seen": {}}
    hidden = o.oracle["hidden"]
    cli = {k: v for r, d in o.facts.items() if r.startswith("cli:") for k, v in d.items()}
    srv, port, _out = _serve.start(c.proj, c.env)
    try:
        tok = c.proj / ".build" / "api-token"
        api = RA.Http(
            port, tok.read_text(encoding="utf-8").strip() if tok.exists() else None, f"127.0.0.1:{port}"
        )
        for ds, items in hidden.items():
            if not items:
                continue
            item, sentinel = next(iter(items.items()))
            arms = [k[1][0] for k in cli if k[0] == "n_runs" and f"/{ds}/" in k[1][0]]
            outputs: list[str] = []
            for args in (
                ["dataset-items", ds, "--item", item],
                ["comparison-item", "--runs", ",".join(arms[:1]), "--item", item],
                ["sheet-show", ds, "--runs", ",".join(arms[:1])],
            ):
                if "--runs" in args and not arms:
                    continue
                r = evh(c, *args, "--json")
                outputs.append(r.stdout + r.stderr)
            if arms:
                _s, body = api.get("/api/item?" + urllib.parse.urlencode({"arms": arms[0], "item": item}))
                outputs.append(json.dumps(body, ensure_ascii=False))
            _s, body = api.get(
                f"/api/v1/datasets/{urllib.parse.quote(ds)}/items?" + urllib.parse.urlencode({"item": item})
            )
            outputs.append(json.dumps(body, ensure_ascii=False))
            leaks[ds] = [s for s in items.values() if any(s in text for text in outputs)]
            local = evh(c, "dataset-items", ds, "--item", item, "--json", public=False)
            leaks["seen"][ds] = sentinel in local.stdout
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except subprocess.TimeoutExpired:
            srv.kill()
    return leaks


def process(mutation: Mutation, base: RA.Project) -> Outcome:
    """Copy `base`, apply the mutation, and read the copy every way (reads, R3's readers, validate)."""
    t = time.time()
    c = Copy(mutation, base)
    if mutation.data:
        c.helper(mutation.data)
    o = Outcome(c)
    o.oracle = json.loads(c.helper("oracle"))
    t_read = time.time()
    o.facts, o.why, o.reader_errors, _collected = read_all(c)
    RA.SPENT[c.name]["readers"] = time.time() - t_read
    inv = inventory(c, o)
    o.reads = run_reads(c, read_commands(inv, o.oracle))
    r = evh(c, "validate")
    o.validate, o.validate_exit = r.stdout + r.stderr, r.returncode
    r = evh(c, "runs-list", "--json")
    o.runs_json = (json.loads(r.stdout).get("result") or {}).get("runs", []) if r.returncode == 0 else []
    if "EVH_PUBLIC" in mutation.env:
        o.extra["leaks"] = public_pass(c, o)
    o.seconds = time.time() - t
    return o


# ── what the files say of each arm ───────────────────────────────────────────────────────────────────────────────────
def arm_facts(o: Outcome, kind: str) -> dict[str, Any]:
    """The CLI's arm-show answer for `kind`, by arm."""
    d = o.facts.get("cli:arm-show", {})
    return {key[0]: v for (k, key), v in d.items() if k == kind}


def oracle_cost_state(o: Outcome, arm_runs: list[str]) -> str:
    """The cost state the files give an arm: the mean of the costs its runs record (none recorded is unknown)."""
    costs = [
        o.oracle["runs"][r]["cost"]
        for r in arm_runs
        if r in o.oracle["runs"] and o.oracle["runs"][r]["cost"] is not None
    ]
    return "unknown" if not costs else "zero" if sum(costs) / len(costs) == 0 else "amount"


def oracle_checks(o: Outcome) -> list[tuple[str, bool, Any]]:
    """The facts every reader gives, against the files: each arm's cost state and the UTC day of its latest run, and
    each run's `dirty` as `runs-list --json` says it."""
    out: list[tuple[str, bool, Any]] = []
    runs_of = arm_facts(o, "runs")
    costs, days = arm_facts(o, "cost_state"), arm_facts(o, "latest_day")
    bad_cost = [
        (a, costs[a], oracle_cost_state(o, rs))
        for a, rs in runs_of.items()
        if a in costs and costs[a] != oracle_cost_state(o, rs)
    ]
    out.append(("files: each arm's cost state is the one its runs record", not bad_cost, bad_cost[:3]))
    bad_day = []
    for a, rs in runs_of.items():
        stamps = [
            o.oracle["runs"][r]["created_at"]
            for r in rs
            if r in o.oracle["runs"] and o.oracle["runs"][r]["created_at"]
        ]
        if a in days and stamps and days[a] != max(stamps)[:10]:
            bad_day.append((a, days[a], max(stamps)[:10]))
    out.append(("files: each arm's latest day is the UTC day of its latest run", not bad_day, bad_day[:3]))
    bad_dirty = [
        (x["run_id"], x.get("dirty"), o.oracle["runs"][x["run_id"]]["dirty"])
        for x in o.runs_json
        if x["run_id"] in o.oracle["runs"]
        and (x.get("dirty") if x.get("dirty") is not None else "absent")
        != o.oracle["runs"][x["run_id"]]["dirty"]
        and not (x.get("dirty") is None and o.oracle["runs"][x["run_id"]]["dirty"] in (None, "absent"))
    ]
    out.append(
        ("files: runs-list says each run's dirty as recorded (null stays null)", not bad_dirty, bad_dirty[:3])
    )
    unknown = sorted({x["run_id"] for x in o.runs_json} - set(o.oracle["runs"]))
    out.append(
        (
            "files: runs-list lists runs, and only runs the files hold",
            bool(o.runs_json) and not unknown,
            unknown[:3],
        )
    )
    return out


# ── what each mutation is about, by hand ─────────────────────────────────────────────────────────────────────────────
def hand_unicode(o: Outcome) -> list[tuple[str, bool, Any]]:
    """The arms of the unicode dataset are given by the CLI and by the catalog's pages, and the unicode system's arm is on a real dataset."""
    givers = {
        r for r, d in o.facts.items() if any(k == "arms" and key == (MUT.UNICODE_DATASET,) for k, key in d)
    }
    cli_arms = [
        a for (k, key), v in o.facts.get("cli:arm-show", {}).items() if k == "n_runs" for a in [key[0]]
    ]
    return [
        (
            "hand: the unicode dataset's arms are given by the CLI and by the export",
            {"cli:arm-list", "catalog:arms index"} <= givers,
            sorted(givers),
        ),
        (
            "hand: the unicode system has an arm",
            any(f"/{MUT.UNICODE_SYSTEM}" in a for a in cli_arms),
            cli_arms[:4],
        ),
    ]


def hand_underscore(o: Outcome) -> list[tuple[str, bool, Any]]:
    """The newest run and its two hand-named `_r1` and `_r2` copies are three runs of one arm: no repeat set."""
    ids = sorted(o.oracle["runs"])
    named = [
        i
        for i in ids
        if re.search(r"_r[12]$", i)
        and i[:-3] in o.oracle["runs"]
        and o.oracle["runs"][i]["dataset"] == o.oracle["runs"][i[:-3]]["dataset"]
    ]
    runs_of = arm_facts(o, "runs")
    n_runs = arm_facts(o, "n_runs")
    together = [
        a for a, rs in runs_of.items() if named and all(n in rs for n in named[:2]) and named[0][:-3] in rs
    ]
    return [
        (
            "hand: the hand-named _r1 and _r2 copies are runs of the arm of the run they copy",
            bool(named) and bool(together),
            (named, together),
        ),
        (
            "hand: that arm counts three runs, all read as plain",
            bool(together) and n_runs.get(together[0]) == 3,
            n_runs.get(together[0]) if together else None,
        ),
    ]


def hand_two_goals(o: Outcome) -> list[tuple[str, bool, Any]]:
    """The two goals promoted two runs of two systems as baselines, and the goal pages name each."""
    cli = o.facts.get("cli:goal-leaderboard", {})
    base = {
        key[1]: v
        for (k, key), v in cli.items()
        if k == "baseline_arm" and key[1] in ("mutation_goal_a", "mutation_goal_b")
    }
    page = {
        key[1]: v
        for (k, key), v in o.facts.get("catalog:dataset page", {}).items()
        if k == "baseline_arm" and key[1] in ("mutation_goal_a", "mutation_goal_b")
    }
    return [
        (
            "hand: each goal names a baseline arm, and the two differ",
            len(base) == 2 and len(set(base.values())) == 2,
            base,
        ),
        (
            "hand: the dataset's page in the export names each goal's baseline",
            len(page) == 2 and page == base,
            (page, base),
        ),
    ]


def hand_public(o: Outcome) -> list[tuple[str, bool, Any]]:
    """In a public environment with no hosts a hidden dataset's text is in no answer."""
    leaks = o.extra.get("leaks", {})
    return [
        ("hand: a hidden dataset exists to withhold", bool(o.oracle["hidden"]), list(o.oracle["hidden"])),
        (
            "hand: the item command shows a hidden dataset's text on a person's own machine, so the probe can see it",
            bool(leaks.get("seen")) and all(leaks["seen"].values()),
            leaks.get("seen"),
        ),
        (
            "hand: no answer shows a hidden dataset's text (CLI items, item comparison, sheet, the inspector's item, the API's items)",
            not any(v for k, v in leaks.items() if k != "seen"),
            leaks,
        ),
    ]


def hand_tz(o: Outcome) -> list[tuple[str, bool, Any]]:
    """Some arm's latest run is one of the stamps at the boundary, so the day check above looked at it."""
    days = set(arm_facts(o, "latest_day").values())
    return [
        (
            "hand: an arm's latest day is the UTC day before or after midnight, not the zone's",
            bool(days & {"2026-11-30", "2026-12-01"}),
            sorted(days)[:4],
        )
    ]


def hand_dirty(o: Outcome) -> list[tuple[str, bool, Any]]:
    """Every run is listed with dirty null."""
    return [
        (
            "hand: runs-list --json says null for every run",
            bool(o.runs_json) and all(x.get("dirty") is None for x in o.runs_json),
            [x.get("dirty") for x in o.runs_json[:3]],
        )
    ]


def hand_cost(o: Outcome) -> list[tuple[str, bool, Any]]:
    """The files hold a run that records 0 and one that records none; the check above tells each arm's state apart."""
    costs = [r["cost"] for r in o.oracle["runs"].values()]
    return [
        (
            "hand: the files hold a run that records a cost of 0 and one that records none",
            0.0 in costs and None in costs,
            costs[:6],
        )
    ]


HAND: dict[str, Callable[[Outcome], list[tuple[str, bool, Any]]]] = {
    "unicode_ids": hand_unicode,
    "underscore_r_not_a_set": hand_underscore,
    "two_goals_two_baselines": hand_two_goals,
    "public_env": hand_public,
    "tz_kiritimati": hand_tz,
    "tz_pago_pago": hand_tz,
    "dirty_null": hand_dirty,
    "cost_zero_and_missing": hand_cost,
}


# ── the checks ───────────────────────────────────────────────────────────────────────────────────────────────────────
def fail_labels(text: str) -> list[str]:
    """The checks `evh validate` failed, by their V-number."""
    return sorted(re.findall(r"^  FAIL (V\d+)", text, re.M))


def said(dis: list[dict[str, Any]], n: int = 2) -> str:
    """The first disagreements with what each reader said: the readers that agree are named together."""
    out = []
    for d in dis[:n]:
        groups: dict[str, list[str]] = {}
        for r, v in sorted(d["values"].items()):
            groups.setdefault(json.dumps(v, ensure_ascii=False, sort_keys=True), []).append(r)
        out.append(
            f"{d['fact']} {'/'.join(d['key'])}: "
            + " | ".join(f"{'+'.join(rs)} = {v}" for v, rs in groups.items())
        )
    return "; ".join(out) + (f" (+{len(dis) - n} more)" if len(dis) > n else "")


def judge(o: Outcome, control: Outcome | None) -> dict[str, str]:
    """Run the checks of one copy; the cell the table prints for it ('ok', or what failed)."""
    m, name = o.copy.mutation, o.copy.name
    flags: list[str] = []

    def chk(label: str, ok: bool, detail: Any = None, flag: str = "") -> None:
        check(f"{name}: {label}", ok, "" if ok else str(detail)[:700])
        if not ok:
            flags.append(flag or label.split(":")[0])

    traces = [(lab, tb) for lab, _rc, _k, tb in o.reads if tb]
    unnamed = [(lab, rc) for lab, rc, kind, tb in o.reads if rc != 0 and not kind and not tb]
    chk("reads: no traceback", not traces, traces[:2], "traceback")
    chk("reads: exit 0 or a refusal that names its kind", not unnamed, unnamed[:4], "unnamed exit")
    chk("readers: each answered", not o.reader_errors, o.reader_errors, "reader failed")
    shapes = {r: [w for w in ws if "Traceback" in w or "unexpected shape" in w] for r, ws in o.why.items()}
    shapes = {r: w for r, w in shapes.items() if w}
    chk("readers: no traceback and no answer of an unexpected shape", not shapes, shapes, "shape")
    unnamed_why = {r: [w for w in ws if "exit" in w and "ERROR (" not in w][:2] for r, ws in o.why.items()}
    unnamed_why = {r: w for r, w in unnamed_why.items() if w}
    chk(
        "readers: a command that gave no answer refused with a named kind",
        not unnamed_why,
        unnamed_why,
        "unnamed refusal",
    )
    dis = RA.compare(o.facts)
    chk(
        f"agree: R3's check ({RA.thin(o.facts)} facts given by two readers or more)",
        not dis and RA.thin(o.facts) > 0,
        said(dis),
        "disagree",
    )
    for label, ok, detail in oracle_checks(o):
        chk(label, ok, detail, "files")
    for label, ok, detail in HAND.get(m.name, lambda _o: [])(o):
        chk(label, ok, detail, "hand")
    chk("validate: no traceback", TRACEBACK not in o.validate, o.validate[-400:], "traceback")
    names = m.names.get(o.copy.project) if isinstance(m.names, dict) else m.names
    if names:
        chk("validate names it", bool(re.search(names, o.validate)), o.validate[-700:], "validate silent")
        if m.verdict is None:
            chk(
                "validate: refuses with a failing check, or says it in a note",
                o.validate_exit in (0, 6),
                o.validate_exit,
                "validate exit",
            )
        elif m.verdict[0] == 6:
            chk(
                f"validate: exit 6, and a FAIL {m.verdict[1]} line",
                o.validate_exit == 6
                and re.search(rf"^\s+FAIL {m.verdict[1]}\b", o.validate, re.M) is not None,
                (o.validate_exit, fail_labels(o.validate)),
                "validate exit",
            )
        else:
            base = fail_labels(control.validate) if control else []
            chk(
                "validate: exit 0 and no FAIL line (the control's own, where it has any), and the mutation is in a note",
                o.validate_exit == (control.validate_exit if control else 0)
                and fail_labels(o.validate) == base
                and any(
                    ln.lstrip().startswith("note:") and re.search(names, ln) for ln in o.validate.splitlines()
                ),
                (o.validate_exit, fail_labels(o.validate)),
                "validate exit",
            )
    else:
        base = fail_labels(control.validate) if control else []
        chk(
            f"validate: legal data, the same failing checks as the control ({', '.join(base) or 'none'})",
            fail_labels(o.validate) == base and o.validate_exit == (control.validate_exit if control else 0),
            (fail_labels(o.validate), o.validate_exit),
            "validate changed",
        )
    return {"cell": "ok" if not flags else ",".join(dict.fromkeys(flags))}


def main() -> int:
    """Build the four projects once, read every mutation of each in parallel, check each; print the table."""
    t0 = time.time()
    print(f"store: {STORE}")
    wanted = sys.argv[1:]
    unknown = [w for w in wanted if w not in BY_NAME]
    if unknown:
        print(f"no such mutation: {unknown}; the table has {[m.name for m in MUTATIONS]}")
        return 2
    table = [m for m in MUTATIONS if not wanted or m.name in wanted or m.name == "control"]
    check(
        "unit: a p-value of None (a pair whose differences do not vary) prints as n/a, the others as ever",
        (stats.fmt_p(None), stats.fmt_p(0.5), stats.fmt_p(0.00001)) == ("n/a", "0.5000", "<0.0001"),
        (stats.fmt_p(None), stats.fmt_p(0.5), stats.fmt_p(0.00001)),
    )
    try:
        with ThreadPoolExecutor(max_workers=len(PROJECTS)) as pool:
            bases = dict(zip(PROJECTS, pool.map(RA.Project, PROJECTS)))
        print(
            "built: "
            + ", ".join(f"{n} {RA.SPENT[n]['build']:.0f}s" for n in PROJECTS)
            + f" ({time.time() - t0:.0f}s)"
        )
        jobs = [(m, bases[p]) for m in table for p in PROJECTS]
        with ThreadPoolExecutor(max_workers=JOBS) as pool:
            done = list(pool.map(lambda j: process(*j), jobs))
        print(f"read {len(done)} mutated copies, {JOBS} at a time ({time.time() - t0:.0f}s)")
        outcomes = {(o.copy.mutation.name, o.copy.project): o for o in done}
        cells: dict[tuple[str, str], str] = {}
        for m in table:
            for p in PROJECTS:
                o = outcomes[(m.name, p)]
                n_ref = sum(1 for _l, rc, _k, _t in o.reads if rc != 0)
                print(
                    f"\n{o.copy.name}: {len(o.reads)} reads ({n_ref} refused), {RA.thin(o.facts)} shared facts, validate exit {o.validate_exit}, {o.seconds:.0f}s"
                )
                for lab, rc, kind, _t in o.reads:
                    if rc != 0:
                        print(f"    refused ({kind or 'no kind'}, exit {rc}): {lab}")
                for r, e in o.reader_errors.items():
                    print(f"    reader {r} failed: {e[:200]}")
                cells[(m.name, p)] = judge(o, outcomes.get(("control", p)))["cell"]
        print("\nmutation x project (ok, or what failed):")
        w = max(len(m.name) for m in table)
        print(f"  {'':<{w}}  " + "  ".join(f"{p:<10}" for p in PROJECTS))
        for m in table:
            print(f"  {m.name:<{w}}  " + "  ".join(f"{cells[(m.name, p)][:10]:<10}" for p in PROJECTS))
        times = {p: sum(outcomes[(m.name, p)].seconds for m in table) for p in PROJECTS}
        print("copy-seconds per project: " + ", ".join(f"{p} {t:.0f}s" for p, t in times.items()))
    finally:
        for d in [*RA.PROJECTS, *COPIES]:
            shutil.rmtree(d, ignore_errors=True)
    print(f"\nwhole test {time.time() - t0:.0f}s on the {STORE} store")
    return summary()


if __name__ == "__main__":
    sys.exit(main())
