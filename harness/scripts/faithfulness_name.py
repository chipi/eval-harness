"""Name a replay's disagreement with production whose cause is outside the system (RFC-030).

    evh faithfulness-name --model signal_fleet --item d0412 --cause "the freezer lost this issue's labels" --by person:ana

The name is appended beside the record (data/faithfulness/<model_id>/<n>.exceptions.jsonl, who and when), never edited
into it, and every page and command that shows the record shows it. A named disagreement no longer holds back the gate.
It is a person's decision: an agent is refused, as for `evh run --unfaithful`.
"""

from __future__ import annotations

import os
from typing import Any

from evaluation_harness import _coderec, _faith, _jsonout
from evaluation_harness._common import die, now
from evaluation_harness.model import faithfulness as model_faithfulness
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Append one named exception to a faithfulness record."""
    args = legacy.namespace(inputs, "faithfulness-name")
    from evaluation_harness._actor import require_named  # noqa: PLC0415

    _coderec.load(args.model)
    who = require_named("naming a replay's disagreement")
    if who["type"] != "person":
        die(
            "an agent cannot name a disagreement; it lets a replay be scored (RFC-030). A person names it.",
            "not-allowed",
        )
    if not args.cause.strip():
        die("--cause: say what outside the system caused the disagreement", "bad-argument")
    nums = model_faithfulness.numbers(args.model)
    n = args.n or (nums[-1] if nums else None)
    if n is None:
        die(f"no faithfulness record of {args.model}: run evh faithfulness first", "not-found")
    rec = model_faithfulness.load(args.model, n)
    if args.item not in {d["item_id"] for d in rec.get("disagreements") or []}:
        die(f"{args.item} is not a disagreement of record {args.model}/{n}", "not-found")
    if args.item in {e.get("item_id") for e in rec.get("exceptions") or []}:
        die(f"{args.item} is named already in record {args.model}/{n}", "would-overwrite")
    ev = {"item_id": args.item, "cause": args.cause.strip(), "actor": who, "at": now()}
    from evaluation_harness import _jobs  # noqa: PLC0415

    key = f"faithfulness:{args.model}"
    with _jobs.holding([(key, True)], os.environ.get("EVH_JOB") or f"pid {os.getpid()}", _jobs.say_waiting):
        model_faithfulness.append_exception(args.model, n, ev)
    now_rec = model_faithfulness.load(args.model, n)
    left = _faith.unnamed(now_rec)
    print(f"named {args.item} in record {args.model}/{n}: {args.cause.strip()}")
    print(f"  {len(left)} disagreement(s) of the record left unnamed")
    _jsonout.value("exception", {**ev, "record": f"{args.model}/{n}", "unnamed_left": len(left)})
    return 0
