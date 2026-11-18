"""What a judge scorer is made of and what hangs on it (RFC-032 step 7): the views the scorer-* operations answer, read
through the layout in model/scorers. A view never carries a list that grows with the data (a judging set's items, a
validation report's per-article numbers, the verdicts, the records): it carries their count. The people's checks of the
judges are part of scorer-show (`checks`), not a view of their own: a report's numbers differ by source, so what is
common to them (who rated, how many articles, which judges, how many records, whether the report is of this scorer as
it is) is counted here and the numbers stay in the report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness.model.dataset_views import rel, where
from evaluation_harness.model.entity import Problem
from evaluation_harness.model.runs import root as runs_root
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


def _loaded(scorer_id: str, data: Path | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """The scorer as judge-score reads it (a judge that names a system given that system's settings) and why it does not
    load: one of the two."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    try:
        return js.load_scorer(SCORER.under(data).path(scorer_id), data), None
    except SystemExit as exc:
        return None, str(exc.code).partition("): ")[2] or str(exc.code)


def _validation(sc: dict[str, Any] | None, data: Path | None = None) -> list[str]:
    """Why the scorer is not validated (judge-score's gate); empty when it is."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    if sc is None:
        return ["the scorer does not load"]
    try:
        return js.validation_problems(sc, runs_dir=runs_root(data=data))
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


def _record(scorers: Any, scorer_id: str, check_format: bool) -> dict[str, Any]:
    """The scorer's record; with `check_format` False a tree of another format is read as it is (the catalog reads
    copies), a record that is not a mapping refused as Problem."""
    if check_format:
        return scorers.get(scorer_id)
    import yaml  # noqa: PLC0415

    try:
        doc = yaml.safe_load(_store.read_text(scorers.path(scorer_id), encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise Problem(f"{scorer_id}: not readable as YAML ({exc})", "invalid-file") from None
    if not isinstance(doc, dict):
        raise Problem(f"{scorer_id}: not a mapping of keys", "invalid-file")
    return doc


def list_scorers(data: Path | None = None, check_format: bool = True) -> list[dict[str, Any]]:
    """Every scorer: its mode, its judges, whether it is validated, how many judged scores it made and how many of those
    were made with another version of it (a hash other than its file's now). `data`: another data directory than the
    project's (the catalog reads a deployment's copy)."""
    from evaluation_harness import judge_score as js  # noqa: PLC0415

    scorers = SCORER.under(data)
    by: dict[str, list[dict[str, Any]]] = {}
    for s in judged_scores(data=data):
        by.setdefault(str(s["scorer"]), []).append(s)
    out: list[dict[str, Any]] = []
    for sid in scorers.ids(check_format=check_format):
        try:
            rec = _record(scorers, sid, check_format)
        except Problem as exc:
            out.append({"scorer": sid, "file": where(scorers, sid), "problem": str(exc)})
            continue
        sc, why = _loaded(sid, data)
        out.append(
            {
                "scorer": sid,
                "mode": js.mode_of(rec),
                "dataset": rec.get("dataset_id"),
                "supersedes": rec.get("supersedes"),
                "judges": _judges(rec, sc),
                "validated": not _validation(sc, data),
                **_made(by.get(sid, []), current_sha256(sid, data)),
                "problem": why,
                "file": where(scorers, sid),
            }
        )
    return out


def _judging_sets(
    scorer_id: str, made: list[dict[str, Any]], now: str | None, data: Path | None = None
) -> list[dict[str, Any]]:
    """The judging sets the scorer judged over (it has verdicts, a summary or a judged score of them), each with what
    was stored of its pass counted."""
    vroot = verdicts_dir(scorer_id, data)
    out: list[dict[str, Any]] = []
    for sid in sorted({*judging_sets_of(scorer_id, data), *(str(s["set"]) for s in made)}):
        ds = _read(judging_set_file(sid, data)) or {}
        sf = summary_file(scorer_id, sid, data)
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


def _verdict_cells(v: dict[str, Any], arm_ids: list[str]) -> list[dict[str, Any]]:
    """One stored verdict as a cell per arm it judged: what the judge said of that arm, and its reason."""
    why = v.get("why")
    if v.get("why_withheld"):
        status = "withheld"
    elif v.get("why_missing"):
        status = "missing"
    elif "why" in v:
        status = "given"
    else:
        status = "not asked"
    out = []
    for i, arm in enumerate(arm_ids):
        if v.get("scores") is not None:
            said: Any = v["scores"][i]
        elif v.get("best") is not None:
            said = "best" if i + 1 in v["best"] else "not best"
        elif v.get("better") is not None:
            said = "tie" if v["better"] == "tie" else ("better" if v["better"] == i + 1 else "worse")
        else:
            said = None
        out.append(
            {
                "arm": arm,
                "position": i + 1,
                "said": said,
                "why": (why[i] if isinstance(why, list) and i < len(why) else why)
                if status == "given"
                else None,
                "why_status": status,
            }
        )
    return out


def verdicts(
    scorer_id: str,
    set: str | None = None,
    item: str | None = None,
    arm: str | None = None,
    judge: str | None = None,
    pass_name: str = "primary",  # noqa: S107 — a judging pass, not a password
    order: str = "low",
    limit: int = 20,
    offset: int = 0,
    data: Path | None = None,
) -> dict[str, Any]:
    """The judges' verdicts with their reasons (RFC-034 §5), one row per arm a verdict judged. `order`: `low` puts the
    lowest graded scores first (what failed, and why), `item` keeps the judging set's order. A page of `limit` rows
    from `offset`, with the total: the list grows with the data."""
    if order not in ("low", "item"):
        raise Problem(f"order must be low or item, got {order!r}", "bad-argument")
    if pass_name not in ("primary", "position", "noise"):
        raise Problem(f"pass must be primary, position or noise, got {pass_name!r}", "bad-argument")
    vroot = verdicts_dir(scorer_id, data)
    sets = [set] if set else judging_sets_of(scorer_id, data)
    if not sets:
        raise Problem(
            f"scorer {scorer_id} has judged nothing yet: evh judge-score --scorer {scorer_id}", "not-found"
        )
    rows: list[dict[str, Any]] = []
    for sid in sets:
        man = _read(judging_set_file(sid, data))
        if man is None:
            raise Problem(f"no judging set {sid} of scorer {scorer_id}", "not-found")
        by_item = {it["item_id"]: it for it in man.get("items") or []}
        for f in sorted(_store.glob(vroot / sid, f"*/*.{pass_name}.b*.json")):
            v = _read(f)
            if not v or (item and v.get("item_id") != item) or (judge and v.get("judge") != judge):
                continue
            it = by_item.get(str(v.get("item_id")))
            if it is None:
                continue
            arm_ids = it["position" if pass_name == "position" else "primary"][int(v["block"])]  # noqa: S105 — a judging pass
            for c in _verdict_cells(v, arm_ids):
                if arm and c["arm"] != arm:
                    continue
                rows.append({"set": sid, "item": v["item_id"], "judge": v["judge"], "pass": pass_name,
                             "block": v["block"], **c})  # fmt: skip
    if order == "low":
        # Graded scores lowest first; a pick's or a pair's words, and unparsed verdicts, after them in set order.
        rows.sort(key=lambda r: (0, r["said"]) if isinstance(r["said"], (int, float)) else (1, 0))
    return {
        "scorer": scorer_id,
        "pass": pass_name,
        "order": order,
        "total": len(rows),
        "explained": sum(1 for r in rows if r["why_status"] == "given"),
        "offset": offset,
        "rows": rows[offset : offset + max(0, limit)],
    }


def show_scorer(scorer_id: str, data: Path | None = None, check_format: bool = True) -> dict[str, Any]:
    """One scorer: its record, its judges with their fingerprints, its validation (the block, and why it passes the gate
    or not), the judging sets it judged with their verdicts and summaries counted, the runs it judged, and the people's
    checks of its judges. `data`: another data directory than the project's (the catalog reads a deployment's copy)."""
    scorers = SCORER.under(data)
    rec = _record(scorers, scorer_id, check_format)
    sc, why = _loaded(scorer_id, data)
    now = current_sha256(scorer_id, data)
    made = judged_scores(scorer_id, data)
    problems = _validation(sc, data)
    return {
        "scorer": scorer_id,
        "file": where(scorers, scorer_id),
        "record": rec,
        "sha256": now,
        "problem": why,
        "judges": _judges(rec, sc),
        "validation": {"validated": not problems, "problems": problems, "block": rec.get("validation")},
        **_made(made, now),
        "judging_sets": _judging_sets(scorer_id, made, now, data),
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
        "checks": checks_of(scorer_id, data),
    }
