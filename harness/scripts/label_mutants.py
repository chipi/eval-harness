#!/usr/bin/env python3
"""Mutation-test a labeller (RFC-031 X1): each named change to the rules or the join must move some labels.

    evh label-mutants --dataset-id triage_v1 --capture decisions --map outcomes.yaml \\
        [--outcomes issues --join fp=fp --within -1m,+15m] [--mutants my_mutants.py]

Three of the triage fleet's labeller mistakes (a recurrence counted from every ledger row, "closed as duplicate" read as
noise, the input rebuilt from the wrong field) were caught only by reading results. A mutant here is the labeller with
one named change, run over the same captures as `label-coverage` runs it: the items whose class or label differ from
the unchanged labeller's are counted. A mutant that moves no label is a finding (the labelled items do not reach what
it changed), as a surviving replay mutant is (RFC-030 R5), and the command exits 6.

Built in: each rule's `min_age_days` halved and one and a half times; each pair of neighbouring rules swapped; each
`when` value replaced; the join's `--within` window moved an hour later. A project adds its own with `--mutants
FILE.py`, a module defining `mutants(rules) -> [(name, rules)]` and, optionally, `join_mutants(join) -> [(name,
join)]` (join: {"capture", "join", "within", "identity", "gone_if_missing", "as"}). Nothing is written.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _outcome_join
from evaluation_harness._common import evh_prog, load_module
from evaluation_harness._outcome_rules import load_rules
from evaluation_harness.label_coverage import coverage

MUTANT_VALUE = "__mutant__"


def builtin(rules: list[dict]) -> list[tuple[str, list[dict]]]:
    """The generic mutants of a rule list."""
    out: list[tuple[str, list[dict]]] = []
    for n, r in enumerate(rules, 1):
        if "min_age_days" in r:
            for factor, said in ((0.5, "halved"), (1.5, "one and a half times")):
                m = copy.deepcopy(rules)
                m[n - 1]["min_age_days"] = r["min_age_days"] * factor
                out.append(
                    (
                        f"rule {n}: min_age_days {said} ({r['min_age_days']} -> {r['min_age_days'] * factor:g})",
                        m,
                    )
                )
        for field in sorted(r.get("when") or {}):
            m = copy.deepcopy(rules)
            m[n - 1]["when"][field] = MUTANT_VALUE
            out.append((f"rule {n}: when {field} replaced", m))
    for n in range(1, len(rules)):
        m = copy.deepcopy(rules)
        m[n - 1], m[n] = m[n], m[n - 1]
        out.append((f"rules {n} and {n + 1} swapped", m))
    return out


def _shift(within: str | None) -> str | None:
    """`--within` moved an hour later (both ends)."""
    if not within:
        return None
    from evaluation_harness._outcome_join import _span  # noqa: PLC0415

    lo, _, hi = within.partition(",")
    mins = [int(_span(x).total_seconds() // 60) + 60 for x in (lo, hi)]
    return ",".join(f"{m:+d}m" for m in mins)


def _signature(cov: dict[str, Any]) -> dict[str, tuple]:
    return {x["item_id"]: (x["class"], tuple(x.get("label") or ())) for x in cov["by_item"]}


def main() -> int:
    """Run every mutant and count the labels each moves."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--capture", required=True, help="the capture whose records hold the decisions")
    ap.add_argument("--map", required=True, type=Path, help="the rules")
    _outcome_join.add_arguments(ap)
    ap.add_argument(
        "--mutants", type=Path, help="a project's own mutants (FILE.py: mutants(rules), join_mutants(join))"
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args(_outcome_join.argv())
    with _jsonout.collect("label-mutants", args.json, live=sys.stderr):
        rules = load_rules(args.map)
        join = _outcome_join.from_args(args)
        base = _signature(coverage(args.dataset_id, args.capture, rules, join))
        labelled = sum(1 for c, _l in base.values() if c == "labelled")
        plans: list[tuple[str, list[dict], Any]] = [(name, m, join) for name, m in builtin(rules)]
        jargs: dict[str, Any] | None = (
            {
                "capture": join.capture,
                "join": f"{join.item_field}={join.record_field}",
                "within": join.within_text,
                "identity": "=".join(join.identity) if join.identity else None,
                "gone_if_missing": join.gone_if_missing,
                "as": join.name,
            }
            if join
            else None
        )

        def make_join(j: dict) -> Any:
            return _outcome_join.Join(
                j["capture"],
                j["join"],
                j.get("within"),
                j.get("identity"),
                j.get("gone_if_missing", False),
                j.get("as"),
            )

        if jargs and jargs.get("within"):
            plans.append(
                (
                    f"the join's window moved an hour later ({jargs['within']} -> {_shift(jargs['within'])})",
                    rules,
                    make_join({**jargs, "within": _shift(jargs["within"])}),
                )
            )
        if args.mutants:
            from evaluation_harness import _common  # noqa: PLC0415

            mod = load_module(
                (_common.ROOT / args.mutants).resolve() if not args.mutants.is_absolute() else args.mutants,
                "evh_label_mutants",
            )
            for name, m in getattr(mod, "mutants", lambda r: [])(copy.deepcopy(rules)) or []:
                plans.append((f"{name} (the project's)", m, join))
            if jargs is not None:
                for name, j in getattr(mod, "join_mutants", lambda j: [])(dict(jargs)) or []:
                    plans.append((f"{name} (the project's)", rules, make_join(j)))
        print(
            f"{args.dataset_id}: {len(plans)} mutant(s) of the labeller over capture {args.capture}"
            + (f" and {join.capture}" if join else "")
            + f"; unchanged it labels {labelled} item(s)"
        )
        results = []
        for name, m, j in plans:
            sig = _signature(coverage(args.dataset_id, args.capture, m, j))
            moved = sorted(i for i in base if sig.get(i) != base[i])
            results.append({"mutant": name, "moved": len(moved)})
            print(f"  {'SURVIVED' if not moved else 'killed  '}  {name}: {len(moved)} label(s) moved")
        survivors = [r["mutant"] for r in results if not r["moved"]]
        print(
            f"{len(results) - len(survivors)} of {len(results)} killed"
            + (
                f"; {len(survivors)} survived: the labelled items do not reach what they change (a finding: read why)"
                if survivors
                else ""
            )
        )
        _jsonout.values({"mutants": results, "survived": survivors, "labelled": labelled})
        return 6 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
