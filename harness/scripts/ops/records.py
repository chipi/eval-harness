"""The reads of the project's records and reports as operations (RFC-032 step 9): what `evh licences`, `looks`, `picks`,
`exposure` and the rest of the older view commands answered, each now one operation with its inputs, its resource and its
structured answer; the command prints the answer as it always printed it (`say`). Nothing here writes."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from typing import Any

from evaluation_harness.ops import legacy
from evaluation_harness.ops.registry import Op


def _num(v: Any) -> Any:
    """A score as the text views print it: four decimals, six below 0.001 (a cost per item); the JSON keeps it."""
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) >= 0.001 or v == 0 else f"{v:.6f}"
    return v


_R = "evaluation_harness.ops.records"
_STR = {"type": "string"}

OPS = (
    Op("licences", "read", "the licences a dataset can name (SPDX ids), a line each: pick one for `--licence`",
       "GET", "/licences", f"{_R}:licences", f"{_R}:say_licences",
       inputs={"search": {"type": "string", "description": "keep the licences whose id or line contains this (any case)"}}),
    Op("looks", "read", "the looks each test set allows: its looks so far, the next one's level, its limit and its prior use",
       "GET", "/looks", f"{_R}:looks", f"{_R}:say_looks",
       inputs={"dataset": {"type": "string", "description": "one test set (default: every one)"}}),
    Op("picks", "read", "the picks waiting for the next version of governed datasets: per target, where each came from, its labels, tags and note",
       "GET", "/picks", f"{_R}:picks", f"{_R}:say_picks",
       inputs={
           "for": {"type": "string", "description": "only the picks for this dataset"},
           "tag": {"type": "array", "items": _STR, "description": "KEY=VALUE: only picks with this tag"},
       }),
    Op("exposure", "read", "a held-out side's exposure register, in counts: who read how many of its items, and what for",
       "GET", "/exposure", f"{_R}:exposure", f"{_R}:say_exposure",
       inputs={
           "dataset": {"type": "string", "description": "the held-out side (default: every one)"},
           "ids": {"type": "boolean", "description": "each read with its item id (a person only)"},
       },
       tool_hidden=("ids",), public_dropped="a held-out side's reads are the project's own"),
    Op("sealed-counts", "read", "counts over a held-out side by the fields it was sealed with: for safety, never to judge effect (RFC-031)",
       "GET", "/datasets/{dataset}/sealed-counts", f"{_R}:sealed_counts", f"{_R}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_R}:print_sealed_counts", inputs={
           "by": {"type": "string", "description": "the allowed fields to group by, comma-separated (default: every allowed one)"},
           "capture": {"type": "string", "description": "also count this capture's records on the held-out side of the boundary"},
           "no_day": {"type": "boolean", "description": "totals only, not per day"},
       }, public_dropped="a held-out side's counts are for the project's own safety watch"),
    Op("periods", "read", "a code record's deployed periods, numbered, dated, with their faithfulness (RFC-031)",
       "GET", "/models/{model}/periods", f"{_R}:periods", f"{_R}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_R}:print_periods", inputs={
           "system": {"type": "string", "description": "a replay system: count the dataset's items per period by its time field"},
           "dataset": {"type": "string", "description": "the dataset whose items are counted (with system)"},
       }),
    Op("period-compare", "read", "a past period at its own code, beside a candidate on the same items: production, the as-run replay and the candidate, with the paired test (RFC-031)",
       "GET", "/systems/{system}/period-compare", f"{_R}:period_compare", f"{_R}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_R}:print_period_compare", inputs={
           "dataset": {"type": "string", "description": "the dataset the three runs are on"},
           "candidate": {"type": "string", "description": "the candidate: a run id, or a system id (its latest run on the dataset)"},
           "production": {"type": "string", "description": "production's recorded arm (arm-from-capture): a run id, as faithfulness takes, or a system id"},
           "period": {"type": "integer", "description": "the code record's deployed period, by number (evh periods)"},
           "from": {"type": "string", "description": "the period's start (ISO, with an offset)"},
           "to": {"type": "string", "description": "its end (default: now)"},
           "metric": {"type": "string", "description": "the measure (default: the replay run's primary metric)"},
       }, required=("dataset", "candidate")),
    Op("faithfulness-show", "read", "a faithfulness record of a code record: its counts, every disagreement and who named which, and its coverage (RFC-030)",
       "GET", "/models/{model}/faithfulness", f"{_R}:faithfulness_show", f"{_R}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_R}:print_faithfulness_show",
       inputs={"n": {"type": "integer", "description": "the faithfulness record's number (default: the newest)"}}),
    Op("label-mutants", "read", "mutation-test a labeller: each named change to the rules or the join must move some labels (RFC-031)",
       "GET", "/datasets/{dataset}/label-mutants", f"{_R}:label_mutants", f"{_R}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_R}:print_label_mutants", inputs={
           "capture": {"type": "string", "description": "the capture whose records hold the decisions"},
           "map": {"type": "string", "description": "the rules"},
           "outcomes": legacy.OUTCOMES,
           "mutants": {"type": "string", "description": "a project's own mutants (FILE.py: mutants(rules), join_mutants(join))"},
       }, required=("capture", "map"), tool_hidden=("mutants",), status=f"{_R}:label_mutants_status",
       public_dropped="it reads a rules file by path and the captures, which are this machine's"),
    Op("validate", "read", "schema and integrity checks over the data tree: each check exists because its absence let a real defect through; run it before you trust any number",
       "GET", "/validate", f"{_R}:validate", f"{_R}:say_blocks", output=legacy.BLOCKS, printer=f"{_R}:print_validate",
       status=f"{_R}:validate_status", public_dropped="a public copy is not a whole project: validate fails by design"),
    Op("run-compare", "read", "diff two runs, fingerprint first; refused when the comparison would be meaningless",
       "GET", "/run-compare", f"{_R}:run_compare", f"{_R}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_R}:print_run_compare", inputs={
           "baseline": {"type": "string", "description": "the baseline run's id"},
           "candidate": {"type": "string", "description": "the candidate run's id"},
           "noise": {"type": "number", "description": "the arm's own spread; deltas at or below it are reported as noise (0 means the arm is deterministic)"},
       }, required=("baseline", "candidate")),
    Op("baselines", "read", "the baselines: each goal's on each dataset, and each dataset's own, with their evidence and history (RFC-027); the export a production system reads",
       "GET", "/baselines", f"{_R}:baselines", f"{_R}:say_baselines", status="",
       inputs={
           "goal": {"type": "string", "description": "only this goal's baselines"},
           "no_goal": {"type": "boolean", "description": "only the datasets' own baselines (runs with no goal)"},
           "dataset": {"type": "string", "description": "only this dataset's"},
           "all_versions": {"type": "boolean", "description": "every version in the history, the current included"},
       }),
    Op("deploy-sheet", "read", "what production must match to run what was measured (RFC-023): the model, its record and deployment, every setting the arm sent, what it reported per item; and whether a capture says production ran it",
       "GET", "/systems/{system}/deploy-sheet", f"{_R}:deploy_sheet", f"{_R}:say_deploy_sheet", status=f"{_R}:deploy_sheet_status",
       inputs={"capture": {"type": "string", "description": "a capture whose records say what production ran (the adapter's production_ran)"}}),
    Op("runs-list", "read", "the runs, each with the three things that make a number mean something: its id, its build and its scores (the baselines: evh baselines)",
       "GET", "/runs", f"{_R}:runs_list", f"{_R}:say_runs_list",
       inputs={"label": {"type": "string", "description": 'the arm label to list (default: "", the plain runs; the labels present are named in the answer)'}}),
    Op("data-ls", "read", "what the project keeps under data/, in either store: the overview, one folder, or the files a name matches (UXS-004)",
       "GET", "/data", f"{_R}:data_ls", f"{_R}:say_data_ls",
       inputs={
           "path": {"type": "string", "description": "a folder under data/ (default: the overview)"},
           "find": {"type": "string", "description": "every file whose path holds TEXT"},
           "offset": {"type": "integer", "description": "the first entry of a long folder to list"},
       }, positional=("path",), public_dropped="the project's files are this machine's (the data page, UXS-004)"),
    Op("data-show", "read", "one file the project keeps under data/, in either store: its text, size, date and sha256, or a setting's fields (UXS-004)",
       "GET", "/data/file", f"{_R}:data_show", f"{_R}:say_data_show",
       inputs={
           "path": {"type": "string", "description": "the file, relative to data/"},
           "text": {"type": "boolean", "description": "its text only, nothing else"},
           "fields": {"type": "boolean", "description": "a setting's fields, one KEY: value a line"},
       }, required=("path",), positional=("path",), public_dropped="a file's text is this machine's: a hidden dataset's items too (the data page, UXS-004)"),
    Op("dataset-card", "read", "a dataset's card: what it is, where it came from and the datasheet's answers; or the same as Croissant 1.1 or a Hugging Face README",
       "GET", "/datasets/{dataset}/card", f"{_R}:dataset_card", f"{_R}:say_dataset_card", printer=f"{_R}:print_dataset_card",
       inputs={
           "format": {"type": "string", "enum": ["text", "croissant", "hf-readme"], "description": "how the card is written (default text)"},
           "creator": {"type": "string", "description": "with format croissant: who made the dataset (a record has no creator)"},
       }),
    Op("dataset-items", "read", "what is inside a dataset, without its text: its shape, then one row per item, or one item and its text when it is here (`evh dataset-profile` writes the profile)",
       "GET", "/datasets/{dataset}/items", f"{_R}:dataset_items", f"{_R}:say_dataset_items",
       inputs={"item": {"type": "string", "description": "one item: its id, or the start of it; its text when it is here"}},
       public_hidden=("item",)),
    Op("search", "read", "the catalog's search: datasets, arms, reference sets, metrics and goals, with the command that shows each hit",
       "GET", "/search", f"{_R}:search", f"{_R}:say_search", status=f"{_R}:search_status",
       inputs={"text": {"type": "array", "items": _STR, "minItems": 1, "description": "the words to look for"}},
       required=("text",), positional=("text",)),
)  # fmt: skip

sealed_counts, print_sealed_counts = legacy.of("evaluation_harness.sealed_counts")
periods, print_periods = legacy.of("evaluation_harness.view_periods")
period_compare, print_period_compare = legacy.of("evaluation_harness.period_compare")
faithfulness_show, print_faithfulness_show = legacy.of("evaluation_harness.faithfulness_show")
label_mutants, print_label_mutants = legacy.of("evaluation_harness.label_mutants")
say_blocks = legacy.say_blocks
validate, print_validate = legacy.of("evaluation_harness.validate_tree")


def label_mutants_status(r: dict[str, Any]) -> int:
    """6 when a mutant survived: the labeller does not feel that change."""
    return 6 if (r.get("values") or {}).get("survived") else 0


def validate_status(r: dict[str, Any]) -> int:
    """1 when a check failed."""
    from evaluation_harness._common import EXIT_PROBLEMS  # noqa: PLC0415

    return 0 if (r.get("values") or {}).get("passed") else EXIT_PROBLEMS


def _run_compare_body(baseline: str, candidate: str, noise: float | None = None) -> int:
    import argparse  # noqa: PLC0415

    from evaluation_harness import compare_runs  # noqa: PLC0415

    return compare_runs._run(argparse.Namespace(baseline=baseline, candidate=candidate, noise=noise))


run_compare, print_run_compare = legacy.pair(_run_compare_body)


def licences(search: str | None = None) -> dict[str, Any]:
    """The licences whose id or line contains `search`, each with where its text is."""
    from evaluation_harness._licences import LICENCES, url  # noqa: PLC0415

    q = (search or "").lower()
    return {
        "search": search or "",
        "licences": [
            {"id": i, "allows": line, "url": url(i)}
            for i, line in LICENCES
            if q in i.lower() or q in line.lower()
        ],
    }


def say_licences(r: dict[str, Any]) -> str:
    """licences' answer as text: a line each, then the two that are not in the list."""
    from evaluation_harness._licences import UNKNOWN  # noqa: PLC0415

    rows = r["licences"]
    if not rows:
        return (
            f"No licence matches {r['search']!r}. `{UNKNOWN}` when the source states none; "
            "LicenseRef-<name> for your own."
        )
    width = max(len(x["id"]) for x in rows)
    out = [f"{x['id']:<{width}}  {x['allows']}" for x in rows]
    out += [
        "",
        f"{UNKNOWN:<{width}}  the source states no licence",
        f"{'LicenseRef-<name>':<{width}}  a licence of its own, described in the dataset's card",
        "",
        "Set it: evh dataset-create … --licence ID, or on a dataset: evh dataset-describe --dataset-id D --licence ID",
    ]
    return "\n".join(out)


def looks(dataset: str | None = None) -> dict[str, Any]:
    """Every test set's looks (or the one named): its look counts, next level and limit."""
    from evaluation_harness import _looks, _store  # noqa: PLC0415
    from evaluation_harness._common import _paths  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if dataset and not _looks.is_test_set(dataset):
        raise Problem(
            f"{dataset} is not a test set (a goal's role: test, or a sealed side of a split)", "not-found"
        )
    d = _paths()["DATASETS"]
    ids = sorted(p.stem for p in _store.glob(d, "*.json")) if _store.is_dir(d) else []
    sets = [dataset] if dataset else [i for i in ids if _looks.is_test_set(i)]
    return {"sets": [_looks.summary(ds) for ds in sets]}


def say_looks(r: dict[str, Any]) -> str:
    """looks' answer as text: a line a test set, a line a look."""
    from evaluation_harness._actor import said as _said  # noqa: PLC0415

    out = []
    for s in r["sets"]:
        out.append(
            f"{s['dataset_id']}: {len({x.get('key') for x in s['looks']})} look(s) of {s['limit']}; the next is look "
            f"{s['next']}, one-sided at {s['next_level']:.4%}"
            + (f"; used {s['prior_use']} time(s) before looks were counted (0.8.0)" if s["prior_use"] else "")
        )
        # One question is one look (_looks module doc): a decision may write several records of it, as study-confirm
        # does (the look named before its runs, the verdict after), so a look is one row.
        by_key: dict[Any, list[dict[str, Any]]] = {}
        for x in s["looks"]:
            by_key.setdefault(x.get("key"), []).append(x)
        for recs in by_key.values():
            x = recs[0]
            out.append(
                f"  look {x.get('number')}  {x.get('level'):.4%}  {x.get('what')}  by "
                f"{_said(x.get('actor'))}  {x.get('at') or ''}"
                + (f"  {x['verdict']}" if x.get("verdict") else "")
                + (
                    f"  ({len(recs)} records of this look, the last {recs[-1].get('at') or ''})"
                    if len(recs) > 1
                    else ""
                )
            )
    if not r["sets"]:
        out.append(
            "no test sets: a goal's dataset with role: test, or a split's sealed side (dataset-split --seal)"
        )
    return "\n".join(out)


def picks(**inputs: Any) -> dict[str, Any]:
    """The picks waiting (for one dataset, or with every tag given), each with the labels its item already has."""
    from evaluation_harness._label_sets import label_line, labels_for, source_line  # noqa: PLC0415
    from evaluation_harness._picks import waiting  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    tags = {}
    for t in inputs.get("tag") or []:
        k, sep, v = t.partition("=")
        if not sep:
            raise Problem(f"tag {t!r}: KEY=VALUE", "bad-argument")
        tags[k] = v
    target = inputs.get("for")
    rows = waiting(target, tags or None)
    labels_by_ds: dict = {}
    for r in rows:
        ds = r["from"]
        if ds not in labels_by_ds:
            labels_by_ds[ds] = labels_for(ds)
        r["labels"] = [
            {
                "set": f"{x['dataset_id']}/{x['set']}",
                "source": source_line(x["source"]),
                "label": label_line(x["text"]),
            }
            for x in labels_by_ds[ds].get(r["item"], [])
        ]
    return {"for": target or "", "picks": rows}


def say_picks(r: dict[str, Any]) -> str:
    """picks' answer as text: per target, a line a pick."""
    rows = r["picks"]
    if not rows:
        return "No picks waiting (evh pick --dataset-id D --item X --for V)."
    groups: dict[str, list] = {}
    for p in rows:
        for t in p.get("for") or [""]:
            if not r["for"] or t == r["for"]:
                groups.setdefault(t, []).append(p)
    out = []
    for t in sorted(groups, key=lambda x: (x == "", x)):
        out.append(f"{t or 'no target yet'}: {len(groups[t])} pick(s) waiting")
        for p in groups[t]:
            labels = "; ".join(f"{x['source']}: {x['label']}" for x in p["labels"]) or "none yet"
            tag = " ".join(f"{k}={v}" for k, v in sorted((p.get("tags") or {}).items()))
            out.append(
                f"  {p['item']}  from {p['from']}"
                + (f" (capture {p['capture']})" if p.get("capture") else "")
                + f"  labels: {labels}"
                + (f"  [{tag}]" if tag else "")
                + (f'  "{p["note"]}"' if p.get("note") else "")
            )
    return "\n".join(out)


def exposure(dataset: str | None = None, ids: bool = False) -> dict[str, Any]:
    """The held-out sides' registers in counts (the one named, or every one); `ids` adds each read, for a person."""
    from collections import Counter  # noqa: PLC0415

    from evaluation_harness import _exposure, _store  # noqa: PLC0415
    from evaluation_harness._common import DATA, load_dataset  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if ids:
        from evaluation_harness._actor import actor  # noqa: PLC0415

        if actor()["type"] != "person":
            raise Problem(
                "ids prints a held-out side's item ids: a person's command (an agent reads the counts)",
                "not-allowed",
            )
        if not dataset:
            raise Problem("ids needs a dataset", "bad-argument")
    if dataset and not _exposure.applies(dataset):
        raise Problem(
            f"{dataset} is not a held-out side (no seal): it has no exposure register", "not-allowed"
        )
    if dataset:
        names = [dataset]
    else:
        root = DATA / "datasets"
        names = [
            i
            for i in (sorted(p.stem for p in _store.glob(root, "*.json")) if _store.is_dir(root) else [])
            if _exposure.applies(i)
        ]
    sides = []
    for ds in names:
        rows = _exposure.rows(ds)
        n_items = len(load_dataset(ds)["items"])
        read = {str(x.get("item_id")) for x in rows}
        sides.append(
            {
                "dataset_id": ds,
                "items": n_items,
                "exposed": len(read),
                "reads": len(rows),
                "by": dict(Counter(str(x.get("by")) for x in rows)),
                "what": dict(Counter(str(x.get("what")) for x in rows)),
                **({"rows": rows} if ids else {}),
            }
        )
    return {"sides": sides}


def say_exposure(r: dict[str, Any]) -> str:
    """exposure's answer as text: per side, how many items were read, by whom and what for."""
    if not r["sides"]:
        return "No held-out sides (dataset-split --seal makes one)."
    out = []
    for s in r["sides"]:
        out.append(
            f"{s['dataset_id']}: {s['exposed']} of {s['items']} item(s) exposed ({s['items'] - s['exposed']} unread), "
            f"{s['reads']} read(s)"
        )
        out += [f"  by {k}: {n}" for k, n in sorted(s["by"].items(), key=lambda kv: -kv[1])]
        out += [f"  what: {k}: {n}" for k, n in sorted(s["what"].items(), key=lambda kv: -kv[1])]
        out += [
            f"  {x.get('item_id')}  {x.get('at')}  {x.get('by')}  {x.get('what')}  ({x.get('source')})"
            for x in s.get("rows", [])
        ]
    return "\n".join(out)


def baselines(**inputs: Any) -> dict[str, Any]:
    """Every selected baseline with its current version, how to reproduce it and its history."""
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415
    from evaluation_harness.view_baselines import SCHEMA, lines  # noqa: PLC0415

    goal, no_goal = inputs.get("goal"), bool(inputs.get("no_goal"))
    if goal and no_goal:
        raise Problem("goal and no_goal: one or the other", "bad-argument")
    with legacy.refusing():
        rows = lines(goal, no_goal, inputs.get("dataset"), bool(inputs.get("all_versions")))
    return {"schema": SCHEMA, "baselines": rows}


def say_baselines(r: dict[str, Any]) -> str:
    """baselines' answer as text: per baseline, its run, why, scores, evidence and history."""
    from evaluation_harness._common import how  # noqa: PLC0415

    rows = r["baselines"]
    if not rows:
        return "no baselines yet: promote a run:  " + how(
            'evh run-promote --run <id> --reason "..."', 'make run-promote RUN=<id> REASON="..."'
        )
    out = []
    for b in rows:
        from evaluation_harness._actor import said  # noqa: PLC0415

        named = said(b.get("actor"))
        out.append(f"{b['goal'] or 'the dataset'}'s baseline on {b['dataset']}: version {b['current']}")
        out.append(
            f"    run      {b.get('promoted_from')}, promoted {str(b.get('promoted_at') or '')[:10]} by {named}"
        )
        out.append(f"    why      {b.get('reason', '(none recorded)')}")
        label = f"scores (mean of {b['repeats']} repeats)" if b.get("repeats") else "scores"
        out.append(
            f"    {label}   " + "  ".join(f"{k}={_num(v)}" for k, v in (b.get("scores") or {}).items())
        )
        ev = b.get("evidence") or {}
        vd = ev.get("verdict")
        if b.get("migrated"):
            out.append("    evidence promoted before 0.8.0: not recorded")
        elif ev.get("compared_to") is None:
            out.append("    evidence the first version: nothing to compare with")
        elif vd:
            out.append(
                f"    evidence against version {ev['compared_to']}: {vd.get('outcome')}, delta {vd.get('delta'):+.4f},"
                f" p {vd.get('p'):.4g} on {ev.get('measure')} (n={ev.get('n')})"
            )
        else:
            out.append(
                f"    evidence against version {ev['compared_to']}: no test ({'; '.join(ev.get('not_comparable') or [])})"
            )
        for h in b["history"]:
            what = (
                f"restores {h['restores']}"
                if h.get("restores")
                else (f"replaced {h['replaces']}" if h.get("replaces") else "first")
            )
            out.append(
                f"    v{h['version']:<4}   {str(h.get('promoted_at') or '')[:10]} {h.get('promoted_from')} ({what}): {h.get('reason', '')}"
            )
    return "\n".join(out)


def deploy_sheet(system: str, capture: str | None = None) -> dict[str, Any]:
    """The deploy sheet of a system's promoted run (else its latest), and with `capture` whether the capture says
    production ran it."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness import deploy_sheet as ds  # noqa: PLC0415

    with legacy.refusing():
        s = ds.sheet(system)
        c = ds.check(s, capture) if capture else None
    out = {k: v for k, v in s.items() if not k.startswith("_")}
    if c is not None:
        ok = bool(c["keys"]) and all(not k["differ"] and not k["missing"] for k in c["keys"].values())
        out["capture_check"] = {**c, "ok": ok}
    return _jsonout.plain(out)


def deploy_sheet_status(r: dict[str, Any]) -> int:
    """1 when a capture was checked and production did not run the promoted model and prompt on every decision."""
    from evaluation_harness._common import EXIT_PROBLEMS  # noqa: PLC0415

    return EXIT_PROBLEMS if r.get("capture_check") and not r["capture_check"]["ok"] else 0


def say_deploy_sheet(s: dict[str, Any]) -> str:
    """deploy-sheet's answer as text."""
    out: list[str] = []
    p = s["promoted"]
    out.append(f"deploy sheet: {s['system_id']}")
    ref = s.get("reference") or {}
    against = f"{ref['id']} ({ref.get('tier') or 'no tier'})" if ref.get("id") else "no reference"
    out.append(f"  measured by   {s['run_id']} on {s['dataset_id']}, against {against}")
    out.append(
        f"  promoted      as {p['goal'] or 'the dataset'}'s baseline on {p['dataset_id']}, version {p['version']},"
        f" {p['promoted_at']}"
        if p
        else "  promoted      no: this is the arm's latest run, not a baseline"
    )
    mm = s["model"]
    out.append(f"\nmodel\n  sent          {mm['sent']}")
    out.append(f"  record        {mm['record'] or '(no model record names it)'}")
    if mm["deployment"]:
        for k, v in mm["deployment"].items():
            out.append(f"  {k:<13} {json.dumps(v) if isinstance(v, dict) else v}")
    out.append(f"  provider      {mm['provider']}")
    out.append(f"  server        {mm['server'] or '(not recorded)'}")
    out.append(f"  build         {mm['build'] or '(none recorded: a hosted model has no digest)'}")
    out.append("\nsettings the arm sent")
    for k, v in s["sent"].items():
        out.append(f"  {k:<22} {v}")
    if s["not_sent"]:
        out.append(f"  (bookkeeping, not sent: {', '.join(s['not_sent'])})")
    for k, v in s["record_settings_not_sent"].items():
        out.append(f"  NOTE: the record sets {k}: {v}; this arm did not send it (it names no model_record)")
    out.append("\ndeclared")
    for part, kv in s["declared"].items():
        for k, v in kv.items():
            out.append(f"  {part}.{k:<14} {v}")
    out.append("\nwhat the system reported per item")
    for k, vs in s["reported"].items():
        out.append(f"  {k:<22} {', '.join(vs)}")
    if not s["reported"]:
        out.append("  (nothing: the adapter records no _meta)")
    out.append(f"\nadapter         {s['adapter'].get('id')} {s['adapter'].get('sha256') or ''}".rstrip())
    out.append(f"harness         {s['harness']['version']} {s['harness']['commit'] or ''}".rstrip())
    c = s.get("capture_check")
    if c is not None:
        out.append(f"\ncapture {c['capture']}: {c['records']} record(s)")
        for k, row in c["keys"].items():
            if row["missing"] == c["records"] and not row["match"] and not row["differ"]:
                out.append(f"  {k:<12} production recorded none, so it cannot be checked")
                continue
            line = f"  {k:<12} {row['match']} match"
            if row["differ"]:
                line += "; differ: " + ", ".join(
                    f"{v} ({n})" for v, n in sorted(row["differ"].items(), key=lambda kv: -kv[1])[:5]
                )
            if row["missing"]:
                line += f"; not recorded: {row['missing']}"
            out.append(line + f"   (expected: {', '.join(row['expected']) or 'nothing the run reported'})")
        if not c["keys"]:
            out.append("  the adapter's production_ran said nothing for any record")
        out.append(
            "\nevery captured decision was made by the promoted model and prompt"
            if c["ok"]
            else "\nNOT every captured decision was made by the promoted model and prompt (above: what differs)"
        )
    return "\n".join(out)


_RUN_COLUMNS = (
    "run_id",
    "system_id",
    "dataset_id",
    "created_at",
    "build_ref",
    "dirty",
    "directory",
    "scores",
)


def runs_list(label: str | None = None) -> dict[str, Any]:
    """The runs read under `label` (the plain runs by default), each with its build and its scores; the labels present."""
    from evaluation_harness._common import BOOKKEEPING_PREFIXES, data_rel  # noqa: PLC0415
    from evaluation_harness._runs import runs_on  # noqa: PLC0415
    from evaluation_harness.model import runs as model_runs  # noqa: PLC0415

    label = label or ""
    metrics = runs_on(label=label)
    return {
        "label": label,
        "labels": [x for x in model_runs.labels() if x != label],
        "count": len(metrics),
        "runs": [
            {
                "run_id": m["run_id"],
                "system_id": m.get("system_id"),
                "dataset_id": m["dataset_id"],
                "created_at": m.get("created_at"),
                "build_ref": (m.get("build") or {}).get("ref"),
                "dirty": (m.get("build") or {}).get("dirty"),
                "directory": data_rel(model_runs.run_of(d)),
                "scores": {
                    k: v for k, v in sorted(m["scores"].items()) if not k.startswith(BOOKKEEPING_PREFIXES)
                },
            }
            for d, m in metrics
        ],
    }


def say_runs_list(r: dict[str, Any]) -> str:
    """runs-list's answer as text: a line a run, the dirty builds marked, the other labels named."""
    from evaluation_harness._common import how  # noqa: PLC0415

    if not r["runs"]:
        return "no runs yet — " + how(
            "start with `evh run --system <id> --dataset <id>` (docs/GUIDE.md)", "try:  make demo"
        )
    out = [f"{'run_id':44} {'dataset_id':18} {'build':14} scores"]
    for m in r["runs"]:
        scores = "  ".join(f"{k}={_num(v)}" for k, v in m["scores"].items())
        dirty = "?" if m["dirty"] is None else "*" if m["dirty"] else " "
        out.append(f"{m['run_id']:44} {m['dataset_id']:18} {(m['build_ref'] or '?')[:12]}{dirty} {scores}")
    if any(m["dirty"] for m in r["runs"]):
        out.append("\n  * = produced by a dirty tree; its build ref does not describe what ran")
    if any(m["dirty"] is None for m in r["runs"]):
        out.append(
            ("" if any(m["dirty"] for m in r["runs"]) else "\n")
            + "  ? = the tree was not checked (EVAL_BUILD_REF set, or an imported run); whether it was dirty is unknown"
        )
    if r["labels"]:
        out.append(f"  also present under --label: {', '.join(repr(x) for x in r['labels'])}")
    return "\n".join(out)


def _size(n: int | None) -> str:
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return ""


@contextlib.contextmanager
def _data_refusals() -> Iterator[None]:
    """The data page's refusals, as the model's own."""
    from evaluation_harness import _data_page  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    try:
        yield
    except _data_page.Refused as exc:
        raise Problem(str(exc), exc.kind) from None


def data_ls(path: str | None = None, find: str | None = None, offset: int = 0) -> dict[str, Any]:
    """What the project keeps under data/: the overview, a folder's listing, or the files whose path holds `find`."""
    from evaluation_harness import _data_page  # noqa: PLC0415

    with _data_refusals():
        if find:
            return {"search": _data_page.search(find), "find": find}
        if not path:
            return {"overview": _data_page.overview()}
        return {"listing": _data_page.listing(path, offset or 0)}


def say_data_ls(r: dict[str, Any]) -> str:
    """data-ls's answer as text."""
    out: list[str] = []
    if "search" in r:
        hits = r["search"]
        out += list(hits["paths"])
        if hits["total"] > len(hits["paths"]):
            out.append(f"... and {hits['total'] - len(hits['paths'])} more")
        out.append(f"{hits['total']} file(s) match {r['find']!r}")
    elif "overview" in r:
        o = r["overview"]
        where = f" · {o['database']} ({_size(o['database_bytes'])})" if o["database"] else ""
        out.append(f"store: {o['store']}{where}")
        out.append("\nsettings (edit them with evh data-put; delete with evh data-rm)")
        out += [f"  {s['folder']:<16} {s['files']:>6}  {s['kind']}" for s in o["settings"]]
        out.append("\ndata (written by evh commands; read-only here)")
        out += [f"  {d['folder']:<16} {d['files']:>6}  {d['kind']}" for d in o["data"]]
    else:
        ls = r["listing"]
        for e in ls["entries"]:
            if e["type"] == "run":
                done = "" if e["finished"] else "  (not finished)"
                out.append(f"  {e['name']}/  run · {e['dataset']} · {e['items']} item(s) · {e['made']}{done}")
            elif e["type"] == "folder":
                out.append(f"  {e['name']}/  {e['files']} file(s)")
            else:
                out.append(f"  {e['name']}  {_size(e['size'])}  {e['modified']}")
        shown = len(ls["entries"])
        more = (
            f" (from {ls['offset'] + 1}; --offset {ls['offset'] + shown} for the next)"
            if ls["total"] > ls["offset"] + shown
            else ""
        )
        out.append(f"{ls['path']}: {ls['total']} entr(ies){more}")
    return "\n".join(out)


def data_show(path: str, text: bool = False, fields: bool = False) -> dict[str, Any]:
    """One file of the project's data: its text, size, date and hash; with `fields`, a setting's fields; with `text`,
    the answer says only its text."""
    from evaluation_harness import _data_page, _settings_form  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    with _data_refusals():
        f = _data_page.show(path)
        if fields:
            if not f["editable"]:
                raise Problem(
                    f"{f['path']} is not a setting: it has no fields to show (text shows it)", "bad-argument"
                )
            return {"file": f, "values": _settings_form.values_of(f["path"])}
    if text and f["text"] is None:
        raise Problem(f"{f['path']} is binary ({f['size']} bytes): it has no text to show", "bad-argument")
    return {"file": f, "text_only": bool(text)}


def say_data_show(r: dict[str, Any]) -> str:
    """data-show's answer as text."""
    from evaluation_harness import _settings_form  # noqa: PLC0415

    f = r["file"]
    if "values" in r:
        out = [
            f"{key}: {value if not isinstance(value, (dict, list)) else ('{}' if isinstance(value, dict) else '[]')}"
            for key, value in _settings_form.flat(r["values"])
        ]
        out.append(
            f"\n{f['path']} · {f['setting_kind']} · change a field with evh data-put {f['path']} --set KEY=VALUE"
        )
        return "\n".join(out)
    if r.get("text_only"):
        return f["text"].rstrip("\n")
    out = [f["text"] if f["text"] is not None else f"binary, {f['size']} bytes"]
    out.append(f"\n{f['path']} · {f['size']} bytes · {f['modified']} · sha256 {f['sha256'][:12]}")
    if f["editable"]:
        note = f" · {f['runs_made']} run(s) were made with this system" if "runs_made" in f else ""
        out.append(
            f"a setting: its fields with --fields; change one with evh data-put {f['path']} --set KEY=VALUE{note}"
        )
    else:
        out.append(f"written by {f['written_by']}; not edited here")
    return "\n".join(out)


def _card_text(record: dict) -> str:
    """The card as a reader reads it: what, where from, then each answered question."""
    from evaluation_harness import _card, _licences  # noqa: PLC0415

    src = record.get("source") or {}
    lic = record.get("licence")
    lines = [
        f"{record['dataset_id']}  version {record.get('version')}  ({len(record.get('items') or [])} items)",
        record.get("description") or "",
        "licence: " + (f"{lic}  {_licences.url(lic) or ''}".rstrip() if lic else "(not given)"),
        "source: "
        + (
            "  ".join(str(x) for x in (src.get("provider"), src.get("ref"), src.get("url")) if x)
            or "(not recorded)"
        )
        + (f"  revision {src['revision']}" if src.get("revision") else ""),
    ]
    card = record.get("card") or {}
    lines.append(f"\ncard: {len(card)} of {len(_card.QUESTIONS)} questions answered")
    for k, q in _card.QUESTIONS.items():
        if k in card:
            lines.append(f"  {q}\n    {card[k]}")
    if len(card) < len(_card.QUESTIONS):
        lines.append("  answer the rest: evh dataset-describe --card-template, then --card FILE")
    return "\n".join(lines) + "\n"


def dataset_card(dataset: str, format: str = "text", creator: str | None = None) -> dict[str, Any]:
    """A dataset's card as text, as Croissant (a JSON document) or as a Hugging Face README."""
    from evaluation_harness import _croissant, _fields, _hf_readme, _store  # noqa: PLC0415
    from evaluation_harness._common import DATASETS, dataset_id_ok, read_json  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if format not in ("text", "croissant", "hf-readme"):
        raise Problem(f"format: one of text, croissant, hf-readme; got {format!r}", "bad-argument")
    with legacy.refusing():
        f = DATASETS / f"{dataset_id_ok(dataset)}.json"
        if not _store.is_file(f):
            raise Problem(f"no dataset {dataset!r} (evh dataset-list lists them)", "not-found")
        record = read_json(f)
    missing: list[str] = []
    if format == "text":
        card: Any = _card_text(record)
    elif format == "hf-readme":
        card = _hf_readme.readme(record)
    else:
        fs = _fields.load_fieldset(record["fieldset"]) if record.get("fieldset") else None
        types = {x["name"]: x["type"] for x in (fs or {}).get("fields") or []}
        card, missing = _croissant.export(record, f, record.get("source_dir") or "", types, creator)
    return {"dataset_id": dataset, "format": format, "card": card, "missing": list(missing)}


def say_dataset_card(r: dict[str, Any]) -> str:
    """dataset-card's answer as text: the card as it is written (a Croissant document as JSON)."""
    card = r["card"]
    return (card if isinstance(card, str) else json.dumps(card, indent=2, ensure_ascii=False)).rstrip("\n")


def print_dataset_card(dataset: str, format: str = "text", creator: str | None = None) -> int:
    """dataset-card on the terminal: the card on stdout, as a file to redirect; what Croissant asks for on stderr."""
    import sys  # noqa: PLC0415

    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    try:
        r = dataset_card(dataset, format, creator)
    except Problem as exc:
        from evaluation_harness import _common  # noqa: PLC0415

        _common.die(str(exc), exc.kind)
    if r["missing"]:
        print(
            f"{dataset}: Croissant asks for {', '.join(r['missing'])}, which the record does not give: left out"
            + (" (--creator names who made it)" if "creator" in r["missing"] else ""),
            file=sys.stderr,
        )
    print(say_dataset_card(r))
    return 0


def dataset_items(dataset: str, item: str | None = None) -> dict[str, Any]:
    """A dataset's profile (data/profiles/<id>.json): its shape and a row an item; one item and its text when it is here.
    A public server's call on a `text: hidden` dataset: ids and lengths only."""
    from evaluation_harness import _common, _exposure, _store, _visibility  # noqa: PLC0415
    from evaluation_harness.dataset_profile import load_profile  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    with legacy.refusing():
        p = load_profile(dataset)
    if _visibility.public() and _visibility.hidden(dataset):
        if item:
            raise Problem(f"{dataset} is `text: hidden`: no item is shown here", "not-public")
        p = _visibility.public_profile(p)
    if (
        _visibility.public()
    ):  # a profile written --with-text carries item text: a public server serves none (L2)
        p = {**p, "rows": [{k: v for k, v in r.items() if k != "text"} for r in p["rows"]]}
    if not item:
        return p
    _exposure.read_by_harness(
        p["dataset_id"],
        [r["item_id"] for r in p["rows"] if r["item_id"].startswith(item)],
        "dataset-items --item",
    )
    rows = [dict(r) for r in p["rows"] if r["item_id"].startswith(item)]
    if not rows:
        raise Problem(f"no item {item!r} in {p['dataset_id']}", "not-found")
    for r in rows:  # its text when it is here, as the printed form shows it
        local = _common.item_path(p["dataset_id"], r["item_id"])
        if local:
            r["text"] = _store.read_text(local, encoding="utf-8", errors="replace")
    return {**p, "rows": rows, "item": item}


def say_dataset_items(p: dict[str, Any]) -> str:
    """dataset-items' answer as text: the profile, and with an item its text."""
    from evaluation_harness.dataset_profile import render  # noqa: PLC0415

    with legacy.refusing():
        return render(p, p.get("item"))


def search(text: list[str]) -> dict[str, Any]:
    """The catalog's search over datasets, arms, reference sets, metrics and goals: the best 40 hits, as the page ranks them."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness.ops.views import _view  # noqa: PLC0415

    A, by_ds = _view()
    words = " ".join(text).lower().split()

    def score(x: dict) -> int:
        # The page's ranking: a word in the title counts more than one in the description.
        t = x["t"].lower()
        return sum(
            4 if t.startswith(w) else 3 if w in t else 1 if w in x["d"].lower() else 0 for w in words
        ) + (x["k"] == "goal")

    hits = sorted(
        (x for x in cb.search_index(A, by_ds) if all(w in x["s"] for w in words)), key=score, reverse=True
    )[:40]
    return {"words": words, "hits": [{k: x[k] for k in ("k", "t", "d", "id") if k in x} for x in hits]}


_SEE = {
    "dataset": lambda x: f"evh dataset-show {x['t']}",
    "arm": lambda x: f"evh comparison-show --runs {x.get('id', x['t'])}",
    "reference": lambda x: "evh reference-show " + " ".join(x["t"].split("/", 1)),
    "metric": lambda x: f"evh metric-show {x['t']}",
    "goal": lambda x: f"evh goal-show {x.get('id', x['t'])}",
}


def say_search(r: dict[str, Any]) -> str:
    """search's answer as text: a line a hit, with the command that shows it."""
    if not r["hits"]:
        return "No match."
    return "\n".join(
        legacy.table_text(
            ["kind", "name", "about", "see it with"],
            [[x["k"], x["t"], x["d"], _SEE[x["k"]](x)] for x in r["hits"]],
        )
    )


def search_status(r: dict[str, Any]) -> int:
    """1 when nothing matched."""
    return 0 if r["hits"] else 1
