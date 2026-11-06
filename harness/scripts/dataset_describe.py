#!/usr/bin/env python3
"""Change what describes a dataset, never its items: its licence, description or card (PLAN_0.8.0 E2, E3, E4).

    evh dataset-describe --dataset-id D --licence CC-BY-SA-4.0
    evh dataset-describe --dataset-id D --description "200 news articles, four topics, stratified"
    evh dataset-describe --dataset-id D --licence none        # take the licence off
    evh dataset-describe --card-template > card.yaml          # the card's questions, to fill
    evh dataset-describe --dataset-id D --card card.yaml      # the filled card (it replaces the one there)

The items, their hashes, the id and the version stay: a dataset described differently is the same dataset, so no
run measured on it changes and no version is spent (E3). `evh licences` lists the ids; `unknown` when the source
states none, `LicenseRef-<name>` for a licence of its own. The card answers the datasheet questions under Croissant
RAI 1.0's property names (`dataUseCases`, `dataCollection`, `dataBiases`, …); an empty answer is left out.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _card, _licences, _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, read_json, write_json


def _read_card(path: _Path) -> dict:
    """A card file read and checked: its answered keys only (an empty answer is not an answer)."""
    import yaml  # noqa: PLC0415

    if not _store.is_file(path):
        die(f"no card file {path}", "not-found")
    try:
        doc = yaml.safe_load(_store.read_text(path, encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        die(f"{path}: not YAML or JSON ({str(e).splitlines()[0]})", "invalid-file")
    if not isinstance(doc, dict):
        die(f"{path}: a card is a mapping of question keys to answers", "invalid-file")
    card = {k: v.strip() if isinstance(v, str) else v for k, v in doc.items() if v not in (None, "")}
    bad = _card.problems(card)
    if bad:
        die(f"{path}: " + "; ".join(bad[:5]), "invalid-file")
    return {k: card[k] for k in _card.QUESTIONS if card.get(k)}


def main() -> int:
    """Set or clear a dataset's licence, or set its description."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id")
    ap.add_argument(
        "--licence", help="an id from evh licences, unknown, LicenseRef-<name>, or none to clear it"
    )
    ap.add_argument("--description", help="a new description")
    ap.add_argument(
        "--card", type=_Path, help="a YAML or JSON card (from --card-template): it replaces the card"
    )
    ap.add_argument("--card-template", action="store_true", help="print the card's questions as YAML to fill")
    args = ap.parse_args()
    if args.card_template:
        print(_card.template(), end="")
        return 0
    if not args.dataset_id:
        die("name the dataset: --dataset-id", "bad-argument")
    if args.licence is None and args.description is None and args.card is None:
        die("nothing to change: name --licence, --description or --card", "bad-argument")
    card = _read_card(args.card) if args.card is not None else None
    f = DATASETS / f"{dataset_id_ok(args.dataset_id)}.json"
    if not _store.is_file(f):
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
    if card is not None and doc.get("card") != card:
        said.append(f"card: {len(card)} of {len(_card.QUESTIONS)} questions answered")
        doc["card"] = card
        if not card:
            doc.pop("card")
    if not said:
        print(f"{args.dataset_id}: already so, nothing written")
        return 0
    write_json(f, doc)
    print(
        f"data/datasets/{args.dataset_id}.json: {'; '.join(said)}; the items and version {doc.get('version')} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
