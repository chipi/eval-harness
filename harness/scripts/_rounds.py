"""Eval rounds (ADR-0004), optional: the records, and which runs belong to which round.

A round is data/rounds/<goal_id>/<round_id>.yaml (schemas/round.schema.json). Its arms are not
listed in it: they are the configs whose runs name the round (`round:` in the config, recorded on
the run), less the ones retired. A project that never opens a round has none of this.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

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
        "budget_usd",
        "harness",
        "carried",
        "scorer",
        "scoring",
    ]
    # `actor` (RFC-027) and `study` (RFC-029) were left out of this list, so a round opened by round-open lost its actor
    # on save (found building RFC-029, 2026-11-11).
    order += ["study", "status", "opened_at", "closed_at", "actor", "retired", "conclusion"]
    body = {k: doc[k] for k in order if k in doc and doc[k] not in (None, [], "")}
    if doc.get("baseline") is None and "baseline" in doc:
        body["baseline"] = None
    _store.write_text(
        p, yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8"
    )
    return p


def runs_of(rnd: dict[str, Any], runs_dir: Path | None = None) -> list[tuple[Path, dict]]:
    """The runs that name this round (and its goal), in data/runs or `runs_dir`."""
    return [
        (d, m)
        for d, m in runs_on(rnd.get("dataset_id"), runs_dir=runs_dir)
        if m.get("round") == rnd["round_id"] and m.get("goal") == rnd["goal"]
    ]


def harness_now() -> dict[str, Any]:
    """The harness code a round is opened on: its version, the project's commit, and the hash of the code that
    can change a measurement (the same `instrument.harness` a run records)."""
    from evaluation_harness import _fingerprint  # noqa: PLC0415

    h = _fingerprint._harness_identity(_common.ROOT, _common.DATA)
    return {k: h.get(k) for k in ("version", "commit", "code_sha256", "installed")}


def off_harness(rnd: dict[str, Any], runs_dir: Path | None = None) -> list[tuple[str, dict]]:
    """The round's runs that ran on other harness code than it opened on (the fleet's feedback 17: code taken
    mid-round splits the round's instrument), as (run id, the harness it recorded). Empty for a round
    opened before rounds recorded it."""
    want = (rnd.get("harness") or {}).get("code_sha256")
    if not want:
        return []
    out = []
    for d, m in runs_of(rnd, runs_dir):
        h = ((m.get("fingerprint") or {}).get("instrument") or {}).get("harness") or {}
        if h.get("code_sha256") and h["code_sha256"] != want:
            out.append((d.name, h))
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


def arms_of(rnd: dict[str, Any], runs_dir: Path | None = None) -> list[str]:
    """The round's arms still in play: configs whose runs name it, and those carried into it
    unchanged from an earlier round, less the retired."""
    here = runs_dir_name(runs_dir)
    retired = {
        r["config_id"] for r in rnd.get("retired") or [] if (r.get("runs_dir") or runs_dir_name(None)) == here
    }
    ran = {m["config_id"] for _, m in runs_of(rnd, runs_dir)}
    return sorted((ran | set(rnd.get("carried") or [])) - retired)


def runs_dir_name(runs_dir: Path | None) -> str:
    """A runs directory as a retirement names it: relative to data/ (runs, runs-linux), or its
    own name when it lies elsewhere."""
    base = (runs_dir or _common.RUNS).resolve()
    try:
        return base.relative_to(_common.DATA.resolve()).as_posix()
    except ValueError:
        return base.name


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
        known.add((doc.get("goal"), doc.get("round_id")))
    for f in sorted(_store.glob(base, "*/*.yaml")):
        doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {} if yaml else {}
        if doc.get("from") and (doc.get("goal"), doc["from"]) not in known:
            out.append(f"rounds/{f.relative_to(base).as_posix()}: from {doc['from']!r}, which does not exist")
    for d, m in runs_on():
        if m.get("round") and (m.get("goal"), m["round"]) not in known:
            out.append(f"run {d.name} names round {m['round']!r} of {m.get('goal')!r}, which does not exist")
    return out
