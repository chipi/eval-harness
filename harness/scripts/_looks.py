"""The looks a test set allows (RFC-029): counted from the decisions written on it, each at a stricter level.

A test set is a dataset a goal declares with `role: test`, or the sealed side of a split. A look is a decision written
on it: a `dataset-unseal`, a `study-confirm`, or a promotion whose evidence was computed on it. Each carries a `look`
record: {key, number, level, set, harness}. One question is one look, whatever records it: its key is the set's items
digest, the two systems, the measure and the rule, and a decision whose key is already recorded reuses it.

Look k is tested one-sided at α·6/(π²k²) (α = 2.5%; 1.52%, 0.38%, 0.17%, ...; the sum over every look is α). Past the
protective limit (10, or a goal's `test_looks`), a look needs the person running the command to consent; an agent
cannot. Before 0.8.0 nothing counts: an unseal without a `look` record is prior use.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness.model.datasets import record_file

ALPHA = 0.025
LIMIT = 10


def level(k: int) -> float:
    """Look k's one-sided level: α·6/(π²k²)."""
    return ALPHA * 6 / (math.pi**2 * k * k)


def _record(dataset_id: str) -> dict[str, Any]:
    p = record_file(dataset_id)
    if not _store.is_file(p):
        return {}
    try:
        doc = json.loads(_store.read_text(p, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def test_role_goals(dataset_id: str) -> list[dict[str, Any]]:
    """The goals that declare this dataset with `role: test`."""
    out = []
    for g in _common.load_goals().values():
        for d in g.get("datasets") or []:
            if isinstance(d, dict) and d.get("dataset_id") == dataset_id and d.get("role") == "test":
                out.append(g)
    return out


def is_test_set(dataset_id: str | None) -> bool:
    """Whether a dataset is a test set: a goal's `role: test`, or a sealed side of a split."""
    if not dataset_id:
        return False
    return bool(_record(dataset_id).get("sealed")) or bool(test_role_goals(dataset_id))


def digest(dataset_id: str) -> str:
    """The set's items digest: what owns its looks (a run on part of it spends the same budget)."""
    from evaluation_harness import _seal  # noqa: PLC0415

    return _seal.items_digest(_record(dataset_id).get("items") or [])


def limit(dataset_id: str) -> int:
    """The protective limit: the smallest `test_looks` of the goals that test on the set, else 10."""
    ks = [int(g["test_looks"]) for g in test_role_goals(dataset_id) if isinstance(g.get("test_looks"), int)]
    return min(ks) if ks else LIMIT


def key(dataset_id: str, a: str, b: str, measure: str | None, rule: str) -> str:
    """One question on a set: its digest, the two systems, the measure, the rule."""
    body = json.dumps([digest(dataset_id), a, b, measure or "", rule], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def recorded(dataset_id: str) -> list[dict[str, Any]]:
    """Every look recorded on the set, oldest first: from its unseals, the baselines' evidence and studies' confirms."""
    d = digest(dataset_id)
    found: list[dict[str, Any]] = []
    for u in _record(dataset_id).get("unsealed") or []:
        if isinstance(u.get("look"), dict):
            found.append(
                {
                    **u["look"],
                    "what": f"dataset-unseal {u.get('config_id')}",
                    "actor": u.get("actor"),
                    "at": u.get("at"),
                }
            )
    from evaluation_harness import _baselines  # noqa: PLC0415

    for v in _baselines.all_versions():
        look = ((v.get("evidence") or {}).get("look")) if isinstance(v.get("evidence"), dict) else None
        if isinstance(look, dict) and look.get("set") == d:
            found.append(
                {
                    **look,
                    "what": f"run-promote {v.get('promoted_from')}",
                    "actor": v.get("actor"),
                    "at": v.get("promoted_at"),
                }
            )
    for c in _study_confirms():
        look = c.get("look")
        if isinstance(look, dict) and look.get("set") == d:
            found.append(
                {
                    **look,
                    "what": f"study-confirm {c.get('study')}",
                    "actor": c.get("actor"),
                    "at": c.get("at"),
                }
            )
    found.sort(key=lambda x: (int(x.get("number") or 0), str(x.get("at") or "")))
    return found


def _study_confirms() -> list[dict[str, Any]]:
    """The confirm lines of every study's log (RFC-029's studies; none before they exist)."""
    root = _common.DATA / "studies"
    out: list[dict[str, Any]] = []
    for p in _store.rglob(root, "*.events.jsonl") if _store.is_dir(root) else []:
        for line in _store.read_text(p, encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                ev = json.loads(line)
                if ev.get("event") == "confirm":
                    out.append({**ev, "study": p.name[: -len(".events.jsonl")]})
    return out


def prior_use(dataset_id: str) -> int:
    """Unseals made before looks were counted (no `look` record): shown beside the levels, never counted."""
    return sum(1 for u in _record(dataset_id).get("unsealed") or [] if not isinstance(u.get("look"), dict))


def next_number(dataset_id: str, k: str | None = None) -> tuple[int, bool]:
    """(the number a look with key `k` takes, whether it reuses a recorded one)."""
    seen: dict[str, int] = {}
    for x in recorded(dataset_id):
        seen.setdefault(str(x.get("key")), int(x.get("number") or 0))
    if k is not None and k in seen:
        return seen[k], True
    return len(seen) + 1, False


@contextlib.contextmanager
def taking(dataset_id: str, k: str, consent: bool = False):
    """A look on the set, under its lock (`dataset:<id>`, RFC-026) while the caller writes the record that carries
    it, so two commands on one clone never take one number. Yields the `look` record to store. Refused past the
    limit without the person's consent; an agent's consent is refused."""
    from evaluation_harness import _actor, _jobs  # noqa: PLC0415

    lock = f"dataset:{dataset_id}"
    held = lock in (os.environ.get("EVH_LOCKS") or "").split(",")
    ctx = (
        contextlib.nullcontext()
        if held
        else _jobs.holding([(lock, True)], f"pid {os.getpid()}", _jobs.say_waiting)
    )
    with ctx:
        number, reused = next_number(dataset_id, k)
        lim = limit(dataset_id)
        if not reused and number > lim:
            if not consent:
                _common.die(
                    f"{dataset_id} has had {number - 1} look(s), its limit is {lim}: look {number} would be tested at "
                    f"{level(number):.4%}. Fresh items are the way out; to look again anyway, the person running the "
                    "command passes --confirm-extra-look",
                    "not-allowed",
                )
            if _actor.actor().get("type") == "agent":
                _common.die(
                    "--confirm-extra-look is the person's own consent: an agent cannot give it (RFC-029)",
                    "not-allowed",
                )
        from evaluation_harness._version import __version__  # noqa: PLC0415

        yield {
            "key": k,
            "number": number,
            "level": level(number),
            "set": digest(dataset_id),
            "dataset_id": dataset_id,
            "harness": __version__,
            "reused": reused,
            "beyond_limit": number > lim,
        }


def summary(dataset_id: str) -> dict[str, Any]:
    """A set's looks: each recorded, the next number and level, the limit, prior use."""
    looks = recorded(dataset_id)
    n, _ = next_number(dataset_id)
    return {
        "dataset_id": dataset_id,
        "test_set": is_test_set(dataset_id),
        "looks": looks,
        "next": n,
        "next_level": level(n),
        "limit": limit(dataset_id),
        "prior_use": prior_use(dataset_id),
    }


def double_spent(dataset_id: str) -> list[tuple[int, list[str]]]:
    """Numbers two different keys took (two clones deciding at once): what validate V25 reports."""
    by: dict[int, set[str]] = {}
    for x in recorded(dataset_id):
        by.setdefault(int(x.get("number") or 0), set()).add(str(x.get("key")))
    return [(n, sorted(ks)) for n, ks in sorted(by.items()) if len(ks) > 1]


def said(dataset_id: str) -> str | None:
    """A test set's looks in one line, for its goals' pages and `evh goals`; None for any other dataset."""
    if not is_test_set(dataset_id):
        return None
    s = summary(dataset_id)
    taken = len({x.get("key") for x in s["looks"]})
    return (
        f"test set: {taken} look(s) of {s['limit']}; a decision here is look {s['next']}, one-sided at "
        f"{s['next_level']:.4%}"
        + (f"; used {s['prior_use']} time(s) before looks were counted" if s["prior_use"] else "")
        + " (evh looks)"
    )
