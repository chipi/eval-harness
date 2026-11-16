"""The significance block, restricted to items a previous dataset did NOT contain.

    python scripts/holdout_significance.py --dataset-id cnn_dailymail_200 \
        --exclude-dataset cnn_dailymail_20 --metric coverage

WHY THIS EXISTS
  `fetch.py --n 200` pages from offset 0 of the same split, so the 20-article slice is
  NESTED inside the 200. Arms chosen because they ranked high on those 20 are being
  re-measured on a set that still contains them — 10% of the new sample is the sample
  that selected them. A replication claim has to be read on the 180 items that did not
  take part in the selection, and "all 200" cannot make that claim.

  It reuses leaderboard.py's own `_significance`, deliberately. A second implementation
  of the same test is a second set of numbers to reconcile; the point here is the item
  set, not the statistics.
"""

from __future__ import annotations

from typing import Any

from evaluation_harness import _outputs
from evaluation_harness import leaderboard as lb
from evaluation_harness._common import dataset_item_ids, die
from evaluation_harness._runs import default_metric, direction, matrix, runs_on, warn_on_ambiguous_runs
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """The significance tests, on only the items a previous dataset did not contain."""
    args = legacy.namespace(inputs, "holdout")
    # Two runs sharing a system_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs("", args.dataset_id)

    args.metric = args.metric or default_metric(args.dataset_id, args.match)
    keep = None
    if args.exclude_dataset:
        prior = dataset_item_ids(args.exclude_dataset)
        all_items = dataset_item_ids(args.dataset_id)
        keep = all_items - prior
        print(
            f"  {args.dataset_id}: {len(all_items)} items, "
            f"{len(prior & all_items)} shared with {args.exclude_dataset}, "
            f"{len(keep)} held out"
        )

    runs = [r for r in runs_on(args.dataset_id, match=args.match) if _outputs.has_rows(r[0])]
    raw: list[float] = []
    M = matrix(runs, args.metric, keep=keep, raw=raw)
    if not M:
        die("no runs matched", "not-found")
    print(f"  {len(runs)} run(s), {len(M)} arm(s)")
    lb.significance(M, args.metric, asc=direction(runs, args.metric, args.asc, args.desc), raw_values=raw)
    return 0
