#!/usr/bin/env python3
"""Open a sealed side of a split to one candidate, named in advance (the fleet's feedback 29).

    evh dataset-unseal triage_v1_test --system candidate_test_v1 --reason "the tuned filter, frozen on validation"

The system must carry a hypothesis (ADR-0025) committed before now: the candidate and what it is compared with are
named before anything is read from the held-out side. The unseal opens the dataset to that system and to the system
its hypothesis is against, and records the look: when, why, the hypothesis and the commit that named it. Every other
system is still refused. Each unseal is one look at the held-out side.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from pathlib import Path

import yaml
from evaluation_harness import _hypothesis, _jsonout, _seal, _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, load_dataset, now, write_json


def _head(config_path: Path) -> dict:
    """The commit the working tree is at, as a run's build names it (the hypothesis must be in its history)."""
    from evaluation_harness._fingerprint import _git  # noqa: PLC0415

    ref = _git(Path(config_path).resolve().parent, "rev-parse", "HEAD")
    return {"source": "git", "ref": ref} if ref else {}


def main() -> int:
    """Open a sealed dataset to a candidate system."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("dataset_id", help="the sealed dataset (a split's test side)")
    ap.add_argument("--system", required=True, help="the candidate system: its id")
    ap.add_argument("--reason", required=True, help="why this candidate, and why now: a sentence")
    ap.add_argument(
        "--confirm-extra-look",
        action="store_true",
        help="past the set's limit of looks (RFC-029): the person's consent to look again (an agent cannot)",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("dataset-unseal", args.json, live=sys.stderr):
        ds_id = dataset_id_ok(args.dataset_id)
        from evaluation_harness._actor import require_named  # noqa: PLC0415

        who = require_named("dataset-unseal")
        doc = load_dataset(ds_id)
        if not doc.get("sealed"):
            die(f"{ds_id} is not sealed (dataset-split --seal seals a test side)", "not-allowed")
        if len(args.reason.split()) < 3:
            die("--reason is a sentence: why this candidate, and why now?", "bad-argument")
        ids = _hypothesis.system_ids()
        path = ids.get(args.system)
        if path is None:
            die(f"--system {args.system}: no system with that id (evh system-list)", "not-found")
        cfg = yaml.safe_load(_store.read_text(path, encoding="utf-8")) or {}
        hyp = _hypothesis.of(cfg)
        if not hyp:
            die(
                f"{args.system} names no hypothesis: write one in it (against, measure, direction, statement; "
                "ADR-0025) and commit it, so the comparison is named before the held-out side is read",
                "not-allowed",
            )
        bad = _hypothesis.problems(cfg, path, ids)
        if bad:
            die(f"{args.system}: " + "; ".join(bad), "invalid-file")
        # The project's database keeps its systems out of git (RFC-025): no commit can speak for one, so the unseal
        # itself, timestamped before any run it allows, is the naming in advance, and the look says so.
        if _store.sqlite() and _store.rel(path) is not None:
            named = {
                "named": None,
                "commit": None,
                "why": "the system is in the project's database, not in git",
            }
        else:
            named = _hypothesis.named_before(path, hyp, _head(path), now())
            if named.get("named") is not True:
                die(
                    f"{args.system}'s hypothesis is not committed: {named.get('why')}. Commit the system first.",
                    "not-allowed",
                )
        opened = sorted({args.system, str(hyp["against"])} - _seal.opened_for(doc))
        # Each unseal is a look at the set (RFC-029): numbered under the set's lock while it is written, its level
        # the look's; the question is the candidate against its hypothesis's arm, on its measure, in its direction.
        from evaluation_harness import _looks  # noqa: PLC0415

        rule = "noninferiority" if hyp.get("direction") == "no-worse" else "superiority"
        k = _looks.key(ds_id, args.system, str(hyp["against"]), hyp.get("measure"), rule)
        with _looks.taking(ds_id, k, consent=args.confirm_extra_look) as taken:
            doc = load_dataset(ds_id)
            entry = {
                "config_id": args.system,
                "at": now(),
                "reason": args.reason,
                "hypothesis": hyp,
                "commit": named.get("commit") or "not determinable",
                "actor": who,
                "look": {x: v for x, v in taken.items() if x != "reused"},
            }
            doc["unsealed"] = [*(doc.get("unsealed") or []), entry]
            write_json(DATASETS / f"{ds_id}.json", doc)
        n = taken["number"]
        print(f"  look {n}: decisions on it are tested one-sided at {taken['level']:.4%} (evh looks)")
        print(
            f"data/datasets/{ds_id}.json  unsealed for {args.system} against {hyp['against']} "
            + (
                f"(look {n} at this held-out side; hypothesis committed {str(named.get('commit'))[:8]})"
                if named.get("commit")
                else f"(look {n} at this held-out side; {named.get('why')}: this unseal names it in advance)"
            )
        )
        if opened:
            print(f"  now open to: {', '.join(sorted(_seal.opened_for(doc) | set(opened)))}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
