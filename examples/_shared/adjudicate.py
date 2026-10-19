#!/usr/bin/env python3
"""Build an adjudicated reference set from a gold one and a committed adjudication file.

    python examples/_shared/adjudicate.py examples/classification-ag-news/adjudication.json

The gold labels are not redistributed (the corpora's licences do not allow it), so neither
is the adjudicated set: this copies the local gold reference set and overwrites only the
adjudicated items. The adjudication file is the committed record: which items, who decided,
what they were shown, and the verdict.

Then re-score every run against it, $0:

    cd harness && python scripts/rescore.py --dataset-id ag_news_200 \\
        --reference-id gold/ag_news_200_adj1 --out data/runs-adjudicated
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REFS = Path(__file__).resolve().parents[2] / "harness" / "data" / "references"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    adj = json.loads(Path(sys.argv[1]).read_text())
    base, dest = REFS / adj["base_reference"], REFS / adj["reference_id"]
    if not base.is_dir():
        print(f"no gold reference set at {base}: run the experiment's fetch.py first")
        return 1
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest)
    changed = 0
    for it in adj["items"]:
        f = dest / f"{it['item_id']}.txt"
        if not f.is_file():
            print(f"item {it['item_id']} is not in {base}")
            return 1
        if f.read_text().strip() != it["gold"]:
            print(f"item {it['item_id']}: local gold is {f.read_text().strip()!r}, "
                  f"the adjudication file says {it['gold']!r}")
            return 1
        f.write_text(it["adjudicated"])
        changed += it["adjudicated"] != it["gold"]
    print(f"{dest.relative_to(REFS)}: {len(adj['items'])} adjudicated, {changed} changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
