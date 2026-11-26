#!/usr/bin/env python3
"""Every reader says the same of a fact on projects whose data this repository did not make (PLAN 0.8.2, the 0.8.1 slip).

    EVAL_STORE=files  python tests/test_reader_agreement_shapes.py
    EVAL_STORE=sqlite python tests/test_reader_agreement_shapes.py

test_reader_agreement.py reads projects the harness built in the test's own process, so the harness agreed with data it
had made itself; the beta projects' data found three bugs in a day. Here the readers are asked about projects committed
under tests/fixtures/shapes/ (written once, then frozen: each is a few runs of invented data in the shape of a beta
project's, and no run of one is made by this checkout's code):

  - fleet:   runs with no goal; a repeat set (`_rN` ids) and a repeat of one run (`of`, an equal hash); two goals on one
             dataset family; runs stamped either side of a UTC midnight;
  - podcast: every run imported (`goal` absent, `dirty: null`, free-text build refs, scorer `none`), no declared
             direction, goals whose measures and datasets are prose;
  - bakeoff: no run at all; zero-priced local models and one with no price; a custom adapter; datasets of 3 and 22 items;
  - unicode: dataset, system, run, item and goal ids with accents, CJK and Cyrillic (written by hand: a command refuses them);
  - old:     tests/fixtures/formats/0, a project in the very first format, taken through `evh migrate` first.

Each is copied, moved into the sqlite store when EVAL_STORE says so, and read by the CLI, the API, the MCP reads, the
catalog export and the inspector (test_reader_agreement.py's own readers and comparison), once under TZ=UTC and once
under Pacific/Kiritimati (UTC+14), where "the day" of a stamp near midnight is another one: the facts of the two
passes must be equal (a value, a run, a reference, a baseline does not depend on the reader's zone), and so must be the
readers' agreement within each. A disagreement or a reader that fails on a fixture is a bug of the harness, not of the
fixture.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_reader_agreement as RA  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

FIXTURES = HERE / "fixtures"
SHAPES = ("fleet", "podcast", "bakeoff", "unicode")
OLD = FIXTURES / "formats" / "0"
UTC, FAR, FAR_WEST = "UTC", "Pacific/Kiritimati", "Pacific/Pago_Pago"
#: (shape, TZ) passes: every shape in UTC and in UTC+14; the shape with stamps either side of midnight also in UTC-11.
PASSES = [(s, tz) for s in (*SHAPES, "old") for tz in (UTC, FAR)] + [("fleet", FAR_WEST)]
#: Shapes with no run: the readers have no arm to agree on, and say so alike.
NO_RUNS = {"bakeoff"}


class Fixture(RA.Project):
    """A copy of a committed fixture in a temporary project, in the store EVAL_STORE names, read with TZ set."""

    def __init__(self, shape: str, tz: str) -> None:
        self.name = f"{shape}@{tz}"
        self.proj = Path(tempfile.mkdtemp(prefix=f"evh-shape-{shape}-"))
        RA.PROJECTS.append(self.proj)
        self.env = dict(os.environ, EVAL_HOME=str(self.proj), EVH_ACTOR="person:fixture", TZ=tz)
        for k in RA.LIMITS:
            self.env.pop(k, None)
        t = time.time()
        if shape == "old":
            shutil.copytree(OLD / "data", self.proj / "data")
            (self.proj / "config.yaml").write_text("store: files\n", encoding="utf-8")
            self.evh_must("migrate")
        else:
            RA.copy_project(FIXTURES / "shapes" / shape, self.proj)
        if RA.STORE == "sqlite":
            self.evh_must("data-migrate", "--to", "sqlite")
        if shape not in (
            "unicode",
            "old",
        ):  # unicode: its profile is committed (a command refuses to write one for these ids)
            for ds in sorted(self.datasets()):
                self.evh_must("dataset-profile", "--dataset-id", ds)
        RA.SPENT[self.name] = {"build": time.time() - t}

    def datasets(self) -> dict[str, int]:
        r = subprocess.run(  # nosec B603 - this interpreter and the harness's own command
            [sys.executable, str(RA.CLI), "dataset-list", "--json"],
            cwd=self.proj, env=self.env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600, check=True, encoding="utf-8",
        )  # fmt: skip
        return {d["dataset"]: d["items"] for d in json.loads(r.stdout)["result"]["datasets"]}

    def evh_must(self, *args: str) -> None:
        env = dict(self.env, EVAL_STORE="files" if args[0] == "migrate" else RA.STORE)
        r = subprocess.run(  # nosec B603 - this interpreter and the harness's own command
            [sys.executable, str(RA.CLI), *args],
            cwd=self.proj, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600, check=False, encoding="utf-8",
        )  # fmt: skip
        if r.returncode != 0:
            raise RuntimeError(f"evh {' '.join(args)} on {self.name} failed: {(r.stdout + r.stderr)[-600:]}")


def no_run_checks(f: Fixture) -> None:
    """What a project of no run says through the CLI, the one reader that lists a dataset: its two datasets with their
    item counts, no arm, and a goal's leaderboard that answers (the other readers are asked by the agreement itself)."""
    cli = RA.FD.Cli(f.evh, str(f.proj), f.env)
    got = f.datasets()
    check(
        f"{f.name}: dataset-list: the datasets of 3 and 22 items",
        got == {"tasks_small_v1": 3, "tasks_wide_v1": 22},
        got,
    )
    check(
        f"{f.name}: arm-list: no arm", not cli.read("arm-list").get("arms"), cli.read("arm-list").get("arms")
    )
    for g in ("bakeoff_small", "bakeoff_wide"):
        try:
            cli.read("goal-leaderboard", goal=g)
            ok, said = True, ""
        except RA.FD.Unavailable as exc:
            ok, said = False, str(exc)
        check(f"{f.name}: goal-leaderboard {g} answers for a goal with no run", ok, said)


def failed(why: dict[str, list[str]]) -> dict[str, list[str]]:
    """The parts a reader gave no answer to for a reason that is a crash and not "this reader does not give it"."""
    bad = ("traceback", "internal", "unexpected", "exception", "error:")
    return {r: [w for w in ws if any(b in w.lower() for b in bad)] for r, ws in why.items() if ws}


def main() -> int:
    t0 = time.time()
    print(f"store: {RA.STORE}")
    jobs = max(1, min(int(os.environ.get("EVH_TEST_JOBS", "2")), len(PASSES)))
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:

            def one(sp: tuple[str, str]) -> tuple[dict, dict]:
                f = Fixture(*sp)
                if sp[0] == "bakeoff" and sp[1] == UTC:
                    no_run_checks(f)
                return RA.gather(f)

            gathered = dict(zip(PASSES, pool.map(one, PASSES)))
        print(f"read {len(PASSES)} passes ({time.time() - t0:.0f}s)")
        for (shape, tz), (facts, why) in gathered.items():
            name = f"{shape}@{tz}"
            print(f"\n{name}: {len(facts)} readers, {RA.thin(facts)} facts given by two readers or more")
            for r in sorted(why):
                print(f"    {r}: no answer for part: {why[r][0][:150]}")
            check(f"{name}: no reader crashed on a part", not any(failed(why).values()), failed(why))
            arms = [
                a
                for r, d in facts.items()
                if r == "cli:arm-list"
                for (k, _), v in d.items()
                if k == "arms"
                for a in v
            ]
            if shape in NO_RUNS:
                check(f"{name}: setup: the project has no arm, and the CLI says so", not arms, arms[:3])
                check(
                    f"{name}: the CLI, the API and the MCP reads answer arm-list, and no reader names an arm",
                    not any(f"{r}:arm-list" in why for r in ("cli", "api", "mcp")) and not arms,
                    {r: w for r, w in why.items() if "arm-list" in r},
                )
            else:
                check(f"{name}: setup: the CLI saw the project's arms", bool(arms), len(arms))
                for kind in ("value", "direction", "runs", "n_runs", "reference", "cost_state", "latest"):
                    n = len({r for r, d in facts.items() if any(k == kind for k, _ in d)})
                    check(
                        f"{name}: coverage: {kind} is given by 2 readers or more, else the agreement means nothing",
                        n >= 2,
                        n,
                    )
            RA.assert_agreement(name, facts)
            if shape not in NO_RUNS:
                RA.arms_shown(name, facts, why)
                RA.superseded_ranked(name, facts)
                hand_checks(shape, name, facts)
        # one zone against another: nothing a reader states of a run depends on where it is read
        for shape in (*SHAPES, "old"):
            base = gathered[(shape, UTC)][0]
            for tz in [t for s, t in PASSES if s == shape and t != UTC]:
                other = gathered[(shape, tz)][0]
                diff = [
                    (r, fk, base[r].get(fk), other[r].get(fk))
                    for r in sorted(base.keys() | other.keys())
                    for fk in sorted(base.get(r, {}).keys() | other.get(r, {}).keys(), key=repr)
                    if base.get(r, {}).get(fk) != other.get(r, {}).get(fk)
                ]
                check(f"zone: {shape}: the facts under {tz} are the facts under {UTC}", not diff, diff[:3])
    finally:
        for d in RA.PROJECTS:
            shutil.rmtree(d, ignore_errors=True)
    print(f"\nwhole test {time.time() - t0:.0f}s")
    return summary()


def hand_checks(shape: str, name: str, facts: dict) -> None:
    """Facts known by hand about each fixture, from the CLI's answer: the agreement above is not agreement on nothing."""
    cli = {fk: v for r, d in facts.items() if r.startswith("cli:arm-show") for fk, v in d.items()}
    say = lambda kind, *key: cli.get((kind, key))  # noqa: E731
    runs = {k[0]: v for (kind, k), v in cli.items() if kind == "runs"}
    if shape == "fleet":
        check(
            f"hand: {name}: arm_p_v1 on triage_v1 is one arm of its repeat set and the repeat of one run",
            say("n_runs", "runs/triage_v1/arm_p_v1") == 3,
            say("n_runs", "runs/triage_v1/arm_p_v1"),
        )
    elif shape == "podcast":
        check(
            f"hand: {name}: no measure has a declared direction, and every reader still says one",
            all(say("direction", "episodes_dev_v1", m) for m in ("rougeL_f1", "wer")),
            [say("direction", "episodes_dev_v1", m) for m in ("rougeL_f1", "wer")],
        )
    elif shape == "unicode":
        check(
            f"hand: {name}: both unicode systems have an arm",
            sum("données_日本語_v1" in a for a in runs) == 2,
            sorted(runs),
        )
        public = {
            fk[1][0]: v
            for r, d in facts.items()
            if r == "cli:dataset-items"
            for fk, v in d.items()
            if fk[0] == "public"
        }
        check(
            f"hand: {name}: the unicode dataset's `public` is read, its id spelt as it is",
            public == {"données_日本語_v1": True},
            public,
        )
    if shape != "podcast":
        check(f"hand: {name}: every arm states its runs", bool(runs) and all(runs.values()), sorted(runs)[:3])


if __name__ == "__main__":
    sys.exit(main())
