#!/usr/bin/env python3
"""Build an adjudicated reference set from a gold one and a committed adjudication file.

    python examples/_shared/adjudicate.py examples/classification-ag-news/adjudication.json

The gold labels are not redistributed (the corpora's licences do not allow it), so neither
is the adjudicated set: this copies the local gold reference set and overwrites only the
adjudicated items. The adjudication file is the committed record: which items, who decided,
what they were shown, and the verdict.

Then write its manifest (the copied one describes the base set) and re-score every run
against it, $0:

    evh reference-manifest --reference-id gold/ag_news_200_adj1 --dataset-id ag_news_200 \\
        --source "examples/_shared/adjudicate.py examples/classification-ag-news/adjudication.json" \\
        --labelled-by "one reader's adjudication of the dataset's labels" --not-redistributed \\
        --reason "the adjudicated labels sit beside the dataset's own, never deciding alone" --by <you>

    evh rescore --dataset-id ag_news_200 \\
        --reference-id gold/ag_news_200_adj1 --out data/runs-adjudicated
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REFS = Path(__file__).resolve().parents[2] / "harness" / "data" / "references"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))  # evaluation_harness: its store
from evaluation_harness import _store  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    adj = json.loads(_store.read_text(Path(sys.argv[1])))
    base, dest = REFS / adj["base_reference"], REFS / adj["reference_id"]
    if adj["reference_id"] == adj["base_reference"] or dest.resolve() == base.resolve():
        print(
            f"reference_id {adj['reference_id']!r} is the base reference: "
            "refusing, because the copy would delete the gold set it copies from"
        )
        return 1
    if not _store.is_dir(base):
        print(f"no gold reference set at {base}: run the eval's fetch.py first")
        return 1
    if _store.exists(dest):
        _store.rmtree(dest)
    _store.copy_tree(base, dest)
    # The base set's manifest describes the base set's texts, not these: it goes, and the
    # printed command writes this set's own.
    _store.unlink(dest / "manifest.json", missing_ok=True)
    changed = 0
    for it in adj["items"]:
        f = dest / f"{it['item_id']}.txt"
        if not _store.is_file(f):
            print(f"item {it['item_id']} is not in {base}")
            return 1
        if _store.read_text(f).strip() != it["gold"]:
            print(
                f"item {it['item_id']}: local gold is {_store.read_text(f).strip()!r}, "
                f"the adjudication file says {it['gold']!r}"
            )
            return 1
        _store.write_text(f, it["adjudicated"])
        changed += it["adjudicated"] != it["gold"]
    print(f"{dest.relative_to(REFS)}: {len(adj['items'])} adjudicated, {changed} changed")
    print(
        f"its manifest:  evh reference-manifest --reference-id {adj['reference_id']} "
        f"--dataset-id {adj['base_reference'].split('/', 1)[1]} "
        f'--source "examples/_shared/adjudicate.py {sys.argv[1]}" --not-redistributed '
        '--labelled-by "one reader\'s adjudication of the dataset\'s labels" --reason "…" --by <you>'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
