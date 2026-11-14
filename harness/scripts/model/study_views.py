"""What a study shows (RFC-032 step 7): a goal's studies as its page and `evh goals` print them, and the study-list and
study-show operations' answers, each read from the study's log through the layout in model/studies, from the project's
data or another data root (a deployment's copy of it, which the catalog reads)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness.model import studies as ms


def _rows(trials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each trial a row: what it changed, why, how it was decided, against the best so far, at what cost."""
    out = []
    for t in trials:
        ch = t.get("change") or {}
        what = ", ".join(f"{k} = {v!r}" for k, v in (ch.get("params") or {}).items())
        what = "; ".join(x for x in (what, ", ".join(f"prompt {n}" for n in ch.get("prompts") or [])) if x)
        out.append(
            {
                "k": t.get("k"),
                "hypothesis": t.get("hypothesis") or "",
                "change": what or ("imported" if t.get("imported") else ""),
                "outcome": t.get("outcome"),
                "reason": t.get("reason") or "",
                "delta": (t.get("vs_best") or {}).get("delta"),
                "cost_usd": t.get("cost_usd"),
            }
        )
    return out


def of_goal(goal: str, data: Path | None = None) -> list[dict[str, Any]]:
    """A goal's studies as its page and `evh goals` show them: each one's state, its trials in rows, its confirms, and
    whether its text is hidden (a public page shows no hypothesis then). A study with no log yet (a spec nothing has
    run) is not shown."""
    out = []
    for rid in ms.ids(goal, data, check_format=False):
        sid = rid.split("/", 1)[1]
        if not _store.is_file(ms.log_path(goal, sid, data)):
            continue
        st = ms.state(goal, sid, data)
        out.append(
            {
                "study": sid,
                "status": st["status"],
                "round": st["round"],
                "baseline": st["baseline"],
                "rows": _rows(st["trials"]),
                "spent_usd": st["spent_usd"],
                "end": (st["end"] or {}).get("reason"),
                "confirms": [c for c in st["confirms"] if c.get("phase") == "verdict"],
                "text_hidden": ms.hidden(goal, sid, data),
            }
        )
    return out


def row(goal: str, sid: str, data: Path | None = None) -> dict[str, Any]:
    """A study as a list shows it: where it stands, its trials and what it spent."""
    st = ms.state(goal, sid, data)
    spec = ms.spec(goal, sid, data)
    return {
        "study": f"{goal}/{sid}",
        "status": st["status"],
        "dataset": spec.get("dataset"),
        "measure": spec.get("measure"),
        "round": st["round"],
        "baseline": st["baseline"],
        "trials": len(st["trials"]),
        "kept": sum(1 for t in st["trials"] if t.get("outcome") == "kept"),
        "spent_usd": st["spent_usd"],
        "confirms": len(st["confirms"]),
    }


def list_studies(goal: str, data: Path | None = None) -> list[dict[str, Any]]:
    """The goal's studies."""
    return [row(goal, i.split("/", 1)[1], data) for i in ms.ids(goal, data)]


def show_study(goal: str, sid: str, data: Path | None = None) -> dict[str, Any]:
    """One study: its spec as written, where it stands as its log says (trials in rows, the best so far, an open ask,
    how it ended), its confirmations and where its parts are."""
    from evaluation_harness.model.dataset_views import rel  # noqa: PLC0415

    st = ms.state(goal, sid, data)
    return {
        "study": f"{goal}/{sid}",
        "file": rel(ms.spec_path(goal, sid, data)),
        "spec": ms.spec(goal, sid, data),
        "status": st["status"],
        "round": st["round"],
        "baseline": st["baseline"],
        "spent_usd": st["spent_usd"],
        "rows": _rows(st["trials"]),
        "best": (st["best"] or {}).get("config_id"),
        "open_ask": (st["open_ask"] or {}).get("ask_id"),
        "end": (st["end"] or {}).get("reason"),
        "summary": (st["end"] or {}).get("summary"),
        "confirms": st["confirms"],
        "trial_systems": [p.stem for p in ms.trial_systems(goal, sid, data)],
    }
