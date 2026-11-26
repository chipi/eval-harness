"""What one process may spend (RFC-026 step 5): the cap, counted where the spend is counted, and a round's budget.

    _spend.cap()          the most this process may spend: EVAL_MAX_COST_USD, and what its round left it (reserve)
    _spend.left()         the cap less what the commands' item loops counted (`add`), across passes (`run --repeat`)
    _spend.net(cost)      the bundled provider layer's own count, a second net for an adapter that reports no cost
    _spend.reserve(...)   a round with budget_usd: what it has left, reserved in its ledger before the first call
    _spend.close()        the reservation closed with what was spent (at the command's end; the supervisor closes it
                          for a command that died, and a reader counts a dead one's written items)

The ledger is `.build/rounds/<goal>/<round>.json`, one entry per spending command: {id, pid, job, command, run_ids,
reserved, spent, closed_at}. What a round has left is its budget, less what its runs have spent (as `evh round-list`
counts it), less each closed entry's spend its runs do not already show, less each open entry's reservation (its
items' spend when its process is gone). Ten arms of a round started at once share what is left; none gets all of it.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import tempfile
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


def reached(spent: float, cap_usd: float | None) -> bool:
    """The cap stops a call once something was spent and it is used up. Nothing spent is never stopped, so a cap of 0
    means "spend nothing" and lets a free run through; the first call that spends is the last."""
    return cap_usd is not None and spent > 0 and spent >= cap_usd


def shown(cap_usd: float | None) -> str:
    """A cap as every command prints it. Three meanings, never two: no cap, spend nothing, and an amount. A test of the
    cap's truth printed a cap of 0 as none (the homelab bake-off, v0.8.0)."""
    if cap_usd is None:
        return "NONE"
    if cap_usd <= 0:
        return "$0.00 (spend nothing: only what is known to be free runs)"
    return f"${cap_usd:.2f}"


ZERO_CAP_HINT = (
    "a cap of 0 runs only what is known to be free: provider echo, a judge of provider fake, a recorded arm (provider "
    "recorded), or a system that declares usd_per_mtok_in: 0 and usd_per_mtok_out: 0. Declare those two prices as 0, "
    "or raise the cap."
)


def known_free(params: dict[str, Any] | None) -> bool:
    """Whether a system (or a judge) is known, before any call, to spend nothing: a bundled provider that makes no paid
    call (`adapter.FREE_PROVIDERS`; judging's `FAKE` for a judge), a recorded arm (the run's own test: it calls nothing),
    or both prices declared 0. A project adapter's provider name proves nothing, and a cost of 0 reported after a call is
    only known after the spending."""
    from evaluation_harness import adapter, judging  # noqa: PLC0415

    p = params or {}
    if p.get("provider") in (*adapter.FREE_PROVIDERS, judging.FAKE, "recorded"):
        return True
    pin, pout = p.get("usd_per_mtok_in"), p.get("usd_per_mtok_out")
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) and x == 0 for x in (pin, pout))


def zero_blocked(cap_usd: float | None, *params: dict[str, Any] | None) -> bool:
    """A cap of 0 (spend nothing) with something that is not known to be free."""
    return cap_usd is not None and cap_usd <= 0 and not all(known_free(p) for p in params)


def stops(spent: float, cap_usd: float | None, *params: dict[str, Any] | None) -> bool:
    """No further call: the cap is used up by what was spent, or it is 0 and `params` (the systems or judges that would
    call) are not known to be free."""
    return reached(spent, cap_usd) or zero_blocked(cap_usd, *params)


def exhausted(*params: dict[str, Any] | None) -> bool:
    """This process's cap (its own, or its round's share) stops a call by `params`."""
    return stops(_SPENT[0], cap(), *params)


def add(cost: float | None) -> None:
    """A call's cost, as the command's item loop counts it."""
    if cost:
        _SPENT[0] += float(cost)
        if _common.SPENT_LIVE:
            with contextlib.suppress(OSError):
                tmp = Path(_common.SPENT_LIVE + ".tmp")
                tmp.write_text(json.dumps({"spent_usd": round(_SPENT[0], 8)}) + "\n", encoding="utf-8")
                os.replace(tmp, _common.SPENT_LIVE)


def _report() -> None:
    """At exit (registered by _common when EVH_SPENT_TO was set), however the command ends but a kill: what it spent,
    for the command that ran it (sweep, model-onboard), which gives the next child what is left. A child that dies
    without writing it is read as having spent all it was given."""
    if not _common.SPENT_TO:
        return
    with contextlib.suppress(OSError):
        Path(_common.SPENT_TO).write_text(
            json.dumps({"spent_usd": round(_SPENT[0], 8)}) + "\n", encoding="utf-8"
        )


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
    env["PYTHONIOENCODING"] = "utf-8"  # the callers read the child's answer as UTF-8
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
    if reached(_NET[0], c):
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
            return stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0] != "Z"
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
    total = 0.0
    for row in _outputs.rows(d, partial=True, errors="replace") or ():
        with contextlib.suppress(ValueError, TypeError):
            total += float(row.get("cost_usd") or 0)
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
    # Gone without closing: what its runs' items say, or (a command that writes no run) all it reserved. Judging opens
    # no entry: its spend is capped by its scorer and EVAL_JUDGE_MAX_COST_USD, never a round's budget (owner, 2026-11-14).
    return items if e.get("run_ids") else float(e.get("reserved") or 0)


def round_left(rnd: dict[str, Any], data: Path | None = None) -> float | None:
    """What a round with budget_usd has left: the budget, less its runs' spend (those under `data`: another data
    directory than the project's), less the ledger's (see above)."""
    if rnd.get("budget_usd") is None:
        return None
    from evaluation_harness import _rounds  # noqa: PLC0415

    # An unknown cost cannot be charged: only what runs recorded counts, and over-budget names the rest.
    used = _rounds.spend_of(rnd, data)[0] or 0.0
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


def refuse_unpriced(rnd: dict[str, Any], system_id: str, params: dict[str, Any], allow: bool = False) -> None:
    """Before an arm of a round with budget_usd starts: refused (`not-configured`) when its system declares no price
    (usd_per_mtok_in and usd_per_mtok_out; an explicit 0 is a price), because what it spends could not be counted
    against the budget. With `allow` (--allow-unpriced) it goes through and the round records that, so the budget
    reads as leaving the arm out."""
    if rnd.get("budget_usd") is None:
        return
    if params.get("usd_per_mtok_in") is not None and params.get("usd_per_mtok_out") is not None:
        return
    model = params.get("model") or "no model named"
    if not allow:
        _common.die(
            f"round {rnd['round_id']} of {rnd['goal']} has a budget (${float(rnd['budget_usd']):.2f}), and arm "
            f"{system_id} (model {model}) declares no price, so what it costs cannot be counted against it: nothing "
            "is called. Put usd_per_mtok_in and usd_per_mtok_out in the system's params (0 is a price, for a model "
            "that costs nothing per token), or start it with --allow-unpriced: the budget then leaves it out, and "
            "the round records that",
            "not-configured",
        )
    from evaluation_harness import _actor, _rounds  # noqa: PLC0415

    _rounds.allow_unpriced(rnd["goal"], rnd["round_id"], system_id, str(model), _actor.actor())
    print(
        f"  round {rnd['round_id']}: {system_id} has no price, started with --allow-unpriced: "
        "its cost is not counted against the budget"
    )


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
            from evaluation_harness import _rounds  # noqa: PLC0415

            unpriced = _rounds.no_cost_words(_rounds.spend_of(rnd)[1])
            _common.die(
                f"round {rnd['round_id']} of {rnd['goal']} has spent its budget (${float(rnd['budget_usd']):.2f}, "
                "counting what its running commands have reserved"
                + (f"; {unpriced}, so what they cost is not counted" if unpriced else "")
                + "): nothing is called. Raise budget_usd in the "
                f"round, or wait for a running arm to end (`evh round-evidence {rnd['goal']} {rnd['round_id']}` shows what was spent)",
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


def said_before(key: str, who: str) -> str | None:
    """Who a dry run of the same sweep printed this note for already, else None and `who` is recorded as the one it is
    printed for (`evh sweep --dry-run` runs each arm in a process of its own and names a file in EVH_DRY_SEEN for them
    to share). Always None outside a sweep."""
    path = os.environ.get("EVH_DRY_SEEN")
    if not path:
        return None
    seen = Path(path)
    for line in seen.read_text(encoding="utf-8").splitlines():
        k, _, first = line.partition("\t")
        if k == key:
            return first
    with seen.open("a", encoding="utf-8") as fh:
        fh.write(f"{key}\t{who}\n")
    return None


def notes_file() -> str:
    """A temp file the arms of one `evh sweep --dry-run` share, so a note for a model is said once (`said_before`)."""
    fd, path = tempfile.mkstemp(prefix="evh-dry-seen-")
    os.close(fd)
    return path


def drop_notes_file(path: str) -> None:
    """The sweep's shared notes file, removed when its arms are done."""
    if path:
        Path(path).unlink(missing_ok=True)
