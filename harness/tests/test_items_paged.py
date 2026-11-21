#!/usr/bin/env python3
"""A dataset's items on its catalog page at 10,000 items (PLAN_0.8.0 S3): paged, not one 13.8 MB page.

    python tests/test_items_paged.py

S1's 10,000-item project built a dataset page of 13.8 MB (every item a row, each with an inspect link naming 50
arms). Now the page holds the first ITEMS_PER_PAGE items and links the rest, ITEMS_PER_PAGE a page; every item is
on exactly one page; a small dataset keeps one page and no pager.
"""

import re
import sys
from pathlib import Path
from typing import Any, cast

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


class Fake:
    item_word = "item"

    def __init__(self, n: int) -> None:
        self.n = n

    def dataset_profile(self, ds):
        rows = [
            {"item_id": f"t{k:05d}", "words": 10 + k % 7, "reference": {"gold/x": "11 words"}}
            for k in range(self.n)
        ]
        return {
            "items": {
                "n": self.n,
                "kind": "text",
                "words": {"min": 10, "max": 16, "median": 13, "p25": 11, "p75": 15},
            },
            "references": [
                {
                    "id": "gold/x",
                    "shape": "text",
                    "items": self.n,
                    "words": {"min": 9, "max": 14, "median": 11, "p25": 10, "p75": 12},
                }
            ],
            "rows": rows,
        }


setattr(cb._visibility, "hidden", lambda ds: False)  # noqa: B010 (a module function replaced for the test)
arms = [f"runs/big/arm_{i}_v1" for i in range(50)]
html, pages = cb.render_inside(cast(Any, Fake(10000)), "big", arms, "overlap_f1")
n_pages = -(-10000 // cb.ITEMS_PER_PAGE)
ids = re.findall(r'title="(t\d{5})"', html) + [
    x for _rel, body in pages for x in re.findall(r'title="(t\d{5})"', body)
]
check(
    f"10,000 items: the page holds the first {cb.ITEMS_PER_PAGE}, the rest on {n_pages - 1} pages of their own",
    len(re.findall(r'title="(t\d{5})"', html)) == cb.ITEMS_PER_PAGE and len(pages) == n_pages - 1,
    (len(pages), n_pages),
)
check("every item on exactly one page, in order", ids == [f"t{k:05d}" for k in range(10000)], len(ids))
biggest = max([len(html)] + [len(b) for _r, b in pages])
check(
    "no page of items over 1 MB (it was 13.8 MB)",
    biggest < 1_000_000,
    biggest,
)
check(
    "the page names how many items there are and links every other page",
    "10000" in html and all(f'href="{rel.split("/")[-1]}#inside"' in html for rel, _b in pages),
    html[:300],
)
small, none = cb.render_inside(cast(Any, Fake(50)), "small", arms, "overlap_f1")
check("a small dataset: one page, no pager", none == [] and len(re.findall(r'title="(t\d{5})"', small)) == 50)
sys.exit(summary())
