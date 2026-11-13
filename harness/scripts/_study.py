"""Studies (RFC-029): research by ask/tell over trials on a validation dataset; evidence only from a confirmation.

    data/studies/<goal>/<study_id>.yaml             the spec, written by a person or an agent
    data/studies/<goal>/<study_id>.events.jsonl     the log: start, ask, trial, end, confirm (one JSON line each)
    data/studies/<goal>/<study_id>/<study_id>-t<k>.yaml   trial k's system, written once (found like any system)
    data/studies/<goal>/<study_id>/confirm/...      a confirmation's item list (its two systems run on the test set)

A study's state (running, stopped, the best so far, what it spent, an open ask) is read from its log, never stored
apart. Every write to the log is under the study's lock (`study:<goal>/<study_id>`, RFC-026). A study never reads a
test set and never suggests a promotion; `study-confirm` is the one step that gives evidence (one look, RFC-029).
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from evaluation_harness import _common, _store

SAMPLERS = ("grid", "command", "agent")
STUDY_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,60}")


# ── files ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def root() -> Path:
    """data/studies/."""
    return _common.DATA / "studies"


def spec_path(goal: str, sid: str) -> Path:
    """A study's spec."""
    return root() / goal / f"{sid}.yaml"


def log_path(goal: str, sid: str) -> Path:
    """A study's log."""
    return root() / goal / f"{sid}.events.jsonl"


def folder(goal: str, sid: str) -> Path:
    """A study's own folder: its trials' systems, its confirmations."""
    return root() / goal / sid


def resolve(name: str) -> tuple[str, str]:
    """`<goal>/<study_id>`, or a study id one goal has, as (goal, study_id); refused otherwise."""
    if "/" in name:
        goal, sid = name.split("/", 1)
        if _store.is_file(spec_path(goal, sid)):
            return goal, sid
        _common.die(f"no study {name} (data/studies/{goal}/{sid}.yaml)", "not-found")
    hits = [p.parent.name for p in _store.glob(root(), f"*/{name}.yaml")] if _store.is_dir(root()) else []
    if len(hits) == 1:
        return hits[0], name
    _common.die(
        f"study {name}: "
        + (
            f"several goals have one ({', '.join(sorted(hits))}): name it <goal>/{name}"
            if hits
            else "no such study"
        ),
        "not-found",
    )
    raise AssertionError  # die exits


def spec(goal: str, sid: str) -> dict[str, Any]:
    """The spec, as written."""
    doc = yaml.safe_load(_store.read_text(spec_path(goal, sid), encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        _common.die(f"{spec_path(goal, sid)}: a mapping", "invalid-file")
    return doc


def events(goal: str, sid: str) -> list[dict[str, Any]]:
    """The log's events, in order (a torn last line is not an event)."""
    p = log_path(goal, sid)
    out = []
    for line in (_store.read_text(p, encoding="utf-8") if _store.is_file(p) else "").splitlines():
        with contextlib.suppress(ValueError):
            ev = json.loads(line)
            if isinstance(ev, dict):
                out.append(ev)
    return out


@contextlib.contextmanager
def locked(goal: str, sid: str):
    """The study's lock for a write, unless this process holds it already (a study job's command holds its own)."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    key = f"study:{goal}/{sid}"
    if key in (os.environ.get("EVH_LOCKS") or "").split(","):
        yield
        return
    with _jobs.holding([(key, True)], os.environ.get("EVH_JOB") or f"pid {os.getpid()}", _jobs.say_waiting):
        yield


@contextlib.contextmanager
def loop_lock(goal: str, sid: str):
    """The study's loop (study-run, study-tell): one at a time, refused at once when another holds it (a job holds it
    already when its command runs). Separate from the log's lock, so study-stop can always write."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    key = f"study-loop:{goal}/{sid}"
    if key in (os.environ.get("EVH_LOCKS") or "").split(","):
        yield
        return
    try:
        with _jobs.holding([(key, True)], os.environ.get("EVH_JOB") or f"pid {os.getpid()}"):
            yield
    except _jobs.Busy as exc:
        _common.die(f"study {goal}/{sid} is running elsewhere ({exc})", "not-allowed")


def append(goal: str, sid: str, ev: dict[str, Any]) -> dict[str, Any]:
    """One event at the log's end, under the study's lock (an append in the SQLite store is a read and a rewrite)."""
    from evaluation_harness._actor import actor  # noqa: PLC0415

    ev = {"at": _common.now(), "actor": actor(), **ev}
    with locked(goal, sid):
        p = log_path(goal, sid)
        before = _store.read_text(p, encoding="utf-8") if _store.is_file(p) else ""
        if before and not before.endswith("\n"):
            before += "\n"
        _store.write_text(p, before + json.dumps(ev, sort_keys=True, default=str) + "\n")
    return ev


# ── the spec ───────────────────────────────────────────────────────────────────────────────────────────────────────


def problems(goal: str, sid: str, s: dict[str, Any]) -> list[str]:
    """What is wrong with a spec, before anything runs."""
    from evaluation_harness import _looks  # noqa: PLC0415

    out = []
    if not STUDY_ID.fullmatch(sid):
        out.append(f"study id {sid!r}: lower-case letters, digits, '_' or '-'")
    goals = _common.load_goals()
    if goal not in goals:
        out.append(f"goal {goal!r} does not exist (data/goals/)")
    ds = s.get("dataset")
    if not ds:
        out.append("dataset: the validation dataset trials run on")
    elif _looks.is_test_set(str(ds)):
        out.append(
            f"dataset {ds} is a test set: a study runs on validation items; study-confirm reads a test set"
        )
    if not (s.get("baseline") or {}).get("system"):
        out.append("baseline: {system: <system_id>} (the system the study starts from)")
    if not s.get("measure"):
        out.append("measure: the goal's metric the study is decided on")
    sampler = s.get("sampler")
    name = sampler if isinstance(sampler, str) else (sampler or {}).get("command") and "command"
    if name not in SAMPLERS:
        out.append("sampler: grid, agent, or {command: '<a program speaking ask/tell>'}")
    acc = s.get("accept") or {}
    if not (acc == "test" or (isinstance(acc, dict) and ("point" in acc or acc.get("rule") == "test"))):
        out.append("accept: {point: {min_gain: 0}} or test")
    stop = s.get("stop") or {}
    if not stop.get("trials") and not (stop.get("usd") and stop.get("wall_h")):
        out.append("stop: trials, or (to run until stopped) both usd and wall_h")
    if name == "grid" and not ((s.get("space") or {}).get("groups")):
        out.append("space.groups: what the grid sampler tries")
    return out


def frozen_hash(s: dict[str, Any], goal: str | None = None, sid: str | None = None) -> str:
    """One hash over the spec's bytes (a comment changed is a change: the spec is the study's record) and the files it
    freezes, checked before every trial."""
    raw = (
        _store.read_bytes(spec_path(goal, sid))
        if goal and sid and _store.is_file(spec_path(goal, sid))
        else b""
    )
    h = hashlib.sha256(raw or json.dumps(s, sort_keys=True, default=str).encode())
    for f in s.get("frozen") or []:
        p = Path(str(f))
        p = p if p.is_absolute() else _common.ROOT / p
        h.update(str(f).encode())
        h.update(_store.read_bytes(p) if _store.is_file(p) else b"(missing)")
    return h.hexdigest()


# ── state, read from the log ───────────────────────────────────────────────────────────────────────────────────────


def state(goal: str, sid: str) -> dict[str, Any]:
    """The study as its log says: status, round, trials, the best so far, spent, the open ask."""
    evs = events(goal, sid)
    start = next((e for e in evs if e.get("event") == "start"), None)
    groups = {e.get("k"): e.get("group") for e in evs if e.get("event") == "group"}
    trials = [
        {**e, "group": groups.get(e.get("k"))} if e.get("k") in groups else e
        for e in evs
        if e.get("event") == "trial"
    ]
    end = next((e for e in evs if e.get("event") == "end"), None)
    kept = [t for t in trials if t.get("outcome") == "kept"]
    asks = [e for e in evs if e.get("event") == "ask"]
    told = {t.get("ask_id") for t in trials if t.get("ask_id")}
    open_ask = next((a for a in reversed(asks) if a["ask_id"] not in told), None)
    status = "not started" if start is None else "ended" if end else "running"
    if status == "running" and any(e.get("event") == "stop" for e in evs):
        status = "stopping"
    return {
        "goal": goal,
        "study": sid,
        "status": status,
        "round": (start or {}).get("round"),
        "baseline": (start or {}).get("baseline"),
        "trials": trials,
        "best": kept[-1] if kept else None,
        "start": start,
        "spent_usd": round(sum(float(t.get("cost_usd") or 0) for t in trials), 8),
        "open_ask": open_ask,
        "end": end,
        "confirms": [e for e in evs if e.get("event") == "confirm"],
        "started_at": (start or {}).get("at"),
    }


# ── a trial's system ───────────────────────────────────────────────────────────────────────────────────────────────


def _set_path(d: dict[str, Any], dotted: str, value: Any) -> None:
    cur = d
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
        if not isinstance(cur, dict):
            _common.die(f"{dotted}: {p} is not a mapping in the baseline's params", "bad-argument")
    cur[parts[-1]] = value


def _get_path(d: dict[str, Any], dotted: str) -> Any:
    cur: Any = d
    for p in dotted.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def system_of(system_id: str) -> tuple[Path, dict[str, Any]]:
    """A system by its id (a trial's included): its file and its content."""
    from evaluation_harness._hypothesis import system_ids  # noqa: PLC0415

    p = system_ids().get(system_id)
    if p is None:
        _common.die(f"no system {system_id!r} (evh system-list)", "not-found")
    return p, yaml.safe_load(_store.read_text(p, encoding="utf-8")) or {}


def write_trial_system(goal: str, sid: str, k: int, base_cid: str, proposal: dict[str, Any]) -> str:
    """Trial k's system: the baseline's (or the best so far's) with the proposal's changes, written once."""
    from evaluation_harness import _prompts  # noqa: PLC0415

    _p, base = system_of(base_cid)
    cfg = copy.deepcopy(base)
    cid = f"{sid}-t{k}"
    cfg["system_id"] = cid
    cfg.pop("hypothesis", None)
    params = cfg.setdefault("params", {})
    for path, value in (proposal.get("params") or {}).items():
        _set_path(params, str(path), value)
    root = cfg.get("prompt_root") or {}
    for name, text in (proposal.get("prompts") or {}).items():
        rel = (
            str(name)[len(str(root.get("name"))) + 1 :]
            if root and str(name).startswith(f"{root.get('name')}/")
            else None
        )
        in_root = rel is not None and rel in (root.get("vary") or [])
        before = (
            (root.get("versions") or {}).get(rel)
            if in_root
            else ((cfg.get("prompts") or {}).get(name) or {}).get("version")
        )
        doc, _new = _prompts.record(
            str(name),
            str(text).encode("utf-8"),
            source={"study": f"{goal}/{sid}", "trial": k},
            note=str(proposal.get("hypothesis") or f"trial {k} of {sid}"),
            parent=before,
        )
        if in_root:
            # A varied file of the prompt root (RFC-028): this version goes into the trial's run copy of the root.
            cfg["prompt_root"] = {**root, "versions": {**(root.get("versions") or {}), rel: doc["id"]}}
            root = cfg["prompt_root"]
        else:
            cfg.setdefault("prompts", {})[str(name)] = {"version": doc["id"]}
    path = folder(goal, sid) / f"{cid}.yaml"
    try:
        _store.create_new(path, yaml.safe_dump(cfg, sort_keys=False).encode("utf-8"))
    except FileExistsError:
        _common.die(
            f"{path} exists: trial {k} was written before (resume continues after the last trial)",
            "would-overwrite",
        )
    return cid


# ── running and comparing ──────────────────────────────────────────────────────────────────────────────────────────


def _evh(argv: list[str], **kw: Any) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603 - this interpreter and the harness's own commands
        [sys.executable, str(Path(__file__).resolve().parent / "cli.py"), *argv],
        capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, **kw,
    )  # fmt: skip


def run_system(
    cid: str,
    dataset: str,
    goal: str | None = None,
    round_id: str | None = None,
    repeats: int = 1,
    items: Path | None = None,
) -> tuple[int, float, list[str]]:
    """`evh run` of a system on a dataset as a child, given what is left of the cap (RFC-026): (exit, spent, run
    ids)."""
    from evaluation_harness import _spend  # noqa: PLC0415

    argv = [sys.executable, str(Path(__file__).resolve().parent / "cli.py"), "run", "--system", cid]
    argv += ["--dataset", dataset, "--json"]
    argv += ["--goal", goal] if goal else []
    argv += ["--round", round_id] if round_id else []
    argv += ["--repeat", str(repeats)] if repeats > 1 else []
    argv += ["--items", str(items)] if items is not None else []
    r, paid = _spend.run_child(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    sys.stderr.write(r.stderr)
    runs = []
    with contextlib.suppress(ValueError, AttributeError):
        runs = [
            x["run_id"] for x in (json.loads(r.stdout).get("result") or {}).get("values", {}).get("runs", [])
        ]
    return r.returncode, paid, runs


def compare(
    dataset: str, a: str, b: str, metric: str, lower: bool, margin: float | None = None
) -> dict[str, Any]:
    """`pair-test --json` of two arms on the dataset (nominal: a study's p values are research): its values, or
    {"error"} when it refuses."""
    argv = ["pair-test", "--dataset-id", dataset, "--a", a, "--b", b, "--metric", metric, "--json"]
    argv += ["--asc"] if lower else ["--desc"]
    argv += ["--margin", repr(margin)] if margin is not None else []
    r = _evh(argv)
    if r.returncode != 0:
        return {"error": (r.stderr.strip().splitlines() or ["pair-test refused"])[-1]}
    return (json.loads(r.stdout).get("result") or {}).get("values") or {}


def decide(
    s: dict[str, Any], vs_best: dict[str, Any], vs_base: dict[str, Any], limits: list[dict[str, Any]]
) -> tuple[str, str]:
    """(kept | dropped | no effect, the reason), by the spec's rule; limits and tie-breaks against the baseline."""
    if vs_best.get("error"):
        return "dropped", f"not compared: {vs_best['error']}"
    for lim in limits:
        if lim.get("error"):
            return "dropped", f"limit {lim['metric']}: not compared: {lim['error']}"
        if lim["fell_by"] > float(lim["limit"]):
            return (
                "dropped",
                f"{lim['metric']} fell {lim['fell_by']:.4g} against the baseline, beyond its limit {lim['limit']}",
            )
    delta = float(vs_best.get("delta") or 0)
    gain = -delta if vs_best.get("direction") == "lower" else delta
    if gain == 0 and not vs_best.get("wins") and vs_best.get("ties") == vs_best.get("n"):
        return "no effect", "measured the same on every item as the best so far"
    acc = s.get("accept") or {}
    if acc == "test" or acc.get("rule") == "test":
        if vs_best.get("verdict") == "SIGNIFICANT" and gain > 0:
            return "kept", f"separated as better than the best so far (nominal p {vs_best.get('p'):.3g})"
        why = f"not separated from the best so far (nominal p {vs_best.get('p'):.3g})"
    else:
        point = acc.get("point") or {}
        need = float(point.get("min_gain") or 0)
        base = float(vs_best.get("mean_b") or 0)
        if point.get("relative") and base:
            need *= abs(base)
        if gain > need:
            return "kept", f"beat the best so far by {gain:.4g} (needed more than {need:.4g})"
        why = f"gained {gain:.4g} on the best so far, not more than {need:.4g}"
    tb = acc.get("tie_break") if isinstance(acc, dict) else None
    if tb and vs_base.get("noninferior"):
        ni = vs_base["noninferior"] or {}
        if ni.get("verdict") == "non-inferior":
            return "kept", f"{why}; kept on {tb}: non-inferior to the baseline by the goal's margin"
        return "dropped", f"{why}; not shown non-inferior to the baseline ({ni.get('verdict')})"
    return "dropped", why


def _mean(run_ids: list[str], metric: str) -> float | None:
    vals = []
    for r in run_ids:
        f = _common.RUNS / r / "metrics.json"
        if _store.is_file(f):
            v = (json.loads(_store.read_text(f, encoding="utf-8")).get("scores") or {}).get(metric)
            if isinstance(v, (int, float)):
                vals.append(float(v))
    return sum(vals) / len(vals) if vals else None


def lower_is_better(goal: str, metric: str) -> bool:
    """Whether the study's measure is better lower: the goal's primary direction when it is that measure."""
    prim = ((_common.load_goals().get(goal) or {}).get("success_criteria") or {}).get("primary") or {}
    return prim.get("measure") == metric and prim.get("direction") == "lower"


def trial(
    goal: str,
    sid: str,
    k: int,
    proposal: dict[str, Any],
    ask_id: str | None = None,
    shown: list | None = None,
) -> dict[str, Any]:
    """Run trial k from a proposal, decide it, and append its line (with the items its sampler was shown). Returns
    the line."""
    s, st = spec(goal, sid), state(goal, sid)
    base_cid = st["baseline"]
    best_cid = (st["best"] or {}).get("config_id") or base_cid
    cid = write_trial_system(goal, sid, k, best_cid, proposal)
    code, paid, runs = run_system(cid, s["dataset"], goal, st["round"], int(s.get("repeats") or 1))
    metric = str(s["measure"])
    lower = lower_is_better(goal, metric) or s.get("direction") == "lower"
    line: dict[str, Any] = {
        "event": "trial",
        "k": k,
        "config_id": cid,
        "from": best_cid,
        "change": {"params": proposal.get("params") or {}, "prompts": sorted(proposal.get("prompts") or {})},
        "hypothesis": proposal.get("hypothesis"),
        "rationale": proposal.get("rationale"),
        "runs": runs,
        "cost_usd": round(paid, 8),
        "shown": list(shown or []),
        **({"ask_id": ask_id} if ask_id else {}),
    }
    if code != 0 or not runs:
        line |= {"outcome": "failed", "reason": f"the run ended with exit {code}"}
        return append(goal, sid, line)
    acc = s.get("accept") or {}
    margin = acc.get("margin") if isinstance(acc, dict) else None
    vs_best = compare(s["dataset"], cid, best_cid, metric, lower)
    vs_best["mean_b"] = _mean(list(_runs_of(s["dataset"], best_cid)), metric)
    vs_base = (
        compare(s["dataset"], cid, base_cid, metric, lower, margin if margin is not None else None)
        if base_cid != best_cid or margin is not None
        else vs_best
    )
    limits = []
    for lim in s.get("limits") or []:
        lo = lim.get("direction") == "lower"
        v = compare(s["dataset"], cid, base_cid, str(lim["metric"]), lo)
        if v.get("error"):
            limits.append({**lim, "error": v["error"]})
            continue
        d = float(v.get("delta") or 0)
        limits.append({**lim, "fell_by": d if lo else -d})
    outcome, reason = decide(s, vs_best, vs_base, limits)
    line |= {
        "outcome": outcome,
        "reason": reason,
        "vs_best": {x: vs_best.get(x) for x in ("delta", "p", "n", "verdict", "error")},
        "vs_baseline": {x: vs_base.get(x) for x in ("delta", "p", "n", "verdict", "error")},
        "nominal": True,
    }
    return append(goal, sid, line)


def _runs_of(dataset: str, cid: str) -> list[str]:
    """The system's runs on the study's dataset (a confirmation's runs on the test set are not its trials')."""
    from evaluation_harness import _runs  # noqa: PLC0415

    return [d.name for d, _m in _runs.runs_on(dataset, config_id=cid)]


# ── samplers ───────────────────────────────────────────────────────────────────────────────────────────────────────


def weakest(goal: str, sid: str, best_cid: str, n: int) -> list[dict[str, Any]]:
    """The best so far's n weakest validation items on the measure: each one's id, score, text and content hash,
    what a sampler is shown so it can see where the arm fails (and what a confirmation then leaves out)."""
    from evaluation_harness import _runs  # noqa: PLC0415
    from evaluation_harness._common import MATERIALIZED, load_dataset  # noqa: PLC0415

    if n <= 0:
        return []
    s = spec(goal, sid)
    metric = str(s["measure"])
    lower = lower_is_better(goal, metric) or s.get("direction") == "lower"
    runs = _runs.runs_on(s["dataset"], config_id=best_cid)
    if not runs:
        return []
    scores: dict[str, list[float]] = {}
    for d, _m in runs:
        for row in _runs.item_rows(d, strict=False):
            v = row.get(metric)
            if isinstance(v, (int, float)):
                scores.setdefault(row["item_id"], []).append(float(v))
    items = {it["item_id"]: it for it in load_dataset(s["dataset"]).get("items") or []}
    ranked = sorted(((sum(v) / len(v), i) for i, v in scores.items() if i in items), reverse=lower)[:n]
    out = []
    for score, iid in ranked:
        it = items[iid]
        path = MATERIALIZED / s["dataset"] / (it.get("source_path") or iid)
        text = _store.read_text(path, encoding="utf-8", errors="replace") if _store.is_file(path) else ""
        out.append({"item_id": iid, "sha256": it.get("source_sha256"), metric: score, "text": text[:4000]})
    return out


def sampler_state(goal: str, sid: str) -> dict[str, Any]:
    """What a sampler sees: the baseline, the best so far with its weakest validation items (`show_items`, default 5;
    each shown item is recorded), the history, the space, the money left, the directions. Never a test set's items."""
    from evaluation_harness import _spend  # noqa: PLC0415

    s, st = spec(goal, sid), state(goal, sid)
    best_cid = (st["best"] or {}).get("config_id") or st["baseline"]
    _p, best_cfg = system_of(best_cid)
    return {
        "weakest_items": weakest(goal, sid, best_cid, int(s.get("show_items", 5))),
        "study": f"{goal}/{sid}",
        "measure": s.get("measure"),
        "baseline": st["baseline"],
        "best": {
            "config_id": best_cid,
            "params": best_cfg.get("params") or {},
            "prompts": {
                n: (_prompt_text(v) if isinstance(v, dict) else None)
                for n, v in (best_cfg.get("prompts") or {}).items()
            },
        },
        "history": [
            {x: t.get(x) for x in ("k", "change", "hypothesis", "outcome", "reason", "vs_best", "cost_usd")}
            for t in st["trials"]
        ],
        "space": s.get("space") or {},
        "money_left": _spend.left(),
        "directions": s.get("directions"),
    }


def _prompt_text(spec_: dict[str, Any]) -> str | None:
    from evaluation_harness import _prompts  # noqa: PLC0415

    with contextlib.suppress(Exception):
        if spec_.get("version"):
            return _prompts.text_of(spec_["version"]).decode("utf-8", "replace")
        if spec_.get("file"):
            p = Path(spec_["file"])
            return _store.read_text(p if p.is_absolute() else _common.ROOT / p, encoding="utf-8")
    return None


def grid_next(goal: str, sid: str) -> dict[str, Any] | None:
    """The grid sampler: the space's groups in order, one value at a time from the best so far; a group ends after
    `move_on_after` trials without a kept one, or when its values are tried. None: the space is exhausted."""
    s, st = spec(goal, sid), state(goal, sid)
    best_cid = (st["best"] or {}).get("config_id") or st["baseline"]
    _p, best_cfg = system_of(best_cid)
    params = best_cfg.get("params") or {}
    tried = {(json.dumps(t.get("change", {}).get("params") or {}, sort_keys=True)) for t in st["trials"]}
    for g in (s.get("space") or {}).get("groups") or []:
        if not g.get("enabled", True) or not g.get("params"):
            continue
        in_group = [t for t in st["trials"] if t.get("group") == g.get("name")]
        cap = g.get("move_on_after")
        since_kept = 0
        for t in in_group:
            since_kept = 0 if t.get("outcome") == "kept" else since_kept + 1
        if cap and since_kept >= int(cap):
            continue
        for path, values in g["params"].items():
            vals = values if isinstance(values, list) else _range(values)
            for v in vals:
                if _get_path(params, str(path)) == v:
                    continue
                change = {str(path): v}
                if json.dumps(change, sort_keys=True) in tried:
                    continue
                return {"params": change, "hypothesis": f"{path} = {v!r} ({g.get('reason') or g.get('name')})",
                        "rationale": "grid: the next value of the group", "group": g.get("name")}  # fmt: skip
    return None


def _range(spec_: Any) -> list[Any]:
    if isinstance(spec_, dict) and {"low", "high", "step"} <= set(spec_):
        out, v = [], float(spec_["low"])
        while v <= float(spec_["high"]) + 1e-12:
            out.append(round(v, 10))
            v += float(spec_["step"])
        return out
    return [spec_]


class CommandSampler:
    """A program speaking ask/tell over stdio, one JSON object a line: {"ask": state} -> a proposal (or
    {"stop": reason}); {"tell": trial} -> {}. Optuna plugs in this way."""

    def __init__(self, command: str) -> None:
        import shlex  # noqa: PLC0415

        self.p = subprocess.Popen(  # nosec B603 - the project's own sampler, named in its spec
            shlex.split(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=_common.ROOT
        )

    def _say(self, msg: dict[str, Any]) -> dict[str, Any]:
        assert self.p.stdin is not None and self.p.stdout is not None
        self.p.stdin.write(json.dumps(msg, default=str) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            return {"stop": "the sampler ended"}
        try:
            out = json.loads(line)
        except ValueError:
            return {"stop": f"the sampler answered no JSON: {line[:120]!r}"}
        return out if isinstance(out, dict) else {"stop": "the sampler answered no object"}

    def ask(self, st: dict[str, Any]) -> dict[str, Any] | None:
        """A proposal for the next trial, or None when the program stops the study."""
        out = self._say({"ask": st})
        return None if out.get("stop") else out

    def tell(self, line: dict[str, Any]) -> None:
        """The trial's line, told to the program."""
        self._say({"tell": line})

    def close(self) -> None:
        """The program's input closed, and the program waited for."""
        with contextlib.suppress(Exception):
            if self.p.stdin:
                self.p.stdin.close()
            self.p.wait(timeout=10)


# ── the loop ───────────────────────────────────────────────────────────────────────────────────────────────────────


def scorer_hash(s: dict[str, Any]) -> str:
    """The scoring code a study's trials are measured by: the harness's code and the baseline system's adapter file,
    by behaviour (_codeid). Checked before every trial: a scorer changed mid-study stops it."""
    from evaluation_harness._adapter import load_adapter  # noqa: PLC0415
    from evaluation_harness._codeid import file_sha256  # noqa: PLC0415
    from evaluation_harness._fingerprint import harness_code_sha256  # noqa: PLC0415

    p, cfg = system_of(s["baseline"]["system"])
    adapter_path = load_adapter(cfg.get("adapter"), p)[3]
    return hashlib.sha256(
        (harness_code_sha256() + ((file_sha256(adapter_path) or "") if adapter_path else "")).encode()
    ).hexdigest()


def stop_reason(goal: str, sid: str, started: float, start_hash: str) -> str | None:
    """Why the study stops now, or None: the spec, a file it freezes or the scorer changed, a stop asked for, trials,
    dollars, wall time, patience."""
    from evaluation_harness import _spend  # noqa: PLC0415

    s, st = spec(goal, sid), state(goal, sid)
    if frozen_hash(s, goal, sid) != start_hash:
        return "the spec or a file it freezes changed"
    if (st["start"] or {}).get("scorer_sha256") not in (None, scorer_hash(s)):
        return "the scoring code changed (the harness or the baseline's adapter)"
    if st["status"] == "stopping":
        return "stopped (study-stop)"
    stop = s.get("stop") or {}
    if stop.get("trials") and len(st["trials"]) >= int(stop["trials"]):
        return f"{stop['trials']} trial(s)"
    left = _spend.left()
    if left is not None and left <= 0:
        return "the dollar cap is spent"
    if stop.get("wall_h") and time.time() - started >= float(stop["wall_h"]) * 3600:
        return f"{stop['wall_h']} h of wall time"
    pat = stop.get("patience")
    if pat:
        since = 0
        for t in st["trials"]:
            since = 0 if t.get("outcome") == "kept" else since + 1
        if since >= int(pat):
            return f"{pat} trial(s) without a kept one"
    return None


def open_study(goal: str, sid: str) -> dict[str, Any]:
    """Open the study's round and append `start`; the cap is the least of the spec's `stop.usd` and the job's."""
    from evaluation_harness import _rounds  # noqa: PLC0415

    s = spec(goal, sid)
    found = problems(goal, sid, s)
    if found:
        _common.die(f"study {goal}/{sid}: " + "; ".join(found), "invalid-file")
    system_of(s["baseline"]["system"])  # refused now when it does not exist
    usd = (s.get("stop") or {}).get("usd")
    if usd is not None:
        own = _common.env_float("EVAL_MAX_COST_USD")
        os.environ["EVAL_MAX_COST_USD"] = str(min(float(usd), own) if own is not None else float(usd))
    rid = _rounds.next_id(goal)
    _rounds.save(
        {
            "round_id": rid,
            "goal": goal,
            "dataset_id": s["dataset"],
            "from": None,
            "hypothesis": str(s.get("directions") or f"study {sid}"),
            "changes": [],
            "baseline": None,
            "budget_usd": None,
            "harness": _rounds.harness_now(),
            "carried": [s["baseline"]["system"]],
            "status": "open",
            "opened_at": _common.now(),
            "study": sid,
            "retired": [],
        }
    )
    return append(
        goal,
        sid,
        {
            "event": "start",
            "round": rid,
            "baseline": s["baseline"]["system"],
            "spec_sha256": frozen_hash(s, goal, sid),
            "scorer_sha256": scorer_hash(s),
            "references_sha256": _references(s),
            "instruction": s.get("directions"),
        },
    )


def _references(s: dict[str, Any]) -> str | None:
    from evaluation_harness import _fingerprint  # noqa: PLC0415

    with contextlib.suppress(Exception):
        return _fingerprint.references_digest(_common.ROOT, f"gold/{s['dataset']}", _common.DATA)
    return None


def close_study(goal: str, sid: str, reason: str) -> dict[str, Any]:
    """Append `end` and close the study's round, its dropped trials retired with their reasons."""
    from evaluation_harness import _rounds  # noqa: PLC0415

    st = state(goal, sid)
    kept = [t for t in st["trials"] if t.get("outcome") == "kept"]
    summary = (
        f"{len(st['trials'])} trial(s), {len(kept)} kept; "
        + (
            f"best: {kept[-1]['config_id']} ({kept[-1].get('hypothesis')})"
            if kept
            else "nothing beat the baseline"
        )
        + ". Research: no evidence; study-confirm on a test set is the one step that gives it."
    )
    ev = append(
        goal, sid, {"event": "end", "reason": reason, "summary": summary, "spent_usd": st["spent_usd"]}
    )
    rnd = _rounds.find(goal, st["round"]) if st["round"] else None
    if rnd is not None and rnd.get("status") != "closed":
        rnd["retired"] = [
            *(rnd.get("retired") or []),
            *({"config_id": t["config_id"], "reason": t.get("reason") or t.get("outcome"), "at": _common.now()}
              for t in st["trials"] if t.get("outcome") != "kept"),
        ]  # fmt: skip
        rnd["status"] = "closed"
        rnd["closed_at"] = _common.now()
        rnd["conclusion"] = {"text": summary, "promoted_run": None}
        _rounds.save(rnd)
    return ev


def run_loop(goal: str, sid: str, sampler: Any) -> str:
    """The ask/tell loop for the grid and command samplers, until a stop rule fires. Returns the reason."""
    start = next(e for e in events(goal, sid) if e.get("event") == "start")
    started = time.time()
    while True:
        why = stop_reason(goal, sid, started, start["spec_sha256"])
        if why:
            return why
        st = state(goal, sid)
        k = len(st["trials"]) + 1
        shown: list = []
        if sampler == "grid":
            proposal = grid_next(goal, sid)
        else:
            seen = sampler_state(goal, sid)
            shown = [{"item_id": x["item_id"], "sha256": x.get("sha256")} for x in seen["weakest_items"]]
            proposal = sampler.ask(seen)
        if proposal is None:
            return "the space is exhausted" if sampler == "grid" else "the sampler stopped"
        group = proposal.pop("group", None)
        print(f"  trial {k}: {proposal.get('hypothesis') or proposal.get('params')}", flush=True)
        line = trial(goal, sid, k, proposal, shown=shown)
        if group:
            line["group"] = group
            _tag_group(goal, sid, k, group)
        print(f"    {line['outcome']}: {line['reason']}", flush=True)
        if sampler != "grid":
            sampler.tell(line)


def _tag_group(goal: str, sid: str, k: int, group: str) -> None:
    """The grid's group of trial k, appended (the trial line itself is written once)."""
    append(goal, sid, {"event": "group", "k": k, "group": group})


def mark_interrupted(goal: str, sid: str) -> list[int]:
    """On resume: a trial whose system was written but whose line never was (the study stopped mid-trial) gets a line,
    failed and interrupted, so the numbering goes on after it. Returns those trials' numbers."""
    st = state(goal, sid)
    have = {t.get("k") for t in st["trials"]}
    out = []

    def number(q: Path) -> int | None:
        tail = q.stem[len(f"{sid}-t") :]
        return int(tail) if tail.isdigit() else None

    for p in sorted(_store.glob(folder(goal, sid), f"{sid}-t*.yaml"), key=lambda q: number(q) or 0):
        k = number(p)
        if k is None or k in have:
            continue
        append(goal, sid, {"event": "trial", "k": k, "config_id": f"{sid}-t{k}", "change": {"params": {}, "prompts": []},
                           "outcome": "failed", "reason": "interrupted: the study stopped during this trial", "runs": [],
                           "cost_usd": 0, "shown": []})  # fmt: skip
        out.append(k)
    return out


def new_ask_id() -> str:
    """An ask's id."""
    return secrets.token_hex(4)


def of_goal(goal: str) -> list[dict[str, Any]]:
    """A goal's studies as its page and `evh goals` show them: each one's state, its trials in rows, its confirms."""
    out = []
    base = root() / goal
    for p in sorted(_store.glob(base, "*.events.jsonl")) if _store.is_dir(base) else []:
        sid = p.name[: -len(".events.jsonl")]
        st = state(goal, sid)
        rows = []
        for t in st["trials"]:
            ch = t.get("change") or {}
            what = ", ".join(f"{k} = {v!r}" for k, v in (ch.get("params") or {}).items())
            what = "; ".join(
                x for x in (what, ", ".join(f"prompt {n}" for n in ch.get("prompts") or [])) if x
            )
            rows.append({
                "k": t.get("k"), "hypothesis": t.get("hypothesis") or "", "change": what or ("imported" if t.get("imported") else ""),
                "outcome": t.get("outcome"), "reason": t.get("reason") or "",
                "delta": (t.get("vs_best") or {}).get("delta"), "cost_usd": t.get("cost_usd"),
            })  # fmt: skip
        out.append({
            "study": sid, "status": st["status"], "round": st["round"], "baseline": st["baseline"], "rows": rows,
            "spent_usd": st["spent_usd"], "end": (st["end"] or {}).get("reason"),
            "confirms": [c for c in st["confirms"] if c.get("phase") == "verdict"],
        })  # fmt: skip
    return out
