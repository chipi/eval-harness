"""Experiment rounds (ADR-0004), optional: the records, and which runs belong to which round.

A round is data/rounds/<goal_id>/<round_id>.yaml (schemas/round.schema.json). Its arms are not
listed in it: they are the configs whose runs name the round (`round:` in the config, recorded on
the run), less the ones retired. A project that never opens a round has none of this.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import _common
from _common import die
from _runs import runs_on

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
    if not base.is_dir() or yaml is None:
        return []
    out = []
    for f in sorted(base.glob(f"{goal or '*'}/r*.yaml"), key=lambda p: (p.parent.name, _num(p.stem))):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
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
            )
        )
    return hits[0]


def next_id(goal: str) -> str:
    """The next round id for a goal: r1, then r2, ..."""
    return f"r{max([_num(r.get('round_id', '')) for r in load_rounds(goal)] or [0]) + 1}"


def save(doc: dict[str, Any]) -> Path:
    """Write a round's record (keys in a stable order, so a diff shows what a command changed)."""
    if yaml is None:  # pragma: no cover
        die("pyyaml is required")
    p = path_of(doc["goal"], doc["round_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    order = [
        "round_id",
        "goal",
        "dataset_id",
        "from",
        "hypothesis",
        "changes",
        "baseline",
        "budget_usd",
        "carried",
    ]
    order += ["status", "opened_at", "closed_at", "retired", "conclusion"]
    body = {k: doc[k] for k in order if k in doc and doc[k] not in (None, [], "")}
    if doc.get("baseline") is None and "baseline" in doc:
        body["baseline"] = None
    p.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    return p


def runs_of(rnd: dict[str, Any], runs_dir: Path | None = None) -> list[tuple[Path, dict]]:
    """The runs that name this round (and its goal), in data/runs or `runs_dir`."""
    return [
        (d, m)
        for d, m in runs_on(rnd.get("dataset_id"), runs_dir=runs_dir)
        if m.get("round") == rnd["round_id"] and m.get("goal") == rnd["goal"]
    ]


def arms_of(rnd: dict[str, Any], runs_dir: Path | None = None) -> list[str]:
    """The round's arms still in play: configs whose runs name it, and those carried into it
    unchanged from an earlier round, less the retired."""
    retired = {r["config_id"] for r in rnd.get("retired") or []}
    ran = {m["config_id"] for _, m in runs_of(rnd, runs_dir)}
    return sorted((ran | set(rnd.get("carried") or [])) - retired)


def config_round(cfg: dict[str, Any], config_path: Any) -> dict[str, Any] | None:
    """The round a config names, checked before a run spends anything: it needs a goal, the round
    must exist and be open, and its dataset must be the config's. None when it names no round."""
    rid = cfg.get("round")
    if not rid:
        return None
    if not cfg.get("goal"):
        die(f"{config_path}: round {rid!r} needs `goal:` too (a round belongs to a goal)")
    rnd = find(cfg["goal"], rid)
    if rnd is None:
        die(
            f"{config_path}: no round {rid!r} for goal {cfg['goal']!r} at {path_of(cfg['goal'], rid)}.\n"
            f"  Open it first:  evh round-open --goal {cfg['goal']} --dataset {cfg.get('dataset_id', '<dataset>')}"
        )
    if rnd.get("status") == "closed":
        die(
            f"{config_path}: round {rid} of {cfg['goal']} is closed; open the next one (evh round-open --from {rid})"
        )
    if rnd.get("dataset_id") != cfg.get("dataset_id"):
        die(
            f"{config_path}: round {rid} runs on {rnd.get('dataset_id')!r}, the config on {cfg.get('dataset_id')!r}"
        )
    return rnd


def problems() -> list[str]:
    """What validate reports about rounds: unreadable or misnamed records, a goal or dataset that
    does not resolve, a `from` that does not exist, a closed round without a conclusion, and a run
    naming a round that does not exist."""
    out: list[str] = []
    base = _common.ROUNDS
    if not base.is_dir():
        return out
    from _common import load_goals  # noqa: PLC0415

    goals = set(load_goals())
    datasets = {p.stem for p in _common.DATASETS.glob("*.json")}
    known = set()
    for f in sorted(base.glob("*/*.yaml")):
        rel = f.relative_to(base).as_posix()
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {} if yaml else {}
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            out.append(f"rounds/{rel}: does not parse ({type(exc).__name__})")
            continue
        try:
            import json  # noqa: PLC0415

            import jsonschema  # noqa: PLC0415

            schema = json.loads((_common.SCHEMAS / "round.schema.json").read_text(encoding="utf-8"))
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
        known.add((doc.get("goal"), doc.get("round_id")))
    for f in sorted(base.glob("*/*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {} if yaml else {}
        if doc.get("from") and (doc.get("goal"), doc["from"]) not in known:
            out.append(f"rounds/{f.relative_to(base).as_posix()}: from {doc['from']!r}, which does not exist")
    for d, m in runs_on():
        if m.get("round") and (m.get("goal"), m["round"]) not in known:
            out.append(f"run {d.name} names round {m['round']!r} of {m.get('goal')!r}, which does not exist")
    return out
