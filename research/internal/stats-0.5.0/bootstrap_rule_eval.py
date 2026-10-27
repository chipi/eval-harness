"""Score candidate small-sample rules for the bootstrap-t non-inferiority test on the simulations
bootstrap_rule_grid.py wrote. A rule is (threshold on g1, level factor when g1 is below it, minimum n when it is
below it, minimum n for any continuous test). For each, per n and shape: the error at the margin (must stay at or
below 0.025 within Monte Carlo error, about +-0.005 at 1000 simulations) and the power at no difference.

python research/internal/stats-0.5.0/bootstrap_rule_eval.py OUT_n10.jsonl OUT_n20.jsonl ...
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

ALPHA = 0.025
RULES = [
    # name, skew threshold, level factor under skew, min n under skew, min n overall
    ("RFC draft: g1<-1 -> a/2, n<50 inconclusive", -1.0, 0.5, 50, 0),
    (
        "CHOSEN: g1<-0.5 -> n<50 inc, a/4 below 100, a/2 from 100; any n<30 inc",
        -0.5,
        (0.25, 100, 0.5),
        50,
        30,
    ),
    ("g1<-0.5 -> a/2, n<50 inconclusive", -0.5, 0.5, 50, 0),
    ("g1<-0.5 -> a/2, n<50 inc; any n<30 inc", -0.5, 0.5, 50, 30),
    ("g1<-0.5 -> a/4, n<50 inc; any n<30 inc", -0.5, 0.25, 50, 30),
    ("g1<-0.25 -> a/2, n<50 inc; any n<30 inc", -0.25, 0.5, 50, 30),
    ("g1<-0.5 -> a/2, n<100 inc; any n<30 inc", -0.5, 0.5, 100, 30),
    ("g1<-0.5 -> a/2, no skew floor; any n<30 inc", -0.5, 0.5, 0, 30),
    ("always a/2, any n<30 inc", 99.0, 0.5, 0, 30),
    ("ADOPTED (revision 2): always a/2, any n<100 inc", 99.0, 0.5, 0, 100),
]


def decide(rec, thr, factor, min_skew_n, min_n):
    if rec["p"] is None or rec["n"] < min_n:
        return False
    skewed = rec["g1"] < thr
    if skewed and rec["n"] < min_skew_n:
        return False
    if isinstance(factor, tuple):
        factor = factor[0] if rec["n"] < factor[1] else factor[2]
    return rec["p"] <= (ALPHA * factor if skewed else ALPHA)


def main():
    recs = [
        json.loads(line)
        for path in sys.argv[1:]
        for line in Path(path).read_text(encoding="utf-8").splitlines()
    ]
    cells = defaultdict(list)
    for r in recs:
        cells[(r["n"], r["shape"], r["truth"])].append(r)
    keys = sorted({(n, s) for n, s, _ in cells})
    for name, thr, factor, msn, mn in RULES:
        print(f"\n{name}")
        print(f"{'n':>4} {'shape':>15} {'error':>6} {'power':>6}")
        worst = 0.0
        for n, shape in keys:
            null, alt = cells[(n, shape, "null")], cells[(n, shape, "alt")]
            e = sum(decide(r, thr, factor, msn, mn) for r in null) / len(null)
            pw = sum(decide(r, thr, factor, msn, mn) for r in alt) / len(alt)
            worst = max(worst, e)
            print(f"{n:>4} {shape:>15} {e:>6.3f} {pw:>6.3f}")
        print(f"worst error {worst:.3f}")


if __name__ == "__main__":
    main()
