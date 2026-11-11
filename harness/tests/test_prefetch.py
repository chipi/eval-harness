#!/usr/bin/env python3
"""Bootstrap-t's drawn at once in child processes, the same p's (PLAN_0.8.0 S2: cheaper resampling below 10,000).

    python tests/test_prefetch.py

S2's re-measure left a 50-arm catalog at 1,000 items at 146 s, its 47 bootstrap-t's drawn one after another.
`stats.prefetch(calls)` runs the calls once to learn which they draw, draws those in child processes and keeps them.
Checked: the p's equal the ones drawn here one by one, bit for bit, items and clusters; the children ran at the same
time (each child's input is written before any output is read); a test already kept is not drawn again; nothing runs
in parallel below PARALLEL_FROM, inside another prefetch, or with one test; a child that cannot start or fails leaves
the tests to be drawn here as before; sign-flips from a fresh generator are drawn the same way; an error in
the look ahead stays in it. A goal's decision with and without it: the S2 bench (PLAN_0.8.0). A family's sign-flips
(family_test's one stream) summed in children from the states each opponent starts at: the same p's as in order.
"""

import math
import os
import random
import shutil
import statistics
import sys
import tempfile
import time
from itertools import chain, compress
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
os.environ["EVH_P_CACHE"] = ""
os.environ["EVH_WORKERS"] = "4"  # children whatever the machine; the cap itself is checked at the end
from evaluation_harness import stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

DRAWS = 1500
rng = random.Random(11)
cases = [([rng.gauss(0.01 * j, 0.3) for _ in range(600)], [1] * 600, 0.02) for j in range(4)]
ks = [rng.randint(1, 6) for _ in range(150)]
cases.append(([sum(rng.gauss(0, 1) for _ in range(k)) for k in ks], ks, 0.1))


def draw_all() -> list:
    return [stats.bootstrap_t_p(t, s, m, draws=DRAWS) for t, s, m in cases]


def fresh() -> None:
    stats._KEPT.clear()


fresh()
t0 = time.monotonic()
here = draw_all()
one_by_one = time.monotonic() - t0

fresh()
stats.PARALLEL_FROM = 0
t0 = time.monotonic()
n = stats.prefetch(draw_all)
in_parallel = time.monotonic() - t0
check(f"all {len(cases)} drawn in child processes", n == len(cases), n)
check("then read back: the same p's bit for bit, items and clusters", draw_all() == here, (draw_all(), here))
check(
    f"the children ran at the same time ({in_parallel:.1f} s against {one_by_one:.1f} s one by one)",
    in_parallel < 0.75 * one_by_one + 1.0,
)
check("kept tests are not drawn again", stats.prefetch(draw_all) == 0)

flips = [[rng.gauss(0.01 * j, 0.3) for _ in range(800)] for j in range(4)]


def flip_all() -> list:
    return [stats.sign_flip_p(d, permutations=3000) for d in flips]


stats._P.clear()
flipped = flip_all()
stats._P.clear()
n = stats.prefetch(flip_all)
check("sign-flips from a fresh generator: drawn in child processes too", n == len(flips), n)
check("... and read back the same, bit for bit", flip_all() == flipped, (flip_all(), flipped))

fresh()
check(
    "an error in the look ahead (a stand-in p met code it breaks) does not reach the caller; what it saw is drawn",
    stats.prefetch(lambda: (draw_all(), 1 / 0)) == len(cases) and draw_all() == here,
)

fresh()
stats.PARALLEL_FROM = 10**12
check("below PARALLEL_FROM nothing runs in parallel", stats.prefetch(draw_all) == 0 and not stats._KEPT)
stats.PARALLEL_FROM = 0
fresh()
one = cases[0]
check(
    "one test is drawn here",
    stats.prefetch(lambda: stats.bootstrap_t_p(one[0], one[1], one[2], draws=DRAWS)) == 0 and not stats._KEPT,
)
inner: list = []
check(
    "a prefetch inside a prefetch draws nothing itself",
    stats.prefetch(lambda: inner.append(stats.prefetch(draw_all))) == len(cases) and inner == [0],
    inner,
)

fresh()
real = sys.executable
sys.executable = "/nonexistent/python"
try:
    check(
        "a child that cannot start: nothing drawn in parallel",
        stats.prefetch(draw_all) == 0 and not stats._KEPT,
    )
finally:
    sys.executable = real
check("... and the tests are drawn here, the same p's", draw_all() == here)

tmp = Path(tempfile.mkdtemp(prefix="evh-prefetch-"))
for name, body in (
    ("exits non-zero", "cat >/dev/null; exit 3"),
    ("prints no answer", "cat >/dev/null; echo '[1'"),
):
    fake = tmp / "python"
    fake.write_text(f"#!/bin/sh\n{body}\n")
    fake.chmod(0o755)
    fresh()
    sys.executable = str(fake)
    try:
        check(f"a child that {name}: nothing kept from it", stats.prefetch(draw_all) == 0 and not stats._KEPT)
    finally:
        sys.executable = real
    check("... and the tests are drawn here, the same p's", draw_all() == here)
shutil.rmtree(tmp)

# How many workers: a container's CPU quota counts, not the host's cores (the deployment runs at cpus 0.5).
del os.environ["EVH_WORKERS"]
cores = len(os.sched_getaffinity(0))
real_read = stats._read
files: dict = {}
stats._read = lambda path: files.get(path, "")
try:
    for name, given, want in (
        ("no quota (cgroup v2 says max)", {"/sys/fs/cgroup/cpu.max": "max 100000\n"}, cores),
        ("a quota of 0.5 CPU: nothing in parallel", {"/sys/fs/cgroup/cpu.max": "50000 100000\n"}, 1),
        ("a quota of 2 CPUs", {"/sys/fs/cgroup/cpu.max": "200000 100000\n"}, min(2, cores)),
        (
            "cgroup v1, no quota (-1)",
            {
                "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1\n",
                "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
            },
            cores,
        ),
        (
            "cgroup v1, a quota of 0.5 CPU",
            {
                "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "50000\n",
                "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
            },
            1,
        ),
    ):
        files.clear()
        files.update(given)
        check(f"workers: {name}: {want}", stats.workers_allowed() == want, stats.workers_allowed())
    files.clear()
    files["/sys/fs/cgroup/cpu.max"] = "50000 100000\n"
    fresh()
    check(
        "under 0.5 CPU the tests are drawn here, not in children",
        stats.prefetch(draw_all) == 0 and not stats._KEPT,
    )
finally:
    stats._read = real_read


# ── a sign-flip's hits on exact integers: the count the fsum formula gives, pattern for pattern ──────────────────────
def fsum_hits(deltas, a, signs):
    """The formula sign_flip_p used before (2026-11-11): the kept deltas and the flipped ones negated, fsum, / n."""
    neg = [-d for d in deltas]
    flip = bytes.maketrans(b"\x00\x01", b"\x01\x00")
    return sum(
        1
        for k in signs
        if abs(math.fsum(chain(compress(deltas, k), compress(neg, k.translate(flip)))) / len(deltas)) >= a
    )


hr = random.Random(5)
kinds = {
    "gaussian": [hr.gauss(0, 1) for _ in range(301)],
    "0/1 steps (ties at the threshold)": [float(hr.choice((-1, 0, 1))) for _ in range(64)],
    "tenths": [round(hr.uniform(-1, 1), 1) for _ in range(97)],
    "1e-12 to 1e6": [hr.gauss(0, 1) * 10 ** hr.randint(-12, 6) for _ in range(80)],
    "halves, all the same size": [hr.choice((0.5, -0.5)) for _ in range(40)],
    "ints": [hr.randint(-3, 3) for _ in range(120)],
}
bad_counts = {}
for name, d in kinds.items():
    sr = random.Random(9)
    signs = [stats._draw(sr, len(d)) for _ in range(4000)]
    a = abs(statistics.fmean(d))
    if stats._count_hits(d, a, iter(signs)) != fsum_hits(d, a, signs):
        bad_counts[name] = (stats._count_hits(d, a, iter(signs)), fsum_hits(d, a, signs))
check(
    "a sign-flip's hits on exact integers: the fsum formula's count, for every kind of data",
    not bad_counts,
    bad_counts,
)

# ── a family's sign-flips (family_test.py): one stream, its sampled opponents summed in children ─────────────────────
fam_rng = random.Random(23)
family: list[list] = [
    [fam_rng.gauss(0.05, 1) for _ in range(20)],  # exact: draws nothing
    [fam_rng.gauss(0.1, 1) for _ in range(400)],  # sampled
    [float(fam_rng.choice((-1, 0, 0, 1))) for _ in range(300)],  # sampled, 0/1 differences
    [fam_rng.gauss(0, 1) for _ in range(stats.LARGE_SAMPLE)],  # the normal limit; the stream moves past it
    [round(fam_rng.uniform(-1, 1), 1) for _ in range(250)],  # sampled, after the large one
    [fam_rng.randint(-3, 3) for _ in range(200)],  # sampled, ints
]
PERMS = 3000


def serial() -> list:
    """The loop family_test.py ran before: one generator, each opponent in order."""
    r = random.Random(stats.SEED)
    out = []
    for j, u in enumerate(family):
        later = any(stats.p_method(len(x)) == "sampled" for x in family[j + 1 :])
        out.append(stats.sign_flip_p(u, permutations=PERMS, rng=r, advance=later))
    return out


fam_want = serial()
os.environ["EVH_WORKERS"] = "4"
real_from, real_popen, real_floor = stats._sampled_from_state, stats.subprocess.Popen, stats.PARALLEL_FROM
here_drawn: list = []


def counted(*a):
    here_drawn.append(1)
    return real_from(*a)


stats._sampled_from_state = counted
stats.PARALLEL_FROM = 1
try:
    fam_got = stats.sign_flip_family(family, PERMS, stats.SEED)
    check(
        "a family in children: every p the one-stream loop gives, bit for bit (exact, sampled, 0/1, ints, a normal "
        "limit between), and the children summed every sampled one",
        [x.hex() for x in fam_got] == [x.hex() for x in fam_want] and not here_drawn,
        (fam_got, fam_want, len(here_drawn)),
    )

    def no_child(*_a, **_k):
        raise OSError("no fork")

    stats.subprocess.Popen = no_child  # type: ignore[misc,assignment]
    here_drawn.clear()
    fam_got = stats.sign_flip_family(family, PERMS, stats.SEED)
    check(
        "no child can start: the family is drawn here, in order, the same p's (no pool left)",
        [x.hex() for x in fam_got] == [x.hex() for x in fam_want],
        fam_got,
    )
    stats.subprocess.Popen = real_popen  # type: ignore[misc]
    stats.PARALLEL_FROM = 10**12  # this file runs at 0 above
    fam_got = stats.sign_flip_family(family, PERMS, stats.SEED)
    check(
        "below PARALLEL_FROM: drawn here, the same p's",
        [x.hex() for x in fam_got] == [x.hex() for x in fam_want],
        fam_got,
    )
finally:
    stats._sampled_from_state = real_from
    stats.subprocess.Popen = real_popen  # type: ignore[misc]
    stats.PARALLEL_FROM = real_floor
    del os.environ["EVH_WORKERS"]

for value, want in (("1", 1), ("3", 3), ("x", 0)):  # 0: not a number, ignored
    os.environ["EVH_WORKERS"] = value
    got = stats.workers_allowed()
    check(f"EVH_WORKERS={value}: {want or 'ignored'}", got == want if want else got >= 1, got)
os.environ["EVH_WORKERS"] = "1"
fresh()
check("EVH_WORKERS=1 turns it off", stats.prefetch(draw_all) == 0)
del os.environ["EVH_WORKERS"]

sys.exit(summary())
