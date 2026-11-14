"""The judge scorers' operations (RFC-032 step 7): `evh scorer-list`, `scorer-show`, `scorer-new`, `scorer-set`, and the
resources under /api/v1/scorers. A scorer that has made judged scores is not changed (a new version is a new scorer, a
new id with `supersedes`); `scorer-set` refuses it, as `data-put` does. The judging itself is `evh judge-score`."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.datasets import _table
from evaluation_harness.ops.registry import Op

_SET = {
    "type": "object",
    "description": "fields to set, by dotted key; the command takes KEY=VALUE",
    "additionalProperties": True,
}
_UNSET = {"type": "array", "items": {"type": "string"}, "description": "fields to remove, by dotted key"}
_S = "evaluation_harness.ops.scorers"
_D = "evaluation_harness.ops.datasets"

OPS = (
    Op("scorer-list", "read", "every judge scorer: its mode, its judges, whether it is validated, the judged scores it made and how many of them with another version of it",
       "GET", "/scorers", f"{_S}:list_scorers", f"{_S}:say_scorers"),
    Op("scorer-show", "read", "one judge scorer: its record, judges, validation, the judging sets and runs it judged, its summaries, and the people's checks of its judges",
       "GET", "/scorers/{scorer}", f"{_S}:show_scorer", f"{_S}:say_scorer"),
    Op("scorer-new", "edit", "make a judge scorer (data/scorers/<id>.yaml), checked against its schema; a new version of one that judged is a new id with `supersedes`",
       "POST", "/scorers/{scorer}", f"{_S}:new_scorer", f"{_D}:say_saved", inputs={"set": _SET}, required=("set",)),
    Op("scorer-set", "edit", "change a judge scorer's fields, checked; its comments kept; refused once it has made judged scores",
       "PATCH", "/scorers/{scorer}", f"{_S}:set_scorer", f"{_D}:say_saved", inputs={"set": _SET, "unset": _UNSET}),
)  # fmt: skip


def list_scorers() -> dict[str, Any]:
    """Every scorer with its judges and what it made."""
    from evaluation_harness.model import scorer_views as v  # noqa: PLC0415

    return {"scorers": v.list_scorers()}


def show_scorer(scorer: str) -> dict[str, Any]:
    """The scorer: record, judges, validation, what it judged and the people's checks."""
    from evaluation_harness.model import scorer_views as v  # noqa: PLC0415

    return v.show_scorer(scorer)


def new_scorer(scorer: str, set: dict[str, Any], by: str) -> dict[str, Any]:
    """Make the scorer from its fields."""
    from evaluation_harness import _settings_form  # noqa: PLC0415
    from evaluation_harness.model.scorers import SCORER  # noqa: PLC0415

    return SCORER.save(
        scorer,
        _settings_form.set_values({"scorer_id": scorer, "kind": "judge"}, list(set.items()), []),
        by,
        new=True,
    )


def set_scorer(
    scorer: str, by: str, set: dict[str, Any] | None = None, unset: list[str] | None = None
) -> dict[str, Any]:
    """Change the scorer's fields."""
    from evaluation_harness.model.scorers import SCORER  # noqa: PLC0415

    return SCORER.patch(scorer, list((set or {}).items()), list(unset or []), by)


def say_scorers(r: dict[str, Any]) -> str:
    """scorer-list's answer as text: one scorer a line."""
    if not r["scorers"]:
        return "no judge scorers yet: evh scorer-new <id> --set dataset_id=<dataset> --set judges.0.id=<judge> ..."
    rows: list[tuple[str, ...]] = []
    for s in r["scorers"]:
        if "judged_scores" not in s:
            rows.append((s["scorer"], "", "does not read", "", s["problem"]))
            continue
        judges = ", ".join(f"{j['judge']} ({j['model']})" for j in s["judges"]) or "no judges"
        made = f"{s['judged_scores']} judged score(s)"
        if s["other_version"]:
            made += f", {s['other_version']} with another version"
        rows.append(
            (
                s["scorer"],
                s["mode"],
                "validated" if s["validated"] else "unvalidated",
                judges,
                made + (f"; does not load: {s['problem']}" if s["problem"] else ""),
            )
        )
    return _table(rows)


def say_scorer(r: dict[str, Any]) -> str:
    """scorer-show's answer as text: its judges, its validation, what it judged and the people's checks."""
    rec = r["record"]
    lines = [f"{r['scorer']}  {rec.get('mode') or 'grade'}  ({r['file']})"]
    if r["problem"]:
        lines.append(f"  does not load: {r['problem']}")
    if rec.get("supersedes"):
        lines.append(f"  supersedes   {rec['supersedes']}" + (f": {rec['why']}" if rec.get("why") else ""))
    lines.append(f"  sha256       {r['sha256']}")
    for j in r["judges"]:
        via = f" (system {j['system']})" if j["system"] else ""
        lines.append(f"  judge        {j['judge']}  {j['model']}  {j['family']}{via}  fp {j['fingerprint']}")
    v = r["validation"]
    lines.append(f"  validation   {'validated' if v['validated'] else 'not validated'}")
    lines += [f"    {p}" for p in v["problems"]]
    lines.append(
        f"  made         {r['judged_scores']} judged score(s)"
        + (f", {r['other_version']} with another version of it" if r["other_version"] else "")
    )
    for s in r["judging_sets"]:
        summ = s["summary"]
        lines.append(
            f"  judging set  {s['set']}: {s['arms']} arms, {s['items']} items, {s['verdicts']} verdicts, "
            f"{s['judged_scores']} judged score(s)"
            + (
                ""
                if summ is None
                else f"; summary {'of this version' if summ['current'] else 'of another version'}"
            )
        )
    for c in r["checks"]:
        judges = ", ".join(f"{j['judge']} {j['records']}" for j in c["judges"])
        lines.append(
            f"  checked by   {c['source']}: {c['articles'] or '?'} articles, {c['records']} records ({judges})"
            + ("" if c["report"] else "; no report")
            + ("" if c["current"] or not c["report"] else "; report of another version")
        )
    return "\n".join(lines)
