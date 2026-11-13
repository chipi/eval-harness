"""A sealed side of a split (the fleet's feedback 29): held out until a candidate is named in advance.

    evh dataset-split triage_v1 --split-by time --key created_at --at 2026-11-07T00:00:00Z --seal
    evh dataset-unseal triage_v1_test --system candidate_v3 --reason "the tuned filter, frozen"

`dataset-split --seal` writes `sealed` on the test side's record: when, and a digest of the open (validation) side's
items as they were then, so `validate` can say the open side was not changed to fit what the sealed one holds. A
sealed dataset refuses every run, score and label written onto it (run, rescore, judge-score, the label and
reference commands) unless the system doing it is named by an `unsealed` entry: `dataset-unseal` adds one, only for a
system whose hypothesis (ADR-0025) is committed, and each entry is one look at the held-out side.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from evaluation_harness import _store
from evaluation_harness._common import die


def items_digest(items: list[dict[str, Any]]) -> str:
    """One sha256 over a dataset's items as they freeze it: id, bytes and where they come from, sorted by id."""
    keys = ("item_id", "source_path", "source_url", "source_sha256")
    body = sorted(({k: it.get(k) for k in keys} for it in items), key=lambda x: str(x["item_id"]))
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def record_of(dataset_id: str | None) -> dict[str, Any]:
    """A dataset's record, {} when there is none (a missing dataset is another command's refusal)."""
    from evaluation_harness._common import _paths  # noqa: PLC0415

    if not dataset_id:
        return {}
    path = _paths()["DATASETS"] / f"{dataset_id}.json"
    if not _store.is_file(path):
        return {}
    try:
        doc = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _opened_at(doc: dict[str, Any]) -> dict[str, str]:
    """{config_id: when it was first opened}: each unseal's candidate and the system its hypothesis is against."""
    out: dict[str, str] = {}
    for u in doc.get("unsealed") or []:
        if not isinstance(u, dict):
            continue
        for c in (u.get("config_id"), (u.get("hypothesis") or {}).get("against")):
            if c:
                out.setdefault(str(c), str(u.get("at") or ""))
    return out


def opened_for(doc: dict[str, Any]) -> set[str]:
    """The systems the unseals open a sealed side to: each candidate and what its hypothesis is against."""
    return set(_opened_at(doc))


def refuse_if_sealed(dataset_id: str | None, what: str, config_id: str | None = None) -> None:
    """Refuse `what` on a sealed dataset, unless `config_id` (a system's id) is one an unseal opened it to; with no
    system (a label or a reference, which every system is read against), unless it was unsealed at all. Nothing for any
    other."""
    doc = record_of(dataset_id)
    if not doc.get("sealed"):
        return
    if (config_id and config_id in opened_for(doc)) or (not config_id and opened_for(doc)):
        return
    named = sorted(opened_for(doc))
    die(
        f"{dataset_id} is sealed (held out at {doc['sealed'].get('at', '?')}): {what} is refused"
        + (f" for {config_id}" if config_id else "")
        + (f"; it is open to {', '.join(named)} only" if named else "")
        + ". Name the candidate first: commit its system with a hypothesis, then "
        f'evh dataset-unseal {dataset_id} --system <system_id> --reason "..."',
        "not-allowed",
    )


def problems(docs: dict[str, dict[str, Any]]) -> list[str]:
    """validate: each sealed side's open side still matches the digest taken when it was sealed."""
    out = []
    for i, d in sorted(docs.items()):
        s = d.get("sealed")
        if not isinstance(s, dict):
            continue
        other = s.get("open_side")
        if other and other in docs and s.get("open_sha256") != items_digest(docs[other].get("items") or []):
            out.append(
                f"datasets/{i}.json: sealed against {other} as it was at {s.get('at')}; {other}'s items have changed "
                "since (the open side must not be fitted to the held-out one)"
            )
        elif other and other not in docs:
            out.append(f"datasets/{i}.json: sealed against {other}, which is gone")
    return out


def runs_on_sealed(docs: dict[str, dict[str, Any]], runs: list[tuple[Any, dict[str, Any]]]) -> list[str]:
    """validate: a run on a sealed dataset by a system no unseal names, or started before its unseal."""
    out = []
    for d, m in runs:
        doc = docs.get(m.get("dataset_id") or "")
        if not doc or not doc.get("sealed"):
            continue
        when = _opened_at(doc)
        cid = m.get("config_id")
        if cid not in when:
            out.append(
                f"{getattr(d, 'name', d)}: a run of {cid} on sealed {m.get('dataset_id')}, which no unseal names"
            )
        elif str(m.get("created_at") or "") < when[cid]:
            out.append(
                f"{getattr(d, 'name', d)}: a run of {cid} on sealed {m.get('dataset_id')} from before its unseal"
            )
    return out
