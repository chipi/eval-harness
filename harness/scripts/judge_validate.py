"""Validate a judge against people's ratings, as ordinary runs (RFC-038 section 3).

    evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1 --dry-run     # the calls, the estimate and the cap
    evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1               # the runs, and the block they make
    evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1 --fill --reason "..." --by person:ana

The rated dataset is items {"source", "outputs"} with, as the reference of each, the people's ratings
(`judge_validation.py` says the shape). The command makes one system per judge of the scorer,
`data/systems/<scorer>__<judge>__validation.yaml`, whose adapter is `scripts/judge_validation.py` and whose params are
the judge's plus what the gate compares, and a floor of seeded random verdicts (or the best free scorer's run,
`--floor-run`). It runs each as `evh run` does (the cap, the fingerprint, the progress, `--resume`), then prints, per
judge, the metric, the floor and the run, and the `validation` block that names them. With `--fill` it writes that block
and the prompt's sha256 into the scorer through the scorer's own operation, as a decision with who and why, and says
what the gate (`judge_score.validation_problems`) answers: the check that the write is right is the gate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from evaluation_harness import _actor, _jsonout, _spend, _store
from evaluation_harness import judge_score as js
from evaluation_harness import judge_validation as jva
from evaluation_harness._common import (
    DATA,
    EXIT_STOPPED,
    EXIT_UNVALIDATED,
    MATERIALIZED,
    ROOT,
    dataset_id_ok,
    die,
    env_float,
    how,
    load_dataset,
    now,
)
from evaluation_harness.model import runs as _model_runs
from evaluation_harness.ops import legacy

SCORERS = DATA / "scorers"
#: How many of a dataset's problems are listed before "and N more".
LISTED = 8
FLOOR = "random"
SHAPE = (
    'A rated dataset\'s item is {"source": text, "outputs": [text, ...]} and its reference is the people\'s ratings, '
    '{"ratings": {dimension: [one number per output]}} over the scorer\'s dimensions.'
)


def system_id(scorer_id: str, judge_id: str) -> str:
    """The system that is this judge on a validation: `<scorer>__<judge>__validation`."""
    return f"{scorer_id}__{judge_id}__validation"


def rated_problems(sc: dict[str, Any], items: dict[str, str], refs: dict[str, str | None]) -> list[str]:
    """What keeps a dataset from being a rated one for this scorer: an item that is not {source, outputs}, an item whose
    reference is not the people's ratings, ratings that carry none of the scorer's dimensions or one it does not judge,
    items that carry different dimensions, a list of ratings that is not one number per output. The ratings may carry
    only some of the scorer's dimensions (the people did not rate them all): the block then says which, and the gate
    names the rest as not validated. Empty when it is rated."""
    dims = js.task_for(sc)["dimensions"]
    out: list[str] = []
    first: tuple[str, list[str]] | None = None
    for iid in sorted(items):
        try:
            n = len(jva.parse_item(items[iid])["outputs"])
        except ValueError as exc:
            out.append(f"item {iid}: {exc}")
            continue
        ref = refs.get(iid)
        if ref is None:
            out.append(
                f"item {iid}: it has no reference; the people's ratings are the reference, "
                '{"ratings": {dimension: [one number per output]}}'
            )
            continue
        try:
            doc = json.loads(ref)
        except ValueError:
            doc = None
        ratings = doc.get("ratings") if isinstance(doc, dict) else None
        if not isinstance(ratings, dict) or not ratings:
            out.append(
                f'item {iid}: its reference has no `ratings`: {{"ratings": {{dimension: [one number per output]}}}}'
            )
            continue
        carried = [d for d in dims if d in ratings]
        extra = [d for d in ratings if d not in dims]
        if not carried:
            out.append(
                f"item {iid}: the ratings carry none of the scorer's dimensions ({', '.join(dims)}); they carry "
                f"{', '.join(ratings)}"
            )
            continue
        if extra:
            out.append(
                f"item {iid}: the ratings carry {', '.join(extra)}, which the scorer does not judge "
                f"(its dimensions: {', '.join(dims)})"
            )
            continue
        if first is None:
            first = (iid, carried)
        elif carried != first[1]:
            out.append(
                f"item {iid} carries {', '.join(carried)}, the first item ({first[0]}) carries {', '.join(first[1])}: "
                "every item must carry the same dimensions"
            )
        groups = [("ratings", ratings)] + [
            (f"rater {k + 1}", r) for k, r in enumerate(doc.get("raters") or []) if isinstance(r, dict)
        ]
        for who, r in groups:
            if sorted(r) != sorted(ratings):
                out.append(
                    f"item {iid}: the {who} carry {', '.join(sorted(r))}, the ratings {', '.join(sorted(ratings))}"
                )
                continue
            for d in carried:
                v = r[d]
                if (
                    not isinstance(v, list)
                    or len(v) != n
                    or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
                ):
                    out.append(
                        f"item {iid}: the {who} for {d} are not one number per output "
                        f"(the item has {n} outputs, the list {len(v) if isinstance(v, list) else 'is not a list'})"
                    )
    return out


def carried_dimensions(sc: dict[str, Any], refs: dict[str, str | None]) -> list[str]:
    """The scorer's dimensions the dataset's ratings carry (the same in every item, as `rated_problems` holds), in the
    scorer's order."""
    ref: dict[str, Any] = next((json.loads(r) for r in refs.values() if r), {})
    return [d for d in js.task_for(sc)["dimensions"] if d in (ref.get("ratings") or {})]


def rated_datasets(sc: dict[str, Any]) -> list[str]:
    """The project's datasets that are rated for this scorer, by their first item and its reference (the command reads
    them all): what a screen offers to validate on."""
    from evaluation_harness.run import _reference_for  # noqa: PLC0415

    out = []
    for f in sorted(_store.glob(DATA / "datasets", "*.json")):
        try:
            ds = json.loads(_store.read_text(f, encoding="utf-8"))
            first = ds["items"][0]
            text = _store.read_text(
                MATERIALIZED / ds["dataset_id"] / (first.get("source_path") or f"{first['item_id']}.txt"),
                encoding="utf-8",
                errors="replace",
            )
            ref_dir, _tier = _reference_for(ds["dataset_id"])
            ref_file = ref_dir / f"{first['item_id']}.txt" if ref_dir is not None else None
            ref = (
                _store.read_text(ref_file, encoding="utf-8")
                if ref_file is not None and _store.is_file(ref_file)
                else None
            )
        except (OSError, ValueError, KeyError, IndexError):
            continue
        if not rated_problems(sc, {first["item_id"]: text}, {first["item_id"]: ref}):
            out.append(ds["dataset_id"])
    return out


def _prompt_path(sc: dict[str, Any]) -> str:
    """The scorer's prompt file as a system may name it: relative to the project when it lies in it."""
    found = next((c for c in js.prompt_candidates(sc) if _store.is_file(c)), None)
    if found is None:
        js.prompt_text(sc)  # dies: not found, saying where it looked
        raise AssertionError("unreachable")
    try:
        return str(found.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(found.resolve())


def judge_system_params(sc: dict[str, Any], judge: dict[str, Any]) -> dict[str, Any]:
    """The params of the system that is this judge on a validation: the judge's, and what the adapter needs and the gate
    compares (mode, explain, the prompt file's name)."""
    return {
        **judge["params"],
        "scorer": sc["scorer_id"],
        "judge": judge["id"],
        "mode": js.mode_of(sc),
        "explain": js.explain_of(sc),
        "outputs_per_call": int(sc["protocol"]["outputs_per_call"]),
        "order_seed": sc["protocol"].get("order_seed", 0),
        "task": js.task_for(sc),
        "prompt_path": _prompt_path(sc),
        "prompt_file": Path(sc["prompt"]["file"]).name,
    }


def floor_system_params(sc: dict[str, Any]) -> dict[str, Any]:
    """The params of the floor: seeded random verdicts of the scorer's mode, no model."""
    return {
        "provider": jva.RANDOM,
        "scorer": sc["scorer_id"],
        "judge": FLOOR,
        "mode": js.mode_of(sc),
        "outputs_per_call": int(sc["protocol"]["outputs_per_call"]),
        "task": js.task_for(sc),
        "seed": jva.FLOOR_SEED,
    }


def ensure_system(sid: str, params: dict[str, Any]) -> bool:
    """Write the system (True), unless it exists with these params (False); one that exists with other params is not
    overwritten."""
    from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

    if sid in SYSTEM.ids():
        have = SYSTEM.get(sid)
        if have.get("params") == params and have.get("adapter") == "scripts/judge_validation.py":
            return False
        die(
            f"system {sid} exists with other params: a system is not overwritten. The judge or the scorer changed since "
            "it was written: move it away (a new scorer version is a new id), then run again.",
            "would-overwrite",
        )
    out = DATA / "systems" / f"{sid}.yaml"
    _store.mkdir(out.parent, parents=True, exist_ok=True)
    _store.write_text(
        out,
        "# A judge on a validation (evh judge-validate, RFC-038): the scorer's judge, run over a rated dataset.\n"
        + yaml.safe_dump(
            {"system_id": sid, "adapter": "scripts/judge_validation.py", "params": params}, sort_keys=False
        ),
        encoding="utf-8",
    )
    return True


def _load_rated(dataset_id: str) -> tuple[dict[str, str], dict[str, str | None]]:
    """The dataset's items' text and the reference of each (the gold, else the silver), by item id."""
    from evaluation_harness.run import _reference_for  # noqa: PLC0415

    ds = load_dataset(dataset_id)
    mat = MATERIALIZED / dataset_id
    items: dict[str, str] = {}
    for it in ds["items"]:
        f = mat / (it.get("source_path") or f"{it['item_id']}.txt")
        if not _store.is_file(f):
            die(
                f"{f} is missing: materialize the dataset first "
                f"({how(f'evh dataset-materialize --dataset-id {dataset_id}', f'make dataset-materialize DATASET_ID={dataset_id}')})",
                "not-materialized",
            )
        items[it["item_id"]] = _store.read_text(f, encoding="utf-8", errors="replace")
    ref_dir, _tier = _reference_for(dataset_id)
    refs: dict[str, str | None] = {}
    for iid in items:
        rf = ref_dir / f"{iid}.txt" if ref_dir is not None else None
        refs[iid] = _store.read_text(rf, encoding="utf-8") if rf is not None and _store.is_file(rf) else None
    return items, refs


def _listed(problems: list[str]) -> str:
    more = f"\n  ... and {len(problems) - LISTED} more" if len(problems) > LISTED else ""
    return "\n  ".join(problems[:LISTED]) + more


def _latest_run(sid: str, dataset_id: str) -> str | None:
    """The latest run of this system on this dataset (model.runs.latest), or None. The system is the record's own, not
    a run id's prefix: `smoke`'s runs are not `smoke_v1`'s."""
    found = _model_runs.latest(
        (_model_runs.run_dir(r), rec)
        for r in _model_runs.run_ids()
        if (rec := _model_runs.run(r)) and rec.get("system_id") == sid and rec.get("dataset_id") == dataset_id
    )
    return found[1]["run_id"] if found else None


def _scores_of(run_id: str) -> dict[str, Any] | None:
    first = _model_runs.first_score(_model_runs.root() / run_id)
    return _model_runs.record(first) if first else None


def _finished(rec: dict[str, Any] | None, n_items: int) -> bool:
    return (
        rec is not None
        and rec["n_items"] == n_items
        and not rec.get("failed_items")
        and bool(rec.get("scores") or {})
    )


def _run(sid: str, dataset_id: str, n_items: int, resume: bool) -> tuple[str | None, int]:
    """One system run on the dataset by `evh run`'s own body: (its run id, the exit code). With `resume`, the latest run
    of the system that finished is used as it is, and one that did not is continued."""
    from evaluation_harness import run as _runmod  # noqa: PLC0415

    inputs: dict[str, Any] = {"system": sid, "dataset": dataset_id}
    if resume and (prior := _latest_run(sid, dataset_id)):
        if _finished(_scores_of(prior), n_items):
            print(f"  {sid}: {prior} is finished, used as it is")
            return prior, 0
        inputs["resume"] = prior
    rid = f"{sid}_{now().replace(':', '').replace('-', '')}"
    try:
        code = _runmod.body(**inputs, run_id=rid)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code)
        return None, exc.code if isinstance(exc.code, int) else 1
    return rid, code


def _metric_of(run_id: str, metric: str) -> tuple[float | None, int | None]:
    rec = _scores_of(run_id) or {}
    v = (rec.get("scores") or {}).get(metric)
    return (float(v) if v is not None else None), rec.get("n_items")


def _extras(run_id: str, names: tuple[str, ...]) -> str:
    sc = (_scores_of(run_id) or {}).get("scores") or {}
    return "  ".join(f"{k} {sc[k]:.4f}" for k in names if k in sc)


def _block(
    sc: dict[str, Any],
    dataset_id: str,
    metric: str,
    floor: float | None,
    got: dict[str, tuple[str, float]],
    what: str,
    differs: str,
    why: str,
    dimensions: list[str],
) -> dict[str, Any]:
    """The scorer's `validation` block: what the gate reads, from the runs just made."""
    mode = js.mode_of(sc)
    return {
        "dataset_id": dataset_id,
        **({"mode": mode} if mode != "grade" else {}),
        "metric": metric,
        "dimensions": dimensions,
        "what": what,
        **({"differs_from_this_use": differs} if differs else {}),
        **({"why": why} if why else {}),
        "runs": [
            {
                "judge": j["id"],
                "run": got[j["id"]][0],
                "value": got[j["id"]][1],
                **({"min_metric": floor} if floor is not None else {}),
            }
            for j in sc["judges"]
            if j["id"] in got
        ],
    }


def body(**inputs: Any) -> int:
    """Validate the scorer's judges against the people's ratings of a dataset."""
    args = legacy.namespace(inputs, "judge-validate")
    sc = js.load_scorer(SCORERS / f"{dataset_id_ok(args.scorer)}.yaml")
    sid_scorer, mode = sc["scorer_id"], js.mode_of(sc)
    metric = jva.primary_metric({"mode": mode})
    base = js.prompt_text(sc)
    unnamed = js.unnamed_dimensions(sc, base)
    if unnamed:
        die(
            f"{sid_scorer}: its prompt does not name the dimension(s) {', '.join(unnamed)}. A grade is one JSON object "
            "with a list of numbers per dimension, keyed by its name (the scorer's task.dimensions), and a judge not told "
            "the names answers with keys of its own: every reply would come back unparsed, and paid for. Name each "
            "dimension in the prompt, with the object's shape.",
            "invalid-file",
        )
    dataset_id = dataset_id_ok(args.dataset)
    items, refs = _load_rated(dataset_id)
    bad = rated_problems(sc, items, refs)
    if bad:
        die(
            f"{dataset_id} is not a rated dataset for {sid_scorer} ({len(bad)} problem(s)). {SHAPE}\n  {_listed(bad)}",
            "invalid-file",
        )
    sizes = [len(jva.parse_item(t)["outputs"]) for t in items.values()]
    if mode == "pairwise" and min(sizes) < 2:
        die(
            f"{sid_scorer} is pairwise and {dataset_id} has an item with fewer than 2 outputs: nothing to compare",
            "invalid-file",
        )
    per_call = int(sc["protocol"]["outputs_per_call"])
    if mode == "pick" and per_call < max(sizes):
        die(
            f"{sid_scorer} is a pick scorer whose protocol.outputs_per_call is {per_call}, and an item of {dataset_id} has "
            f"{max(sizes)} outputs: a pick made in blocks would name each block's winner, not the item's. Raise "
            "outputs_per_call to cover every output",
            "not-enough",
        )
    chosen = [
        j for j in sc["judges"] if not args.judges or j["id"] in {x.strip() for x in args.judges.split(",")}
    ]
    unknown = sorted(
        {x.strip() for x in (args.judges or "").split(",") if x.strip()} - {j["id"] for j in sc["judges"]}
    )
    if unknown or not chosen:
        die(
            f"--judges {args.judges}: {sid_scorer} has no judge {', '.join(unknown) or '(none named)'} "
            f"(its judges: {', '.join(j['id'] for j in sc['judges'])})",
            "not-found",
        )
    fakes = [j["id"] for j in chosen if j["params"].get("provider") == js.FAKE]
    if args.fill:
        if len(chosen) != len(sc["judges"]):
            die(
                f"--fill writes a block that names a run of every judge of {sid_scorer}: leave out --judges "
                f"(it has {', '.join(j['id'] for j in sc['judges'])})",
                "bad-argument",
            )
        if fakes:
            die(
                f"--fill: judge {', '.join(fakes)} uses provider: fake, a stand-in the gate refuses whatever the block "
                "says; the run is allowed (it tests the plumbing for $0), the fill is not",
                "not-allowed",
            )
        if not args.reason:
            die(
                "--fill needs --reason: the validation is a decision, with who made it and why",
                "bad-argument",
            )
        if args.dry_run:
            die("--fill and --dry-run: a dry run writes nothing", "bad-argument")
        _actor.require_named("judge-validate --fill")
        from evaluation_harness.model import scorers as _scorers  # noqa: PLC0415

        judged = _scorers.judged_scores(sid_scorer)
        if judged:
            die(
                f"{sid_scorer} has made {len(judged)} judged score(s), and its hash is recorded on each: a scorer that "
                "has judged is not edited. Make a new version of it, which is a new id that supersedes this one: "
                f"evh scorer-new <id> --set supersedes={sid_scorer} --set why=... --set validation=..., or "
                "validate the new version",
                "not-allowed",
            )
        if sc.get("validation") and not args.replace:
            die(
                f"{sid_scorer} has a validation block already: --replace replaces it with the one these runs make",
                "would-overwrite",
            )
    if args.floor_run:
        fr_rec = _scores_of(args.floor_run)
        if fr_rec is None:
            die(f"--floor-run {args.floor_run}: no such run (evh arm-list {dataset_id})", "not-found")
        if fr_rec.get("dataset_id") != dataset_id or (fr_rec.get("scores") or {}).get(metric) is None:
            die(
                f"--floor-run {args.floor_run} is on {fr_rec.get('dataset_id')!r} and has no {metric}: the floor is a run "
                f"of {dataset_id} scored on the judges' metric ({metric})",
                "mismatch",
            )
    units = {j["id"]: judge_system_params(sc, j) for j in chosen}
    cap = js.effective_cap(sc)
    texts = list(items.values())
    est = {jid: jva.estimate(texts, p) for jid, p in units.items()}
    paid = [j for j in chosen if j["params"].get("provider") != js.FAKE]
    print(
        f"validating {sid_scorer} on {dataset_id}: {len(items)} items, {mode} ({metric}), judges {', '.join(j['id'] for j in chosen)}"
    )
    blocked = False
    for jid, where, found in js.judge_access(sc):
        if jid not in units:
            continue
        print(f"  judge {jid:8s} {where}")
        for p in [] if args.dry_run else found:
            print(f"    MISSING: {p}")
        blocked = blocked or bool(found)
    if args.dry_run:
        print(
            f"DRY RUN (nothing called, nothing written; tokens are chars/{jva.CHARS_PER_TOKEN} estimates, cost from the scorer's price table)"
        )
        tc, tcost = 0, 0.0
        for jid, e in est.items():
            cost = e["est_cost_usd"]
            print(
                f"  judge {jid:8s} calls {e['calls']:5d}  tokens in {e['tokens_in']:>10,}  out {e['tokens_out']:>8,}  "
                f"est {'$' + format(cost, '.4f') if cost is not None else 'unpriced'}"
            )
            tc += e["calls"]
            tcost += cost or 0.0
        print("  floor        " + (f"run {args.floor_run}" if args.floor_run else "random: 0 calls, $0"))
        print(f"  TOTAL        calls {tc:5d}  est ${tcost:.4f}   cap {_spend.shown(cap)}")
        _jsonout.value(
            "dry_run",
            {"scorer": sid_scorer, "dataset": dataset_id, "calls": tc, "estimate_usd": round(tcost, 6), "cap_usd": cap,
             "judges": dict(est)},
        )  # fmt: skip
        return 0
    if blocked:
        die(
            "a judge cannot be called (MISSING above): nothing was sent. `evh env-check` shows what each role reads.",
            "not-configured",
        )
    if paid and cap is None:
        total = sum((est[j["id"]]["est_cost_usd"] or 0.0) for j in paid)
        die(
            f"no cost cap: set cost_cap_usd in the scorer, or EVAL_JUDGE_MAX_COST_USD (the dry run estimates ${total:.4f} "
            f"for {sum(est[j['id']]['calls'] for j in paid)} calls)",
            "not-configured",
        )
    # The runs share one cap, the command's: `_spend` counts across them in this process.
    if cap is not None:
        os.environ["EVAL_MAX_COST_USD"] = str(
            min(cap, own) if (own := env_float("EVAL_MAX_COST_USD")) is not None else cap
        )

    for j in chosen:
        if ensure_system(system_id(sid_scorer, j["id"]), units[j["id"]]):
            print(f"  wrote system {system_id(sid_scorer, j['id'])}")
    floor_sid = system_id(sid_scorer, FLOOR)
    if not args.floor_run and ensure_system(floor_sid, floor_system_params(sc)):
        print(f"  wrote system {floor_sid}")

    got: dict[str, tuple[str, float]] = {}
    n_each: dict[str, int | None] = {}
    floor: float | None = None
    floor_name = ""
    if args.floor_run:
        floor_name = args.floor_run
        floor, _ = _metric_of(args.floor_run, metric)
    else:
        rid, code = _run(floor_sid, dataset_id, len(items), args.resume)
        if rid is None or code not in (0,):
            return code or 1
        floor, _ = _metric_of(rid, metric)
        floor_name = rid
    for j in chosen:
        sid = system_id(sid_scorer, j["id"])
        if _spend.exhausted(j["params"]):
            print(f"  {j['id']}: NOT RUN, the cap is spent (${_spend.spent():.4f} of ${_spend.cap():.4f})")
            return EXIT_STOPPED
        rid, code = _run(sid, dataset_id, len(items), args.resume)
        if rid is None or code != 0:
            print(f"  {j['id']}: stopped (exit {code}); what was done is kept, and --resume continues it")
            return code or 1
        value, n = _metric_of(rid, metric)
        if value is None:
            print(f"  {j['id']}: run {rid} scored no {metric}")
            return 1
        got[j["id"]], n_each[j["id"]] = (rid, value), n

    print(
        f"\nvalidation of {sid_scorer} on {dataset_id}, {metric} (people's ratings; floor: {'a random verdict' if not args.floor_run else args.floor_run})"
    )
    print(
        f"  floor    {floor_name}  {metric} {floor:.4f}"
        if floor is not None
        else f"  floor    {floor_name}: no {metric}"
    )
    human = {
        "tau": ("human_tau",),
        "top1": ("human_top1", "top1_chance"),
        "pair_agreement": ("human_pair_agreement", "n_pairs"),
    }[metric]
    for j in chosen:
        rid, value = got[j["id"]]
        beat = "" if floor is None else ("  above the floor" if value >= floor else "  BELOW THE FLOOR")
        print(
            f"  {j['id']:8s} {metric} {value:.4f}  n {n_each[j['id']]}  {_extras(rid, human)}  run {rid}{beat}"
        )
    dims = js.task_for(sc)["dimensions"]
    carried = carried_dimensions(sc, refs)
    first_ref: dict[str, Any] = next((json.loads(r) for r in refs.values() if r), {})
    people = len(first_ref.get("raters") or []) or None
    what = args.what or (
        f"{metric} against the mean of {people or 'the'} people's ratings, over {', '.join(carried)} "
        f"({len(carried)} of the scorer's {len(dims)} dimension(s)) and {len(items)} items of {dataset_id}"
    )
    for d in dims:
        if d not in carried:
            print(
                f"  {d}: not validated on {dataset_id} (its ratings carry {', '.join(carried)}); nothing is averaged in"
            )
    block = _block(
        sc,
        dataset_id,
        metric,
        floor,
        got,
        what,
        args.differs or "",
        args.reason if args.fill else "",
        carried,
    )
    shown = {"validation": block, "prompt": {"sha256_at_16": js._sha(base)}}
    print("\nthe `validation` block these runs make (and the prompt's sha256):")
    print("  " + yaml.safe_dump(shown, sort_keys=False).replace("\n", "\n  ").rstrip())
    _jsonout.value("validation", {**block, "prompt_sha256": js._sha(base)})
    if not args.fill:
        print(
            '  write it into the scorer: re-run with --fill --reason "..." --by person:NAME (it reuses the runs with --resume)'
        )
        return 0
    from evaluation_harness.model.scorers import SCORER  # noqa: PLC0415

    by = _actor.stated("judge-validate --fill") or ""
    SCORER.patch(sid_scorer, [("validation", block), ("prompt.sha256_at_16", js._sha(base))], [], by)
    print(f"\nwrote the block into data/scorers/{sid_scorer}.yaml, by {by}")
    problems = js.validation_problems(js.load_scorer(SCORERS / f"{sid_scorer}.yaml"))
    if not problems:
        print("  validation_problems: none, the scorer is validated")
        return 0
    print(f"  validation_problems: {len(problems)}, the scorer is not validated:")
    for p in problems:
        print(f"    - {p}")
    return EXIT_UNVALIDATED
