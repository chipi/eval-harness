#!/usr/bin/env python3
"""Promote labels to a reference (RFC-023, ADR-0022): the chosen labels, at the tier you decide, with a reason.

    evh reference-promote --dataset-id tickets_v1 --labels owner_v1 --tier gold --by owner \\
        --reason "the owner's labels of all six tickets, checked twice"
    evh reference-promote --dataset-id tickets_v2 --labels tickets_v1/author_v1 --tier silver --name tickets_v2_author \\
        --items t01_login --items t02_invoice --by owner --reason "the author model's answers on the two new tickets"

A reference is made only this way. The labels are the dataset's in the named set (`SET`, made on this dataset, or
`DATASET/SET`, made on another holding the same items: labels follow the item by its sha256), all of them or those
named with --items. They are written to data/references/<tier>/<name>/ (name: the dataset's id by default), the
layout runs, rescore and goals read, and its manifest records `promoted_from` (the set, its dataset and source), the
reason, who and when; for a set a model's run made, the run, its system and model too, so a run scored against it
is known to be graded against that model's answers. No rule ties the tier to the source: the promotion decides, and
records the source beside the tier. A reference is never overwritten.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from collections import Counter

from evaluation_harness import _jsonout, _store
from evaluation_harness._common import REFERENCES, die, evh_prog, load_dataset, now, read_json
from evaluation_harness._label_sets import answers, label_line, label_text, labels_for, sets, source_line
from evaluation_harness._references import write_manifest

CAVEAT = {
    "gold": "GOLD: promoted as gold from {set} ({source}): the answers a decision rests on.",
    "silver": (
        "SILVER: promoted as silver from {set} ({source}): consistent, not a claim that any arm is right. Good "
        "enough to RANK arms against each other; say so wherever a number scored against it is published."
    ),
}


def _write_reference(
    into, chosen, mine, hand_made, source, args, doc, not_here, set_ds, set_name, name
) -> None:
    """The reference's texts (unless adopted), its manifest and, when its texts are not redistributed, its
    .gitignore, written into `into`."""
    for iid in [] if hand_made else chosen:
        _store.write_text(into / f"{iid}.txt", mine[iid]["text"] + "\n", encoding="utf-8")
    authorship = {}
    if source.get("kind") == "model":
        # Who authored the texts is part of a reference's identity (the fingerprint hashes it): a run scored against
        # a model's answers is graded against that model.
        authorship = {
            "authored_by": source.get("config_id"),
            "model": source.get("model"),
            "from_run": {k: source.get(k) for k in ("run_id", "config_id", "fingerprint_hash", "build")},
        }
    write_manifest(
        into,
        args.tier,
        args.dataset_id,
        caveat=CAVEAT[args.tier].format(set=f"{set_ds}/{set_name}", source=source_line(source)),
        created_at=now(),
        promoted_from={"labels": set_name, "dataset_id": set_ds, "source": source},
        reason=args.reason,
        promoted_by=args.by,
        **authorship,
        **(
            {
                "redistributed": False,
                "source": f"{doc.get('rebuild')}, then evh reference-promote --dataset-id {args.dataset_id} --labels "
                f"{set_ds}/{set_name} --tier {args.tier} --reason … --by …"
                + (f" --name {name}" if args.name else ""),
            }
            if not_here
            else {}
        ),
    )
    if not_here:
        _store.write_text(
            into / ".gitignore",
            "# the reference set's texts are not redistributed (see manifest.json)\n*.txt\n",
        )


def main() -> int:
    """Promote a label set's labels to a reference set."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="the dataset the reference set is for")
    ap.add_argument("--labels", required=True, help="SET (made on this dataset) or DATASET/SET")
    ap.add_argument("--tier", required=True, choices=("gold", "silver"))
    ap.add_argument("--reason", required=True, help="why these labels are the yardstick (a sentence)")
    ap.add_argument(
        "--items", action="append", default=[], help="only this item (repeatable; default all labelled)"
    )
    ap.add_argument("--name", help="the reference set's name under its tier (default: the dataset's id)")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap, required=True, help="who promotes (recorded in the manifest)")
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("reference-promote", args.json, live=sys.stderr):
        if len(args.reason.split()) < 3:
            die(
                'REFUSED: --reason must be a sentence, not a word. It answers "why is this the yardstick?" later.',
                "bad-argument",
            )
        set_ds, _, set_name = args.labels.rpartition("/")
        set_ds = set_ds or args.dataset_id
        name = args.name or args.dataset_id
        if "/" in name or name.startswith(".") or not name:
            die(f"--name {name!r}: one name, no path", "bad-argument")
        ref_dir = REFERENCES / args.tier / name
        kept_out = _store.is_file(ref_dir / "manifest.json") and not any(_store.glob(ref_dir, "*.txt"))
        hand_made = (
            _store.is_dir(ref_dir)
            and not _store.exists(ref_dir / "manifest.json")
            and any(_store.glob(ref_dir, "*.txt"))
        )
        if _store.exists(ref_dir) and any(_store.iterdir(ref_dir)) and not kept_out and not hand_made:
            die(
                f"{ref_dir} exists: a reference set is never overwritten. Name another with --name.",
                "would-overwrite",
            )
        ds = load_dataset(args.dataset_id)
        from evaluation_harness import _seal  # noqa: PLC0415

        _seal.refuse_if_sealed(args.dataset_id, "a reference")
        ids = [it["item_id"] for it in ds.get("items") or []]
        mine = {
            iid: r
            for iid, rows in labels_for(args.dataset_id).items()
            for r in rows
            if r["dataset_id"] == set_ds and r["set"] == set_name
        }
        if not mine:
            die(
                f"no labels of {set_ds}/{set_name} on {args.dataset_id}'s items (evh labels --dataset-id {args.dataset_id})",
                "not-found",
            )
        if args.items:
            unknown = sorted(set(args.items) - set(ids))
            if unknown:
                die(f"--items: not in {args.dataset_id}: {', '.join(unknown[:8])}", "not-found")
            missing = sorted(set(args.items) - set(mine))
            if missing:
                die(f"--items: {set_ds}/{set_name} has no label for {', '.join(missing[:8])}", "not-enough")
            chosen = [i for i in ids if i in set(args.items)]
        else:
            chosen = [i for i in ids if i in mine]
        source = next(iter(mine.values()))["source"]
        if kept_out:
            return _rebuild(ref_dir, mine, set_ds, set_name)
        if hand_made:
            # A folder made by hand, with no manifest (ADR-0022): adopted only when it holds exactly these labels, so a
            # reference is still never overwritten; it then gets the promotion record it never had.
            here = {
                f.stem: _store.read_text(f, encoding="utf-8").strip() for f in _store.glob(ref_dir, "*.txt")
            }
            if set(here) != set(chosen) or any(
                label_text(answers(here[i])) != mine[i]["text"].strip() for i in chosen
            ):
                die(
                    f"{ref_dir} exists, made by hand with no manifest, and its texts are not {set_ds}/{set_name}'s: a "
                    f"reference is never overwritten. To keep it, import it as the labels first (evh label-import "
                    f"{ref_dir} --dataset-id {args.dataset_id} --set S --by WHO) and promote those; or name another with "
                    "--name.",
                    "would-overwrite",
                )
        doc = next((d for d in sets() if d["dataset_id"] == set_ds and d["set"] == set_name), {})
        not_here = doc.get("redistributed") is False
        # A new reference is built in a staging folder and moved into place whole (RFC-026 step 1): a reader (a run
        # starting, a job, the catalog) never sees its texts without its manifest. An adopted folder keeps its files byte
        # for byte: they are the labels already, and the reference digest every run scored against it recorded is of
        # these bytes (a newline added to each moved it); only its manifest is written, one file, whole.
        into = ref_dir if hand_made else _store.staging(ref_dir, f".{ref_dir.name}.partial-")
        try:
            _write_reference(
                into, chosen, mine, hand_made, source, args, doc, not_here, set_ds, set_name, name
            )
            if not hand_made:
                _store.adopt(into, ref_dir)
        except BaseException:
            if not hand_made:
                _store.rmtree(into, ignore_errors=True)
            raise
        print(
            f"{ref_dir}: {len(chosen)} of {len(ids)} item(s), {args.tier}, promoted from {set_ds}/{set_name} "
            f"({source_line(source)})"
        )
        print(
            "  commit it before the next run: an untracked reference marks every run scored against it dirty"
        )
        several = Counter(label_line(mine[i]["text"]) for i in chosen if len(answers(mine[i]["text"])) > 1)
        if several:
            print(
                f"  {sum(several.values())} label(s) accept more than one answer ("
                + ", ".join(f"{k}: {v}" for k, v in sorted(several.items()))
                + "): an output matching any of them scores as right, so each must be fully right, not a guess"
            )
        if not_here:
            print(
                "  its texts are kept out of git, as its label set's are: commit the manifest and the .gitignore"
            )
        return 0


def _rebuild(ref_dir, mine: dict, set_ds: str, set_name: str) -> int:
    """A promoted reference whose texts are kept out of git and not here: write them from its label set and check
    them against the manifest's checksums."""
    import hashlib  # noqa: PLC0415

    m = read_json(ref_dir / "manifest.json")
    pf = m.get("promoted_from") or {}
    if (pf.get("labels"), pf.get("dataset_id")) != (set_name, set_ds):
        die(
            f"{ref_dir} exists, promoted from {pf.get('dataset_id')}/{pf.get('labels')}: a reference set is never overwritten",
            "would-overwrite",
        )
    want = m.get("items_sha256") or {}
    texts = {iid: mine[iid]["text"] + "\n" for iid in want if iid in mine}
    bad = [iid for iid in want if hashlib.sha256(texts.get(iid, "").encode()).hexdigest() != want[iid]]
    if bad:
        die(
            f"REFUSED: the texts from {set_ds}/{set_name} do not match {ref_dir / 'manifest.json'}'s checksums "
            f"({len(bad)} of {len(want)} differ). Nothing was written.",
            "mismatch",
        )
    for iid, text in texts.items():
        _store.write_text(ref_dir / f"{iid}.txt", text, encoding="utf-8")
    print(f"{ref_dir}: {len(texts)} text(s) rebuilt from {set_ds}/{set_name}, matching the manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
