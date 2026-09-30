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
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import MATERIALIZED, REFERENCES, RUNS, ROOT, die, now, read_json, write_json  # noqa: E402
from _fingerprint import _references_digest  # noqa: E402
from experiment_run import load_adapter, _score_wants_source  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    die("pyyaml is required — pip install -r requirements.txt")

#: Carried across from the original run rather than recomputed: these describe the CALL,
#: not the measurement. A rescore that recomputed a latency would be reporting a number
#: no clock ever produced.
#:
#: This is a FLOOR, not the whole list. Anything else the original row carried that the
#: new scorer does not produce is carried too — `truncated` and `reasoning_tokens` come
#: from the adapter's `Result.extra` at call time and are unrecoverable afterwards, and a
#: fixed list silently dropped them on the first run of this script.
CARRY = ("latency_ms", "tokens_in", "tokens_out", "cost_usd")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--match", help="only runs whose config_id contains this substring")
    ap.add_argument("--out", type=Path, default=ROOT / "data/runs-rescored")
    ap.add_argument("--config-dir", type=Path,
                    help="where to find the arm configs naming the adapter "
                         "(default: alongside each run's recorded adapter path)")
    args = ap.parse_args()

    srcs = [
        d for d in (RUNS.iterdir() if RUNS.is_dir() else [])
        if (d / "metrics.json").is_file()
    ]
    todo = []
    for d in srcs:
        m = read_json(d / "metrics.json")
        if m.get("dataset_id") != args.dataset_id:
            continue
        if args.match and args.match not in m.get("config_id", ""):
            continue
        todo.append((d, m))
    if not todo:
        die(f"no runs on {args.dataset_id!r}" + (f" matching {args.match!r}" if args.match else ""))

    mat = MATERIALIZED / args.dataset_id

    # THE DATASET KNOWS EACH ITEM'S FILENAME. PREDICTION ROWS DO NOT.
    #
    # Below, `source_path` was read off the stored prediction row -- and no prediction
    # row has ever carried one. Measured: 0 of 20,001 rows across every committed run.
    # `dataset_create.py` writes `source_path` into the DATASET; `experiment_run`,
    # `materialize`, `reference_create` and `validate_tree` all read it from there, and
    # rescore was the one place that looked in the wrong object. So the fallback
    # `<item_id>.txt` fired every single time, and on any dataset whose files are not
    # named that way the source text arrived as None -- silently, because a scorer that
    # wanted the source then measured nothing rather than failing.
    #
    # Round 1 reported this fixed. The commit that claimed it added the `source_path`
    # lookup without checking that the field existed where it was being read from.
    item_source: Dict[str, str] = {}
    ds_file = ROOT / "data" / "datasets" / f"{args.dataset_id}.json"
    if ds_file.is_file():
        for it in (read_json(ds_file).get("items") or []):
            if it.get("item_id") and it.get("source_path"):
                item_source[it["item_id"]] = it["source_path"]
    print(f"rescoring {len(todo)} run(s) -> {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    adapters: Dict[str, Any] = {}
    written = 0
    for d, m in sorted(todo, key=lambda t: t[0].name):
        spec = m.get("adapter")
        if not spec:
            print(f"  SKIP {d.name}: the run records no adapter")
            continue
        if spec not in adapters:
            # Adapter ids are relative to the HARNESS root for its own bundled adapter
            # ("scripts/adapter.py"), to the REPO root for most examples
            # ("examples/ner-few-nerd/adapter.py"), and to the EXAMPLES root for the
            # oldest sweep ("summarization-cnn-dailymail/adapter.py").
            #
            # The examples root was named in this comment and not in the list below, so
            # the case it describes was the case that failed. 24 committed
            # cnn_dailymail_200 runs -- the whole summarisation measurement sweep, and
            # the experiment this repo leads with -- could not be rescored at all:
            #
            #   ERROR: adapter not found ... 'summarization-cnn-dailymail/adapter.py'
            #   is under neither .../harness nor .../eval-harness
            #
            # Found while testing a different fix. Resolving the id is the right repair;
            # rewriting `adapter` inside 24 finished runs is not, because their
            # fingerprint hashes were computed over the bytes that are there.
            for base in (ROOT, ROOT.parent, ROOT.parent / "examples"):
                cand = Path(spec) if Path(spec).is_absolute() else base / spec
                if cand.is_file():
                    adapters[spec] = load_adapter(str(cand), None)
                    break
            else:
                die(f"adapter not found for {d.name}: {spec!r} is under none of "
                    f"{ROOT}, {ROOT.parent}, {ROOT.parent / 'examples'}")
        _call, score, adapter_id, adapter_path, _warm, _fp = adapters[spec]
        wants_source = _score_wants_source(score)

        tier = m.get("reference_tier")
        ref_dir = (REFERENCES / m["fingerprint"]["data"]["reference_id"]) \
            if (m.get("fingerprint", {}).get("data", {}) or {}).get("reference_id") else None

        rows: List[Dict[str, Any]] = []
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
                    refs_found += 1
            source_text = None
            # `source_path` is the dataset's own name for the file; it only happens to
            # equal "<item_id>.txt" here. Ignoring it means source_text is silently None
            # on any dataset that names files differently -- and a scorer that wanted the
            # source then measures nothing, quietly.
            rel = (item_source.get(item_id) or old.get("source_path")
                   or f"{item_id}.txt")
            for cand in (mat / rel, mat / f"{item_id}.txt", mat / item_id):
                if cand.is_file():
                    source_text = cand.read_text(encoding="utf-8", errors="replace")
                    break
            scored = (score(output, reference, source_text) if wants_source
                      else score(output, reference))
            row: Dict[str, Any] = {"item_id": item_id, **scored}
            for k, v in old.items():
                if k == "item_id" or k in scored:
                    continue
                # Carry ONLY things that describe the call. "Keep everything the new
                # scorer does not produce" was too generous: it carried the previous
                # scorer's metrics (`rouge2`, `rougeL`) into the rescored run, where the
                # leaderboard showed them as live quality columns beside the new ones.
                # A rescored run must not report a number the current scorer never
                # computed.
                if k in CARRY or k in extra_keys or k.startswith("_"):
                    row[k] = v

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
                        recosted += 1
                except (TypeError, ValueError):
                    pass
                else:
                    dropped.add(k)
            rows.append(row)

        # A MISSING REFERENCE SET MUST NOT SCORE. Two lines above, a missing OUTPUT calls
        # die(); a missing REFERENCE used to fall through as None and the run scored
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
                die(f"{d.name}: reference_id {m['fingerprint']['data']['reference_id']!r} "
                    f"is declared but NOT ONE of its {len(rows)} reference files exists "
                    f"under {ref_dir}.\n"
                    f"  Scoring would silently treat every gold set as empty and report a "
                    f"plausible wrong number.\n"
                    f"  The corpora are gitignored, not committed: rebuild them with the "
                    f"example's fetcher, e.g.\n"
                    f"    python examples/<example>/fetch.py\n"
                    f"    make dataset-create DATASET_ID={m.get('dataset_id')}")
            if refs_found < len(rows):
                print(f"    WARNING: only {refs_found} of {len(rows)} items have a "
                      f"reference under {ref_dir}; the rest scored against None",
                      flush=True)

        import statistics
        keys = sorted({k for r in rows for k in r if k != "item_id" and not k.startswith("_")})
        scores = {k: round(statistics.fmean([float(r[k]) for r in rows if k in r]), 10)
                  for k in keys}
        for k in ("cost_usd", "tokens_in", "tokens_out"):
            vals = [float(r[k]) for r in rows if k in r]
            if vals:
                scores[f"total_{k}"] = round(sum(vals), 8)

        run_dir = args.out / d.name
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
        for f in (d / "outputs").glob("*.txt"):
            shutil.copy2(f, run_dir / "outputs" / f.name)
        (run_dir / "predictions.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        new = dict(m)
        new["scores"] = scores
        new["metric_kinds"] = _kinds(adapter_path) or m.get("metric_kinds") or {}
        new["primary_metric"] = _primary(adapter_path) or m.get("primary_metric")
        # Provenance of the RESCORE itself: which run it came from, and which scorer
        # produced these numbers. Without this a rescored run is indistinguishable from
        # a measured one, which is the whole risk of having this script at all.
        new["rescored_from"] = d.name
        new["rescored_at"] = now()
        new["rescored_with"] = {
            "adapter": adapter_id,
            "sha256": _sha(adapter_path),
        }
        # The adapter FILE's hash does not cover a scorer that lives in a shared module.
        # An adapter may expose `scorer_id()` -- no params, no network -- naming the
        # hashes that identify its scoring rule; without it, an extraction.py-only change
        # is invisible here and a rescored run cannot say what measured it.
        sid = getattr(sys.modules.get(getattr(score, "__module__", ""), None),
                      "scorer_id", None)
        if callable(sid):
            new["rescored_with"]["scorer"] = sid()
        # The fingerprint is copied from the source run, and its `instrument.adapter`
        # identifies the scorer that produced the ORIGINAL numbers -- not these. Left
        # alone, a rescored run asserts the old scorer in the one field meant to identify
        # it, and every downstream tool (compare_runs, validate_tree, promote_baseline)
        # believes it. Overwrite it and invalidate the hash, which no longer describes
        # anything that was computed together.
        fp = new.get("fingerprint")
        if isinstance(fp, dict):
            fp = json.loads(json.dumps(fp))
            fp.setdefault("instrument", {})["adapter"] = {
                "id": adapter_id, "sha256": _sha(adapter_path),
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
            actual_refs = _references_digest(ROOT, fp_data.get("reference_id"))
            prior_refs = fp_data.get("references_sha256")
            fp_data["references_sha256"] = actual_refs
            if prior_refs and actual_refs and prior_refs != actual_refs:
                fp_data["references_sha256_at_measurement"] = prior_refs
                fp_data["references_changed_since_measurement"] = True
                print(f"    WARNING: {d.name}: the reference files have CHANGED since "
                      f"this run was measured; scores here are against the current ones")
            fp["hash"] = None
            fp["hash_invalid_because"] = (
                "scores were recomputed by a different scorer than the one this "
                "fingerprint was built from; see rescored_with"
            )
            new["fingerprint"] = fp
        if dropped:
            new["rescore_dropped_metrics"] = sorted(dropped)
        write_json(run_dir / "metrics.json", new)
        written += 1
        note = f", {recosted} re-costed from the bill" if recosted else ""
        print(f"  {d.name}  -> {len(rows)} item(s){note}")

    print(f"\n{written} run(s) rescored into {args.out}")
    print(f"  EVAL_RUNS_DIR={args.out} make leaderboard DATASET_ID={args.dataset_id}")
    return 0


def _kinds(path):
    from experiment_run import _adapter_metric_kinds
    return _adapter_metric_kinds("", path)


def _primary(path):
    from experiment_run import _adapter_primary_metric
    return _adapter_primary_metric(path)


def _sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None


if __name__ == "__main__":
    raise SystemExit(main())
