"""The judge panel: promote finalists on a cheap metric, judge their outputs, aggregate, report.

    evh judge --config judge_panel.yaml --use-fake-judge   # no API key
    evh judge --config judge_panel.yaml                    # the judges in the config (Claude)

`evh init --tutorial` puts an example config at tutorial/judge_panel.yaml; in a checkout,
`make judge` runs harness/config.example.yaml with the fake judge.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import logging
import pathlib
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

# The harness's own run reading, so the panel finds runs where every command does (the
# project, EVAL_RUNS_DIR) and picks the metric the same way.
from evaluation_harness._common import ROOT, RUNS
from evaluation_harness._runs import default_metric, direction, item_rows, runs_on
from evaluation_harness.panel_judges import ItemScore, build_judge

logger = logging.getLogger("eval-harness")


# ---------------------------------------------------------------------------
# Domain types — kept narrow for clarity. Adapt as needed.


@dataclass
class RunCandidate:
    """One candidate run. `primary_score` is the cheap metric used for triage."""

    run_id: str
    stratum: str
    primary_score: float
    #: The run's directory, when the candidate is a real run: its outputs are what is judged.
    run_dir: str | None = None


@dataclass
class StratumPromotion:
    """Per-stratum promotion summary, for traceability in the report."""

    name: str
    leader_score: float
    floor: float
    promoted: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FinalistAggregate:
    """Per-finalist aggregate after judging."""

    run_id: str
    stratum: str
    primary_judge: str
    cross_judge: str | None
    n_items: int
    primary_mean_per_dim: dict[str, float] = field(default_factory=dict)
    cross_mean_per_dim: dict[str, float] = field(default_factory=dict)
    primary_overall_mean: float = 0.0
    cross_overall_mean: float | None = None
    agreement_rate: float | None = None
    contested: bool = False
    total_cost_usd: float = 0.0
    errors: int = 0


# ---------------------------------------------------------------------------
# Step 1 — Promote


def promote_finalists(
    candidates: Iterable[RunCandidate],
    *,
    per_stratum_top_k: int,
    floor_fraction: float,
    overall_cap: int,
    carte_blanche: Iterable[str] = (),
) -> tuple[list[RunCandidate], list[StratumPromotion]]:
    """Top-K per stratum, drop below floor, cap globally, carte-blanche overrides.

    The carte-blanche override exists because the cheap metric is the very
    thing the LLM judging is supposed to bypass — excluding a candidate on
    a metric you don't trust is the bias you're trying to fix.
    """
    carte_blanche_terms = tuple(s for s in carte_blanche if s)
    by_stratum: dict[str, list[RunCandidate]] = {}
    for c in candidates:
        by_stratum.setdefault(c.stratum, []).append(c)

    promoted: list[RunCandidate] = []
    summary: list[StratumPromotion] = []
    for name, runs in by_stratum.items():
        runs_sorted = sorted(runs, key=lambda r: r.primary_score, reverse=True)
        if not runs_sorted:
            continue
        leader = runs_sorted[0].primary_score
        floor = floor_fraction * leader
        promo = StratumPromotion(name=name, leader_score=leader, floor=floor)

        for run in runs_sorted[:per_stratum_top_k]:
            if run.primary_score >= floor:
                promoted.append(run)
                promo.promoted.append(run.run_id)
            else:
                promo.rejected.append(
                    {
                        "run_id": run.run_id,
                        "reason": f"below_floor ({run.primary_score:.4f} < {floor:.4f})",
                        "primary_score": run.primary_score,
                    }
                )
        for rank, run in enumerate(runs_sorted[per_stratum_top_k:], start=per_stratum_top_k + 1):
            promo.rejected.append(
                {
                    "run_id": run.run_id,
                    "reason": f"not_top_{per_stratum_top_k} (rank={rank})",
                    "primary_score": run.primary_score,
                }
            )
        summary.append(promo)

    if len(promoted) > overall_cap:
        promoted = sorted(promoted, key=lambda r: r.primary_score, reverse=True)[:overall_cap]
        kept = {r.run_id for r in promoted}
        for s in summary:
            s.promoted = [rid for rid in s.promoted if rid in kept]

    if carte_blanche_terms:
        promoted_ids = {r.run_id for r in promoted}
        all_candidates = [c for cs in by_stratum.values() for c in cs]
        for cand in all_candidates:
            if cand.run_id in promoted_ids:
                continue
            if any(term in cand.run_id for term in carte_blanche_terms):
                promoted.append(cand)
                promoted_ids.add(cand.run_id)
                for s in summary:
                    if s.name == cand.stratum:
                        s.promoted.append(cand.run_id)
                        s.rejected = [r for r in s.rejected if r.get("run_id") != cand.run_id]
                        break

    return promoted, summary


# ---------------------------------------------------------------------------
# Step 2 — Judge (with cost cap, partial-result preservation)


def judge_finalist(
    *,
    finalist: RunCandidate,
    judge,
    items: list[dict[str, Any]],
    dimensions: list[str],
    cost_budget_remaining: float | None,
) -> tuple[list[ItemScore], float, int]:
    """Score every item of `finalist` with `judge`.

    Aborts mid-finalist if cost cap drops to <= 0. Caller's responsibility
    to track cumulative spend across finalists.
    """
    scores: list[ItemScore] = []
    total_cost = 0.0
    errors = 0
    remaining = cost_budget_remaining

    for item in items:
        score = judge.score(
            run_id=finalist.run_id,
            item_id=str(item.get("item_id", f"item_{len(scores)}")),
            item_content=str(item.get("content", "")),
            dimensions=dimensions,
        )
        scores.append(score)
        total_cost += score.total_cost_usd
        errors += len(score.errors)
        if remaining is not None:
            remaining -= score.total_cost_usd
            if remaining <= 0:
                logger.warning(
                    "Cost budget exhausted mid-finalist %s after %d items",
                    finalist.run_id,
                    len(scores),
                )
                break
    return scores, total_cost, errors


# ---------------------------------------------------------------------------
# Step 3 — Aggregate


def aggregate_finalist(
    *,
    finalist: RunCandidate,
    primary_judge_name: str,
    primary_scores: list[ItemScore],
    cross_judge_name: str | None = None,
    cross_scores: list[ItemScore] | None = None,
    contested_threshold: float = 0.5,
    agreement_tolerance: int = 1,
    dimensions: Iterable[str] = (),
) -> FinalistAggregate:
    """Reduce per-item scores to per-dimension means + contested flag."""

    def _per_dim_mean(scores: list[ItemScore], dim: str) -> float | None:
        vals = [s.per_dimension[dim] for s in scores if dim in s.per_dimension]
        return (sum(vals) / len(vals)) if vals else None

    primary_per_dim_raw = {d: _per_dim_mean(primary_scores, d) for d in dimensions}
    primary_per_dim = {d: v for d, v in primary_per_dim_raw.items() if v is not None}
    primary_overall = sum(primary_per_dim.values()) / len(primary_per_dim) if primary_per_dim else 0.0
    total_cost = sum(s.total_cost_usd for s in primary_scores)
    n_err = sum(len(s.errors) for s in primary_scores)

    cross_per_dim: dict[str, float] = {}
    cross_overall: float | None = None
    agree_rate: float | None = None
    contested = False
    if cross_scores is not None:
        cross_per_dim_raw = {d: _per_dim_mean(cross_scores, d) for d in dimensions}
        cross_per_dim = {d: v for d, v in cross_per_dim_raw.items() if v is not None}
        if cross_per_dim:
            cross_overall = sum(cross_per_dim.values()) / len(cross_per_dim)
            contested = abs(primary_overall - cross_overall) > contested_threshold
        agree_rate = _pairwise_agreement_rate(primary_scores, cross_scores, tolerance=agreement_tolerance)
        total_cost += sum(s.total_cost_usd for s in cross_scores)
        n_err += sum(len(s.errors) for s in cross_scores)

    return FinalistAggregate(
        run_id=finalist.run_id,
        stratum=finalist.stratum,
        primary_judge=primary_judge_name,
        cross_judge=cross_judge_name,
        n_items=len(primary_scores),
        primary_mean_per_dim=primary_per_dim,
        cross_mean_per_dim=cross_per_dim,
        primary_overall_mean=primary_overall,
        cross_overall_mean=cross_overall,
        agreement_rate=agree_rate,
        contested=contested,
        total_cost_usd=total_cost,
        errors=n_err,
    )


def _pairwise_agreement_rate(
    primary: list[ItemScore],
    cross: list[ItemScore],
    *,
    tolerance: int,
) -> float | None:
    """Per-(item, dim) agreement (exact-or-adjacent within tolerance)."""
    cross_by_item = {s.item_id: s for s in cross}
    total = 0
    agree = 0
    for ps in primary:
        cs = cross_by_item.get(ps.item_id)
        if cs is None:
            continue
        for dim, p_score in ps.per_dimension.items():
            c_score = cs.per_dimension.get(dim)
            if c_score is None:
                continue
            total += 1
            if abs(p_score - c_score) <= tolerance:
                agree += 1
    return (agree / total) if total else None


# ---------------------------------------------------------------------------
# Step 4 — Report


def write_report(
    *,
    output_dir: Path,
    finalists: list[FinalistAggregate],
    promotion_summary: list[StratumPromotion],
    config: dict[str, Any],
) -> None:
    """Write finalists.jsonl + report.json + report.md."""
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / "finalists.jsonl").open("w", encoding="utf-8") as fh:
        for fin in finalists:
            fh.write(json.dumps(asdict(fin), default=str) + "\n")

    report = {
        "config": config,
        "git_sha": _git_sha(),
        "promotion": [asdict(p) for p in promotion_summary],
        "finalists": [asdict(f) for f in finalists],
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))

    md = _markdown_report(finalists, promotion_summary)
    (output_dir / "report.md").write_text(md)

    logger.info("Report written to %s", output_dir)


def _markdown_report(
    finalists: list[FinalistAggregate],
    promotion_summary: list[StratumPromotion],
) -> str:
    lines = ["# Eval report", ""]
    for s in promotion_summary:
        lines.append(f"## Stratum: {s.name}")
        lines.append(f"- Leader score: {s.leader_score:.4f} (floor: {s.floor:.4f})")
        lines.append(f"- Promoted: {', '.join(s.promoted) or '(none)'}")
        if s.rejected:
            lines.append("- Rejected:")
            for r in s.rejected:
                lines.append(f"  - {r['run_id']} — {r['reason']}")
        lines.append("")

    lines.append("## Finalists (by primary overall mean)")
    lines.append("")
    lines.append("| Run | Stratum | Primary | Cross | Agreement | Contested | Cost | Errors |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for f in sorted(finalists, key=lambda x: -x.primary_overall_mean):
        cross = f"{f.cross_overall_mean:.2f}" if f.cross_overall_mean is not None else "-"
        agree = f"{f.agreement_rate:.0%}" if f.agreement_rate is not None else "-"
        contested = "⚠" if f.contested else ""
        lines.append(
            f"| {f.run_id} | {f.stratum} | {f.primary_overall_mean:.2f} | "
            f"{cross} | {agree} | {contested} | ${f.total_cost_usd:.4f} | {f.errors} |"
        )
    return "\n".join(lines) + "\n"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# main


def _synth_items(run_id: str, n: int = 5) -> list[dict[str, Any]]:
    """Placeholder items for the literal `runs:` demo list, which names no real run."""
    return [{"item_id": f"{run_id}-{i}", "content": f"Synthetic item {i} for {run_id}"} for i in range(n)]


def _items_of(finalist: RunCandidate, n: int) -> list[dict[str, Any]]:
    """What the judges read: the finalist run's own stored outputs, first `n` items in
    prediction order. It judged `_synth_items` for every candidate, real runs included, so
    a billed panel scored placeholder text."""
    if finalist.run_dir is None:
        return _synth_items(finalist.run_id, n=n)
    d = Path(finalist.run_dir)
    items: list[dict[str, Any]] = []
    for row in item_rows(d):
        out = d / "outputs" / f"{row['item_id']}.txt"
        if out.is_file():
            items.append({"item_id": row["item_id"], "content": out.read_text(encoding="utf-8")})
        if len(items) == n:
            break
    if not items:
        raise SystemExit(f"{finalist.run_id}: no stored outputs under {d / 'outputs'} to judge")
    return items


def _candidates_from(cfg: dict[str, Any]) -> list[RunCandidate]:
    """Build candidates from real runs when asked, else from the config list.

    The panel used to accept ONLY a hand-written `runs:` block, which meant it
    could not judge the runs the rest of this harness produces — you had to
    copy ids and scores across by hand. Setting

        runs_from: data/runs          # any path, or the string "runs"
        primary_metric: overlap_f1    # which score ranks them
        dataset_id: my_v1             # optional filter

    reads `metrics.json` from each run directory instead. The stratum defaults
    to the config_id, so repeats of one arm group together.
    """
    src = cfg.get("runs_from")
    if not src:
        return [RunCandidate(**r) for r in cfg["runs"]]

    # "runs" is the runs directory every command reads (EVAL_RUNS_DIR, else <project>/data/runs);
    # a relative path is the PROJECT's, not this file's directory's.
    root = RUNS if src == "runs" else pathlib.Path(src)
    if not root.is_absolute():
        root = ROOT / root
    if not root.is_dir():
        raise SystemExit(f"runs_from: no such directory: {root}")

    want_ds: str | None = cfg.get("dataset_id")
    metric: str | None = cfg.get("primary_metric")
    if not metric:
        if not want_ds:
            raise SystemExit(
                "runs_from: name dataset_id (its runs' primary metric ranks them) or primary_metric"
            )
        # The metric every command defaults to: the primary metric the runs recorded.
        metric = default_metric(want_ds, runs_dir=root)
    runs = runs_on(want_ds, runs_dir=root)
    if direction(runs, metric):
        raise SystemExit(
            f"{metric!r} is lower-is-better; the panel promotes the HIGHEST scores within a "
            "floor of the leader, so name a quality metric as primary_metric"
        )
    out: list[RunCandidate] = []
    for d, m in runs:
        scores = m.get("scores", {})
        if metric not in scores:
            continue
        out.append(
            RunCandidate(
                run_id=m["run_id"],
                stratum=m["config_id"],
                primary_score=float(scores[metric]),
                run_dir=str(d),
            )
        )
    if not out:
        raise SystemExit(
            f"runs_from={root} matched no runs"
            + (f" on dataset {want_ds}" if want_ds else "")
            + (f" carrying metric {metric!r}" if metric else "")
        )
    logger.info("Loaded %d candidate run(s) from %s", len(out), root)
    return out


def main(argv: list[str]) -> int:
    """Promote, judge, aggregate, and report on finalists."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--use-fake-judge", action="store_true")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())

    candidates = _candidates_from(cfg)
    promoted, promo_summary = promote_finalists(
        candidates,
        per_stratum_top_k=cfg["promotion"]["per_stratum_top_k"],
        floor_fraction=cfg["promotion"]["floor_fraction"],
        overall_cap=cfg["promotion"]["overall_cap"],
        carte_blanche=cfg["promotion"].get("carte_blanche", []),
    )
    logger.info("Promoted %d finalists across %d strata", len(promoted), len(promo_summary))

    primary = build_judge(cfg["judging"]["primary_judge"], use_fake=args.use_fake_judge)
    if primary is None:
        raise SystemExit("judging.primary_judge is required: name the judge that scores every finalist")
    cross = build_judge(cfg["judging"].get("cross_judge"), use_fake=args.use_fake_judge)
    dims = cfg["judging"]["dimensions"]
    cost_remaining = float(cfg["judging"]["cost_cap_usd"])
    max_items = int(cfg["judging"]["max_items_per_finalist"])

    aggregates: list[FinalistAggregate] = []
    for finalist in promoted:
        items = _items_of(finalist, n=max_items)

        primary_scores, primary_cost, _ = judge_finalist(
            finalist=finalist,
            judge=primary,
            items=items,
            dimensions=dims,
            cost_budget_remaining=cost_remaining,
        )
        cost_remaining -= primary_cost

        cross_scores = None
        if cross is not None and cost_remaining > 0:
            cross_scores, cross_cost, _ = judge_finalist(
                finalist=finalist,
                judge=cross,
                items=items,
                dimensions=dims,
                cost_budget_remaining=cost_remaining,
            )
            cost_remaining -= cross_cost

        aggregates.append(
            aggregate_finalist(
                finalist=finalist,
                primary_judge_name=primary.name,
                primary_scores=primary_scores,
                cross_judge_name=cross.name if cross else None,
                cross_scores=cross_scores,
                contested_threshold=cfg["aggregation"]["contested_threshold"],
                agreement_tolerance=cfg["aggregation"]["agreement_tolerance"],
                dimensions=dims,
            )
        )
        if cost_remaining <= 0:
            logger.warning("Global cost cap hit after %d/%d finalists", len(aggregates), len(promoted))
            break

    # The project's, as runs are: relative to the shell's directory it landed wherever evh ran.
    output_dir = ROOT / cfg["output_root"] / cfg["tag"]
    write_report(
        output_dir=output_dir,
        finalists=aggregates,
        promotion_summary=promo_summary,
        config=cfg,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
