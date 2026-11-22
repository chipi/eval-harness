#!/usr/bin/env python3
"""What a view costs, in both stores: the evidence for a change to how views are computed (RFC-032 step 9).

    python tools/view_bench.py [--project DIR] [--views "a;b X"] [--stores files,sqlite] [--rounds 2] [--json]

It copies a project's data/ into a scratch directory twice (a files copy and, by `evh data-migrate --to sqlite`, a
SQLite copy), then runs each view in a fresh process through the real `evh` entry point (cli.main), so the paired
tests' on-disk cache (EVH_P_CACHE) is set as a user has it. Each process calls the view twice: the first call is cold
(nothing read yet), the second warm (the same process,
whatever it kept). A round is one process per view; each view starts with an empty p cache, so round 1 pays for the
view's own paired tests and round 2 reads the p cache round 1 wrote (what a user sees on the second command). Per store, per round
and view: cold seconds, cold CPU seconds (this process and the children it ran, the tests' workers), warm seconds, the
process's wall seconds (interpreter start to exit), peak resident memory, and whether the cold and the warm answer are
byte-identical. The code under test is the checkout this file is in (`--code` names another).

The scratch copy is kept between runs (`--rebuild` makes it again); it is outside any git checkout because a project
inside one reads only the runs git keeps. The copy's data is a snapshot of `--project`'s data/ (a project in the files store): its
numbers are for that data, not for whatever the project holds today.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess  # nosec B404 - this interpreter, the project's own commands
import sys
import time
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
SCRATCH = Path.home() / ".cache" / "evh-view-bench"
#: A view per line: the reads that compute from every arm's scores, then the ones that do not.
DEFAULT_VIEWS = (
    "overview-show",
    "arm-list",
    "goal-leaderboard {goal}",
    "dataset-arm-list {dataset}",
    "metric-list",
    "dataset-list",
    "goal-list",
)
STORES = ("files", "sqlite")


# ── the child: one view, called twice in this process ───────────────────────────────────────────────────────────────
def _cpu() -> float:
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


def child(code: str, argv: list[str]) -> int:
    """Run `evh <argv> --json` twice in this process; print one JSON line with what each call cost."""
    sys.path.insert(0, code)
    import resource  # noqa: PLC0415

    from evaluation_harness import cli  # noqa: PLC0415

    calls = []
    for _ in range(2):
        buf = io.StringIO()
        t, c = time.perf_counter(), _cpu()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main([*argv, "--json"])
        calls.append(
            {
                "s": time.perf_counter() - t,
                "cpu_s": _cpu() - c,
                "rc": rc,
                "bytes": len(buf.getvalue()),
                "sha": hashlib.sha256(buf.getvalue().encode()).hexdigest()[:12],
            }
        )
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(json.dumps({"cold": calls[0], "warm": calls[1], "peak_rss_mb": rss}))
    return 0


# ── the parent: the copies, the processes, the table ────────────────────────────────────────────────────────────────
def _run(project: Path, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """`cmd` in the project, with the environment a user has (no store, data or p-cache setting of ours)."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("EVAL_STORE", "EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_P_CACHE", "EVAL_HOME")
    }
    env.update(EVAL_HOME=str(project), EVAL_BUILD_REF="view-bench")
    return subprocess.run(  # nosec B603 - this interpreter and this checkout's own entry point
        cmd,
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _evh(project: Path, code: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """The child: `evh <argv>` called twice in one process."""
    return _run(
        project, [sys.executable, str(Path(__file__).resolve()), "--child", "--code", str(code), "--", *argv]
    )


def _source_stamp(source: Path, code: Path) -> str:
    sys.path.insert(0, str(code))
    from evaluation_harness import _store  # noqa: PLC0415

    n, _acc, newest = _store.fingerprint(
        source / "data"
    )  # not the checksum: it hashes strings, which differ per process
    return f"{source.resolve()} {n} {newest}"


def prepare(
    source: Path, code: Path, scratch: Path, stores: tuple[str, ...], rebuild: bool
) -> dict[str, Path]:
    """The scratch projects, one per store; reused while the source's data/ is what they were made from."""
    stamp = _source_stamp(source, code)
    out: dict[str, Path] = {}
    for store in stores:
        proj = scratch / store
        marker = scratch / f"{store}.stamp"
        if not rebuild and marker.is_file() and marker.read_text() == stamp and proj.is_dir():
            out[store] = proj
            continue
        shutil.rmtree(proj, ignore_errors=True)
        proj.mkdir(parents=True)
        shutil.copytree(source / "data", proj / "data", symlinks=True)
        for name in ("config.yaml", "project.yaml"):
            if (source / name).is_file():
                shutil.copy2(source / name, proj / name)
        if store == "sqlite":
            cfg = proj / "config.yaml"
            kept = re.sub(r"(?m)^store:.*\n?", "", cfg.read_text()) if cfg.is_file() else ""
            cfg.write_text(f"{kept}store: sqlite\n")
            r = _run(
                proj, [sys.executable, str(code / "scripts" / "cli.py"), "data-migrate", "--to", "sqlite"]
            )
            if r.returncode != 0 or not (proj / "data" / "project.sqlite").is_file():
                raise SystemExit(f"data-migrate to sqlite failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        marker.write_text(stamp)
        out[store] = proj
    return out


def _views(spec: str | None, project: Path) -> list[list[str]]:
    goals = sorted(p.stem for p in (project / "data" / "goals").glob("*.yaml") if p.stem != "policy")
    datasets = sorted(p.stem for p in (project / "data" / "datasets").glob("*.json"))
    goal = "news_summary_cnn" if "news_summary_cnn" in goals else (goals[0] if goals else "")
    dataset = "cnn_dailymail_200" if "cnn_dailymail_200" in datasets else (datasets[0] if datasets else "")
    lines = spec.split(";") if spec else list(DEFAULT_VIEWS)
    return [ln.format(goal=goal, dataset=dataset).split() for ln in lines if ln.strip()]


def measure(
    projects: dict[str, Path], code: Path, views: list[list[str]], rounds: int
) -> list[dict[str, Any]]:
    """One row per store, view and round: each view in a process of its own, called twice in it."""
    rows: list[dict[str, Any]] = []
    for store, proj in projects.items():
        for view in views:
            # Each view starts with an empty p cache, so its round 1 pays for its own tests and round 2 reads what
            # round 1 wrote (another view's tests are never in it).
            (proj / ".cache" / "evh-p.jsonl").unlink(missing_ok=True)
            for rnd in range(1, rounds + 1):
                t = time.perf_counter()
                r = _evh(proj, code, view)
                wall = time.perf_counter() - t
                row: dict[str, Any] = {
                    "store": store,
                    "round": rnd,
                    "view": " ".join(view),
                    "process_s": wall,
                }
                try:
                    got = json.loads(r.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    row["error"] = (r.stderr or r.stdout)[-300:]
                else:
                    row.update(got)
                    row["same"] = got["cold"]["sha"] == got["warm"]["sha"]
                rows.append(row)
                print(f"{store} {row['view']} round {rnd}: {wall:.1f} s", file=sys.stderr, flush=True)
    return rows


def table(rows: list[dict[str, Any]]) -> str:
    """The rows as one table per store."""
    out = []
    for store in dict.fromkeys(r["store"] for r in rows):
        head = f"{'round':>5} {'view':<36} {'cold s':>7} {'cold CPU s':>10} {'warm s':>7} {'process s':>9} {'RSS MB':>7}  rc same"
        out += [f"== {store} ==", head]
        for r in (x for x in rows if x["store"] == store):
            if "error" in r:
                out.append(f"{r['round']:>5} {r['view']:<36} ERROR {r['error'].strip()[-120:]!r}")
                continue
            out.append(
                f"{r['round']:>5} {r['view']:<36} {r['cold']['s']:>7.2f} {r['cold']['cpu_s']:>10.2f} "
                f"{r['warm']['s']:>7.2f} {r['process_s']:>9.2f} {r['peak_rss_mb']:>7.0f}  "
                f"{r['cold']['rc']}/{r['warm']['rc']} {'yes' if r['same'] else 'NO'}"
            )
        out.append("")
    return "\n".join(out)


def main() -> int:
    """Copy the project (unless the copies are current), measure the views in each store, print the table or the JSON."""
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0], formatter_class=argparse.RawTextHelpFormatter
    )
    ap.add_argument(
        "--project",
        type=Path,
        default=HARNESS,
        help="the project whose data/ is copied (default: this checkout)",
    )
    ap.add_argument(
        "--code", type=Path, default=HARNESS, help="the checkout whose code is measured (default: this one)"
    )
    ap.add_argument("--scratch", type=Path, default=SCRATCH, help="where the copies are kept")
    ap.add_argument(
        "--views",
        help="`;`-separated views, each as it is typed after `evh` ({goal} and {dataset} are filled)",
    )
    ap.add_argument(
        "--stores", default=",".join(STORES), help="files, sqlite or both (default), in the order measured"
    )
    ap.add_argument(
        "--rounds", type=int, default=2, help="processes per view and store; round 2 reads round 1's p cache"
    )
    ap.add_argument("--rebuild", action="store_true", help="make the copies again")
    ap.add_argument("--json", action="store_true", help="the rows as JSON instead of the table")
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("argv", nargs="*", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.child:
        return child(str(args.code), args.argv)
    stores = tuple(s for s in args.stores.split(",") if s)
    if bad := [s for s in stores if s not in STORES]:
        ap.error(f"--stores: files or sqlite, not {', '.join(bad)}")
    args.scratch.mkdir(parents=True, exist_ok=True)
    projects = prepare(args.project, args.code, args.scratch, stores, args.rebuild)
    rows = measure(projects, args.code, _views(args.views, args.project), args.rounds)
    print(json.dumps(rows, indent=1) if args.json else table(rows))
    return 1 if any("error" in r or r["cold"]["rc"] or r["warm"]["rc"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
