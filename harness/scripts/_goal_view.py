"""What `evh goals --goal G` adds to a long table: a filter on its arms (--arms, --top), the paired test against
the leader as text, an arm's hypothesis beside it, and the same as named values for --json.

The decision (leader, contenders, recommended) is always made over every arm of the group; the filter only
chooses which rows are shown, and it never drops the baseline, the leader or the recommended arm.
"""

from __future__ import annotations

from fnmatch import fnmatchcase

from evaluation_harness.stats import fmt_p


def patterns(raw: list[str] | None) -> list[str]:
    """--arms values, repeatable and comma-separated, as one list of non-empty patterns."""
    return [p.strip() for chunk in raw or [] for p in chunk.split(",") if p.strip()]


def matches(arm: str, pats: list[str]) -> bool:
    """Whether the arm id (runs/<dataset>/<config_id>) or its config id fits a pattern: a glob when the
    pattern has *, ? or [, else a substring."""
    cfg = arm.rsplit("/", 1)[-1]
    return any(
        (fnmatchcase(cfg, p) or fnmatchcase(arm, p)) if any(c in p for c in "*?[") else p in arm for p in pats
    )


def select(rows: list[dict], pats: list[str], top: int | None, keep: set[str]) -> list[dict]:
    """The rows to show, in the goal's own order: those fitting a pattern (all, with none), the first `top` of
    them, and every row whose arm is in `keep` whatever the filter."""
    fit = [r for r in rows if not pats or matches(r["arm"], pats)]
    if top is not None:
        fit = fit[:top]
    shown = {r["arm"] for r in fit} | keep
    return [r for r in rows if r["arm"] in shown]


def vs_text(v: dict | None) -> str:
    """The paired test against the leader in a cell: '-0.031, p 0.002, significant: worse'."""
    if not v:
        return "—"
    delta = "—" if v.get("delta") is None else f"{v['delta']:+.3f}"
    p = "" if v.get("p") is None else f", p {fmt_p(v['p'])}"
    return f"{delta}{p}, {v.get('verdict') or '—'}"


def hypothesis_of(A, arm: str) -> dict | None:
    """The arm's hypothesis with whether it was named in advance, read across ALL its runs (the goal averages
    them; one run made before the hypothesis makes it "no", whichever run is newest); None without one. An adapter
    that cannot list an arm's runs answers from `arm_config`, its latest run."""
    from evaluation_harness import _hypothesis  # noqa: PLC0415

    dirs_fn = getattr(A, "_dirs", None)
    runs = [m for d in (dirs_fn(arm) if callable(dirs_fn) else []) if (m := _metrics_json(d)) is not None]
    if runs:
        found = _hypothesis.across_runs(runs)
    else:
        fn = getattr(A, "arm_config", None)
        cfg = (fn(arm) if callable(fn) else None) or {}
        h = cfg.get("hypothesis")
        found = (
            {**h, **{k: (cfg.get("hypothesis_in_advance") or {}).get(k) for k in ("named", "commit")}}
            if isinstance(h, dict)
            else None
        )
    if not found:
        return None
    named = found.get("named")
    return {
        **{k: v for k, v in found.items() if k not in ("named", "why")},
        "named_in_advance": "yes" if named is True else "no" if named is False else "not determinable",
        "commit": found.get("commit"),
    }


def _metrics_json(run_dir) -> dict | None:
    """A run directory's metrics.json, or None when it has none or it does not parse."""
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    f = Path(run_dir) / "metrics.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except (OSError, ValueError):
        return None


def hypothesis_text(h: dict | None) -> str:
    """An arm's hypothesis as the goals table shows it: its direction, against which arm, on which
    measure, and whether it was named in advance; "" when the arm has none."""
    if not h:
        return ""
    direction = str(h.get("direction") or "")
    shown = {"better": "better than", "worse": "worse than", "no-worse": "no worse than"}.get(
        direction, direction
    )
    return f"{shown} {h.get('against')} on {h.get('measure')}; named in advance: {h['named_in_advance']}"


def group_values(
    *,
    dataset: str,
    scored_against: str,
    measure: str,
    dec: dict,
    rows: list[dict],
    shown: list[dict],
    axes: list[dict],
    baseline: str | None,
    hypotheses: dict[str, dict | None],
    retired: dict[str, str | None],
    arms_filter: list[str],
    top: int | None,
) -> dict:
    """One group of the table as named values with raw numbers (the table's cells are display strings)."""
    leader, rec = dec.get("leader"), dec.get("recommended")
    contenders = set(dec.get("contenders") or [])
    vs = {
        r["arm"]: (dec["rows"].get(r["arm"], {}).get("quality") or {}).get("vs_leader") or None for r in rows
    }
    return {
        "dataset": dataset,
        "scored_against": scored_against,
        "measure": measure,
        "direction": (dec["axes"][0]["direction"] if dec.get("axes") else None),
        "leader": leader,
        "baseline": baseline,
        "contenders": list(dec.get("contenders") or []),
        "recommended": rec,
        "shown_only": bool(dec.get("shown_only")),
        "vs_leader": vs,
        "arms_total": len(rows),
        "arms_shown": len(shown),
        "arms_left_out": len(rows) - len(shown),
        "filter": {"arms": arms_filter, "top": top},
        "arms": [
            {
                "arm": r["arm"],
                "label": r["label"],
                "mean": r["mean"],
                "n": r["n"],
                "baseline": r["arm"] == baseline,
                "leader": r["arm"] == leader,
                "recommended": r["arm"] == rec,
                "contender": r["arm"] in contenders,
                "retired_in": retired.get(r["arm"]) or None,
                "flags": list(r["flags"]) + dec["out"].get(r["arm"], []),
                "vs_leader": vs[r["arm"]],
                "axes": {ax["name"]: dec["rows"][r["arm"]][ax["name"]] for ax in axes},
                "hypothesis": hypotheses.get(r["arm"]),
            }
            for r in shown
        ],
    }
