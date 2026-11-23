#!/usr/bin/env python3
"""What a view reads, kept while the data is what it was read from (RFC-032 step 9): model/view_cache.

    python tests/test_view_cache.py

In a throwaway project, in whichever store EVAL_STORE names (the store matrix runs both): a value is computed once and
reused; this process's own write through the store clears it at once, with no look at the data (the sqlite store's own
change counter does not move for a process's own writes); another process's write is seen at the next look (`begin()`;
in the sqlite store at every lookup); a value that a write overtook while it was being built is returned and not kept;
the weights stay under the budget, the least recently used out first, and a value heavier than the budget is not
kept; the cache can be turned off; threads that read and write at once never see a value older than a write that had
returned. And the store layer under it: `rel` gives the keys it always gave, for every shape of path, and the
connection is resolved once per project, not once per call.
"""

import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
proj = Path(tempfile.mkdtemp(prefix="evh-viewcache-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ.setdefault("EVAL_STORE", "files")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
from evaluation_harness import _common, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import view_cache as vc  # noqa: E402

STORE = os.environ["EVAL_STORE"]
data = proj / "data"
data.mkdir()
(proj / "config.yaml").write_text("catalog: {}\n")
_store.write_text(data / "a.txt", "one")


class Count:
    """A computation that says how often it ran."""

    def __init__(self, value: object = "v") -> None:
        self.n = 0
        self.value = value

    def __call__(self) -> object:
        self.n += 1
        return self.value


def other_process_writes(name: str, text: str) -> None:
    """What another process does to the data: not through this process's _store, so nothing of ours is told."""
    if STORE == "sqlite":
        c = sqlite3.connect(str(data / "project.sqlite"), timeout=60)
        c.execute(
            "INSERT OR REPLACE INTO files VALUES (?, ?, 'x', ?)",
            (name, text.encode(), 1_700_000_000_000_000_000),
        )
        c.commit()
        c.close()
    else:
        (data / name).write_text(text)


# ── a value is kept ────────────────────────────────────────────────────────────────────────────────────────────────
vc.clear()
c = Count()
vc.get("k", c)
vc.get("k", c)
check("a value is computed once and then kept", c.n == 1, c.n)
check("another key is another value", Count("w") is not None and vc.get("k2", Count("w")) == "w")

# ── what it did is counted (a deployment's /metrics reads stats()) ─────────────────────────────────────────────────
s0 = vc.stats()
kc = Count()
vc.get("counted", kc)
vc.get("counted", kc)
s1 = vc.stats()
vc.clear()
s2 = vc.stats()
check(
    "stats() counts a miss (computed) and a hit, the entries kept, and an invalidation when everything is dropped",
    s1["miss"] - s0["miss"] == 1
    and s1["hit"] - s0["hit"] == 1
    and s1["entries"] >= 1
    and s2["invalidation"] - s1["invalidation"] == 1
    and s2["entries"] == 0
    and s2["budget"] == vc.BUDGET,
    (s0, s1, s2),
)

# ── this process's own write clears it, at once ────────────────────────────────────────────────────────────────────
_store.write_text(data / "b.txt", "two")
vc.get("k", c)
check("a write through the store clears it, with no look at the data first (no begin())", c.n == 2, c.n)
_store.unlink(data / "b.txt")
vc.get("k", c)
check("so does a removal", c.n == 3, c.n)
_store.write_text(data / "d" / "x.txt", "x")
_store.rmtree(data / "d")
vc.get("k", c)
check("and a removed tree", c.n == 4, c.n)
vc.get("k", c)
check("a read is not a write: still kept", c.n == 4, c.n)

# ── another process's write ────────────────────────────────────────────────────────────────────────────────────────
other_process_writes("c.txt", "three")
if STORE == "sqlite":
    vc.get("k", c)
    check("sqlite: another process's commit is seen at the next lookup", c.n == 5, c.n)
else:
    vc.get("k", c)
    check("files: no look is due between two lookups of one operation", c.n == 4, c.n)
    vc.begin()
    vc.get("k", c)
    check("files: another process's write is seen at the next operation's first lookup", c.n == 5, c.n)
vc.get("k", c)
check("and then kept again", c.n == 5, c.n)
other_process_writes("c.txt", "three, changed")
vc.begin()
vc.get("k", c)
check("a file changed in place is seen too", c.n == 6, c.n)

# ── one look for an operation ──────────────────────────────────────────────────────────────────────────────────────
if STORE == "files":
    looks = [0]
    real_print = vc._print

    def counted() -> tuple:
        looks[0] += 1
        return real_print()

    vc._print = counted
    try:
        vc.clear()
        with vc.operation():
            vc.get("a", Count())
            vc.begin()  # a view starting inside the operation: it already asked
            vc.get("b", Count())
            vc.get("c", Count())
        check(
            "an operation looks at the data once, however many views it starts (files)",
            looks[0] == 1,
            looks[0],
        )
        vc.begin()
        vc.get("a", Count())
        check("outside an operation, begin() makes the next lookup look again", looks[0] == 2, looks[0])
    finally:
        vc._print = real_print

# ── the project's own files that decide what is read ───────────────────────────────────────────────────────────────
(proj / "config.yaml").write_text("catalog: {}\n# changed\n")
vc.begin()
vc.get("k", c)
check("config.yaml changed: the next look drops what was kept", c.n == 7, c.n)

# ── a value a write overtook ───────────────────────────────────────────────────────────────────────────────────────
vc.clear()


def slow() -> str:
    _store.write_text(data / "overtaken.txt", "while it was being read")
    return "old"


check("a value a write overtook is the caller's", vc.get("slow", slow) == "old")
late = Count("new")
check("and is not kept: the next lookup computes again", vc.get("slow", late) == "new" and late.n == 1)
born = vc.epoch()
_store.write_text(data / "later.txt", "x")
vc.get("by an old adapter", Count(), epoch_of=born)
again = Count()
vc.get("by an old adapter", again)
check("a value an older epoch built is never kept", again.n == 1)

# ── bounded ────────────────────────────────────────────────────────────────────────────────────────────────────────
was = vc.BUDGET
vc.BUDGET = 10
try:
    vc.clear()
    cs = {k: Count(k) for k in "abcd"}
    for k in "abc":
        vc.get(k, cs[k], weigh=lambda v: 4)
    check(
        "the total weight stays under the budget: 3 x 4 > 10, the least recently used is out",
        vc.weight() == 8,
    )
    vc.get("b", cs["b"], weigh=lambda v: 4)
    vc.get("c", cs["c"], weigh=lambda v: 4)
    check("what is kept is not computed again", cs["b"].n == 1 and cs["c"].n == 1)
    vc.get("a", cs["a"], weigh=lambda v: 4)
    check("the one out was the oldest: it is computed again", cs["a"].n == 2 and cs["b"].n == 1)
    check("each value thrown out for room is counted as an eviction", vc.stats()["eviction"] >= 2, vc.stats())
    big = Count("big")
    vc.get("big", big, weigh=lambda v: 11)
    vc.get("big", big, weigh=lambda v: 11)
    check(
        "a value heavier than the whole budget is not kept, and nothing else is thrown out for it",
        big.n == 2 and vc.weight() == 8,
    )
finally:
    vc.BUDGET = was

# ── two threads asking for one value at once: one computes ──────────────────────────────────────────────────────────
vc.clear()
started, release = threading.Event(), threading.Event()
got: list[str] = []
computed = [0]


def slow_value() -> str:
    computed[0] += 1
    started.set()
    release.wait(10)
    return "v"


def asker() -> None:
    got.append(vc.get("flight", slow_value))


first_t = threading.Thread(target=asker)
first_t.start()
started.wait(10)
second_t = threading.Thread(target=asker)
second_t.start()
second_t.join(0.3)
waiting = second_t.is_alive()
waits = vc.stats()["wait"]
release.set()
first_t.join(10)
second_t.join(10)
check(
    "a second thread that asks for a value being computed waits for it (counted as a wait): computed once, both given it",
    waiting and computed[0] == 1 and got == ["v", "v"] and waits >= 1,
    (waiting, computed[0], got),
)
failed = [0]


def broken() -> str:
    failed[0] += 1
    raise RuntimeError("no")


try:
    vc.get("flight2", broken)
except RuntimeError:
    pass
check(
    "a computation that raised is not in flight: the next asker computes it",
    vc.get("flight2", lambda: "ok") == "ok",
)

# ── an operation's answer ──────────────────────────────────────────────────────────────────────────────────────────
vc.clear()
runs = [0]


def answer() -> dict:
    runs[0] += 1
    return {"arms": [{"arm": "a", "values": (1, 2)}], "n": runs[0]}


first = vc.result("arm-list", {"x": 1}, answer)
second = vc.result("arm-list", {"x": 1}, answer)
check("an answer is computed once and kept", runs[0] == 1 and second == first, runs[0])
second["arms"].clear()
check(
    "what a caller changes in an answer it was given is not changed in what is kept",
    vc.result("arm-list", {"x": 1}, answer) == first,
)
check(
    "the first caller is given what was computed; a later one is given an equal copy, a new object",
    first is not second,
)
check(
    "its inputs are its key: other inputs, other answer",
    vc.result("arm-list", {"x": 2}, answer)["n"] == 2 and vc.result("other", {"x": 1}, answer)["n"] == 3,
)
check(
    "the key does not depend on the order of the inputs",
    vc.result("o2", {"a": 1, "b": 2}, answer) == vc.result("o2", {"b": 2, "a": 1}, answer) and runs[0] == 4,
)
_store.write_text(data / "w.txt", "w")
check("a write clears it", vc.result("arm-list", {"x": 1}, answer)["n"] == 5)


def refuse() -> dict:
    runs[0] += 1
    raise ValueError("no such dataset")


for _ in range(2):
    try:
        vc.result("refused", {}, refuse)
    except ValueError:
        pass
check("a refusal is raised every time and never kept", runs[0] == 7, runs[0])


def unpicklable() -> dict:
    runs[0] += 1
    return {"f": lambda: 1}


check(
    "an answer that cannot be pickled is given, not kept",
    callable(vc.result("u", {}, unpicklable)["f"])
    and callable(vc.result("u", {}, unpicklable)["f"])
    and runs[0] == 9,
)
before = vc.weight()
vc.result("sized", {}, lambda: {"text": "x" * 6400})
check(
    "what an answer weighs is its size: one per 64 bytes",
    100 <= vc.weight() - before <= 110,
    vc.weight() - before,
)


class Day:
    """_common.today() as another day."""

    n = 1

    @classmethod
    def today(cls) -> "Day":
        return cls()

    def toordinal(self) -> int:
        return Day.n


real_today = vc._common.today if hasattr(vc._common, "today") else None
vc._common.today = Day.today  # type: ignore[assignment]
try:
    runs[0] = 0
    vc.result("daily", {}, answer)
    vc.result("daily", {}, answer)
    Day.n = 2
    vc.result("daily", {}, answer)
finally:
    vc._common.today = real_today  # type: ignore[assignment]
check(
    "a view that counts back from today is another view tomorrow: kept for the day it was computed",
    runs[0] == 2,
    runs[0],
)
vc.ON = False
runs[0] = 0
off_a, off_b = vc.result("off", {}, answer), vc.result("off", {}, answer)
vc.ON = True
check(
    "with the cache off the caller is given what is computed, every time", runs[0] == 2 and off_a is not off_b
)

# ── off ────────────────────────────────────────────────────────────────────────────────────────────────────────────
vc.clear()
vc.ON = False
off = Count()
vc.get("o", off)
vc.get("o", off)
vc.ON = True
check("turned off, every lookup computes", off.n == 2, off.n)

# ── threads: a reader never sees a value older than a write that had returned ──────────────────────────────────────
vc.clear()
errors: list[str] = []
stop = threading.Event()
counter = [0]


def snapshot() -> int:
    return int(_store.read_text(data / "n.txt"))


def reader() -> None:
    while not stop.is_set():
        floor = counter[0]  # a write that had returned before this lookup began
        got = vc.get("n", snapshot)
        if got < floor:
            errors.append(f"read {got} after {floor} had been written")


_store.write_text(data / "n.txt", "0")
readers = [threading.Thread(target=reader) for _ in range(6)]
for t in readers:
    t.start()
for n in range(1, 60):
    _store.write_text(data / "n.txt", str(n))
    counter[0] = n
stop.set()
for t in readers:
    t.join()
check(
    "six readers and a writer: no reader ever read a value older than a returned write",
    not errors,
    errors[:3],
)

# ── the store layer under it: rel ──────────────────────────────────────────────────────────────────────────────────


def rel_before(path: object) -> str | None:
    """`_store.rel` as it was written before the path-to-key work: pathlib for every call."""
    if STORE != "sqlite" or not isinstance(path, (str, os.PathLike)):
        return None
    try:
        key = Path(os.path.abspath(path)).relative_to(os.path.abspath(_common.DATA)).as_posix()
    except ValueError:
        return None
    if key in ("", ".") or key == _store.DB or key.startswith(_store.DB + "-"):
        return None
    return key


shapes = [
    data / "runs" / "r1" / "run.json", str(data / "runs" / "r1" / "run.json"), data, str(data), str(data) + "/",
    data / "a.txt", data / ".." / "data" / "a.txt", data / "x" / ".." / "y.txt", str(data) + "//runs//r1",
    data / "project.sqlite", data / "project.sqlite-wal", data / "project.sqlitefoo", data / "project.sqlite" / "x",
    proj / "config.yaml", proj, proj / "data2" / "x", Path("/etc/passwd"), "relative/path.txt",
    Path(str(data) + "x") / "y", data / "a b" / "ü.txt", data / "..", 3, None, b"bytes",
]  # fmt: skip
cwd = os.getcwd()
os.chdir(data)
shapes += ["a.txt", "runs/r1", ".", "./a.txt", "../data/a.txt"]
try:
    bad = [(s, _store.rel(s), rel_before(s)) for s in shapes if _store.rel(s) != rel_before(s)]
    check(f"rel: every shape of path gives the key it gave ({STORE}; {len(shapes)} shapes)", not bad, bad[:3])
    later = [(s, _store.rel(s)) for s in shapes if _store.rel(s) != rel_before(s)]
    check("rel: a second call gives the same", not later, later[:3])
finally:
    os.chdir(cwd)

# ── the connection: one per project, resolved once ─────────────────────────────────────────────────────────────────
if STORE == "sqlite":
    resolves = [0]
    real = Path.resolve

    def counting(self: Path, *a: object, **k: object) -> Path:
        resolves[0] += 1
        return real(self, *a, **k)  # type: ignore[arg-type]

    Path.resolve = counting  # type: ignore[method-assign,assignment]
    try:
        conn1 = _store.connect(create=False)
        resolves[0] = 0
        same = all(_store.connect(create=False) is conn1 for _ in range(500))
    finally:
        Path.resolve = real  # type: ignore[method-assign]
    check("connect: 500 calls give the one connection of the process", same and conn1 is not None)
    check("connect: and resolve the database's path no more than once", resolves[0] <= 1, resolves[0])
    _store.close()
    reopened = _store.connect(create=False)
    check(
        "connect: after close() a new connection is opened (a project's database that moved)",
        reopened is not conn1,
    )
    errs: list[str] = []

    def hammer(n: int) -> None:
        try:
            for i in range(200):
                _store.write_text(data / f"t{n}" / f"{i}.txt", str(i))
                if _store.read_text(data / f"t{n}" / f"{i}.txt") != str(i):
                    errs.append("read back wrong")
        except Exception as exc:  # noqa: BLE001
            errs.append(repr(exc))

    ts = [threading.Thread(target=hammer, args=(n,)) for n in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    check(
        "connect: six threads writing and reading through the one connection: all correct", not errs, errs[:3]
    )

sys.exit(summary())
