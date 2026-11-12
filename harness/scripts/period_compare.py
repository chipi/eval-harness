#!/usr/bin/env python3
"""A past period at its own code, beside a candidate on the same items (RFC-031 P2).

    evh period-compare --config data/configs/filing_replay_v1.yaml --candidate filing_candidate_v3 \\
        --production filing_production_v1 --period 2          # or --from T --to T

The code changed ten times in nineteen days on the triage fleet, and a reading over the whole window mixed a fix's
before and after (the rollup "buried more than it promoted": all six misses came before the fix). A period's fair
comparison is that period's items: what production recorded, the code that ran then (the replay's run, which must
agree with production on those items or the report says it does not count), and the candidate on the same items,
with the paired test between the last two. It reads the latest run of each config on the dataset (run them first:
nothing is called here). A period is a code record's deployed period (`evh periods --model ID`) or --from/--to.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any

from evaluation_harness import _coderec, _fields, _jsonout, _outputs, _runs, _store
from evaluation_harness._adapter import same_of
from evaluation_harness._common import die, evh_prog, load_dataset


def _latest(dataset_id: str, name: str) -> tuple[Any, dict]:
    """A run named by its id, or the latest run of a config named by its config_id (the fleet's beta: `faithfulness
    --production` takes a run id, and the same id given here was refused)."""
    runs = _runs.runs_on(dataset_id)
    by_id = [(d, m) for d, m in runs if d.name == name]
    if by_id:
        return by_id[0]
    of_config = [(d, m) for d, m in runs if m.get("config_id") == name]
    if not of_config:
        die(
            f"no run of {name} on {dataset_id}, by run id or config_id: run it first (evh run --config …)",
            "not-found",
        )
    return of_config[-1]


def window_of(rec: dict, period: int | None, start: str | None, end: str | None) -> tuple[Any, Any, str]:
    """(from, to or None, what it is called) for --period N or --from/--to."""
    if period is not None:
        spans, bad = _coderec.periods(rec)
        if bad:
            die(f"code record {rec['model_id']}: {bad[0]}", "invalid-file")
        if not 1 <= period <= len(spans):
            die(
                f"--period {period}: the record has {len(spans)} deployed period(s) (evh periods --model {rec['model_id']})",
                "not-found",
            )
        f, t, c = spans[period - 1]
        return f, t, f"period {period} ({c[:12]})"
    if not start:
        die("--period N, or --from T (and --to T)", "bad-argument")
    f = _fields.moment(start)
    t = _fields.moment(end) if end else None
    if f is None or (end and t is None):
        die("--from/--to: ISO date-times with an offset (2026-11-01T00:00:00Z)", "bad-argument")
    return f, t, f"{start} to {end or 'now'}"


def main() -> int:
    """Compare a period's production, as-run replay and candidate."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--config", required=True, type=Path, help="the replay config (production's code as it ran)"
    )
    ap.add_argument(
        "--candidate",
        required=True,
        help="the candidate: a run id, or a config_id (its latest run on the dataset)",
    )
    ap.add_argument(
        "--production",
        help="production's recorded arm (arm-from-capture): a run id, as faithfulness takes, or a config_id",
    )
    ap.add_argument("--period", type=int, help="the code record's deployed period, by number (evh periods)")
    ap.add_argument("--from", dest="start", help="the period's start (ISO, with an offset)")
    ap.add_argument("--to", dest="end", help="its end (default: now)")
    ap.add_argument("--metric", help="the measure (default: the replay run's primary metric)")
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("period-compare", args.json, live=sys.stderr):
        import yaml  # noqa: PLC0415

        if not _store.is_file(args.config):
            die(f"no config at {args.config}", "not-found")
        cfg = yaml.safe_load(_store.read_text(args.config, encoding="utf-8")) or {}
        spec = cfg.get("replay") or {}
        tf = spec.get("time_field")
        if not spec or not tf or not cfg.get("model_record"):
            die(
                f"{args.config}: a replay config with replay.time_field and model_record (RFC-030)",
                "invalid-file",
            )
        rec = _coderec.load(str(cfg["model_record"]))
        start, end, called = window_of(rec, args.period, args.start, args.end)
        ds = load_dataset(cfg["dataset_id"])
        items = [
            it["item_id"]
            for it in ds["items"]
            if (t := _fields.moment(str((it.get("fields") or {}).get(tf) or ""))) is not None
            and t >= start
            and (end is None or t < end)
        ]
        if not items:
            die(f"no item of {ds['dataset_id']} falls in {called}", "not-enough")
        rd, rm = _latest(ds["dataset_id"], cfg["config_id"])
        cd, cm = _latest(ds["dataset_id"], args.candidate)
        metric = (
            args.metric
            or rm.get("primary_metric")
            or _runs.default_metric(ds["dataset_id"], match=cfg["config_id"])
        )
        if not metric:
            die("--metric: the replay run names no primary metric", "bad-argument")
        same = same_of(rm.get("adapter"))
        counts = True
        disagree: list[str] = []
        prod: dict[str, float] = {}
        if args.production:
            pd, pm = _latest(ds["dataset_id"], args.production)
            for i in items:
                a, b = _outputs.output(rd, i), _outputs.output(pd, i)
                if a is None or b is None or not same(a, b):
                    disagree.append(i)
            counts = not disagree
            prod = _runs.per_item([(pd, pm)], metric, keep=set(items))
        else:
            counts = bool((rm.get("faithfulness") or {}).get("faithful"))
        asrun = _runs.per_item([(rd, rm)], metric, keep=set(items))
        cand = _runs.per_item([(cd, cm)], metric, keep=set(items))
        shared = sorted(set(asrun) & set(cand))

        def mean(v: dict[str, float]) -> float | None:
            vals = [v[i] for i in items if i in v]
            return statistics.fmean(vals) if vals else None

        print(f"{ds['dataset_id']}, {called}: {len(items)} item(s) whose {tf} falls in it; {metric}")
        rows = [
            ("production (recorded)", args.production or "-", mean(prod) if args.production else None),
            ("the code that ran then (replay)", cfg["config_id"], mean(asrun)),
            ("the candidate", args.candidate, mean(cand)),
        ]
        for what, cid, v in rows:
            print(f"  {what:<34} {cid:<32} {'-' if v is None else f'{v:.4f}'}")
        if args.production:
            print(
                f"  the replay agrees with production on {len(items) - len(disagree)} of {len(items)}"
                + ("" if counts else f": DOES NOT COUNT (disagrees on {', '.join(disagree[:5])})")
            )
        elif not counts:
            print("  the replay run is not faithful (its faithfulness record): DOES NOT COUNT")
        p = delta = None
        if len(shared) >= 2:
            from evaluation_harness.stats import sign_flip_p  # noqa: PLC0415

            deltas = [cand[i] - asrun[i] for i in shared]
            delta = statistics.fmean(deltas)
            p = sign_flip_p(deltas)
            print(
                f"  candidate - the code that ran: {delta:+.4f} on {len(shared)} item(s), sign-flip p {p:.4f}"
            )
        _jsonout.values(
            {
                "period": called,
                "from": start.isoformat(),
                "to": end.isoformat() if end else None,
                "items": len(items),
                "metric": metric,
                "production": mean(prod) if args.production else None,
                "as_run": mean(asrun),
                "candidate": mean(cand),
                "counts": counts,
                "disagree": len(disagree),
                "delta": delta,
                "p": p,
            }
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
