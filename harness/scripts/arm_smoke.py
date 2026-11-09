#!/usr/bin/env python3
"""Smoke an arm before its full run (RFC-020): a few items, the way evh run would run them.

    evh arm-smoke --config configs/<arm>.yaml [--items 3] [--replies] [--json]

Writes no run. For any arm (an LLM, an ML model, a baseline) it checks, from what every run already
produces: that each item runs and its output is valid for the scorer; the time per item and a projection
of the full run; that the build is pinned; whether the same item twice gives the same output; and the
cost (what it spent, and whether that is the provider's bill or the config's price table), and each item's
reply (its first 300 characters, all with --replies). For an arm that calls an LLM it reads each call (a built-in provider's `_meta`, or the calls an
adapter reports as `meta["calls"]`) and flags reasoning, slow calls, long replies, cut-off replies and
calls with no answer. An ML adapter's facts (`meta`: device, precision, load time) are printed beside.

SMOKE PASS (exit 0) or SMOKE CHECK with the flags (exit 1). When the config names a model record
(`model_record:`), the report is written into the record's `smokes` under the config's id. With
`deployment:` the build is checked against that deployment, and a hosted deployment's pinned route
(`provider_routing`) against the upstream provider each call reports.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _models, _store
from evaluation_harness._adapter import load_adapter, score_wants_source
from evaluation_harness._common import DATA, EXIT_PROBLEMS, MATERIALIZED, die, evh_prog, load_dataset, now

#: A reply is long when it is this many times the arm's median reply (RFC-020: "far longer than the arm's
#: normal ones"), over at least LONG_FLOOR tokens, among at least LONG_MIN_CALLS calls. A fixed count was a
#: triage reply's length: a summarising arm would have flagged every item.
LONG_FACTOR, LONG_FLOOR, LONG_MIN_CALLS = 3, 64, 3
ML_FACTS = ("device", "precision", "load_ms", "batch_size", "dtype")
#: How much of a reply is printed (`--replies` prints all of it).
REPLY_EXCERPT = 300


def calls_of(res: Any, wall_s: float | None = None) -> list[dict[str, Any]]:
    """The model calls an item made, as one shape: an adapter's `meta["calls"]`, else a built-in provider's
    single call from its `_meta` (usage, finish_reason, reasoning tokens), else none. The single call's time is the
    result's `latency_ms`, else `wall_s`, the wall-clock the caller measured: an adapter that does not time itself
    (the bundled hosted provider, called from a project's adapter) leaves `latency_ms` unset, and the call read 0.0 s."""
    meta = getattr(res, "meta", None) or {}
    if isinstance(meta.get("calls"), list):
        return [c for c in meta["calls"] if isinstance(c, dict)]
    if "finish_reason" in meta or "usage" in meta:
        usage = meta.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return [
            {
                "s": (getattr(res, "latency_ms", None) or 0) / 1000 or wall_s or 0,
                "tokens_out": usage.get("completion_tokens") or getattr(res, "tokens_out", None),
                "reasoning_tokens": details.get("reasoning_tokens")
                or meta.get("reasoning_tokens_reported")
                or 0,
                "finish_reason": meta.get("finish_reason"),
                "answered": bool(getattr(res, "output", "")),
                "upstream": meta.get("provider"),
            }
        ]
    return []


def route_of(deployment: dict[str, Any] | None) -> list[str]:
    """The upstream providers a hosted deployment pins (`provider_routing`: a list, or the provider's
    routing object with `only` or `order`); [] when it pins none."""
    routing = (deployment or {}).get("provider_routing")
    if isinstance(routing, dict):
        routing = routing.get("only") or routing.get("order")
    return [str(x) for x in routing] if isinstance(routing, list) else []


def flags_for(items: list[dict[str, Any]], calls: list[dict[str, Any]], params: dict[str, Any]) -> list[str]:
    """The smoke's verdict: one line per thing to revisit, general checks first, then the LLM layer."""
    out = []
    failed = [i for i in items if i.get("error")]
    if failed:
        out.append(f"runs: {len(failed)} of {len(items)} item(s) failed ({failed[0]['error'][:90]})")
    empty = [i for i in items if not i.get("error") and not i.get("output_chars")]
    if empty:
        out.append(f"runs: {len(empty)} item(s) produced no output")
    unscored = [i for i in items if not i.get("error") and i.get("scored") is False]
    if unscored:
        out.append(
            f"valid output: the scorer could not read {len(unscored)} output(s) ({unscored[0].get('score_error', '')[:80]})"
        )
    if items and items[0].get("deterministic") is False:
        out.append("determinism: item 1 twice gave different outputs (repeats will vary)")
    if not params.get("_build_pinned", True):
        out.append(
            "where it ran: the build is not pinned (no digest, revision or hash in the model record's deployment)"
        )
    limit = float(params.get("call_timeout_s") or params.get("timeout_s") or 0) or None
    route = params.get("_route") or []
    strays = sorted({str(c["upstream"]) for c in calls if c.get("upstream") and c["upstream"] not in route})
    if route and strays:
        out.append(
            f"route: call(s) served by {', '.join(strays)}, the deployment pins {', '.join(route)} (provider_routing)"
        )
    if calls:
        reasoned = [
            c for c in calls if (c.get("reasoning_tokens") or 0) > 0 or (c.get("reasoning_chars") or 0) > 0
        ]
        if reasoned and "reasoning_effort" not in params and "reasoning" not in params:
            out.append(
                f"reasoning: {len(reasoned)} of {len(calls)} call(s) reasoned and the arm sets no reasoning_effort"
            )
        if limit:
            slow = [c for c in calls if (c.get("s") or 0) > limit / 2]
            if slow:
                out.append(
                    f"slow call: {len(slow)} call(s) over half the {limit:.0f} s limit (max {max(c['s'] for c in slow):.1f} s)"
                )
        sizes = sorted(c["tokens_out"] for c in calls if c.get("tokens_out"))
        cap = params.get("max_tokens")
        if cap:
            # With a reply cap, a reply is long when it passes half the cap: an adapter that makes short probe calls
            # beside its answer (the triage fleet) made every answer 3x the median.
            long = [n for n in sizes if n > int(cap) / 2]
            if long:
                out.append(f"long reply: {len(long)} call(s) over half the {cap}-token cap (max {max(long)})")
        elif len(sizes) >= LONG_MIN_CALLS:
            median = (
                sizes[len(sizes) // 2]
                if len(sizes) % 2
                else (sizes[len(sizes) // 2 - 1] + sizes[len(sizes) // 2]) / 2
            )
            bar = max(LONG_FACTOR * median, LONG_FLOOR)
            long = [n for n in sizes if n > bar]
            if long:
                out.append(
                    f"long reply: {len(long)} call(s) over {LONG_FACTOR}x the arm's median of {median:g} tokens "
                    f"(max {max(long)})"
                )
        cut = [c for c in calls if c.get("finish_reason") == "length"]
        if cut:
            out.append(f"cut off: {len(cut)} reply(ies) hit max_tokens")
        dead = [c for c in calls if c.get("error") or c.get("answered") is False]
        if dead:
            out.append(f"no answer: {len(dead)} call(s) failed or came back empty")
    return out


def bill_of(res: Any) -> float | None:
    """What the provider billed for this result (its `meta["usage"]["cost"]`, as the bundled provider keeps it), or None."""
    usage = (getattr(res, "meta", None) or {}).get("usage")
    cost = usage.get("cost") if isinstance(usage, dict) else None
    return float(cost) if isinstance(cost, (int, float)) else None


def reply_text(output: str, full: bool) -> str:
    """One reply as printed: its first REPLY_EXCERPT characters (all with `--replies`), indented under its item."""
    shown = output if full or len(output) <= REPLY_EXCERPT else output[:REPLY_EXCERPT]
    more = "" if shown == output else f" ... (+{len(output) - len(shown)} ch; --replies for all)"
    return "      reply: " + (shown + more).replace("\n", "\n             ")


def spend_line(spent: float, billed: float, calls: int, unpriced: int) -> str:
    """What the smoke spent and on what basis: the same words `evh run` uses for its own spend."""
    from evaluation_harness.run import spend_basis  # noqa: PLC0415

    if unpriced == calls:
        return (
            "spent: unknown (the adapter reported no cost: no bill from the provider and no "
            "usd_per_mtok_in / usd_per_mtok_out in the config)"
        )
    base = f"spent ${spent:.6f} on {calls} call(s)"
    if spent <= 0:
        return base + " (the arm reports no cost: nothing paid)"
    return f"{base} ({spend_basis(billed, spent - billed)})" + (
        f"; {unpriced} call(s) reported no cost" if unpriced else ""
    )


def projection(items: list[dict[str, Any]], n_items: int) -> dict[str, Any]:
    """The full run from the smoke: about how long and how much, from the mean and the slowest item."""
    secs = [i["s"] for i in items if i.get("s") is not None]
    costs = [i.get("cost_usd") or 0.0 for i in items]
    if not secs:
        return {}
    return {
        "items": n_items,
        "minutes": round(statistics.fmean(secs) * n_items / 60, 1),
        "worst_minutes": round(max(secs) * n_items / 60, 1),
        "usd": round(statistics.fmean(costs) * n_items, 4),
    }


def main() -> int:
    """Smoke one arm; exit 0 on SMOKE PASS, 1 on SMOKE CHECK."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--items", type=int, default=3, help="how many of the dataset's first items (default 3)")
    ap.add_argument("--no-record", action="store_true", help="do not write the report into the model record")
    ap.add_argument(
        "--replies",
        action="store_true",
        help=f"print each reply whole (default: its first {REPLY_EXCERPT} characters)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr): result.values has status, flags, "
        "spent_usd, cost_basis (bill, price, mixed or none), calls, projection and items (with each reply)",
    )
    args = ap.parse_args()
    with _jsonout.collect("arm-smoke", args.json, live=sys.stderr):
        return _smoke(args)


def _smoke(args: argparse.Namespace) -> int:
    if not _store.is_file(args.config):
        die(f"no config at {args.config}", "not-found")
    import yaml  # noqa: PLC0415

    cfg = yaml.safe_load(_store.read_text(args.config, encoding="utf-8")) or {}
    try:
        cfg = _models.resolve(cfg, DATA)
    except ValueError as exc:
        die(f"{args.config}: {exc}", "invalid-file")
    call_system, score, *_ = load_adapter(cfg.get("adapter"), args.config)
    ds = load_dataset(cfg["dataset_id"])
    from evaluation_harness import _seal  # noqa: PLC0415

    _seal.refuse_if_sealed(cfg["dataset_id"], "a smoke test", cfg.get("config_id"))
    mat = MATERIALIZED / ds["dataset_id"]
    params = dict(cfg.get("params") or {})
    rec = _models.find(DATA, cfg["model_record"]) if cfg.get("model_record") else None
    named = _models.deployment_of(rec, cfg["deployment"]) if rec and cfg.get("deployment") else None
    deployments = [named] if named else (rec or {}).get("deployments") or []
    params_for_flags = {
        **params,
        "_build_pinned": (not rec)
        or any(d.get("digest") or d.get("revision") or d.get("file_hash") for d in deployments),
        "_route": route_of(named),
    }

    from evaluation_harness.run import _reference_for  # noqa: PLC0415

    ref_dir, _tier = _reference_for(ds["dataset_id"])
    print(f"arm-smoke: {cfg['config_id']} on {ds['dataset_id']}, {args.items} item(s)")
    shown = {
        k: params[k]
        for k in (
            "model",
            "reasoning_effort",
            "max_tokens",
            "call_timeout_s",
            "temperature",
            "device",
            "precision",
        )
        if k in params
    }
    print(f"  settings: {shown or '(none set)'}" + (f"  · model record {cfg['model_record']}" if rec else ""))
    items: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    replies: dict[str, str] = {}
    first_output = None
    spent = billed = 0.0
    n_calls = unpriced = 0

    def pay(res: Any) -> None:
        """Count one call's cost: what it reports, and how much of that the provider billed."""
        nonlocal spent, billed, n_calls, unpriced
        n_calls += 1
        cost = getattr(res, "cost_usd", None)
        if cost is None:
            unpriced += 1
            return
        spent += cost
        bill = bill_of(res)
        billed += min(bill, cost) if bill is not None else 0.0

    for n, item in enumerate(ds["items"][: args.items]):
        text = _store.read_text(
            mat / (item.get("source_path") or item["item_id"]), encoding="utf-8", errors="replace"
        )
        row: dict[str, Any] = {"item": item["item_id"]}
        t0 = time.perf_counter()
        try:
            res = call_system(text, params)
            wall = time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001  (a smoke reports a failure, it does not stop on it)
            row.update(s=round(time.perf_counter() - t0, 2), error=f"{type(exc).__name__}: {exc}")
            items.append(row)
            print(f"  {item['item_id'][:48]:<48} FAILED {row['error'][:80]}")
            continue
        row["s"] = round((getattr(res, "latency_ms", None) or wall * 1000) / 1000, 2)
        pay(res)
        replies[item["item_id"]] = res.output or ""
        row["output_chars"] = len(res.output or "")
        row["cost_usd"] = getattr(res, "cost_usd", None)
        ref = None
        if ref_dir is not None and _store.is_file(ref_dir / f"{item['item_id']}.txt"):
            ref = _store.read_text(ref_dir / f"{item['item_id']}.txt", encoding="utf-8", errors="replace")
        try:
            scored = score(res.output, ref, text) if score_wants_source(score) else score(res.output, ref)
            row["scored"] = bool(scored)
        except Exception as exc:  # noqa: BLE001
            row.update(scored=False, score_error=f"{type(exc).__name__}: {exc}")
        item_calls = calls_of(res, wall)
        calls += item_calls
        facts = {k: v for k, v in (getattr(res, "meta", None) or {}).items() if k in ML_FACTS}
        if n == 0:
            first_output = res.output
            try:
                again = call_system(text, params)
                pay(again)
                row["deterministic"] = again.output == res.output
            except Exception:  # noqa: BLE001
                row["deterministic"] = None
        items.append(row)
        print(
            f"  {item['item_id'][:48]:<48} {row['s']:>7.2f} s  out {row['output_chars']:>6} ch"
            + (f"  {len(item_calls)} call(s)" if item_calls else "")
            + (f"  {facts}" if facts else "")
            + ("" if row.get("scored", True) else "  NOT SCORABLE")
        )
        print(reply_text(res.output or "", args.replies))
        for c in item_calls:
            print(
                f"      call {c.get('s') or 0:>6.2f} s  out {c.get('tokens_out')!s:>5} tok  reasoning "
                f"{c.get('reasoning_tokens') or c.get('reasoning_chars') or 0:>6}  end {c.get('finish_reason') or c.get('error')}"
            )
    del first_output
    proj = projection(items, len(ds["items"]))
    if proj:
        print(
            f"  full run: {proj['items']} items, about {proj['minutes']} min (slowest item x all: "
            f"{proj['worst_minutes']} min), about ${proj['usd']}"
        )
    print(f"  {spend_line(spent, billed, n_calls, unpriced)}")
    if items and items[0].get("deterministic") is True:
        print("  determinism: item 1 twice gave the same output: repeats on this machine will be identical")
    flags, accepted = _models.split_accepted(
        rec, flags_for(items, calls, params_for_flags), cfg.get("deployment")
    )
    status = "pass" if not flags else "check"
    basis = "none" if spent <= 0 else "bill" if billed >= spent else "price" if billed <= 0 else "mixed"
    cost = {"spent_usd": round(spent, 8), "cost_basis": basis, "calls": n_calls, "calls_unpriced": unpriced}
    print("SMOKE PASS" if not flags else "SMOKE CHECK")
    for f in flags:
        print(f"  - {f}")
    for f in accepted:
        kind = f.split(":", 1)[0]
        dep = _models.deployment_of(rec or {}, cfg.get("deployment") or "") or {}
        why = ((rec or {}).get("accepted") or {}).get(kind) or (dep.get("accepted") or {}).get(kind, "")
        print(f"  accepted: {f} ({why})")
    if rec is not None and not args.no_record:
        smoke = {
            "status": status,
            "at": now(),
            "flags": flags,
            "report": {"items": items, "calls": calls, "projection": proj, "settings": shown, **cost},
        }
        if accepted:
            smoke["accepted"] = accepted
        _models.update_record(
            DATA,
            cfg["model_record"],
            lambda doc: doc.setdefault("smokes", {}).__setitem__(cfg["config_id"], smoke),
        )
        path = _models.records_dir(DATA) / f"{cfg['model_record']}.yaml"
        print(f"  written into {path.relative_to(DATA.parent) if DATA.parent in path.parents else path}")
    _jsonout.values(
        {
            "status": status,
            "flags": flags,
            **cost,
            "projection": proj,
            "items": [
                {
                    **r,
                    "reply": replies.get(r["item"], "")
                    if args.replies
                    else replies.get(r["item"], "")[:REPLY_EXCERPT],
                }
                for r in items
            ],
        }
    )
    return 0 if not flags else EXIT_PROBLEMS


if __name__ == "__main__":
    raise SystemExit(main())
