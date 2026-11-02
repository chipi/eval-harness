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
and one of `label: TEXT` (or `label: [TEXT, ...]`: more than one answer is right) or `skip: true`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from evaluation_harness._common import die

RULE_KEYS = {"when", "unless", "exists", "absent", "range", "min_age_days", "label", "skip"}


def load_rules(path: Path) -> list:
    """The mapping's rules, checked: each a known set of keys with one label or a skip."""
    import yaml  # noqa: PLC0415

    if not path.is_file():
        die(f"--map: no file {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    rules = doc.get("rules") if isinstance(doc, dict) else doc
    if not isinstance(rules, list) or not rules:
        die(f"{path}: a list of rules (or `rules:` holding one)")
    for n, r in enumerate(rules, 1):
        if not isinstance(r, dict) or set(r) - RULE_KEYS:
            die(
                f"{path}: rule {n}: keys are {sorted(RULE_KEYS)}; got {sorted(r) if isinstance(r, dict) else r!r}"
            )
        if ("label" in r) == bool(r.get("skip")):
            die(f"{path}: rule {n}: exactly one of label or skip: true")
        lab = r.get("label")
        if isinstance(lab, list) and not (lab and all(str(a).strip() for a in lab)):
            die(f"{path}: rule {n}: a label list names the right answers, none empty; got {lab!r}")
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
