"""What one process may spend (RFC-026 step 5): the cap, counted where the spend is counted, and a round's budget.

    _spend.cap()          the most this process may spend: EVAL_MAX_COST_USD, and what its round left it (reserve)
    _spend.left()         the cap less what the commands' item loops counted (`add`), across passes (`run --repeat`)
    _spend.net(cost)      the bundled provider layer's own count, a second net for an adapter that reports no cost
    _spend.reserve(...)   a round with budget_usd: what it has left, reserved in its ledger before the first call
    _spend.close()        the reservation closed with what was spent (at the command's end; the supervisor closes it
                          for a command that died, and a reader counts a dead one's written items)

The ledger is `.build/rounds/<goal>/<round>.json`, one entry per spending command: {id, pid, job, command, run_ids,
reserved, spent, closed_at}. What a round has left is its budget, less what its runs have spent (as `evh rounds`
counts it), less each closed entry's spend its runs do not already show, less each open entry's reservation (its
items' spend when its process is gone). Ten arms of a round started at once share what is left; none gets all of it.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

from evaluation_harness import _common

#: What the commands' item loops counted in this process (an adapter's reported cost_usd), every pass.
_SPENT = [0.0]
#: What the bundled provider layer counted in this process: its second net.
_NET = [0.0]
#: What this process's round left it, when it reserved (None: no round budget applies).
_ROUND_CAP: list[float | None] = [None]
#: This process's open reservation: (the ledger, the entry's id).
_OPEN: list[tuple[Path, str]] = []


def own_cap() -> float | None:
    """EVAL_MAX_COST_USD (a job's max_cost_usd arrives as it)."""
    return _common.env_float("EVAL_MAX_COST_USD")


def cap() -> float | None:
    """The most this process may spend: the least of its own cap and its round's share; None when neither is set."""
    caps = [c for c in (own_cap(), _ROUND_CAP[0]) if c is not None]
    return min(caps) if caps else None


def left() -> float | None:
    """What is left to spend in this process (never below 0), or None with no cap."""
    c = cap()
    return None if c is None else max(c - _SPENT[0], 0.0)


def add(cost: float | None) -> None:
    """A call's cost, as the command's item loop counts it."""
    if cost:
        _SPENT[0] += float(cost)
        if _common.SPENT_LIVE:
            with contextlib.suppress(OSError):
                tmp = Path(_common.SPENT_LIVE + ".tmp")
                tmp.write_text(json.dumps({"spent_usd": round(_SPENT[0], 8)}) + "\n")
                os.replace(tmp, _common.SPENT_LIVE)


def _report() -> None:
    """At exit (registered by _common when EVH_SPENT_TO was set), however the command ends but a kill: what it spent,
    for the command that ran it (sweep, model-onboard), which gives the next child what is left. A child that dies
    without writing it is read as having spent all it was given."""
    if not _common.SPENT_TO:
        return
    with contextlib.suppress(OSError):
        Path(_common.SPENT_TO).write_text(json.dumps({"spent_usd": round(_SPENT[0], 8)}) + "\n")


def run_child(cmd: list[str], **kw: Any) -> tuple[Any, float]:
    """A spending child (an arm of a sweep, model-onboard's smoke) run with what is left of this process's cap as its
    EVAL_MAX_COST_USD; its output goes where this process's goes (a job's log, as it comes). Returns (the completed
    process, what it spent): what it wrote at exit, else all it was given (it died before it could say)."""
    import subprocess  # noqa: PLC0415  # nosec B404 - the harness's own commands
    import tempfile  # noqa: PLC0415

    env = dict(kw.pop("env", None) or os.environ)
    given = left()
    if given is not None:
        env["EVAL_MAX_COST_USD"] = f"{given:.8f}"
    fd, name = tempfile.mkstemp(prefix="evh-spent-", suffix=".json")
    os.close(fd)
    env["EVH_SPENT_TO"] = name
    try:
        r = subprocess.run(cmd, env=env, **kw)
        try:
            paid = float(json.loads(Path(name).read_text(encoding="utf-8") or "{}").get("spent_usd") or 0)
            wrote = bool(Path(name).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            paid, wrote = 0.0, False
        if not wrote:  # killed before it could say: all it was given (with no cap, nothing is counted)
            paid = given or 0.0
    finally:
        Path(name).unlink(missing_ok=True)
    add(paid)
    return r, paid


def spent() -> float:
    """What the item loops counted in this process."""
    return _SPENT[0]


def net(cost: float | None) -> None:
    """A call's cost as the provider layer saw it."""
    if cost:
        _NET[0] += float(cost)


def net_check() -> None:
    """Before a provider call: refused once the provider layer's own count reached the cap (an adapter that reports
    no cost to its command's loop is stopped here)."""
    c = cap()
    if c is not None and _NET[0] >= c:
        raise _common.CostCapExceeded(f"the provider layer counted ${_NET[0]:.4f} of the ${c:.4f} cap")


# ── a round's budget ────────────────────────────────────────────────────────────────────────────────────────────────


def ledger_path(goal: str, round_id: str) -> Path:
    """A round's ledger of reservations (not project data: under .build/, as the jobs are)."""
    return _common.project_root() / ".build" / "rounds" / goal / f"{round_id}.json"


def _alive(pid: Any) -> bool:
    try:
        pid = int(pid)
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            return stat.read_text().rsplit(")", 1)[1].split()[0] != "Z"
        os.kill(pid, 0)
    except (OSError, ValueError, TypeError, IndexError):
        return False
    return True


def _run_spend(run_id: str) -> tuple[bool, float]:
    """(whether the run is visible, what it spent): a finished run's first score, else what its written items say. A
    throwaway pass (`evh run --scratch`) is read where it was written, and is never visible to what reads data/runs."""
    from evaluation_harness import _outputs  # noqa: PLC0415
    from evaluation_harness.model import runs as _model_runs  # noqa: PLC0415

    d = _model_runs.run_dir(run_id)
    scratch = (
        not _model_runs.run(run_id) and _model_runs.run(_model_runs.run_dir(run_id, scratch=True)) is not None
    )
    if scratch:
        d = _model_runs.run_dir(run_id, scratch=True)
    first = _model_runs.first_score(d)
    doc = _model_runs.record(first) if first else None
    if doc is not None:
        return not scratch, float((doc.get("scores") or {}).get("total_cost_usd") or 0)
    text = _outputs.store().rows_text(d, partial=True, errors="replace") or ""
    total = 0.0
    for line in text.splitlines():
        with contextlib.suppress(ValueError, TypeError, AttributeError):
            total += float(json.loads(line).get("cost_usd") or 0)
    return False, total


def _entry_use(e: dict[str, Any]) -> float:
    """What one entry takes from the budget beyond what its visible runs already show."""
    shown = items = 0.0
    for rid in e.get("run_ids") or []:
        visible, amount = _run_spend(rid)
        if visible:
            shown += amount
        else:
            items += amount
    if e.get("closed_at"):
        return max(float(e.get("spent") or 0) - shown, 0.0)
    if _alive(e.get("pid")):
        return max(float(e.get("reserved") or 0) - shown, 0.0)
    # Gone without closing: what its runs' items say, or (a command that writes no run, judge-score) all it reserved.
    return items if e.get("run_ids") else float(e.get("reserved") or 0)


def round_left(rnd: dict[str, Any]) -> float | None:
    """What a round with budget_usd has left: the budget, less its runs' spend, less the ledger's (see above)."""
    if rnd.get("budget_usd") is None:
        return None
    from evaluation_harness import _rounds  # noqa: PLC0415

    used = sum(float((m.get("scores") or {}).get("total_cost_usd") or 0) for _, m in _rounds.runs_of(rnd))
    for e in _read(ledger_path(rnd["goal"], rnd["round_id"])).get("entries", []):
        used += _entry_use(e)
    return float(rnd["budget_usd"]) - used


def _read(p: Path) -> dict[str, Any]:
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"entries": []}
    return doc if isinstance(doc, dict) else {"entries": []}


@contextlib.contextmanager
def _goal_lock(goal: str):
    """The goal's lock for the moment the ledger is read and written, unless this process holds it already (a job's
    command holds its own locks, passed to it: taking it again here would wait on itself)."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    key = f"goal:{goal}"
    if key in (os.environ.get("EVH_LOCKS") or "").split(","):
        yield
        return
    with _jobs.holding([(key, True)], os.environ.get("EVH_JOB") or f"pid {os.getpid()}", _jobs.say_waiting):
        yield


def reserve(rnd: dict[str, Any], command: str, run_ids: list[str] | None = None) -> float | None:
    """Before a spending command's first call on a round with budget_usd: what it may spend (the least of its own cap
    and what the round has left), reserved in the ledger. Refused (`over-budget`) when nothing is left. None when the
    round has no budget."""
    if rnd.get("budget_usd") is None:
        return None
    p = ledger_path(rnd["goal"], rnd["round_id"])
    with _goal_lock(rnd["goal"]):
        left_now = round_left(rnd)
        assert left_now is not None
        if left_now <= 0:
            _common.die(
                f"round {rnd['round_id']} of {rnd['goal']} has spent its budget (${float(rnd['budget_usd']):.2f}, "
                "counting what its running commands have reserved): nothing is called. Raise budget_usd in the "
                "round, or wait for a running arm to end (`evh rounds` shows what was spent)",
                "over-budget",
            )
        own = own_cap()
        share = left_now if own is None else min(own, left_now)
        doc = _read(p)
        eid = secrets.token_hex(4)
        doc.setdefault("entries", []).append(
            {
                "id": eid,
                "pid": os.getpid(),
                "job": os.environ.get("EVH_JOB") or None,
                "command": command,
                "run_ids": list(run_ids or []),
                "reserved": round(share, 8),
                "spent": None,
                "at": _common.now(),
                "closed_at": None,
            }
        )
        p.parent.mkdir(parents=True, exist_ok=True)
        _common.write_text_atomic(p, json.dumps(doc, indent=2, sort_keys=True) + "\n")
    _ROUND_CAP[0] = share
    _OPEN[:] = [(p, eid)]
    import atexit  # noqa: PLC0415

    atexit.register(close)
    return share


def add_run(run_id: str) -> None:
    """A run this process's reservation covers (each pass of `run --repeat` is a run)."""
    if _OPEN:
        _update(
            _OPEN[0],
            lambda e: e.setdefault("run_ids", []).append(run_id) if run_id not in e["run_ids"] else None,
        )


def _update(where: tuple[Path, str], fn) -> None:
    p, eid = where
    goal = p.parent.name
    with _goal_lock(goal):
        doc = _read(p)
        for e in doc.get("entries", []):
            if e.get("id") == eid:
                fn(e)
        _common.write_text_atomic(p, json.dumps(doc, indent=2, sort_keys=True) + "\n")


def close(amount: float | None = None) -> None:
    """The reservation closed with what this process spent (its loops' count). Called at exit as well; once."""
    if not _OPEN:
        return
    where = _OPEN.pop()
    total = _SPENT[0] if amount is None else amount
    _update(where, lambda e: e.update(spent=round(total, 8), closed_at=_common.now()))


def close_for_job(job_id: str) -> int:
    """The supervisor, after its command ended: every reservation the job's command left open is closed with what
    its runs' written items say it spent (a stopped run writes no metrics.json, but its items were paid for); one that
    writes no run is closed at all it reserved, since what it paid cannot be read back. Returns how many it closed."""
    root = _common.project_root() / ".build" / "rounds"
    n = 0
    for p in sorted(root.glob("*/*.json")) if root.is_dir() else []:
        doc = _read(p)
        mine = [e for e in doc.get("entries", []) if e.get("job") == job_id and not e.get("closed_at")]
        if not mine:
            continue

        def shut(e: dict[str, Any]) -> None:
            if e.get("job") == job_id and not e.get("closed_at"):
                runs = e.get("run_ids") or []
                paid = sum(_run_spend(r)[1] for r in runs) if runs else float(e.get("reserved") or 0)
                e.update(spent=round(paid, 8), closed_at=_common.now())

        for e in mine:
            _update((p, e["id"]), shut)
            n += 1
    return n
