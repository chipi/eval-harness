#!/usr/bin/env python3
"""evh periods: a code record's deployed periods, numbered, with how each was dated and its faithfulness (RFC-031 P2).

    evh periods --model toy_filing [--config data/configs/filing_replay_v1.yaml]

Each period: its number (for `period-compare --period N`), from and to, the commit, how the deployment was dated
(`dated_by: pull` from the host's own pull time, `commit` from the commit's time when the pull is no longer
recorded: approximate, RFC-031 X2) and the version's faithfulness summary. With a replay config, how many of its
dataset's items fall in each.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from pathlib import Path

from evaluation_harness import _coderec, _fields, _jsonout, _store
from evaluation_harness._common import die, evh_prog, load_dataset


def main() -> int:
    """List the periods."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="the kind: code record")
    ap.add_argument("--config", type=Path, help="a replay config: count its dataset's items per period")
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("periods", args.json, live=sys.stderr):
        rec = _coderec.load(args.model)
        spans, bad = _coderec.periods(rec)
        if bad:
            die(f"code record {args.model}: {bad[0]}", "invalid-file")
        by_commit = {str(v.get("commit")): v for v in rec.get("versions") or []}
        times: list = []
        if args.config:
            import yaml  # noqa: PLC0415

            cfg = yaml.safe_load(_store.read_text(args.config, encoding="utf-8")) or {}
            tf = (cfg.get("replay") or {}).get("time_field")
            if not tf:
                die(f"{args.config}: a replay config with replay.time_field", "invalid-file")
            ds = load_dataset(cfg["dataset_id"])
            times = [_fields.moment(str((it.get("fields") or {}).get(tf) or "")) for it in ds["items"]]
        out = []
        print(f"{args.model}: {len(spans)} deployed period(s)")
        for n, (f, t, c) in enumerate(spans, 1):
            v = by_commit.get(c, {})
            faith = v.get("faithfulness") or {}
            n_items = (
                sum(1 for x in times if x is not None and x >= f and (t is None or x < t))
                if args.config
                else None
            )
            dated = next(
                (
                    p.get("dated_by")
                    for p in v.get("deployed") or []
                    if _fields.moment(str(p.get("from"))) == f
                ),
                None,
            )
            print(
                f"  {n}. {f.isoformat()} to {t.isoformat() if t else 'now'}  {c[:12]}"
                + (f"  dated by {dated}" + (" (approximate)" if dated == "commit" else "") if dated else "")
                + (f"  {n_items} item(s)" if n_items is not None else "")
                + (
                    f"  faithful {faith.get('agreed')} of {faith.get('items')}"
                    if faith.get("items") is not None
                    else ""
                )
            )
            out.append(
                {
                    "period": n,
                    "from": f.isoformat(),
                    "to": t.isoformat() if t else None,
                    "commit": c,
                    "dated_by": dated,
                    "items": n_items,
                    "faithfulness": faith or None,
                }
            )
        _jsonout.value("periods", out)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
