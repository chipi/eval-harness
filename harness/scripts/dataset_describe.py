#!/usr/bin/env python3
"""Change what describes a dataset, never its items: its licence, its description (PLAN_0.8.0 E2, E3).

    evh dataset-describe --dataset-id D --licence CC-BY-SA-4.0
    evh dataset-describe --dataset-id D --description "200 news articles, four topics, stratified"
    evh dataset-describe --dataset-id D --licence none        # take the licence off

The items, their hashes, the id and the version stay: a dataset described differently is the same dataset, so no
run measured on it changes and no version is spent (E3). `evh licences` lists the ids; `unknown` when the source
states none, `LicenseRef-<name>` for a licence of its own.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _licences
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, read_json, write_json


def main() -> int:
    """Set or clear a dataset's licence, or set its description."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument(
        "--licence", help="an id from evh licences, unknown, LicenseRef-<name>, or none to clear it"
    )
    ap.add_argument("--description", help="a new description")
    args = ap.parse_args()
    if args.licence is None and args.description is None:
        die("nothing to change: name --licence or --description", "bad-argument")
    f = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if not f.is_file():
        die(f"no dataset {args.dataset_id!r} (evh datasets lists them)", "not-found")
    doc = read_json(f)
    said = []
    if args.licence is not None:
        if args.licence.strip().lower() == "none":
            if "licence" in doc:
                said.append(f"licence {doc.pop('licence')} taken off")
        else:
            why = _licences.problem(args.licence)
            if why:
                die(why, "bad-argument")
            lic = _licences.canonical(args.licence)
            if doc.get("licence") != lic:
                said.append(f"licence {doc.get('licence') or '(none)'} -> {lic}")
                doc["licence"] = lic
    if args.description is not None and doc.get("description") != args.description:
        said.append("description changed")
        doc["description"] = args.description
    if not said:
        print(f"{args.dataset_id}: already so, nothing written")
        return 0
    # The licence sits after the description, before the items: the record reads top-down.
    order = ["dataset_id", "version", "description", "licence"]
    write_json(
        f, {**{k: doc[k] for k in order if k in doc}, **{k: v for k, v in doc.items() if k not in order}}
    )
    print(
        f"data/datasets/{args.dataset_id}.json: {'; '.join(said)}; the items and version {doc.get('version')} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
