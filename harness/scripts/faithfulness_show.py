"""A faithfulness record (RFC-030): its counts, every disagreement and who named which, and its coverage.

evh faithfulness-show signal_fleet
evh faithfulness-show signal_fleet --n 2 --json
"""

from __future__ import annotations

from types import SimpleNamespace

from evaluation_harness import _coderec, _faith, _jsonout
from evaluation_harness._actor import said
from evaluation_harness._common import die
from evaluation_harness.model import faithfulness as model_faithfulness


def body(model: str, n: int | None = None) -> int:
    """One faithfulness record of a code record: its counts, disagreements and coverage."""
    args = SimpleNamespace(model=model, n=n)
    _coderec.load(args.model)
    nums = model_faithfulness.numbers(args.model)
    n = args.n or (nums[-1] if nums else None)
    if n is None:
        die(f"no faithfulness record of {args.model}", "not-found")
    rec = model_faithfulness.load(args.model, n)
    c = rec["counts"]
    named = {e["item_id"]: e for e in rec.get("exceptions") or []}
    print(
        f"{args.model}/{n}: replay of {rec['system_id']} on {rec['dataset_id']} at {len(rec['commits'])} commit(s), "
        f"against {rec['production_run']}, {rec['at']} by {said(rec.get('actor'))}"
    )
    print(
        f"  {c['agree']} of {c['items']} agree; {c['differ']} differ, {c['replay_errors']} replay error(s), "
        f"{c['production_missing']} without a production output; {len(named)} named, "
        f"{len(_faith.unnamed(rec))} unnamed"
    )
    for d in rec.get("disagreements") or []:
        e = named.get(d["item_id"])
        print(
            f"  {d['kind']:18} {d['item_id']}"
            + (f"  NAMED by {said(e.get('actor'))}: {e['cause']}" if e else "")
        )
    for commit, v in (rec.get("coverage") or {}).items():
        print(
            f"  coverage {commit[:12]}: {v['entered']} of {v['defined']} functions entered; never: {v['never_count']}"
        )
        for name in v["never"]:
            print(f"      {name}")
    _jsonout.value("record", rec)
    return 0
