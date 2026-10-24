#!/usr/bin/env python3
"""Re-score finished runs from their stored outputs. No API calls, no money.

The outputs are the expensive part of a run; the scores are arithmetic over them. But
scores were only ever computed at run time, so every change to a metric meant re-running
the whole sweep — ~$1.45 and 80 minutes to answer "what would this look like under a
different measure". That is backwards, and it is why a scorer bug survived two sweeps:
checking it would have cost another one.

    make rescore DATASET_ID=my_v1 MATCH=_v2 OUT=data/runs-rescored
    EVAL_RUNS_DIR=data/runs-rescored make leaderboard DATASET_ID=my_v1

Rescored runs are written to a SEPARATE directory, never over the originals. Two reasons:
the originals are the record of what was actually measured and paid for, and a rescored
run grouped under the same `config_id` as its source would average two different metrics
into one row. Point the leaderboard at the new directory with EVAL_RUNS_DIR.

What is recomputed: everything `score()` returns. What is carried across untouched:
latency, cost, token counts and the raw provider `_meta` — those are properties of the
call that happened, not of how it was later measured, and re-deriving them would be
inventing them.
"""

from __future__ import annotations

import argparse
import inspect
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from _adapter import load_recorded_adapter, score_wants_source
from _common import (
    DATA,
    DATASETS,
    MATERIALIZED,
    REFERENCES,
    ROOT,
    adapter_search_dirs,
    die,
    how,
    read_json,
    write_json,
)
from _fingerprint import references_digest
from _record import aggregate_scores, derived_record
from _runs import runs_on

#: Carried across from the original run rather than recomputed: these describe the CALL,
#: not the measurement. A rescore that recomputed a latency would be reporting a number
#: no clock ever produced.
#:
#: This is a FLOOR, not the whole list. Anything else the original row carried that the
#: new scorer does not produce is carried too — `truncated` and `reasoning_tokens` come
#: from the adapter's `Result.extra` at call time and are unrecoverable afterwards, and a
#: fixed list silently dropped them on the first run of this script.
# `resumed` records whether the item was replayed from a stopped run: a fact about the call.
CARRY = ("latency_ms", "tokens_in", "tokens_out", "cost_usd", "resumed")


def _item_sources(dataset_id: str) -> dict[str, str]:
    """{item_id: source_path} from the dataset file.

    THE DATASET KNOWS EACH ITEM'S FILENAME. PREDICTION ROWS DO NOT. `source_path` was read
    off the stored prediction row, and no prediction row has ever carried one (0 of 20,001
    rows across every committed run). `dataset_create.py` writes it into the DATASET, where
    `experiment_run`, `materialize`, `reference_create` and `validate_tree` all read it, so
    the fallback `<item_id>.txt` fired every time, and on any dataset whose files are named
    otherwise the source text arrived as None: silently, because a scorer that wanted the
    source then measured nothing rather than failing."""
    ds_file = DATASETS / f"{dataset_id}.json"
    items = read_json(ds_file).get("items") or [] if ds_file.is_file() else []
    return {it["item_id"]: it["source_path"] for it in items if it.get("item_id") and it.get("source_path")}


def _references_for(m: dict[str, Any], reference_id: str | None) -> tuple[Path | None, str | None]:
    """(the reference directory to score against, its tier): the run's own, or `--reference-id`.

    NEW REFERENCES, OLD OUTPUTS. The usual life of a golden dataset: runs are made against
    silver because nothing better exists, then a person writes or reviews gold. The outputs
    are the expensive part and do not change, so re-scoring them against gold is arithmetic,
    not a re-run. Without this the only way to a gold-scored leaderboard was to pay for
    every arm again."""
    if reference_id:
        return REFERENCES / reference_id, reference_id.split("/", 1)[0]
    recorded = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id")
    return (REFERENCES / recorded if recorded else None), m.get("reference_tier")


def _rescore_row(
    old: dict[str, Any],
    d: Path,
    ref_dir: Path | None,
    mat: Path,
    item_source: dict[str, str],
    score: Any,
    wants_source: bool,
    extra_keys: set[str],
) -> tuple[dict[str, Any], bool, bool]:
    """One stored prediction row, scored again from its stored output: (the new row, whether
    a reference was found for it, whether its cost was re-read from the bill)."""
    had_ref = False
    recosted = False
    item_id = old["item_id"]
    out_f = d / "outputs" / f"{item_id}.txt"
    if not out_f.is_file():
        die(f"{d.name}: no stored output for {item_id} — cannot rescore")
    output = out_f.read_text(encoding="utf-8")
    reference = None
    if ref_dir:
        rf = ref_dir / f"{item_id}.txt"
        if rf.is_file():
            reference = rf.read_text(encoding="utf-8", errors="replace")
            had_ref = True
    source_text = None
    # `source_path` is the dataset's own name for the file; it only happens to
    # equal "<item_id>.txt" here. Ignoring it means source_text is silently None
    # on any dataset that names files differently -- and a scorer that wanted the
    # source then measures nothing, quietly.
    rel = item_source.get(item_id) or old.get("source_path") or f"{item_id}.txt"
    for cand in (mat / rel, mat / f"{item_id}.txt", mat / item_id):
        if cand.is_file():
            source_text = cand.read_text(encoding="utf-8", errors="replace")
            break
    scored = score(output, reference, source_text) if wants_source else score(output, reference)
    row: dict[str, Any] = {"item_id": item_id, **scored}
    for k, v in old.items():
        if k == "item_id" or k in scored:
            continue
        # Carry ONLY things that describe the call. "Keep everything the new
        # scorer does not produce" was too generous: it carried the previous
        # scorer's metrics (`rouge2`, `rougeL`) into the rescored run, where the
        # leaderboard showed them as live quality columns beside the new ones.
        # A rescored run must not report a number the current scorer never
        # computed.
        # The row's own `_extra` names what the adapter attached at call time (any adapter's
        # extras, not only the examples' names): those describe the call too.
        if k in CARRY or k in extra_keys or k in (old.get("_extra") or {}) or k.startswith("_"):
            row[k] = v

    # ...EXCEPT THE PARTS OF `_meta` THE PARSER PRODUCED.
    #
    # The rule above is "carry only things that describe the call", and `_meta`
    # passes it on `k.startswith("_")` alone. But `_meta.predicted` is the
    # PARSER'S OUTPUT, not a property of the call, so a rescored run carried new
    # scores beside the old parse -- and `extraction_report.py` reads exactly
    # that field. §3.6's consensus analysis and the annotation bound were
    # computed on pre-fix parses for the four arms the round-4 parser fix moved:
    # `glm_l` reported 0.5269 against its own run's 0.5662, in BOTH trees,
    # because the stale field is identical in both.
    #
    # An adapter that stores parser output in `_meta` declares how to rebuild
    # it. One that does not is not asked to.
    _mod = inspect.getmodule(score)
    if _mod is not None and hasattr(_mod, "reparse_meta") and isinstance(row.get("_meta"), dict):
        try:
            fresh = _mod.reparse_meta(output)
        except Exception as exc:  # noqa: BLE001
            die(
                f"{d.name}: the adapter's reparse_meta() raised on item "
                f"{item_id}: {type(exc).__name__}: {exc}\n"
                f"  A rescored run must not carry a parse the current parser "
                f"did not produce, so this is a failure rather than a carry."
            )
        if isinstance(fresh, dict):
            row["_meta"] = {**row["_meta"], **fresh}

    # COST IS RECOMPUTED FROM THE BILL, NOT CARRIED.
    #
    # `cost_usd` was carried verbatim, and for every run measured before the
    # adapters learned to prefer `usage.cost` that value is the PRICE TABLE --
    # tokens multiplied by the rate in the arm's yaml. The provider's actual
    # charge is sitting in the same row, in `_meta.usage.cost`, and the two
    # differ by 0.67x to 3.76x per arm and 1.25x over the whole repo
    # ($9.78 recorded against $12.28 billed). Every cost column, every
    # dollars-per-month figure and every cost-per-quality-point in the reports
    # is computed from the wrong one.
    #
    # An alias is not a price: a provider routes, discounts, caches and rounds.
    # The bill is the measurement; the price table was always the fallback for
    # when there is no bill, and it is kept as exactly that.
    billed = ((old.get("_meta") or {}).get("usage") or {}).get("cost")
    if billed is not None:
        try:
            row["cost_usd"] = round(float(billed), 10)
            if abs(float(billed) - float(old.get("cost_usd") or 0)) > 1e-9:
                recosted = True
        except (TypeError, ValueError):
            pass
    return row, had_ref, recosted


def _check_references(
    d: Path, m: dict[str, Any], ref_dir: Path | None, rows: list[dict[str, Any]], refs_found: int
) -> None:
    """Die when a declared reference set has none of its files here; warn when it has some."""
    # A MISSING REFERENCE SET MUST NOT SCORE. A missing OUTPUT calls die()
    # (_rescore_row); a missing REFERENCE used to fall through as None and the run scored
    # anyway. That asymmetry guarded the expensive artifact and left the free one
    # unchecked -- and the free one is exactly what a fresh clone lacks, because the
    # corpora are gitignored and rebuilt by each example's fetch.py.
    #
    # What that cost: rescoring fn_anthropic_l in a clone with no references produced
    # f1 = 0.1071 against the recorded 0.6798. Not an error, not a zero -- a
    # plausible number, arrived at because every prediction became a false positive
    # against an empty gold set. A reader could have published it.
    #
    # Zero found is always wrong when a reference_id is declared, so it dies. A
    # PARTIAL set is not necessarily wrong -- a reference tier may legitimately not
    # cover every item -- so it warns and says how many, rather than refusing.
    if ref_dir and rows:
        if refs_found == 0:
            die(
                f"{d.name}: reference_id {m['fingerprint']['data']['reference_id']!r} "
                f"is declared but NOT ONE of its {len(rows)} reference files exists "
                f"under {ref_dir}.\n"
                f"  Scoring would silently treat every gold set as empty and report a "
                f"plausible wrong number.\n"
                f"  References are often gitignored rather than committed: put them back (in a "
                f"checkout of the harness, an example's fetcher: python examples/<example>/fetch.py),\n"
                f"  or make them again:\n"
                f"    "
                + how(
                    f"evh dataset-create --dataset-id {m.get('dataset_id')} --source-dir …",
                    f"make dataset-create DATASET_ID={m.get('dataset_id')}",
                )
            )
        if refs_found < len(rows):
            print(
                f"    WARNING: only {refs_found} of {len(rows)} items have a "
                f"reference under {ref_dir}; the rest scored against None",
                flush=True,
            )


def _rescored_fingerprint(
    source_fp: dict[str, Any],
    adapter_id: str,
    adapter_path: Path | None,
    reference_id: str | None,
    tier: str | None,
    run_name: str,
) -> dict[str, Any]:
    """The source run's fingerprint, made true of the rescore."""
    # The fingerprint is copied from the source run, and its `instrument.adapter`
    # identifies the scorer that produced the ORIGINAL numbers -- not these. Left
    # alone, a rescored run asserts the old scorer in the one field meant to identify
    # it, and every downstream tool (compare_runs, validate_tree, promote_baseline)
    # believes it. Overwrite it and invalidate the hash, which no longer describes
    # anything that was computed together.
    fp = json.loads(json.dumps(source_fp))
    fp.setdefault("instrument", {})["adapter"] = {
        "id": adapter_id,
        "sha256": _sha(adapter_path),
    }
    # THE REFERENCE HASH DESCRIBED THE WRONG BYTES. `data.references_sha256`
    # was copied from the source run, where it records the references as they
    # were WHEN THAT RUN EXECUTED -- while these scores were computed against
    # whatever is in data/references now. A rescored run could therefore assert
    # a hash over reference files it had never read, which is the one claim a
    # fingerprint exists to make. Recomputed here, with the source's value kept
    # beside it when the two differ, because "the gold set changed under us" is
    # a finding and not a detail. Found by external review.
    fp_data = fp.setdefault("data", {})
    moved = bool(reference_id and fp_data.get("reference_id") != reference_id)
    if moved:
        fp_data["reference_id_at_measurement"] = fp_data.get("reference_id")
        fp_data["reference_tier_at_measurement"] = fp_data.get("reference_tier")
        fp_data["reference_id"] = reference_id
        fp_data["reference_tier"] = tier
    actual_refs = references_digest(ROOT, fp_data.get("reference_id"), DATA)
    prior_refs = fp_data.get("references_sha256")
    fp_data["references_sha256"] = actual_refs
    if prior_refs and actual_refs and prior_refs != actual_refs:
        fp_data["references_sha256_at_measurement"] = prior_refs
        # Onto ANOTHER reference set the hashes always differ (other files): that is
        # the move, recorded above, not a change. Only the same set's files changing
        # under the run is (found by the GUIDE's check, 0.4.0).
        if not moved:
            fp_data["references_changed_since_measurement"] = True
            print(
                f"    WARNING: {run_name}: the reference files have CHANGED since "
                f"this run was measured; scores here are against the current ones"
            )
    fp["hash"] = None
    fp["hash_invalid_because"] = (
        "scores were recomputed by a different scorer than the one this "
        "fingerprint was built from; see derived.with"
    )
    return fp


def main() -> int:
    """Re-score finished runs from their stored outputs: no API calls, no money."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--match", help="only runs whose config_id contains this substring")
    ap.add_argument("--out", type=Path, default=DATA / "runs-rescored")
    ap.add_argument(
        "--reference-id",
        help="score against THIS reference set (e.g. gold/my_v1) instead of the "
        "one each run recorded -- for when gold arrives after the runs",
    )
    ap.add_argument(
        "--config-dir",
        type=Path,
        help="where to find the arm configs naming the adapter "
        "(default: alongside each run's recorded adapter path)",
    )
    args = ap.parse_args()
    if args.reference_id and not (REFERENCES / args.reference_id).is_dir():
        die(f"no reference set at data/references/{args.reference_id}")

    todo = runs_on(args.dataset_id, match=args.match)
    if not todo:
        die(f"no runs on {args.dataset_id!r}" + (f" matching {args.match!r}" if args.match else ""))
    # A rescored run is its own record, derived from the run it reads: written into that run's
    # directory it would overwrite the measurement (it died copying a file onto itself).
    if any(d.parent.resolve() == args.out.resolve() for d, _m in todo):
        die(
            f"--out {args.out} is where the runs being rescored are read from; a rescore writes "
            f"new records beside them, so give it another directory (the default is {DATA / 'runs-rescored'})"
        )

    mat = MATERIALIZED / args.dataset_id
    item_source = _item_sources(args.dataset_id)
    print(f"rescoring {len(todo)} run(s) -> {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    adapters: dict[str, Any] = {}
    written = 0
    for d, m in sorted(todo, key=lambda t: t[0].name):
        spec = m.get("adapter")
        if not spec:
            print(f"  SKIP {d.name}: the run records no adapter")
            continue
        if spec not in adapters:
            # The id the run recorded, resolved under the project (and in a checkout the
            # repository root, where the examples' ids start): _adapter.load_recorded_adapter,
            # shared with silver-calibrate.
            found = load_recorded_adapter(spec)
            if found is None:
                die(
                    f"adapter not found for {d.name}: {spec!r} is under none of "
                    f"{', '.join(str(d) for d in adapter_search_dirs())}"
                )
            adapters[spec] = found
        _call, score, adapter_id, adapter_path, _warm, _fp = adapters[spec]
        wants_source = score_wants_source(score)

        ref_dir, tier = _references_for(m, args.reference_id)

        rows: list[dict[str, Any]] = []
        refs_found = 0
        recosted = 0
        # Keys the ADAPTER attached at call time (Result.extra) rather than at score time:
        # `truncated`, `reasoning_tokens`. Unrecoverable afterwards, so they ride along.
        extra_keys = set(m.get("metric_kinds", {})) & {"truncated", "reasoning_tokens"}
        extra_keys |= {"truncated", "reasoning_tokens"}
        dropped: set = set()
        for line in (d / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            old = json.loads(line)
            row, had_ref, recost = _rescore_row(
                old, d, ref_dir, mat, item_source, score, wants_source, extra_keys
            )
            refs_found += had_ref
            recosted += recost
            # What the source scored per item and these rows no longer carry: the previous
            # scorer's metrics. It added whichever key the carry loop above ended on, so 24
            # NER runs recorded `untyped_tp` as dropped beside an `untyped_tp` score.
            dropped |= {k for k in old if k != "item_id" and not k.startswith("_") and k not in row}
            rows.append(row)

        _check_references(d, m, ref_dir, rows, refs_found)

        scores = aggregate_scores(rows)

        run_dir = args.out / d.name
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        for f in (d / "outputs").glob("*.txt"):
            shutil.copy2(f, run_dir / "outputs" / f.name)
        (run_dir / "predictions.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
        )
        # Provenance of the RESCORE itself: which run it came from, and which scorer
        # produced these numbers. Without this a rescored run is indistinguishable from
        # a measured one, which is the whole risk of having this script at all.
        provenance: dict = {"adapter": adapter_id, "sha256": _sha(adapter_path)}
        # The adapter FILE's hash does not cover a scorer that lives in a shared module.
        # An adapter may expose `scorer_id()` -- no params, no network -- naming the
        # hashes that identify its scoring rule; without it, an extraction.py-only change
        # is invisible here and a rescored run cannot say what measured it.
        sid = getattr(sys.modules.get(getattr(score, "__module__", ""), None), "scorer_id", None)
        if callable(sid):
            provenance["scorer"] = sid()
        new = derived_record(
            m,
            kind="rescore",
            source_dir=d.name,
            with_=provenance,
            scores=scores,
            n_items=len(rows),
            metric_kinds=_kinds(adapter_path) or m.get("metric_kinds") or {},
            primary_metric=_primary(adapter_path) or m.get("primary_metric"),
            metric_descriptions=_descriptions(adapter_path) or m.get("metric_descriptions"),
            metric_directions=_directions(adapter_path) or m.get("metric_directions"),
            reference_tier=tier if args.reference_id else None,
        )
        if isinstance(new.get("fingerprint"), dict):
            new["fingerprint"] = _rescored_fingerprint(
                new["fingerprint"], adapter_id, adapter_path, args.reference_id, tier, d.name
            )
        if dropped:
            new["rescore_dropped_metrics"] = sorted(dropped)
        write_json(run_dir / "metrics.json", new)
        written += 1
        note = f", {recosted} re-costed from the bill" if recosted else ""
        print(f"  {d.name}  -> {len(rows)} item(s){note}")

    print(f"\n{written} run(s) rescored into {args.out}")
    print(
        f"  EVAL_RUNS_DIR={args.out} "
        + how(
            f"evh leaderboard --dataset-id {args.dataset_id}",
            f"make leaderboard DATASET_ID={args.dataset_id}",
        )
    )
    return 0


def _kinds(path):
    from _adapter import metric_kinds  # noqa: PLC0415

    return metric_kinds(path)


def _primary(path):
    from _adapter import primary_metric  # noqa: PLC0415

    return primary_metric(path)


def _directions(path):
    """The rescoring adapter's METRIC_DIRECTIONS, refreshed on the run like its kinds."""
    from _adapter import metric_directions  # noqa: PLC0415

    return metric_directions(path)


def _descriptions(path):
    from _adapter import metric_descriptions  # noqa: PLC0415

    return metric_descriptions(path)


def _sha(path):
    from _codeid import file_sha256  # noqa: PLC0415

    # By behaviour: an adapter whose docstrings or METRIC_DESCRIPTIONS changed scores the same.
    return file_sha256(Path(path)) if path else None


if __name__ == "__main__":
    raise SystemExit(main())
