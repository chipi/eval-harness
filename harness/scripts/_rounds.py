"""Eval rounds (ADR-0004), optional: the records, and which runs belong to which round.

A round is data/rounds/<goal_id>/<round_id>.yaml (schemas/round.schema.json). It stores its arms (RFC-032 step 5,
model/rounds): each a system read under one label, the runs it is read through, how it entered and its retirement.
A run made with `--round` names the round it came from and joins its system's arm. A project that never opens a
round has none of this.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import json
import re
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._common import die
from evaluation_harness._runs import runs_on

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def path_of(goal: str, round_id: str) -> Path:
    """Where a round's record lives."""
    return _common.ROUNDS / goal / f"{round_id}.yaml"


def load_rounds(goal: str | None = None) -> list[dict[str, Any]]:
    """Every round (of one goal, when named), in goal then round order."""
    base = _common.ROUNDS
    if not _store.is_dir(base) or yaml is None:
        return []
    # A goal is a plain name: `..`, a path separator or a glob character would reach (or probe for)
    # files outside data/rounds, and an agent can pass any string as --goal.
    if goal is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", goal):
        return []
    out = []
    for f in sorted(_store.glob(base, f"{goal or '*'}/r*.yaml"), key=lambda p: (p.parent.name, _num(p.stem))):
        doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {}
        if isinstance(doc, dict):
            out.append(doc)
    return out


def _num(round_id: str) -> int:
    m = re.fullmatch(r"r(\d+)", round_id or "")
    return int(m.group(1)) if m else 0


def find(goal: str, round_id: str) -> dict[str, Any] | None:
    """One round, or None."""
    return next((r for r in load_rounds(goal) if r.get("round_id") == round_id), None)


def resolve(round_id: str, goal: str | None = None) -> dict[str, Any]:
    """The round a `--round` flag names: by goal when given, else the only goal that has it."""
    hits = [r for r in load_rounds(goal) if r.get("round_id") == round_id]
    if len(hits) != 1:
        goals = sorted({str(r.get("goal")) for r in hits})
        die(
            f"--round {round_id}: "
            + (
                f"rounds of several goals ({', '.join(goals)}); add --goal"
                if hits
                else "no such round" + (f" of {goal}" if goal else "")
            ),
            "not-found",
        )
    return hits[0]


def next_id(goal: str) -> str:
    """The next round id for a goal: r1, then r2, ..."""
    return f"r{max([_num(r.get('round_id', '')) for r in load_rounds(goal)] or [0]) + 1}"


def save(doc: dict[str, Any]) -> Path:
    """Write a round's record (keys in a stable order, so a diff shows what a command changed)."""
    if yaml is None:  # pragma: no cover
        die("pyyaml is required", "missing-dependency")
    p = path_of(doc["goal"], doc["round_id"])
    _store.mkdir(p.parent, parents=True, exist_ok=True)
    order = [
        "round_id",
        "goal",
        "dataset_id",
        "from",
        "hypothesis",
        "changes",
        "baseline",
        "arms",
        "budget_usd",
        "harness",
        "scorer",
        "scoring",
    ]
    # `actor` (RFC-027) and `study` (RFC-029) were left out of this list, so a round opened by round-open lost its actor
    # on save (found building RFC-029, 2026-11-11).
    order += ["study", "status", "opened_at", "closed_at", "actor", "conclusion"]
    # Through JSON: an actor shared by several arms is written out each time, not as a YAML anchor.
    body = json.loads(json.dumps({k: doc[k] for k in order if k in doc and doc[k] not in (None, [], "")}))
    if doc.get("baseline") is None and "baseline" in doc:
        body["baseline"] = None
    _store.write_text(
        p, yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )
    return p


def runs_of(rnd: dict[str, Any], label: str = "") -> list[tuple[Path, dict]]:
    """The scores of runs that name this round (and its goal), read under `label` ("": the plain runs)."""
    return [
        (d, m)
        for d, m in runs_on(rnd.get("dataset_id"), label=label)
        if m.get("round") == rnd["round_id"] and m.get("goal") == rnd["goal"]
    ]


def harness_now() -> dict[str, Any]:
    """The harness code a round is opened on: its version, the project's commit, and the hash of the code that
    can change a measurement (the same `instrument.harness` a run records)."""
    from evaluation_harness import _fingerprint  # noqa: PLC0415

    h = _fingerprint._harness_identity(_common.ROOT, _common.DATA)
    return {k: h.get(k) for k in ("version", "commit", "code_sha256", "installed")}


def off_harness(rnd: dict[str, Any], label: str = "") -> list[tuple[str, dict]]:
    """The round's runs that ran on other harness code than it opened on (the fleet's feedback 17: code taken
    mid-round splits the round's instrument), as (run id, the harness it recorded). Empty for a round
    opened before rounds recorded it."""
    want = (rnd.get("harness") or {}).get("code_sha256")
    if not want:
        return []
    out = []
    for _d, m in runs_of(rnd, label):
        h = ((m.get("fingerprint") or {}).get("instrument") or {}).get("harness") or {}
        if h.get("code_sha256") and h["code_sha256"] != want:
            out.append((m["run_id"], h))
    return out


def how_to_run_on(rnd: dict[str, Any]) -> str:
    """How to run an arm on the harness code a round opened on."""
    h = rnd.get("harness") or {}
    if h.get("installed"):
        return f"pin the harness to {h.get('version')} (pip install evaluation-harness=={h.get('version')}) and run it again"
    return (
        f"run it from a worktree at the round's commit (git worktree add ../{rnd['round_id']}-harness "
        f"{h.get('commit')}), or open a new round on the new code"
    )


def arms_of(rnd: dict[str, Any]) -> list[str]:
    """The systems of the round's arms in play, as the round stores them (RFC-032 step 5); `model.rounds` has the
    arms themselves (their labels, their runs, how they entered and their retirements)."""
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

    return sorted({a["system"] for a in model_rounds.in_play(rnd)})


def join(
    goal: str, round_id: str, system: str, run_id: str, label: str = "", who: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """A run made in the round joins its system's arm read under the label of the run's own score, or adds that arm
    (model.rounds.add_run); None when the round reads the system under a re-score the run is not yet. The round is
    read afresh and saved under the goal's lock: two runs of one round finish at once, and each saved the round it
    had read."""
    from evaluation_harness import _spend  # noqa: PLC0415
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

    with _spend._goal_lock(goal):
        rnd = find(goal, round_id)
        if rnd is None:
            return None
        arm = model_rounds.add_run(rnd, system, run_id, who, label)
        if arm is not None:
            save(rnd)
        return arm


def read_under_rescore(
    rnd: dict[str, Any], done: list[tuple[Path, dict]], apart: frozenset[str] = frozenset()
) -> None:
    """After a re-score of the round's runs (`done`: the scores written): each arm in play whose runs were all
    re-scored as one label is read under it, through the runs it has under it. A system re-scored against another
    reference than it was measured on stays as it was (`apart`): the goals show that one as a table of its own."""
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415
    from evaluation_harness.model import runs as model_runs  # noqa: PLC0415

    labels: dict[str, set[str]] = {}
    for d, m in done:
        labels.setdefault(m["config_id"], set()).add(model_runs.label(d))
    for arm in model_rounds.in_play(rnd):
        got = labels.get(arm["system"])
        if not got or len(got) != 1 or arm["system"] in apart:
            continue
        lbl = next(iter(got))
        arm["label"] = lbl
        arm["runs"] = sorted(
            m["run_id"] for _d, m in runs_on(rnd.get("dataset_id"), label=lbl, config_id=arm["system"])
        )


def summary(rnd: dict[str, Any]) -> dict[str, Any]:
    """One round as a line of `evh rounds` and `round-list`: its arms in play and retired, counted from the stored arms."""
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

    arms = model_rounds.arms(rnd)
    return {
        "round_id": rnd["round_id"],
        "status": rnd["status"],
        "dataset_id": rnd.get("dataset_id", ""),
        "arms": len(arms_of(rnd)),
        "retired": sum(1 for a in arms if a.get("retired")),
        "conclusion": (rnd.get("conclusion") or {}).get("text", ""),
    }


def view(rnd: dict[str, Any]) -> dict[str, Any]:
    """The round with its arms, as `evh rounds --json`, `round-show` and the API give it: each arm with the id the
    catalog names it by."""
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415

    keys = (
        "round_id",
        "status",
        "dataset_id",
        "from",
        "hypothesis",
        "scorer",
        "baseline",
        "harness",
        "budget_usd",
        "opened_at",
        "closed_at",
        "study",
    )
    return {k: rnd.get(k) for k in keys} | {
        "changes": rnd.get("changes") or [],
        "arms": [{"arm": model_rounds.arm_id(rnd, a), **a} for a in model_rounds.arms(rnd)],
        "scoring": rnd.get("scoring") or [],
        "conclusion": (rnd.get("conclusion") or {}).get("text"),
    }


def evidence_values(rnd: dict[str, Any], ev: dict[str, Any]) -> dict[str, Any]:
    """`model.rounds.evidence`'s answer as JSON: the round's arms read, its leader, the tests, the spend and what to
    decide next (a closed round takes no more decisions: none are given)."""
    return {
        "metric": ev["metric"],
        "arms": ev["arms"],
        "leader": ev.get("leader"),
        "reference": ev.get("reference"),
        "rows": ev["rows"],
        "against": ev["against"],
        "spent_usd": ev.get("spent"),
        "left_usd": ev.get("left"),
        "cost_per_item": ev.get("cost_per_item") or {},
        "notes": ev["notes"],
        "suggest": [{"what": what, "command": cmd or None} for what, cmd in ev["suggest"]]
        if rnd["status"] == "open"
        else [],
    }


def config_round(cfg: dict[str, Any], config_path: Any) -> dict[str, Any] | None:
    """The round a run names (`--round`), checked before it spends anything: it needs a goal, the round
    must exist and be open, and its dataset must be the run's. None when it names no round."""
    rid = cfg.get("round")
    if not rid:
        return None
    if not cfg.get("goal"):
        die(f"--round {rid}: name its goal too (--goal; a round belongs to a goal)", "bad-argument")
    rnd = find(cfg["goal"], rid)
    if rnd is None:
        die(
            f"--round {rid}: no round {rid!r} for goal {cfg['goal']!r} at {path_of(cfg['goal'], rid)}.\n"
            f"  Open it first:  evh round-open --goal {cfg['goal']} --dataset {cfg.get('dataset_id', '<dataset>')}",
            "not-found",
        )
    if rnd.get("status") == "closed":
        die(
            f"--round {rid}: round {rid} of {cfg['goal']} is closed; open the next one (evh round-open --from {rid})",
            "not-allowed",
        )
    if rnd.get("dataset_id") != cfg.get("dataset_id"):
        die(
            f"--round {rid}: round {rid} runs on {rnd.get('dataset_id')!r}, this run on {cfg.get('dataset_id')!r}",
            "mismatch",
        )
    return rnd


def _arm_problems(rel: str, rnd: dict[str, Any]) -> list[str]:
    """An arm names runs that are not runs of its system on the round's dataset, or not scored under its label."""
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415
    from evaluation_harness.model import runs as model_runs  # noqa: PLC0415

    out: list[str] = []
    ds = rnd.get("dataset_id")
    for a in model_rounds.arms(rnd):
        lbl = str(a.get("label") or "")
        arm = f"{model_runs.arm_prefix(lbl)}/{ds}/{a['system']}"
        for rid in a.get("runs") or []:
            run = model_runs.run(str(rid))
            if run is None or run.get("config_id") != a["system"] or run.get("dataset_id") != ds:
                out.append(f"rounds/{rel}: arm {arm}: {rid} is not a run of {a['system']} on {ds}")
            elif not any(model_runs.label(sd) == lbl for sd in model_runs.scores_of(str(rid))):
                out.append(f"rounds/{rel}: arm {arm}: {rid} is not scored under {lbl or 'the plain runs'!r}")
    return out


def problems() -> list[str]:
    """What validate reports about rounds: unreadable or misnamed records, a goal or dataset that
    does not resolve, a `from` that does not exist, a closed round without a conclusion, and a run
    naming a round that does not exist."""
    out: list[str] = []
    base = _common.ROUNDS
    if not _store.is_dir(base):
        return out
    from evaluation_harness._common import load_goals  # noqa: PLC0415

    goals = set(load_goals())
    datasets = {p.stem for p in _store.glob(_common.DATASETS, "*.json")}
    known = set()
    for f in sorted(_store.glob(base, "*/*.yaml")):
        rel = f.relative_to(base).as_posix()
        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {} if yaml else {}
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            out.append(f"rounds/{rel}: does not parse ({type(exc).__name__})")
            continue
        try:
            import json  # noqa: PLC0415

            import jsonschema  # noqa: PLC0415

            schema = json.loads(_store.read_text(_common.SCHEMAS / "round.schema.json", encoding="utf-8"))
            for err in jsonschema.Draft202012Validator(schema).iter_errors(doc):
                out.append(f"rounds/{rel}: {err.message[:90]}")
        except ImportError:  # pragma: no cover - V1 says jsonschema is missing
            pass
        if doc.get("round_id") != f.stem or doc.get("goal") != f.parent.name:
            out.append(f"rounds/{rel}: round_id and goal must be its file name and folder")
        if doc.get("goal") not in goals:
            out.append(f"rounds/{rel}: goal {doc.get('goal')!r} does not exist")
        if doc.get("dataset_id") not in datasets:
            out.append(f"rounds/{rel}: dataset {doc.get('dataset_id')!r} does not exist")
        if doc.get("status") == "closed" and not (doc.get("conclusion") or {}).get("text"):
            out.append(f"rounds/{rel}: closed without a conclusion")
        out += _arm_problems(rel, doc)
        known.add((doc.get("goal"), doc.get("round_id")))
    for f in sorted(_store.glob(base, "*/*.yaml")):
        doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {} if yaml else {}
        if doc.get("from") and (doc.get("goal"), doc["from"]) not in known:
            out.append(f"rounds/{f.relative_to(base).as_posix()}: from {doc['from']!r}, which does not exist")
    for _d, m in runs_on():
        if m.get("round") and (m.get("goal"), m["round"]) not in known:
            out.append(
                f"run {m['run_id']} names round {m['round']!r} of {m.get('goal')!r}, which does not exist"
            )
    return out
