#!/usr/bin/env python3
"""Make a reference from outcomes: what production recorded after each record (RFC-019).

    evh reference-from-outcomes --dataset-id triage_v1 --capture fleet_2026_10 --map outcomes.yaml
    evh reference-from-outcomes --dataset-id triage_v1 --capture fleet_2026_10 --map outcomes.yaml \\
        --name silver/triage_v1_outcomes

For each item of the dataset, the capture's record of the same id is read, and the mapping's rules
are tried in order against its outcome's FIELDS (flat names: a project's importer computes what the
rules need, such as `issue_verdict` or `days_to_filing`). The first rule that matches gives the
item's label, or skips it; an item no rule matches has no reference. The texts are written to
data/references/<tier>/<name>/<item_id>.txt, and the manifest records the capture, the mapping and
its hash, and the counts, with its own caveat: an outcome is not a person's label.

The mapping (YAML), a list of rules, each with any of:
  when:   {field: value or [values]}   every one must hold
  unless: {field: value or [values]}   none may hold
  exists: [field, ...]                 present and not null
  absent: [field, ...]                 missing or null
  range:  {field: {min: N, max: N}}    a number within bounds (either bound optional)
  min_age_days: N                      the record is at least N days older than the capture
and one of `label: TEXT` or `skip: true`.

--name defaults to gold/<dataset>, the reference experiment-run scores against. Any other name is
read with `evh rescore --reference-id`. A reference that exists is never overwritten.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness._common import CAPTURES, REFERENCES, die, load_dataset, now
from evaluation_harness._importers import parse_time
from evaluation_harness._references import write_manifest
from evaluation_harness.dataset_from_capture import load_capture

RULE_KEYS = {"when", "unless", "exists", "absent", "range", "min_age_days", "label", "skip"}
CAVEAT = (
    "OUTCOME: what production recorded afterwards, as of {date}, mapped to a label by a recorded rule "
    "set; not a person's label. It can repeat what production decided (an item nothing happened to "
    "reads as right)."
)


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


def main() -> int:
    """Label a dataset's items from their outcomes, by rules."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--capture", required=True, help="the capture whose records hold the outcomes")
    ap.add_argument("--map", required=True, type=Path, help="the mapping: YAML rules")
    ap.add_argument("--name", help="<gold|silver>/<name>; default gold/<dataset-id>")
    args = ap.parse_args()

    name = args.name or f"gold/{args.dataset_id}"
    tier, _, ref = name.partition("/")
    if tier not in ("gold", "silver") or not ref or "/" in ref or ref.startswith("."):
        die(f"--name {name!r}: gold/<name> or silver/<name>")
    ref_dir = REFERENCES / tier / ref
    if ref_dir.exists() and any(ref_dir.iterdir()):
        die(f"{ref_dir} exists: a reference is never overwritten. Name another with --name (silver/<name>).")
    rules = load_rules(args.map)
    ds = load_dataset(args.dataset_id)
    doc, recs = load_capture(args.capture)
    by_id = {r["id"]: r for r in recs}
    captured = parse_time(doc.get("captured_at"))

    labels: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for it in ds["items"]:
        rec = by_id.get(it["item_id"])
        if rec is None:
            counts["no_record"] += 1
            continue
        out = rec.get("outcome") if isinstance(rec.get("outcome"), dict) else {}
        t = parse_time(rec.get("created_at"))
        age = (captured - t).total_seconds() / 86400 if captured and t else None
        rule = next((r for r in rules if matches(r, out, age)), None)
        if rule is None:
            counts["unmatched"] += 1
        elif rule.get("skip"):
            counts["skipped"] += 1
        else:
            counts["matched"] += 1
            labels[it["item_id"]] = str(rule["label"])
    if not labels:
        die(f"no item got a label ({dict(counts)}): nothing written")

    ref_dir.mkdir(parents=True, exist_ok=True)
    for iid, text in labels.items():
        (ref_dir / f"{iid}.txt").write_text(text + "\n", encoding="utf-8")
    write_manifest(
        ref_dir,
        tier,
        args.dataset_id,
        caveat=CAVEAT.format(date=doc.get("captured_at", "?")),
        source=f"evh reference-from-outcomes --capture {args.capture} --map {args.map.as_posix()}",
        created_at=now(),
        from_outcomes={
            "capture": args.capture,
            "capture_sha256": hashlib.sha256(
                (CAPTURES / args.capture / "capture.json").read_bytes()
            ).hexdigest(),
            "captured_at": doc.get("captured_at"),
            "mapping": args.map.as_posix(),
            "mapping_sha256": hashlib.sha256(args.map.read_bytes()).hexdigest(),
            "matched": counts["matched"],
            "skipped": counts["skipped"],
            "unmatched": counts["unmatched"],
            "no_record": counts["no_record"],
            "labels": dict(Counter(labels.values())),
        },
    )
    print(
        f"{ref_dir}: {len(labels)} of {len(ds['items'])} item(s) labelled "
        f"({counts['skipped']} skipped, {counts['unmatched']} matched no rule, {counts['no_record']} not in the capture)"
    )
    if tier == "silver" or ref != args.dataset_id:
        print(
            f"  read it with: evh rescore --dataset-id {args.dataset_id} --reference-id {name} --out data/runs-{ref}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
