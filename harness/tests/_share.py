"""How much of the machine the tests take. The X3 is shared (32 CPUs): a run that started one suite per CPU, each
drawing permutations on a thread per CPU, starved robotics-lab of CPU on 2026-11-24 (homelab, 2026-11-26).

- EVH_TEST_JOBS: how many suites the runners run side by side; by default 4 on a machine of more than 8 CPUs, and
  on a smaller one (CI's runners have 4) what the runner used before;
- EVH_TEST_NICE: the niceness a run takes, once, its children with it (default 10; 0 leaves it);
- on a machine of more than 8 CPUs each test process draws its permutations on 2 workers (stats.py's EVH_WORKERS),
  unless EVH_WORKERS is set.

tests/test_share.py checks it.
"""

import os

#: A machine of more CPUs than this is a shared one, held back by default.
BIG = 8


def cpus() -> int:
    """The CPUs this process may run on."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 4


def jobs(default: int | None = None) -> int:
    """How many suites to run side by side: EVH_TEST_JOBS, else 4 on a big machine, else `default` (the runner's own,
    when it has one) or the CPU count."""
    env = os.environ.get("EVH_TEST_JOBS", "").strip()
    if env.isdigit() and int(env) > 0:
        return int(env)
    n = cpus()
    return 4 if n > BIG else (default or n)


def share() -> None:
    """Called by a runner before it starts anything: the run's priority lowered once (a runner a runner starts is
    not lowered again), and the test processes' permutation workers capped on a big machine."""
    if not os.environ.get("EVH_TEST_NICED"):
        try:
            n = int(os.environ.get("EVH_TEST_NICE", "10"))
        except ValueError:
            n = 10
        if n > 0 and hasattr(os, "nice"):
            try:
                os.nice(n)
            except OSError:
                pass
        os.environ["EVH_TEST_NICED"] = "1"
    if cpus() > BIG:
        os.environ.setdefault("EVH_WORKERS", "2")
