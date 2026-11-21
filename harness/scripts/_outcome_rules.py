"""The rule language that turns what happened after a record into a label (RFC-019, RFC-023): `evh
label-from-capture` reads it.

The mapping (YAML), a list of rules (or `rules:` holding one), tried in order against a record's outcome FIELDS
(flat names: a project's importer computes what the rules need, such as `issue_verdict` or `days_to_filing`); the
first that matches gives the item's label, or skips it. Each rule has any of:
  when:   {field: value or [values]}   every one must hold
  unless: {field: value or [values]}   none may hold
  exists: [field, ...]                 present and not null
  absent: [field, ...]                 missing or null
  range:  {field: {min: N, max: N}}    a number within bounds (either bound optional)
  min_age_days: N                      the record is at least N days older than the capture
and one of `label: TEXT` (or `label: [TEXT, ...]`: more than one answer is right) or `skip: true`. Two more
(RFC-031):
  date: FIELD                          the outcome field holding when it happened (an issue's closed_at)
  under: action                        the outcome was observed only under the action production took (an issue's
                                       close reason exists because production filed it): a variant that acted
                                       otherwise is not scored on it
A label has two dates: when it happened (`date:`), and when it became knowable (the record's time plus
`min_age_days`, else when it happened, else the capture's time).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness._common import die

RULE_KEYS = {"when", "unless", "exists", "absent", "range", "min_age_days", "label", "skip", "date", "under"}


def load_rules(path: Path) -> list:
    """The mapping's rules, checked: each a known set of keys with one label or a skip."""
    import yaml  # noqa: PLC0415

    if not _store.is_file(path):
        die(f"--map: no file {path}", "not-found")
    doc = yaml.safe_load(_store.read_text(path, encoding="utf-8"))
    rules = doc.get("rules") if isinstance(doc, dict) else doc
    if not isinstance(rules, list) or not rules:
        die(f"{path}: a list of rules (or `rules:` holding one)", "invalid-file")
    for n, r in enumerate(rules, 1):
        if not isinstance(r, dict) or set(r) - RULE_KEYS:
            die(
                f"{path}: rule {n}: keys are {sorted(RULE_KEYS)}; got {sorted(r) if isinstance(r, dict) else r!r}",
                "invalid-file",
            )
        if ("label" in r) == bool(r.get("skip")):
            die(f"{path}: rule {n}: exactly one of label or skip: true", "invalid-file")
        if "under" in r and r["under"] != "action":
            die(
                f"{path}: rule {n}: under: action is the one value (the outcome holds only under production's action)",
                "invalid-file",
            )
        lab = r.get("label")
        if isinstance(lab, list) and not (lab and all(str(a).strip() for a in lab)):
            die(
                f"{path}: rule {n}: a label list names the right answers, none empty; got {lab!r}",
                "invalid-file",
            )
    return rules


def _is(value: Any, want: Any) -> bool:
    wants = want if isinstance(want, list) else [want]
    return any(value == w or (value is not None and str(value) == str(w)) for w in wants)


def matches(rule: dict, out: dict, age_days: float | None) -> bool:
    """Whether a rule holds for one record's outcome fields."""
    if any(not _is(out.get(f), w) for f, w in (rule.get("when") or {}).items()):
        return False
    if any(_is(out.get(f), w) for f, w in (rule.get("unless") or {}).items()):
        return False
    if any(out.get(f) is None for f in rule.get("exists") or []):
        return False
    if any(out.get(f) is not None for f in rule.get("absent") or []):
        return False
    for f, bounds in (rule.get("range") or {}).items():
        v = out.get(f)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return False
        if ("min" in bounds and v < bounds["min"]) or ("max" in bounds and v > bounds["max"]):
            return False
    return not ("min_age_days" in rule and (age_days is None or age_days < rule["min_age_days"]))


def dates(rule: dict, out: dict, record_time: Any, captured: Any) -> dict[str, str | None]:
    """A label's two dates (RFC-031 L2): when its outcome happened, and when it became knowable."""
    from datetime import timedelta  # noqa: PLC0415

    from evaluation_harness._importers import parse_time  # noqa: PLC0415

    happened = parse_time(out.get(rule["date"])) if rule.get("date") else None
    if "min_age_days" in rule and record_time is not None:
        knowable = record_time + timedelta(days=rule["min_age_days"])
    else:
        knowable = happened or captured
    return {
        "happened_at": happened.isoformat() if happened else None,
        "knowable_at": knowable.isoformat() if knowable else None,
    }
