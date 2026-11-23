#!/usr/bin/env python3
"""The facts a project's readers state, collected from `evh <command> --json` and nothing else (RFC-041, PLAN 0.8.1 R3).

    python tools/facts_dump.py [--project DIR] [--evh "evh"] [--jobs 8] [--out facts.json]
    python tools/facts_dump.py --diff old.json new.json

Standard library only, so it runs beside any installed `evh` that has the JSON outputs (v0.8.0 and later): a beta
project runs it under the version it has and under the release candidate, and sends both documents. Nothing is read from
the project's files and no `evaluation_harness` module is imported; every fact names the command it came from.

For every (dataset, arm, metric): the value (the mean), the items behind it and the direction word. For every arm: its
run ids and their number, the latest run, the reference it is read against, its cost state (unknown, zero or an
amount). For every dataset: the baseline each goal promoted, and whether its text is shown on a public server. A fact
that this `evh` cannot give is `{"unavailable": "<why>"}`, never a guess. One JSON document, sorted keys.

`--diff` prints, per fact, old -> new, grouped by what changed; it exits 0 (a difference is the answer, not an error).

The same collection is the CLI reader of tests/test_reader_agreement.py, which asks every other reader (the API, the MCP
reads, the catalog export, the inspector) for the same facts and fails when two disagree.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import subprocess  # nosec B404 - the point of this tool: `evh <command> --json`
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

SCHEMA = "evh-facts-dump/1"
#: (kind, key, value) and, for a fact a command states in a second place, that place's name (`goal-leaderboard:group`)
Fact = tuple[Any, ...]
SUFFIXES = ("group", "arm flag", "answer")

#: kind of fact -> what it is, in the words of the dump
KINDS = {
    "arms": "the arms on a dataset (key: dataset)",
    "ranked": "the arms a leaderboard ranks on a dataset: those that record its ranking metric, so some of its arms (key: dataset)",
    "value": "the mean of a metric over the arm's items (key: arm, metric)",
    "n_items": "the items behind that mean (key: arm, metric)",
    "direction": "which way is better for a metric on a dataset: lower, higher or neutral (key: dataset, metric)",
    "runs": "the run ids of an arm (key: arm)",
    "n_runs": "how many runs the arm has (key: arm)",
    "latest": "the latest run of an arm (key: arm)",
    "latest_day": "the day of the latest run (key: arm)",
    "reference": "the reference the arm is read against, `none` when it has none (key: arm)",
    "cost_state": "unknown (not recorded), zero (recorded as 0) or amount (key: arm)",
    "baseline_run": "the run a goal promoted as its baseline on a dataset (key: dataset, goal)",
    "baseline_arm": "the arm that run is read in (key: dataset, goal)",
    "public": "whether the dataset's text is shown on a public server (key: dataset)",
}
#: the reader whose answer the dump keeps for a kind, first to last (the others are only compared)
PREFERRED = (
    "arm-show",
    "arm-list",
    "metric-show",
    "metric-list",
    "goal-leaderboard",
    "leaderboard",
    "runs-list",
    "baselines",
    "dataset-items",
)
#: the commands, with the words their arguments take (CLI: positional or flag)
ARGV: dict[str, Callable[..., list[str]]] = {
    "runs-list": lambda label="": ["runs-list", "--label", label],
    "arm-list": lambda: ["arm-list"],
    "arm-show": lambda label, dataset, system: ["arm-show", label, dataset, system],
    "metric-list": lambda: ["metric-list"],
    "metric-show": lambda metric: ["metric-show", metric],
    "leaderboard": lambda dataset: ["leaderboard", dataset],
    "baselines": lambda: ["baselines"],
    "goal-list": lambda: ["goal-list"],
    "goal-leaderboard": lambda goal: ["goal-leaderboard", goal],
    "dataset-items": lambda dataset: ["dataset-items", dataset],
    "migrate": lambda: ["migrate", "--check"],
}


class Unavailable(Exception):
    """A reader could not answer: the reason is what the dump records."""


# ── the runner: `evh <command> --json` ───────────────────────────────────────────────────────────────────────────────
class Cli:
    """Runs `evh` as a subprocess in a project, for the commands the dump reads."""

    def __init__(
        self, evh: str = "evh", project: str | None = None, env: dict[str, str] | None = None
    ) -> None:
        self.evh = shlex.split(evh)
        self.project = project
        self.env = env

    def read(self, op: str, public: bool = False, **params: Any) -> dict[str, Any]:
        """The `result` of `evh <op> --json`, or Unavailable with what the command said."""
        argv = [*self.evh, *ARGV[op](**params), "--json"]
        env = dict(self.env if self.env is not None else os.environ)
        env.pop("EVH_PUBLIC", None)
        if public:
            env["EVH_PUBLIC"] = "1"
        try:
            p = subprocess.run(  # nosec B603 - the operator's own evh
                argv, cwd=self.project, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                timeout=900, check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Unavailable(f"evh {op}: {type(exc).__name__}: {exc}") from None
        if p.returncode != 0:
            first = next((ln for ln in (p.stderr + p.stdout).splitlines() if ln.strip()), "")
            raise Unavailable(f"evh {op}: exit {p.returncode}: {re.sub(r' [(]/[^)]*[)]', '', first)[:160]}")
        return parse(p.stdout, op)


def parse(stdout: str, op: str) -> dict[str, Any]:
    """The envelope's `result`: the whole output, else its last JSON line (a command that prints its table first)."""
    for text in (stdout, *reversed([ln for ln in stdout.splitlines() if ln.startswith("{")])):
        try:
            return dict(json.loads(text)["result"])
        except (ValueError, KeyError, TypeError):
            continue
    raise Unavailable(f"evh {op}: no JSON envelope in its output")


# ── normal forms ─────────────────────────────────────────────────────────────────────────────────────────────────────
def cost_state(v: Any) -> str:
    """`unknown` for no cost, `zero` for 0, else `amount`: a missing price is not a free one."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "unknown"
    return "zero" if v == 0 else "amount"


def word(text: Any) -> str | None:
    """A direction word as a reader prints it: its first word, lower case (`neutral: a description` is `neutral`)."""
    m = re.match(r"\s*([A-Za-z-]+)", str(text or ""))
    return m.group(1).lower() if m else None


def ref(v: Any) -> str:
    """A reference id; `none` for an arm scored against none (a reader says `no reference`, `none` or nothing)."""
    return "none" if not v or str(v) in ("none", "no reference", "—") else str(v)


def scored_by(v: Any) -> str | None:
    """What an arm is scored against, as a reference id: None where the reader says it is scored by a judge (`judge <scorer>`:
    an arm judged is grouped by its judge, and its reference is the one `arm-list` names, which these readers do not)."""
    return None if str(v or "").startswith("judge ") else ref(v)


def arm_id(label: str, dataset: str, system: str) -> str:
    """The arm's id: `<label as a slug>/dataset/system`, `runs` for a plain arm's empty label: a label that holds a `/` or a
    space (`judged/<scorer>`, `rescored 3d3a6afd`) is `judged-<scorer>`, `rescored-3d3a6afd` in the id `evh arm-list` gives
    (the slug of `model.runs.arm_prefix`, which `runs-list` does not apply to the label it prints)."""
    return f"{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-') or 'runs'}/{dataset}/{system}"


def parse_arm_label(text: str) -> tuple[str, str, int]:
    """`system`, `system · label` and either with ` ×N` (a reader that names an arm by its label, not its id):
    (label, system, runs). The label of a plain arm is ''."""
    m = re.match(r"^(?P<sys>.+?)(?: · (?P<label>.+?))?(?: ×(?P<n>\d+))?$", text.strip())
    assert m is not None  # the pattern matches any text  # nosec B101
    return m.group("label") or "", m.group("sys"), int(m.group("n") or 1)


def split_arm(arm: str, datasets: set[str]) -> tuple[str, str, str]:
    """`label/dataset/system` as (label, dataset, system); a label may hold a `/` (judged/<scorer>), a dataset never does."""
    parts = arm.split("/")
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] in datasets:
            return "/".join(parts[:i]), parts[i], "/".join(parts[i + 1 :])
    return "/".join(parts[:-2]), parts[-2], parts[-1]


def newest(runs: list[tuple[str, str]]) -> str | None:
    """The run id with the greatest (created_at, run_id): RFC-041 F2's latest run."""
    return max(runs)[1] if runs else None


# ── one extractor per command: result -> facts ───────────────────────────────────────────────────────────────────────
def from_runs_list(r: dict[str, Any], label: str) -> list[Fact]:
    """Facts from `evh runs list`: each arm's runs, latest run, mean values and cost state."""
    arms: dict[str, list[dict[str, Any]]] = {}
    for run in r.get("runs") or []:
        arms.setdefault(arm_id(label, run["dataset_id"], run["system_id"]), []).append(run)
    out: list[Fact] = []
    for arm, runs in arms.items():
        ds = runs[0]["dataset_id"]
        out.append(("arms", (ds,), [arm]))
        ids = sorted(x["run_id"] for x in runs)
        out += [("runs", (arm,), ids), ("n_runs", (arm,), len(ids))]
        out.append(("latest", (arm,), newest([(x.get("created_at") or "", x["run_id"]) for x in runs])))
        out.append(("latest_day", (arm,), max((x.get("created_at") or "")[:10] for x in runs) or None))
        keys = {k for x in runs for k in x.get("scores") or {}}
        for k in sorted(keys):
            vals = [x["scores"][k] for x in runs if isinstance(x.get("scores", {}).get(k), (int, float))]
            if vals:
                out.append(("value", (arm, k), sum(vals) / len(vals)))
        costs = [x["scores"]["cost_usd"] for x in runs if (x.get("scores") or {}).get("cost_usd") is not None]
        out.append(("cost_state", (arm,), cost_state(sum(costs) / len(costs) if costs else None)))
    return out


def from_arm_list(r: dict[str, Any]) -> list[Fact]:
    """Facts from `evh arm list`: each arm's reference, cost state, run count, latest day and its measure's value and direction."""
    out: list[Fact] = []
    by_ds: dict[str, list[str]] = {}
    for a in r.get("arms") or []:
        arm, ds = a["arm"], a["dataset"]
        by_ds.setdefault(ds, []).append(arm)
        out += [
            ("reference", (arm,), ref(a.get("reference"))),
            ("cost_state", (arm,), cost_state(a.get("cost"))),
        ]
        if a.get("repeats") is not None:
            out.append(("n_runs", (arm,), a["repeats"]))
        if a.get("last"):
            out.append(("latest_day", (arm,), str(a["last"])[:10]))
        if a.get("measure") and isinstance(a.get("value"), (int, float)):
            out.append(("value", (arm, a["measure"]), a["value"]))
            out.append(("direction", (ds, a["measure"]), "lower" if a.get("lower") else "not-lower"))
    return out + [("arms", (ds,), sorted(arms)) for ds, arms in by_ds.items()]


def from_arm_show(r: dict[str, Any]) -> list[Fact]:
    """Facts from `evh arm show`: reference, runs, latest run, and each metric's mean, item count and direction."""
    arm, ds = r["arm"], r["dataset"]
    out: list[Fact] = [
        ("reference", (arm,), scored_by(r.get("scored_against"))),
        ("n_runs", (arm,), r.get("runs")),
    ]
    listed = r.get("run_list") or []
    out.append(("runs", (arm,), sorted(x["run"] for x in listed)))
    out.append(("latest", (arm,), newest([(x.get("made") or "", x["run"]) for x in listed])))
    if r.get("last"):
        out.append(("latest_day", (arm,), str(r["last"])[:10]))
    metrics = {m["metric"]: m for m in r.get("metrics") or []}
    for name, m in metrics.items():
        out += [("value", (arm, name), m.get("mean")), ("n_items", (arm, name), m.get("n"))]
        out.append(("direction", (ds, name), word(m.get("better"))))
    out.append(("cost_state", (arm,), cost_state((metrics.get("cost_usd") or {}).get("mean"))))
    return out


def from_metric_list(r: dict[str, Any]) -> list[Fact]:
    """`better_on` (a word per dataset) where this evh has it; else `better`, one word for every dataset that records it."""
    out: list[Fact] = []
    for m in r.get("metrics") or []:
        on = m.get("better_on") or {ds: m.get("better") for ds in (m.get("datasets") or {})}
        out += [("direction", (ds, m["metric"]), word(w)) for ds, w in on.items()]
    return out


def from_metric_show(r: dict[str, Any]) -> list[Fact]:
    """Facts from `evh metric show`: the metric's direction per dataset and each arm's mean, items, reference and runs."""
    out: list[Fact] = []
    m = r["metric"]
    on = r.get("better_on") or {}
    for d in r.get("datasets") or []:
        ds = d["dataset"]
        out.append(("direction", (ds, m), word(on.get(ds, r.get("better")))))
        for a in d.get("arms") or []:
            label, system, n = parse_arm_label(a["arm"])
            arm = arm_id(label, ds, system)
            out += [
                ("value", (arm, m), a.get("mean")),
                ("n_items", (arm, m), a.get("n")),
                ("reference", (arm,), scored_by(a.get("scored_against"))),
                ("n_runs", (arm,), n),
            ]
    return out


def from_leaderboard(r: dict[str, Any], dataset: str) -> list[Fact]:
    """Facts from `evh leaderboard`: the ranked-by direction and each arm's runs, values and cost state."""
    out: list[Fact] = []
    lines = [ln for b in r.get("blocks") or [] for ln in b.get("lines") or []]
    for ln in lines:
        m = re.search(r"ranked by: (\S+) \((higher|lower) is better\)", ln)
        if m:
            out.append(("direction", (dataset, m.group(1)), m.group(2)))
    tables = [
        b for b in r.get("blocks") or [] if "system_id" in (b.get("columns") or [])
    ]  # one per reference scored against
    arms = []
    for row in (row for t in tables for row in t.get("rows") or []):
        label, system, _n = parse_arm_label(row["system_id"])
        arm = arm_id(label, dataset, system)
        arms.append(arm)
        out.append(("n_runs", (arm,), row.get("n_runs")))
        for k, v in row.items():
            if k not in ("system_id", "n_runs", "tier") and isinstance(v, (int, float)):
                out.append(("value", (arm, k), v))
        if "cost_usd" in row:
            out.append(("cost_state", (arm,), cost_state(row["cost_usd"])))
    return [*out, ("ranked", (dataset,), sorted(arms))] if tables else out


def from_baselines(r: dict[str, Any]) -> list[Fact]:
    """Facts from `evh baselines`: the run each goal's current baseline was promoted from."""
    return [
        ("baseline_run", (b["dataset"], b["goal"]), b.get("promoted_from"))
        for b in r.get("baselines") or []
        if b.get("goal") and b.get("current", 1) == b.get("version", 1)
    ]


def from_goal_leaderboard(r: dict[str, Any]) -> list[Fact]:
    """Facts from `evh goal leaderboard`: the baseline run and arm per dataset, and each group's direction, reference, values and cost."""
    out: list[Fact] = []
    goal = r["goal"]
    for d in r.get("datasets") or []:
        ds, b = d["dataset"], d.get("baseline")
        if b:
            out += [("baseline_run", (ds, goal), b.get("run")), ("baseline_arm", (ds, goal), b.get("arm"))]
        for g in d.get("groups") or []:
            if g.get("baseline"):
                out.append(("baseline_arm", (ds, goal), g["baseline"], "group"))
            out += [
                ("baseline_arm", (ds, goal), a["arm"], "arm flag")
                for a in g.get("arms") or []
                if a.get("baseline")
            ]
    for a in r.get("answer") or []:
        if (a.get("baseline") or {}).get("arm"):
            out.append(("baseline_arm", (a["dataset"], goal), a["baseline"]["arm"], "answer"))
        if (a.get("baseline") or {}).get("run"):
            out.append(("baseline_run", (a["dataset"], goal), a["baseline"]["run"], "answer"))
    for d in r.get("datasets") or []:
        ds = d["dataset"]
        for g in d.get("groups") or []:
            measure = g.get("measure")
            if measure and g.get("direction"):
                out.append(("direction", (ds, measure), word(g["direction"])))
            for a in g.get("arms") or []:
                arm = a["arm"]
                out.append(("reference", (arm,), scored_by(g.get("scored_against"))))
                if measure and isinstance(a.get("mean"), (int, float)):
                    out += [("value", (arm, measure), a["mean"]), ("n_items", (arm, measure), a.get("n"))]
                cost = (a.get("axes") or {}).get("cost")
                if cost is not None:
                    out.append(("cost_state", (arm,), cost_state(cost.get("mean"))))
    return out


def from_dataset_items(r: dict[str, Any], dataset: str) -> list[Fact]:
    """Facts from `evh dataset items`: whether the item text is shown (`public`)."""
    return [("public", (dataset,), not r.get("text_hidden"))]


# ── the collection ───────────────────────────────────────────────────────────────────────────────────────────────────
class Collected:
    """facts[reader][(kind, key)] = value; why[reader] = the reasons a reader (or one of its calls) gave no answer."""

    def __init__(self) -> None:
        self.facts: dict[str, dict[tuple[str, tuple[str, ...]], Any]] = {}
        self.why: dict[str, list[str]] = {}
        self.meta: dict[str, Any] = {}

    def add(self, reader: str, facts: list[Fact]) -> None:
        """Record `reader`'s facts; a fact with a fourth element is kept under `reader:<that>`, and a None value is skipped."""
        for f in facts:
            kind, key, value = f[:3]
            d = self.facts.setdefault(f"{reader}:{f[3]}" if len(f) > 3 else reader, {})
            if value is None:
                continue
            if kind in ("arms", "runs") and (kind, key) in d:  # lists from several calls (labels, arms) join
                value = sorted({*d[(kind, key)], *value})
            d[(kind, key)] = value

    def fail(self, reader: str, why: str) -> None:
        """Record why `reader` gave no answer."""
        self.why.setdefault(reader, []).append(why)


def collect(read: Callable[..., dict[str, Any]], jobs: int = 1, only: set[str] | None = None) -> Collected:
    """Every reader's facts, through `read(op, public=False, **params) -> result` (raises Unavailable). The CLI runner is
    the dump's; the test hands in the API's and the MCP server's. `only`: just these readers (the arm and run lists that
    find what to ask are always read)."""
    c = Collected()
    pool = ThreadPoolExecutor(max_workers=jobs) if jobs > 1 else None

    def want(*names: str) -> bool:
        return only is None or bool(only.intersection(names))

    def ask(reader: str, op: str, extract: Callable[[dict[str, Any]], list[Fact]], **params: Any) -> bool:
        try:
            c.add(reader, extract(read(op, **params)))
            return True
        except Unavailable as exc:
            c.fail(reader, str(exc))
        except (
            KeyError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:  # an answer in a shape this reader does not know
            c.fail(reader, f"{op}: an answer of an unexpected shape ({type(exc).__name__}: {exc})")
        return False

    def many(
        reader: str,
        op: str,
        extract: Callable[[dict[str, Any], dict[str, Any]], list[Fact]],
        calls: list[dict[str, Any]],
    ) -> None:
        def one(p: dict[str, Any]) -> tuple[dict[str, Any], list[Fact] | str]:
            try:
                return p, extract(read(op, **p), p)
            except Unavailable as exc:
                return p, str(exc)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                return p, f"{op} {p}: an answer of an unexpected shape ({type(exc).__name__}: {exc})"

        if not want(reader, *(f"{reader}:{s}" for s in SUFFIXES)):
            return
        for _p, got in pool.map(one, calls) if pool else map(one, calls):
            if isinstance(got, str):
                c.fail(reader, got)
            else:
                c.add(reader, got)

    # the runs, per label
    labels = [""]
    try:
        first = read("runs-list", label="")
        labels += [lab for lab in first.get("labels") or [] if lab]
        c.add("runs-list", from_runs_list(first, ""))
    except Unavailable as exc:
        c.fail("runs-list", str(exc))
    for lab in labels[1:]:

        def of_label(r: dict[str, Any], lab: str = lab) -> list[Fact]:
            return from_runs_list(r, lab)

        ask("runs-list", "runs-list", of_label, label=lab)
    ask("arm-list", "arm-list", from_arm_list)

    arms = sorted(
        {a for k, v in c.facts.get("arm-list", {}).items() if k[0] == "arms" for a in v}
        | {a for k, v in c.facts.get("runs-list", {}).items() if k[0] == "arms" for a in v}
    )
    datasets = sorted({k[1][0] for r in c.facts.values() for k in r if k[0] == "arms"})
    dset = set(datasets)
    many(
        "arm-show",
        "arm-show",
        lambda r, _p: from_arm_show(r),
        [dict(zip(("label", "dataset", "system"), split_arm(a, dset))) for a in arms],
    )

    ask("metric-list", "metric-list", from_metric_list)  # its names are what metric-show is asked for
    listed = {k[1][1] for k in c.facts.get("metric-list", {}) if k[0] == "direction"}
    metrics = sorted(listed or {k[1][1] for r in c.facts.values() for k in r if k[0] == "value"})
    many("metric-show", "metric-show", lambda r, _p: from_metric_show(r), [{"metric": m} for m in metrics])
    many(
        "leaderboard",
        "leaderboard",
        lambda r, p: from_leaderboard(r, p["dataset"]),
        [{"dataset": d} for d in datasets],
    )

    if want("baselines"):
        ask("baselines", "baselines", from_baselines)
    goals: list[str] = []
    try:
        goals = (
            [g["goal"] for g in read("goal-list").get("goals") or []]
            if want("goal-leaderboard", "baselines")
            else []
        )
    except Unavailable as exc:
        c.fail("goal-leaderboard", str(exc))
    many(
        "goal-leaderboard",
        "goal-leaderboard",
        lambda r, _p: from_goal_leaderboard(r),
        [{"goal": g} for g in goals],
    )
    many(
        "dataset-items",
        "dataset-items",
        lambda r, p: from_dataset_items(r, p["dataset"]),
        [{"dataset": d, "public": True} for d in datasets],
    )

    # a baseline run's arm, where the reader named the run only
    # (one run can be read in several arms, as its own and as re-scored or silver: the plain one is the baseline's)
    in_arm: dict[str, str] = {}
    for r in c.facts.values():
        for (k, key), v in r.items():
            for run in v if k == "runs" else ():
                if run not in in_arm or (key[0].startswith("runs/") and not in_arm[run].startswith("runs/")):
                    in_arm[run] = key[0]
    for reader, d in c.facts.items():
        for (k, key), run in list(d.items()):
            if k == "baseline_run" and ("baseline_arm", key) not in d and reader == "baselines":
                d[("baseline_arm", key)] = in_arm.get(run, "(in no arm)")
    return c


def cli_collect(evh: str, project: str | None, jobs: int) -> Collected:
    """Collect every reader's facts through the `evh` command, with the project's data format and the evh version in `meta`."""
    cli = Cli(evh, project)
    c = collect(cli.read, jobs)
    try:
        v = cli.read("migrate")
        c.meta["data_format"] = (v.get("values") or {}).get("format")
    except Unavailable as exc:
        c.meta["data_format"] = {"unavailable": str(exc)}
    try:
        p = subprocess.run(  # nosec B603
            [*cli.evh, "--version"], cwd=project, capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=120, check=False,
        )  # fmt: skip
        c.meta["evh_version"] = p.stdout.strip() or {"unavailable": p.stderr.strip()[:200]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        c.meta["evh_version"] = {"unavailable": str(exc)}
    return c


# ── agreement ────────────────────────────────────────────────────────────────────────────────────────────────────────
def same(kind: str, a: Any, b: Any) -> bool:
    """Whether two readers' answers to one fact are the same: numbers within the formatting of a printed value, a
    direction `not-lower` (a reader that only says whether lower) for any word but lower."""
    if kind in ("value",) and isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-4, abs_tol=1e-6)
    if kind == "direction" and "not-lower" in (a, b):
        return "lower" not in (a, b) and not (a == b == "lower")
    return bool(a == b)


def disagreements(by_reader: dict[str, dict[tuple[str, tuple[str, ...]], Any]]) -> list[dict[str, Any]]:
    """Per fact that two or more readers give: the readers that do not say what the most readers say (every answer when
    no answer has more readers than another)."""
    facts: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for reader, d in by_reader.items():
        for fk, v in d.items():
            facts.setdefault(fk, {})[reader] = v
    out = []
    for (kind, key), seen in sorted(facts.items()):
        if len(seen) < 2:
            continue
        groups: list[list[str]] = []
        for reader, v in seen.items():
            for g in groups:
                if same(kind, seen[g[0]], v):
                    g.append(reader)
                    break
            else:
                groups.append([reader])
        if len(groups) > 1:
            groups.sort(key=lambda g: -len(g))
            tie = len(groups[0]) == len(groups[1])
            odd = sorted(r for g in groups[1:] for r in g) if not tie else sorted(seen)
            out.append(
                {"fact": kind, "key": list(key), "readers": odd, "values": {r: seen[r] for r in sorted(seen)}}
            )
    return out


# ── the document ─────────────────────────────────────────────────────────────────────────────────────────────────────
def command_of(reader: str) -> str:
    """The command a reader's facts came from, as the dump names it."""
    return f"evh {reader}{' (EVH_PUBLIC=1)' if reader == 'dataset-items' else ''} --json"


def leaf(c: Collected, kind: str, key: tuple[str, ...]) -> dict[str, Any]:
    """The preferred reader's answer to a fact, else `unavailable` with what the readers that give it said."""
    order = [*PREFERRED, *sorted(set(c.facts) - set(PREFERRED))]
    for reader in order:
        d = c.facts.get(reader) or {}
        if (kind, key) in d:
            return {"value": d[(kind, key)], "from": command_of(reader)}
    givers = {
        "public": ["dataset-items"],
        "baseline_run": ["baselines", "goal-leaderboard"],
        "baseline_arm": ["goal-leaderboard", "baselines"],
    }.get(kind, ["arm-show", "arm-list"])
    why = [w for g in givers for w in c.why.get(g, [])]
    return {
        "unavailable": "; ".join(sorted(set(why))[:3])
        or f"no command of this evh gave it for {'/'.join(key)}"
    }


def document(c: Collected) -> dict[str, Any]:
    """The dump's JSON document: every fact of every dataset and arm with its source command, the disagreements and what was unavailable."""
    keys: dict[str, set[tuple[str, ...]]] = {k: set() for k in KINDS}
    for d in c.facts.values():
        for kind, key in d:
            keys[kind].add(key)
    datasets = sorted(
        {k[0] for k in keys["arms"]} | {k[0] for k in keys["public"]} | {k[0] for k in keys["baseline_run"]}
    )
    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "evh_version": c.meta.get("evh_version"),
        "data_format": c.meta.get("data_format"),
        "datasets": {},
    }
    arms_of: dict[str, set[str]] = {ds: set() for ds in datasets}
    for (ds,) in keys["arms"]:
        for reader in c.facts.values():
            arms_of[ds].update(reader.get(("arms", (ds,)), ()))
    for ds in datasets:
        entry: dict[str, Any] = {"public": leaf(c, "public", (ds,)), "baselines": {}, "arms": {}}
        for _d, goal in sorted(k for k in keys["baseline_run"] if k[0] == ds):
            entry["baselines"][goal] = {
                "run": leaf(c, "baseline_run", (ds, goal)),
                "arm": leaf(c, "baseline_arm", (ds, goal)),
            }
        for arm in sorted(arms_of[ds]):
            a: dict[str, Any] = {
                k: leaf(c, k, (arm,))
                for k in ("runs", "n_runs", "latest", "latest_day", "reference", "cost_state")
            }
            a["metrics"] = {
                m: {
                    k: leaf(c, k, key)
                    for k, key in (("value", (arm, m)), ("n_items", (arm, m)), ("direction", (ds, m)))
                }
                for _a, m in sorted(k for k in keys["value"] if k[0] == arm)
            }
            entry["arms"][arm] = a
        doc["datasets"][ds] = entry
    doc["disagreements"] = disagreements(c.facts)
    doc["unavailable"] = {r: sorted(set(w))[:5] for r, w in sorted(c.why.items())}
    return doc


# ── --diff ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def flat(node: Any, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    """Every leaf of a dump as {path: what it says}: a fact's value, or `unavailable: <why>`."""
    if (
        isinstance(node, dict)
        and ("value" in node or "unavailable" in node)
        and set(node) <= {"value", "from", "unavailable"}
    ):
        return {path: node["value"] if "value" in node else f"unavailable: {node['unavailable']}"}
    if isinstance(node, dict):
        out: dict[tuple[str, ...], Any] = {}
        for k, v in node.items():
            if k not in ("disagreements", "unavailable") or path:
                out.update(flat(v, (*path, k)))
        return out
    return {path: node}


def where_of(path: tuple[str, ...]) -> tuple[str, int]:
    """Where a fact is, in words, and how many arms stand for it: a direction is a dataset's and a metric's, so it is named
    once however many arms record the metric."""
    if path[0] != "datasets":
        return "/".join(path[:-1]), 1
    ds, rest, fact = path[1], path[2:-1], path[-1]
    if rest[:1] == ("arms",):
        if fact == "direction":
            return f"{ds}  {rest[3]}", 1
        return "  ".join([ds, rest[1], *rest[3:4]]), 1
    if rest[:1] == ("baselines",):
        return f"{ds}  goal {rest[1]}", 1
    return ds, 1


def diff(old: dict[str, Any], new: dict[str, Any]) -> str:
    """Text of what changed between two dumps, grouped by fact, with the counts of facts the same and changed."""
    a, b = flat(old), flat(new)
    lines = [
        f"evh {old.get('evh_version')} (format {old.get('data_format')})  ->  evh {new.get('evh_version')} (format {new.get('data_format')})"
    ]
    groups: dict[str, dict[tuple[str, str, str], int]] = {}
    for path in sorted(a.keys() | b.keys()):
        was, now = a.get(path, "(absent)"), b.get(path, "(absent)")
        if was == now:
            continue
        fact = path[-1] if path[0] == "datasets" else path[0]
        where, _n = where_of(path)
        key = (where, repr(was), repr(now))
        groups.setdefault(fact, {})[key] = groups.get(fact, {}).get(key, 0) + 1
    for fact in sorted(groups):
        lines += ["", f"{fact} ({len(groups[fact])} changed)"]
        for (where, was, now), n in groups[fact].items():
            lines.append(f"  {where}: {was} -> {now}" + (f"  ({n} arms)" if n > 1 else ""))
    same_n = sum(1 for p in a.keys() & b.keys() if a[p] == b[p])
    lines += ["", f"{same_n} facts the same, {sum(len(v) for v in groups.values())} changed"]
    for name, doc in (("old", old), ("new", new)):
        if doc.get("disagreements"):
            lines.append(
                f"{name}: {len(doc['disagreements'])} fact(s) the commands of that version state differently (see its `disagreements`)"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the facts of a project (or, with `--diff`, what changed between two dumps) and return 0."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None, help="the project's folder (default: the current directory)")
    ap.add_argument("--evh", default="evh", help='the command to run, as one string (default: "evh")')
    ap.add_argument("--jobs", type=int, default=4, help="evh commands at once (default 4)")
    ap.add_argument("--out", default=None, help="write the document here (default: stdout)")
    ap.add_argument(
        "--diff", nargs=2, metavar=("OLD", "NEW"), help="print what changed between two dumps; exit 0"
    )
    args = ap.parse_args(argv)
    if args.diff:
        docs = []
        for f in args.diff:
            with open(f, encoding="utf-8") as fh:
                docs.append(json.load(fh))
        print(diff(*docs))
        return 0
    text = json.dumps(
        document(cli_collect(args.evh, args.project, args.jobs)), indent=1, sort_keys=True, ensure_ascii=False
    )
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
