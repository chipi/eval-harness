#!/usr/bin/env python3
"""Rules over a capture's recorded outcomes as a rule label set (RFC-023): what production recorded afterwards.

    evh label-from-capture --dataset-id triage_v1 --capture fleet_2026_10 --map outcomes.yaml --set issue_verdicts
    evh label-from-capture … --outcomes issues_2026_11 --join fingerprint=fingerprint --within -1m,+15m
    evh label-from-capture … --set issue_verdicts_2 --from-set issue_verdicts      # a relabel: adds what matured

For each item of the dataset, the capture's record of the same id is read, and the mapping's rules are tried in
order against its outcome's fields; the first that matches gives the item's label, or skips it; an item no rule
matches has no label. The rules are the outcome rule language (`_outcome_rules`: when, unless, exists, absent, range,
min_age_days, date, under; label or skip). The set's source is `rule`, whoever wrote the outcome: the capture, its
sha256, the mapping and its hash, and the counts.

RFC-031: the outcome can come from another capture (`--outcomes`, `_outcome_join`: an outside system's records, joined
by key and time window; an item whose outside record is gone, or its id reused, is its own class, never labelled).
Each label carries two dates: when its outcome happened and when it became knowable; the set records `as_of`, the
newest capture's time. A relabel (`--from-set`) keeps the earlier set's labels, adds the ones matured since, and gives
an item whose outcome changed after maturing (a reopen, a recurrence) its new label marked `changed_after_maturing`; a
label the earlier set had and today's rules no longer give is refused unless `--keep-vanished` keeps it, said. A rule
with `under: action` records production's action per item (`--action-field`, the record's field holding it): a run
that acted otherwise is not scored on that item.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _outcome_join, _store
from evaluation_harness._common import CAPTURES, die, evh_prog, load_dataset, now, read_json
from evaluation_harness._importers import parse_time
from evaluation_harness._label_sets import answers, label_text, set_dir, write_set
from evaluation_harness._outcome_rules import dates, load_rules, matches


def _dig(d: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _previous(dataset_id: str, name: str) -> tuple[dict[str, Any], dict[str, str]]:
    """An earlier set's labels.json and its labels' texts."""
    base = set_dir(dataset_id, name)
    if not _store.is_file(base / "labels.json"):
        die(f"--from-set: no label set {dataset_id}/{name}", "not-found")
    doc = read_json(base / "labels.json")
    texts = {
        i: _store.read_text(base / f"{i}.txt", encoding="utf-8").strip()
        for i in (doc.get("items") or {})
        if _store.is_file(base / f"{i}.txt")
    }
    return doc, texts


def _reproduced(
    replay_id: str, production_id: str, labels: dict[str, str], info: dict[str, dict]
) -> dict[str, Any]:
    """RFC-031 X2: keep each label only where the replay reproduces production's decision; mark one at a version whose
    deployment was dated by commit time (approximate). Mutates `labels` and `info`; returns the counts."""
    from evaluation_harness import _coderec, _outputs, _runs  # noqa: PLC0415
    from evaluation_harness._adapter import same_of  # noqa: PLC0415
    from evaluation_harness._common import RUNS  # noqa: PLC0415

    rd, pd = RUNS / replay_id, RUNS / production_id
    rm, pm = _runs.read_metrics(rd), _runs.read_metrics(pd)
    if rm is None or pm is None:
        die(f"no run {replay_id if rm is None else production_id} in {RUNS}", "not-found")
    code = ((rm.get("fingerprint") or {}).get("deployment") or {}).get("code") or {}
    if not code.get("record"):
        die(f"{replay_id} is not a replay run (RFC-030): it names no code record", "bad-argument")
    rec = _coderec.load(str(code["record"]))
    approximate_commits = {
        str(v.get("commit"))
        for v in rec.get("versions") or []
        if any(p.get("dated_by") == "commit" for p in v.get("deployed") or [])
    }
    commit_of = {r["item_id"]: str(r.get("_commit") or "") for r in _runs.item_rows(rd, strict=False)}
    same = same_of(rm.get("adapter"))
    out: dict[str, Any] = {
        "replay": replay_id,
        "production": production_id,
        "reproduced": 0,
        "approximate": 0,
        "not_reproduced": 0,
    }
    left: list[str] = []
    for iid in sorted(labels):
        a, b = _outputs.output(rd, iid), _outputs.output(pd, iid)
        if a is None or b is None or not same(a, b):
            left.append(iid)
            continue
        out["reproduced"] += 1
        c = commit_of.get(iid, "")
        approx = bool(c) and any(full.startswith(c) for full in approximate_commits)
        info.setdefault(iid, {})["reproduced"] = "approximate" if approx else "yes"
        out["approximate"] += approx
    for iid in left:
        labels.pop(iid, None)
        info.pop(iid, None)
    out["not_reproduced"] = len(left)
    out["left_out"] = left
    return out


def main() -> int:
    """Label a dataset's items from a capture's outcomes, by rules."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument(
        "--capture", required=True, help="the capture whose records hold the decisions (and outcomes)"
    )
    ap.add_argument("--map", required=True, type=Path, help="the mapping: YAML rules")
    ap.add_argument("--set", required=True, dest="name", help="the label set's name (lowercase, _ . -)")
    _outcome_join.add_arguments(ap)
    ap.add_argument("--from-set", help="a relabel: keep this earlier set's labels and add what matured since")
    ap.add_argument(
        "--keep-vanished",
        action="store_true",
        help="with --from-set: keep an earlier label today's rules no longer give (said), instead of refusing",
    )
    ap.add_argument(
        "--reproduced-by",
        help="a replay run at the recorded versions (RFC-030): keep a label only where it reproduces production's "
        "decision (with --production); a version dated by commit time counts as approximate (RFC-031 X2)",
    )
    ap.add_argument("--production", help="with --reproduced-by: production's recorded run")
    ap.add_argument(
        "--action-field",
        help="the record field holding production's action, for rules with under: action (RFC-031)",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("label-from-capture", args.json, live=sys.stderr):
        from evaluation_harness.dataset_from_capture import load_capture  # noqa: PLC0415

        rules = load_rules(args.map)
        if any(r.get("under") == "action" for r in rules) and not args.action_field:
            die(
                "a rule says under: action: name the record field holding production's action (--action-field)",
                "bad-argument",
            )
        join = _outcome_join.from_args(args)
        ds = load_dataset(args.dataset_id)
        doc, recs = load_capture(args.capture)
        by_id = {r["id"]: r for r in recs}
        captured = parse_time(doc.get("captured_at"))
        as_of = max(
            (
                t
                for t in (captured, parse_time(join.doc.get("captured_at")) if join else None)
                if t is not None
            ),
            default=None,
        )
        labels: dict[str, str] = {}
        info: dict[str, dict[str, Any]] = {}
        gone: dict[str, Any] = {}
        counts: Counter[str] = Counter()
        for it in ds["items"]:
            iid = it["item_id"]
            rec = by_id.get(iid)
            if rec is None:
                counts["no_record"] += 1
                continue
            out = dict(rec.get("outcome")) if isinstance(rec.get("outcome"), dict) else {}
            if join is not None:
                joined, is_gone = join.outcome(rec)
                if is_gone:
                    counts["gone"] += 1
                    gone[iid] = _dig(rec.get("fields") or {}, "last_seen") or rec.get("created_at")
                    continue
                out |= joined
            t = parse_time(rec.get("created_at"))
            age = (as_of - t).total_seconds() / 86400 if as_of and t else None
            rule = next((r for r in rules if matches(r, out, age)), None)
            if rule is None:
                counts["unmatched"] += 1
            elif rule.get("skip"):
                counts["skipped"] += 1
            else:
                counts["matched"] += 1
                labels[iid] = (
                    label_text([str(a) for a in rule["label"]])
                    if isinstance(rule["label"], list)
                    else str(rule["label"])
                )
                row: dict[str, Any] = dict(dates(rule, out, t, as_of))
                if rule.get("under") == "action":
                    act = _dig(rec.get("fields") or {}, args.action_field) or _dig(rec, args.action_field)
                    if act is None:
                        die(
                            f"{iid}: its record has no {args.action_field} (production's action), and its label holds "
                            "only under that action",
                            "not-found",
                        )
                    row["under_action"] = str(act)
                info[iid] = row
        relabel: dict[str, Any] = {}
        if args.from_set:
            prev, before = _previous(args.dataset_id, args.from_set)
            vanished = sorted(set(before) - set(labels) - set(gone))
            if vanished and not args.keep_vanished:
                die(
                    f"{len(vanished)} label(s) of {args.from_set} are given by no rule today ({', '.join(vanished[:5])}"
                    + (" ..." if len(vanished) > 5 else "")
                    + "): a label never vanishes silently. --keep-vanished keeps them (said), or name why in a new set",
                    "not-allowed",
                )
            changed = 0
            for iid, text in before.items():
                prow = dict((prev.get("items") or {}).get(iid) or {})
                if iid not in labels:  # vanished (kept) or gone: the earlier label stays
                    labels[iid] = text
                    info[iid] = {
                        k: prow[k] for k in ("happened_at", "knowable_at", "under_action") if prow.get(k)
                    }
                    info[iid]["kept_from"] = args.from_set
                elif sorted(answers(labels[iid])) != sorted(answers(text)):
                    changed += 1
                    info[iid]["changed_after_maturing"] = {"from": text, "at": now()}
                else:
                    info[iid] = {
                        k: prow[k] for k in ("happened_at", "knowable_at", "under_action") if prow.get(k)
                    } or info[iid]
            relabel = {
                "from_set": args.from_set,
                "kept": len(set(before) & set(labels)) - changed,
                "added": len(set(labels) - set(before)),
                "changed_after_maturing": changed,
                "vanished_kept": len(vanished),
            }
        reproduced: dict[str, Any] = {}
        if args.reproduced_by or args.production:
            if not (args.reproduced_by and args.production):
                die(
                    "--reproduced-by and --production go together (the replay and what it must reproduce)",
                    "bad-argument",
                )
            reproduced = _reproduced(args.reproduced_by, args.production, labels, info)
        if not labels:
            die(f"no item got a label ({dict(counts)}): nothing written", "not-enough")
        source = {
            "kind": "rule",
            "capture": args.capture,
            "capture_sha256": hashlib.sha256(
                _store.read_bytes(CAPTURES / args.capture / "capture.json")
            ).hexdigest(),
            "captured_at": doc.get("captured_at"),
            "as_of": as_of.isoformat() if as_of else None,
            "mapping": args.map.as_posix(),
            "mapping_sha256": hashlib.sha256(_store.read_bytes(args.map)).hexdigest(),
            **({"outcomes": join.source()} if join else {}),
            **({"relabel": relabel} if relabel else {}),
            **({"reproduced_by": reproduced} if reproduced else {}),
            **{k: counts[k] for k in ("matched", "skipped", "unmatched", "no_record", "gone")},
        }
        out = write_set(
            args.dataset_id,
            args.name,
            labels,
            source,
            args.map,
            item_info=info,
            extra={"gone": gone} if gone else None,
        )
        print(
            f"data/labels/{args.dataset_id}/{args.name}: {out['n_items']} of {len(ds['items'])} item(s) labelled "
            f"({counts['skipped']} skipped, {counts['unmatched']} matched no rule, {counts['no_record']} not in the capture"
            + (f", {counts['gone']} gone from the source or their id reused" if counts["gone"] else "")
            + ")"
            + (f", as of {source['as_of'][:10]}" if source.get("as_of") else "")
        )
        if reproduced:
            print(
                f"  reproduced by {args.reproduced_by}: {reproduced['reproduced']} kept, of them "
                f"{reproduced['approximate']} at a version dated by commit time (approximate); "
                f"{reproduced['not_reproduced']} left out (the replay does not reproduce production's decision)"
            )
        if relabel:
            print(
                f"  relabel of {args.from_set}: {relabel['kept']} kept, {relabel['added']} added (matured since), "
                f"{relabel['changed_after_maturing']} changed after maturing"
                + (
                    f", {relabel['vanished_kept']} no longer given today, kept"
                    if relabel["vanished_kept"]
                    else ""
                )
            )
        _jsonout.values(
            {"set": args.name, "labelled": out["n_items"], "counts": dict(counts), "relabel": relabel or None}
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
