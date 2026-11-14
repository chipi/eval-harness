"""Studies (RFC-032 step 7): a study's record, its log, its trials' systems and its confirmations, with one table of where
each lives, read through a data root (`under`) so the catalog reads a study where its data directory is, a deployment's
copy of the project's included. Nothing outside the model builds these paths.

A study is data/studies/<goal>/<study_id>.yaml (its spec, written once by a person or an agent); its parts are beside it:

    its log                 <study_id>.events.jsonl          start, ask, trial, end, confirm, one JSON line each
    its folder              <study_id>/
    a trial's system        <study_id>/<study_id>-t<k>.yaml  written once, found by `_common.system_files`
    a confirmation's items  <study_id>/confirm/t<k>-on-<test set>.items, and its two systems' files beside them

A study's state is read from its log, never stored apart (RFC-029).
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from evaluation_harness import _common, _store
from evaluation_harness.model.entity import Entity

_PARTS = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
LOG = ".events.jsonl"
#: The events a study's log holds.
EVENTS = ("start", "ask", "trial", "group", "stop", "end", "confirm")

#: Its id is `<goal>/<study_id>`. The spec names no goal and no id of its own: its place is both.
STUDY = Entity(
    name="study",
    plural="studies",
    folder="studies",
    id_field="",
    parent_field="goal",
    schema="study.schema.json",
    id_pattern=_PARTS,
    editable=False,
)


def root(data: Path | None = None) -> Path:
    """data/studies/."""
    return STUDY.under(data).base()


def spec_path(goal: str, sid: str, data: Path | None = None) -> Path:
    """A study's spec."""
    return root(data) / goal / f"{sid}.yaml"


def log_path(goal: str, sid: str, data: Path | None = None) -> Path:
    """A study's log."""
    return root(data) / goal / f"{sid}{LOG}"


def folder(goal: str, sid: str, data: Path | None = None) -> Path:
    """A study's own folder: its trials' systems, its confirmations."""
    return root(data) / goal / sid


def trial_path(goal: str, sid: str, k: int, data: Path | None = None) -> Path:
    """Trial k's system."""
    return folder(goal, sid, data) / f"{sid}-t{k}.yaml"


def confirm_dir(goal: str, sid: str, data: Path | None = None) -> Path:
    """A study's confirmations: each one's item list and its systems."""
    return folder(goal, sid, data) / "confirm"


def confirm_items(goal: str, sid: str, k: int, test: str, data: Path | None = None) -> Path:
    """The items a confirmation of trial k on a test set runs, one id a line."""
    return confirm_dir(goal, sid, data) / f"t{k}-on-{test}.items"


def trial_systems(goal: str, sid: str, data: Path | None = None) -> list[Path]:
    """The trials' system files written, by trial number."""
    base = folder(goal, sid, data)

    def number(p: Path) -> int:
        tail = p.stem[len(f"{sid}-t") :]
        return int(tail) if tail.isdigit() else 0

    return sorted(_store.glob(base, f"{sid}-t*.yaml") if _store.is_dir(base) else [], key=number)


def system_files(data: Path | None = None) -> list[Path]:
    """Every study's systems, its trials' and its confirmations' (the files `_common.system_files` adds to the project's)."""
    base = root(data)
    if not _store.is_dir(base):
        return []
    found = [*_store.glob(base, "*/*/*-t*.yaml"), *_store.glob(base, "*/*/confirm/*.yaml")]
    return sorted(f for f in found if _store.is_file(f))


def ids(goal: str | None = None, data: Path | None = None, check_format: bool = True) -> list[str]:
    """Every study's id (`<goal>/<study_id>`), sorted; one goal's with `goal`."""
    found = STUDY.under(data).ids(check_format=check_format)
    return [i for i in found if goal is None or i.split("/", 1)[0] == goal]


def resolve(name: str, data: Path | None = None) -> tuple[str, str]:
    """`<goal>/<study_id>`, or a study id one goal has, as (goal, study_id); refused otherwise."""
    if "/" in name:
        goal, sid = name.split("/", 1)
        if _store.is_file(spec_path(goal, sid, data)):
            return goal, sid
        _common.die(f"no study {name} (data/studies/{goal}/{sid}.yaml)", "not-found")
    hits = [i.split("/", 1)[0] for i in ids(data=data) if i.split("/", 1)[1] == name]
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


def spec(goal: str, sid: str, data: Path | None = None) -> dict[str, Any]:
    """The spec, as written."""
    doc = yaml.safe_load(_store.read_text(spec_path(goal, sid, data), encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        _common.die(f"{spec_path(goal, sid, data)}: a mapping", "invalid-file")
    return doc


def events(goal: str, sid: str, data: Path | None = None) -> list[dict[str, Any]]:
    """The log's events, in order (a torn last line is not an event)."""
    p = log_path(goal, sid, data)
    out = []
    for line in (_store.read_text(p, encoding="utf-8") if _store.is_file(p) else "").splitlines():
        with contextlib.suppress(ValueError):
            ev = json.loads(line)
            if isinstance(ev, dict):
                out.append(ev)
    return out


def state(goal: str, sid: str, data: Path | None = None) -> dict[str, Any]:
    """The study as its log says: status, round, trials, the best so far, spent, the open ask."""
    evs = events(goal, sid, data)
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


def shown(goal: str, data: Path | None = None) -> set[Any]:
    """Every item shown to a sampler in any study of the goal, by id and by content (a test item with a shown item's
    bytes is the same text)."""
    out: set[Any] = set()
    for rid in ids(goal, data):
        for ev in events(goal, rid.split("/", 1)[1], data):
            for x in ev.get("shown") or []:
                out |= {x.get("item_id"), x.get("sha256")} - {None}
    return out


def confirms(data: Path | None = None, check_format: bool = True) -> list[dict[str, Any]]:
    """The confirm lines of every study's log, each with the study's id (`study`; none before studies exist)."""
    out: list[dict[str, Any]] = []
    for rid in ids(data=data, check_format=check_format):
        goal, sid = rid.split("/", 1)
        out += [{**e, "study": sid} for e in events(goal, sid, data) if e.get("event") == "confirm"]
    return out


def hidden(goal: str, sid: str, data: Path | None = None) -> bool:
    """Whether a study was run or confirmed on a dataset whose text is hidden (RFC-019 §4): its validation dataset, or a
    test set it was confirmed on. What an agent wrote of its trials may quote the items it was shown."""
    from evaluation_harness._visibility import hidden as dataset_hidden  # noqa: PLC0415
    from evaluation_harness.model.datasets import DATASET  # noqa: PLC0415

    names: list[Any] = []
    with contextlib.suppress(OSError, ValueError, yaml.YAMLError, SystemExit):
        names.append(spec(goal, sid, data).get("dataset"))
    names += [e.get("test") for e in events(goal, sid, data) if e.get("event") == "confirm"]
    base = DATASET.under(data).base()
    return any(dataset_hidden(n, base) for n in names)


def problems(rid: str, data: Path | None = None) -> list[dict[str, Any]]:
    """What is wrong with the study's spec against its schema; [] when it holds. (The spec names neither its goal nor
    its id, so the entity's own check of them is not made.)"""
    import jsonschema  # noqa: PLC0415
    from evaluation_harness import _settings_form  # noqa: PLC0415

    ent = STUDY.under(data)
    return [
        _settings_form._said(e)
        for e in sorted(
            jsonschema.Draft202012Validator(ent.schema_doc()).iter_errors(ent.get(rid)),
            key=lambda e: list(e.path),
        )
    ]
