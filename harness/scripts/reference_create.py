#!/usr/bin/env python3
"""Establish ground truth for a dataset, so later runs have something to be scored against.

THE CHICKEN AND EGG: you cannot measure quality without something to measure
against, and most projects have no ground truth for the thing they actually
ship. The usual answers:

  gold    a human wrote it. Expensive, slow, and the only thing you can
          honestly call correct.
  silver  a model you trust wrote it. Cheap, plentiful, and NOT the same
          thing — it encodes that model's opinion, including its mistakes.

This script produces SILVER by default and says so in the manifest. That is a
legitimate starting point: a consistent reference lets you rank arms against
each other today, and you can replace items with human-authored gold later
without changing anything downstream.

What it must never do is let you forget which you have. `make validate` reads
the manifest, and every run scored against silver carries that fact.

    evh reference-create --dataset-id my_v1 --from-run <run_id>     # a run you already paid for
    evh reference-create --dataset-id my_v1 --config data/configs/golden.yaml
    evh reference-create --dataset-id my_v1 --config ... --tier gold   # human-reviewed

--from-run is the usual path: run the expensive model as an arm, read its results, then make
its outputs the reference. It calls nothing, and the reference records the run it came from
(config, fingerprint, build). --config authors the reference in a pass of its own, one call per
item. Either way an output that is empty or stopped at max_tokens is refused: it would be the
answer every later run is scored against.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from _common import (
    MATERIALIZED,
    REFERENCES,
    ROOT,
    RUNS,
    die,
    how,
    load_dataset,
    now,
    read_json,
    write_json,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")

# NOT `from adapter import call_system`. That hard-wired the BUNDLED adapter and ignored the
# config's `adapter:` key, which only experiment_run honoured — so a reference authored from
# an example's config ran the example's MODEL through the core's CODE.
#
# It produced a wrong finding before it was noticed. The bundled adapter reads
# `params.get("prompt", "Summarise:")`; the example declares `prompt_file:`, a key only the
# example's adapter understands. So Opus was asked a bare "Summarise:" and wrote 207 words
# against a 37-word human reference — which was read as "Opus ignores instructions" when it
# had simply never been given one. A reference is the thing everything else is scored
# against; authoring it with different code than the arms run is not a small inconsistency.
from _adapter import load_adapter


def _repo_relative(path: object) -> str:
    """Paths in a committed artifact are relative to the repo, never to a home directory.

    An absolute path leaks the author's username into a public repo and is meaningless
    on anybody else's machine. This manifest carried
    `/Users/<name>/projects/.../adapter.py`, and the harness's own self-test flags it.
    """
    try:
        return str(Path(str(path)).resolve().relative_to(ROOT))
    except (ValueError, OSError):
        return Path(str(path)).name


def _identity(hook: object, params: dict) -> object:
    """The adapter's own identity record, or a stated absence. Never a guess."""
    if not callable(hook):
        return {"identity_declared": False}
    try:
        return {"identity_declared": True, **(hook(params) or {})}
    except Exception as exc:  # noqa: BLE001 - provenance must not kill authoring
        return {"identity_declared": False, "error": f"{type(exc).__name__}: {exc}"}


def _unusable(rows: list[tuple[str, str, object]], max_tokens: object) -> tuple[list[str], list[str]]:
    """The items whose output is empty, and those that stopped at max_tokens.

    Both are refused. Opus at max_tokens 80 wrote 19 of 20 news summaries that stopped
    mid-sentence, and one reply that was empty, and they were frozen as the silver every other
    arm was scored against, with no word from the harness.
    """
    empty = [item for item, text, _ in rows if not text.strip()]
    cap = int(max_tokens) if isinstance(max_tokens, (int, float)) and max_tokens > 0 else None
    cut = [
        item
        for item, text, out in rows
        if text.strip() and cap and isinstance(out, (int, float)) and out >= cap
    ]
    return empty, cut


def _refuse_unusable(
    rows: list[tuple[str, str, object]], max_tokens: object, allow_cut_off: bool, where: str
) -> None:
    """Die on an empty output, or on outputs cut off at max_tokens unless they are allowed."""
    empty, cut = _unusable(rows, max_tokens)
    if empty:
        die(
            f"REFUSED: {len(empty)} empty output(s) ({', '.join(empty[:8])}"
            + (" ..." if len(empty) > 8 else "")
            + f").\n  An empty reference is never the right answer. {where}"
        )
    if cut and not allow_cut_off:
        die(
            f"REFUSED: {len(cut)} of {len(rows)} output(s) stopped at max_tokens={max_tokens} "
            f"({', '.join(cut[:8])}" + (" ..." if len(cut) > 8 else "") + ").\n"
            "  A reference cut off mid-answer marks every complete answer down. Raise max_tokens\n"
            f"  in the config (a new config_id) and run it again. {where}\n"
            "  (--allow-cut-off freezes them anyway, for outputs that end at the cap by design.)"
        )


def _from_run(run_id: str, dataset_id: str, items: list[dict], args: argparse.Namespace) -> tuple[list, dict]:
    """A finished run's outputs, and the provenance its reference carries.

    The refusals are run-promote's: a reference is a decision every later score depends on,
    so it must name the code and the system that produced it.
    """
    run_dir = RUNS / run_id
    if not (run_dir / "metrics.json").is_file():
        hint = " (it has no metrics.json: it did not finish)" if run_dir.is_dir() else ""
        die(f"no finished run {run_id!r} under {RUNS}{hint}")
    m = read_json(run_dir / "metrics.json")
    if m.get("dataset_id") != dataset_id:
        die(f"REFUSED: run {run_id} is on {m.get('dataset_id')!r}, not {dataset_id!r}")
    if (m.get("derived") or {}).get("kind"):
        die(
            f"REFUSED: run {run_id} is {m['derived']['kind']}d from {m['derived'].get('from')}; "
            "make the reference from the run that produced the outputs"
        )
    build = m.get("build") or {}
    if build.get("ref", "unknown") == "unknown" and not args.allow_unknown_build:
        die(
            f"REFUSED: run {run_id} does not identify its build, so the reference could not say\n"
            "  which system wrote it. Set EVAL_BUILD_REF and run the arm again\n"
            "  (--allow-unknown-build overrides)."
        )
    if build.get("dirty") and not args.allow_dirty:
        die(
            f"REFUSED: run {run_id} was produced by a dirty tree; build.ref={str(build.get('ref', '?'))[:12]}\n"
            "  does not describe what ran. Commit, run the arm again, and use that run\n"
            "  (--allow-dirty overrides)."
        )
    tokens: dict[str, object] = {}
    pred = run_dir / "predictions.jsonl"
    if pred.is_file():
        for line in pred.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                tokens[row.get("item_id")] = row.get("tokens_out")
    rows, missing = [], []
    for item in items:
        f = run_dir / "outputs" / f"{item['item_id']}.txt"
        if not f.is_file():
            missing.append(item["item_id"])
            continue
        rows.append((item["item_id"], f.read_text(encoding="utf-8"), tokens.get(item["item_id"])))
    if missing:
        die(
            f"REFUSED: run {run_id} has no output for {len(missing)} item(s) "
            f"({', '.join(missing[:8])}" + (" ..." if len(missing) > 8 else "") + ")"
        )
    params = dict(m.get("params") or {})
    _refuse_unusable(rows, params.get("max_tokens"), args.allow_cut_off, f"Run {run_id}.")
    source = {
        "run_id": run_id,
        "config_id": m.get("config_id"),
        "fingerprint_hash": (m.get("fingerprint") or {}).get("hash"),
        "build": build,
        "reference_tier": m.get("reference_tier"),
        "cost_usd": (m.get("scores") or {}).get("total_cost_usd"),
    }
    meta = {
        "authored_by": m.get("config_id"),
        "authored_with": m.get("adapter"),
        "model": params.get("model", params.get("provider", "unknown")),
        "system_under_test": ((m.get("fingerprint") or {}).get("system_under_test") or {}).get("model"),
        "params": params,
        "from_run": source,
        "cost_usd": 0.0,
    }
    return rows, meta


def main() -> int:
    """Create a reference (gold or silver) for a dataset."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--from-run",
        metavar="RUN_ID",
        help="make a finished run's outputs the reference: no calls, and the reference records the run",
    )
    src.add_argument("--config", type=Path, help="author the reference in a pass of its own, with this arm")
    ap.add_argument(
        "--tier",
        choices=["gold", "silver"],
        default="silver",
        help="gold = human-authored or human-reviewed; silver = model-generated (default)",
    )
    ap.add_argument("--limit", type=int, help="only the first N items — keep the first pass cheap")
    ap.add_argument("--force", action="store_true", help="overwrite existing references")
    ap.add_argument(
        "--allow-cut-off",
        action="store_true",
        help="freeze outputs that stopped at max_tokens (refused by default)",
    )
    ap.add_argument("--allow-dirty", action="store_true", help="--from-run: a run from a dirty tree")
    ap.add_argument(
        "--allow-unknown-build", action="store_true", help="--from-run: a run whose build is unknown"
    )
    args = ap.parse_args()
    if args.from_run and args.tier == "gold":
        die(
            "REFUSED: gold is what a person wrote or checked, and a run is a model's output.\n"
            f"  Make it silver, review the items, and copy the ones you would sign into\n"
            f"  {REFERENCES / 'gold' / args.dataset_id}/<item_id>.txt."
        )

    ds = load_dataset(args.dataset_id)
    items = ds["items"][: args.limit] if args.limit else ds["items"]
    out_dir = REFERENCES / args.tier / args.dataset_id
    if out_dir.exists() and not args.force:
        die(
            f"{out_dir} already exists.\n"
            "  References are frozen — every score already reported was measured\n"
            "  against these. Use a new dataset version, or --force if nothing cites them."
        )

    if args.from_run:
        rows, meta = _from_run(args.from_run, args.dataset_id, items, args)
        print(f"{args.tier} reference(s) for {len(rows)} item(s) from run {args.from_run}: no calls")
    else:
        rows, meta = _author(args, items)

    # Write into a sibling .partial/ and rename at the end, so a failure midway leaves NOTHING
    # under the reference's name: a crash on item 1 used to leave an empty frozen directory, and
    # the refusal above then blocked the retry.
    final_dir = out_dir
    out_dir = out_dir.with_name(out_dir.name + ".partial")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for item_id, text, _ in rows:
        (out_dir / f"{item_id}.txt").write_text(text, encoding="utf-8")
    write_json(
        out_dir / "manifest.json",
        {
            "dataset_id": args.dataset_id,
            "tier": args.tier,
            **meta,
            "created_at": now(),
            "n_items": len(rows),
            "caveat": (
                "GOLD: human-authored or human-reviewed."
                if args.tier == "gold"
                else "SILVER: model-generated. It encodes that model's opinion, including "
                "its mistakes. Good enough to RANK arms against each other; not the same "
                "thing as correct. Say so wherever a number scored against it is published."
            ),
        },
    )
    if final_dir.exists():
        shutil.rmtree(final_dir)
    out_dir.rename(final_dir)

    cost = meta.get("cost_usd")
    print(f"\n{final_dir}  ({len(rows)} item(s), tier={args.tier}" + (f", ${cost:.4f}" if cost else "") + ")")
    gold = REFERENCES / "gold" / args.dataset_id
    if args.tier == "silver" and gold.is_dir():
        print(
            f"Gold exists for {args.dataset_id} and outranks silver: new runs keep scoring against gold.\n"
            "Score against this one with:  "
            + how(
                f"evh rescore --dataset-id {args.dataset_id} --reference-id silver/{args.dataset_id} --out data/runs-silver",
                f"make rescore DATASET_ID={args.dataset_id} REFERENCE=silver/{args.dataset_id} OUT=data/runs-silver",
            )
        )
    else:
        print("Runs against this dataset will now be scored against it automatically.")
    print(
        f"Commit it before the next run (git add {_repo_relative(final_dir)}): an uncommitted\n"
        "reference makes every run after it dirty, and a dirty run cannot become a baseline or\n"
        "a reference."
    )
    if meta.get("authored_by"):
        print(
            f"{meta['authored_by']} wrote it: scored against it, that arm is graded against its own\n"
            "outputs, and the leaderboard marks its row."
        )
    return 0


def _author(args: argparse.Namespace, items: list[dict]) -> tuple[list, dict]:
    """Author the reference with a config's arm, one call per item."""
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8")) or {}
    params = dict(cfg.get("params") or {})
    # Same adapter the arms would run, resolved the same way, relative to the same config.
    call_system, _score, adapter_id, _path, warmup, fp_hook = load_adapter(cfg.get("adapter"), args.config)
    if warmup is not None:
        warmup(params)
    mat = MATERIALIZED / args.dataset_id
    if not mat.is_dir():
        die(
            "materialize first:  "
            + how(
                f"evh dataset-materialize --dataset-id {args.dataset_id}",
                f"make dataset-materialize DATASET_ID={args.dataset_id}",
            )
        )
    total_cost, n_priced = 0.0, 0
    print(f"authoring {len(items)} {args.tier} reference(s) with {cfg.get('config_id', args.config.name)}")
    rows = []
    for i, item in enumerate(items, 1):
        rel = item.get("source_path") or item["item_id"]
        src = mat / rel
        if not src.is_file():
            die(f"missing materialized item: {src}")
        res = call_system(src.read_text(encoding="utf-8", errors="replace"), params)
        rows.append((item["item_id"], res.output, res.tokens_out))
        if res.cost_usd is not None:
            total_cost += res.cost_usd
            n_priced += 1
        print(
            f"  [{i}/{len(items)}] {item['item_id']}  {len(res.output.split())} words"
            + (f"  ${res.cost_usd:.5f}" if res.cost_usd is not None else "")
        )
    spent = f"${total_cost:.4f} spent and not frozen." if n_priced else "Nothing was frozen."
    _refuse_unusable(rows, params.get("max_tokens"), args.allow_cut_off, spent)
    meta = {
        "authored_by": cfg.get("config_id", str(args.config)),
        # Which CODE produced it, not just which model. A reference authored by a
        # different adapter than the arms use is a different measurement.
        "authored_with": _repo_relative(adapter_id),
        "model": params.get("model", params.get("provider", "unknown")),
        # THE SAME identity record a run writes, from the SAME hook: the upstream model, the
        # temperature, the prompt hash, whether reasoning was on.
        "system_under_test": _identity(fp_hook, params),
        "params": {
            k: params.get(k)
            for k in ("temperature", "max_tokens", "reasoning", "reasoning_effort", "prompt_file", "provider")
            if params.get(k) is not None
        },
        "cost_usd": round(total_cost, 6) if n_priced else None,
    }
    return rows, meta


if __name__ == "__main__":
    raise SystemExit(main())
