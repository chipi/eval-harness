"""The rows view (RFC-023, PRD-014 FR8): one row per item of a dataset, what each run decided, its labels, its signals.

    evh inspect --dataset-id prod_2026_11 --rows --runs production_2026_11,triage_lead_v1 \\
        --wrong-against owner_2026_11 --new-vs triage_v1

The signals, each a filter (given together, an item needs all of them) and the sort (most signals first):

- wrong: the first run's decision (production's, by convention) is not the label's, in --wrong-against SET;
- disagree: another run decided differently from the first;
- split: the other runs (the candidates) decided differently among themselves;
- new: a field value the dataset in --new-vs has never had (fields with at most NEW_MAX values there);
- unlabelled: no label in any set yet.

"Decided the same" is the first run's adapter's `same(a, b)` (the same text when it has none). Nothing is written:
the view ends with the `evh pick` and `evh label-sheet` commands for the rows it shows.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from typing import Any

from evaluation_harness._common import die, load_dataset, read_json
from evaluation_harness._label_sets import labels_for, sets
from evaluation_harness.label_sheet import output, run_dir

SIGNALS = ("wrong", "disagree", "split", "new", "unlabelled")
#: --new-vs compares a field only when the governed dataset has at most this many values for it (a choice, an
#: alert name, a source), not a free text where every value is new.
NEW_MAX = 30


def _set_named(name: str) -> None:
    """Refuse a label set no dataset has."""
    if not any(name in (d["set"], f"{d['dataset_id']}/{d['set']}") for d in sets()):
        die(f"--wrong-against {name}: no such label set (evh labels lists them)")


def _new_values(fields_of, dataset_id: str, new_vs: str) -> dict[str, list[str]]:
    """{item: ["field=value", ...]}: the values of this dataset's items that `new_vs` has never had."""
    decl, values = fields_of(dataset_id)
    vdecl, vvalues = fields_of(new_vs)
    seen: dict[str, set[str]] = {}
    for name in decl:
        if name in vdecl:
            have = {str(v) for vs in vvalues.values() if (v := vs.get(name)) is not None}
            if len(have) <= NEW_MAX:
                seen[name] = have
    out: dict[str, list[str]] = {}
    for item, vs in values.items():
        new = [f"{n}={vs[n]}" for n, have in seen.items() if vs.get(n) is not None and str(vs[n]) not in have]
        if new:
            out[item] = new
    return out


def rows(
    dataset_id: str,
    runs: list[str],
    fields_of,
    wrong_against: str | None = None,
    new_vs: str | None = None,
) -> list[dict[str, Any]]:
    """Every item of the dataset in order: {item, fields, decisions {run: output}, labels, signals {name: detail}}.
    `fields_of(dataset)` gives ({name: field}, {item: {name: value}}) (the inspector's `_fields_of`)."""
    from evaluation_harness._adapter import same_of  # noqa: PLC0415

    ds = load_dataset(dataset_id)
    dirs = {n: run_dir(n, dataset_id) for n in runs}
    same = same_of(read_json(next(iter(dirs.values())) / "metrics.json").get("adapter")) if dirs else None
    if wrong_against:
        _set_named(wrong_against)
    if new_vs:
        load_dataset(new_vs)
    new = _new_values(fields_of, dataset_id, new_vs) if new_vs else {}
    _, values = fields_of(dataset_id)
    labels = labels_for(dataset_id)
    out = []
    for it in ds.get("items") or []:
        i = it["item_id"]
        dec = {n: output(d, i) for n, d in dirs.items()}
        mine = labels.get(i, [])
        sig: dict[str, str] = {}
        outs = [(n, o) for n, o in dec.items() if o is not None]
        first = dec.get(runs[0]) if runs else None
        if wrong_against and first is not None and same is not None:
            lab = next(
                (r["text"] for r in mine if wrong_against in (r["set"], f"{r['dataset_id']}/{r['set']}")),
                None,
            )
            if lab is not None and not same(lab, first):
                sig["wrong"] = wrong_against
        if first is not None and same is not None:
            off = [n for n, o in outs if n != runs[0] and not same(first, o)]
            if off:
                sig["disagree"] = ", ".join(off)
        cands = [o for n, o in outs if n != runs[0]]
        if same is not None and len(cands) > 1 and any(not same(cands[0], o) for o in cands[1:]):
            sig["split"] = f"{len(cands)} candidates"
        if i in new:
            sig["new"] = ", ".join(new[i])
        if not mine:
            sig["unlabelled"] = ""
        out.append({"item": i, "fields": values.get(i, {}), "decisions": dec, "labels": mine, "signals": sig})
    return out
