"""What a judge scorer is made of and what hangs on it (RFC-032 step 7): the views the scorer-* operations answer, read
through the layout in model/scorers. A view never carries a list that grows with the data (a judging set's items, a
validation report's per-article numbers, the verdicts, the records): it carries their count. The people's checks of the
judges are part of scorer-show (`checks`), not a view of their own: a report's numbers differ by source, so what is
common to them (who rated, how many articles, which judges, how many records, whether the report is of this scorer as
it is) is counted here and the numbers stay in the report."""

from __future__ import annotations

import json
from typing import Any

from evaluation_harness import _store
from evaluation_harness.model.dataset_views import rel, where
from evaluation_harness.model.entity import Problem
from evaluation_harness.model.scorers import (
    SCORER,
    checks_of,
    current_sha256,
    judged_scores,
    judging_set_file,
    judging_sets_of,
    summary_file,
    verdicts_dir,
)


def _loaded(scorer_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """The scorer as judge-score reads it (a judge that names a system given that system's settings) and why it does not
    load: one of the two."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    try:
        return js.load_scorer(SCORER.path(scorer_id)), None
    except SystemExit as exc:
        return None, str(exc.code).partition("): ")[2] or str(exc.code)


def _validation(sc: dict[str, Any] | None) -> list[str]:
    """Why the scorer is not validated (judge-score's gate); empty when it is."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    if sc is None:
        return ["the scorer does not load"]
    try:
        return js.validation_problems(sc)
    except SystemExit as exc:
        return [str(exc.code).partition("): ")[2] or str(exc.code)]


def _judges(rec: dict[str, Any], sc: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Each judge: its id, the model and family it is called as, the system it names, and its fingerprint (what its
    verdicts are stored under). From the loaded scorer when it loads, else as written."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    for j in (sc or rec).get("judges") or []:
        p = j.get("params") or {}
        out.append(
            {
                "judge": j.get("id"),
                "model": p.get("model"),
                "family": p.get("family"),
                "system": j.get("system"),
                "fingerprint": js.judge_fingerprint(j) if sc is not None else None,
            }
        )
    return out


def _made(made: list[dict[str, Any]], now: str | None) -> dict[str, int]:
    """How many judged scores the scorer made, and how many of them with another version of it."""
    return {"judged_scores": len(made), "other_version": sum(1 for s in made if s["sha256"] != now)}


def _read(path: Any) -> dict[str, Any] | None:
    try:
        v = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def list_scorers() -> list[dict[str, Any]]:
    """Every scorer: its mode, its judges, whether it is validated, how many judged scores it made and how many of those
    were made with another version of it (a hash other than its file's now)."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    by: dict[str, list[dict[str, Any]]] = {}
    for s in judged_scores():
        by.setdefault(str(s["scorer"]), []).append(s)
    out: list[dict[str, Any]] = []
    for sid in SCORER.ids():
        try:
            rec = SCORER.get(sid)
        except Problem as exc:
            out.append({"scorer": sid, "file": where(SCORER, sid), "problem": str(exc)})
            continue
        sc, why = _loaded(sid)
        out.append(
            {
                "scorer": sid,
                "mode": js.mode_of(rec),
                "dataset": rec.get("dataset_id"),
                "supersedes": rec.get("supersedes"),
                "judges": _judges(rec, sc),
                "validated": not _validation(sc),
                **_made(by.get(sid, []), current_sha256(sid)),
                "problem": why,
                "file": where(SCORER, sid),
            }
        )
    return out


def _judging_sets(scorer_id: str, made: list[dict[str, Any]], now: str | None) -> list[dict[str, Any]]:
    """The judging sets the scorer judged over (it has verdicts, a summary or a judged score of them), each with what
    was stored of its pass counted."""
    vroot = verdicts_dir(scorer_id)
    out: list[dict[str, Any]] = []
    for sid in sorted({*judging_sets_of(scorer_id), *(str(s["set"]) for s in made)}):
        ds = _read(judging_set_file(sid)) or {}
        sf = summary_file(scorer_id, sid)
        summ = _read(sf)
        out.append(
            {
                "set": sid,
                "dataset": ds.get("dataset_id"),
                "arms": len(ds.get("arms") or []),
                "items": len(ds.get("items") or []),
                "verdicts": sum(1 for _ in _store.glob(vroot / sid, "*/*.json"))
                if _store.is_dir(vroot / sid)
                else 0,
                "judged_scores": sum(1 for s in made if s["set"] == sid),
                "summary": None
                if summ is None
                else {
                    "file": rel(sf),
                    "label": summ.get("label"),
                    "validated": summ.get("validated"),
                    "partial": summ.get("partial"),
                    "items_scored": summ.get("items_scored"),
                    "scorer_sha256": summ.get("scorer_sha256"),
                    "current": summ.get("scorer_sha256") == now,
                },
            }
        )
    return out


def show_scorer(scorer_id: str) -> dict[str, Any]:
    """One scorer: its record, its judges with their fingerprints, its validation (the block, and why it passes the gate
    or not), the judging sets it judged with their verdicts and summaries counted, the runs it judged, and the people's
    checks of its judges."""
    rec = SCORER.get(scorer_id)
    sc, why = _loaded(scorer_id)
    now = current_sha256(scorer_id)
    made = judged_scores(scorer_id)
    problems = _validation(sc)
    return {
        "scorer": scorer_id,
        "file": where(SCORER, scorer_id),
        "record": rec,
        "sha256": now,
        "problem": why,
        "judges": _judges(rec, sc),
        "validation": {"validated": not problems, "problems": problems, "block": rec.get("validation")},
        **_made(made, now),
        "judging_sets": _judging_sets(scorer_id, made, now),
        "runs": [
            {
                "run": s["run"],
                "system": s["system"],
                "set": s["set"],
                "scorer_sha256": s["sha256"],
                "current": s["sha256"] == now,
            }
            for s in made
        ],
        "checks": checks_of(scorer_id),
    }
