#!/usr/bin/env python3
"""The project's data format and the numbered migrations (RFC-032).

    python tests/test_format.py

`evh init` stamps a new project at this release's format and `migrate --check` holds; a project with no stamp (the
data releases before 0.8.0 wrote) is refused by `--check` as old-format; `--dry-run` writes nothing; `migrate` runs the
steps and stamps the format, a second run does nothing; data stamped by a later release is refused, naming it; a
malformed stamp is an invalid file; in a SQLite project the stamp lives in the database and the database is copied
before the first change; the steps are numbered 1..n without a gap.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _format, migrations  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

base = Path(tempfile.mkdtemp(prefix="evh-format-"))


def evh(proj: Path, *args: str, store: str = "files") -> subprocess.CompletedProcess:
    """`evh <args>` in the project `proj`, with the store given."""
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    env.update(EVAL_HOME=str(proj), EVAL_STORE=store, EVAL_BUILD_REF="test-format")
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


try:
    files = base / "files"
    r = evh(base, "init", str(files))
    stamp = files / "data" / _format.NAME
    check(
        "evh init stamps a new project at this release's format",
        r.returncode == 0 and stamp.is_file(),
        r.stderr[-300:],
    )
    r = evh(files, "migrate", "--check")
    check(
        "migrate --check holds on a stamped project",
        r.returncode == 0 and f"data format {_format.FORMAT}" in r.stdout,
        (r.returncode, r.stdout[-200:]),
    )

    # The deploy's gate (infra/deploy/render.sh): the release's copy of the data carries the stamp, and --check on it
    # holds; a copy of data with no stamp stops the deploy.
    rel = base / "release"
    gates = []
    # _release copies only what git tracks: the project is a git checkout, its data committed
    git = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "a project", "--no-gpg-sign"]):
        subprocess.run(["git", *args], cwd=files, env=git, check=True, capture_output=True, timeout=60)
    for stamped in (True, False):
        shutil.rmtree(rel, ignore_errors=True)
        if not stamped:
            stamp.rename(base / "kept.yaml")
        cp = subprocess.run(
            [sys.executable, str(HERE / "_release.py"), "copy-data", str(files / "data"), str(rel / "data")],
            cwd=files, env=dict(os.environ, EVAL_HOME=str(files), EVAL_STORE="files"), capture_output=True,
            text=True, timeout=300,
        )  # fmt: skip
        g = evh(rel, "migrate", "--check")
        gates.append((cp.returncode, (rel / "data" / _format.NAME).is_file(), g.returncode))
        if not stamped:
            (base / "kept.yaml").rename(stamp)
    check(
        "the deploy's gate: a release's data carries the stamp and passes; without it the deploy stops",
        gates == [(0, True, 0), (0, False, 1)],
        gates,
    )

    stamp.unlink()
    r = evh(files, "migrate", "--check")
    check(
        "a project with no stamp is format 0, refused as old-format",
        r.returncode == 1 and "ERROR (old-format)" in r.stderr and "data format 0" in r.stdout,
        (r.returncode, r.stderr[-300:]),
    )
    r = evh(files, "migrate", "--dry-run")
    check(
        "--dry-run names the steps and writes no stamp",
        r.returncode == 0 and "1: 0.8.0" in r.stdout and not stamp.exists(),
        (r.returncode, r.stdout[-300:], r.stderr[-300:]),
    )
    r = evh(files, "migrate")
    check(
        "migrate runs the steps and stamps the format",
        r.returncode == 0
        and f"format: {_format.FORMAT}" in stamp.read_text()
        and evh(files, "migrate", "--check").returncode == 0,
        (r.returncode, r.stdout[-300:], r.stderr[-300:]),
    )
    r = evh(files, "migrate")
    check("a second migrate does nothing", r.returncode == 0 and "nothing to do" in r.stdout, r.stdout[-200:])

    stamp.write_text(f"format: {_format.FORMAT + 1}\nwritten_by: 9.9.9\n")
    r1, r2 = evh(files, "migrate", "--check"), evh(files, "migrate")
    check(
        "data a later release wrote is refused, naming it, by --check and by migrate",
        all(x.returncode == 1 and "ERROR (mismatch)" in x.stderr and "9.9.9" in x.stderr for x in (r1, r2)),
        (r1.stderr[-200:], r2.stderr[-200:]),
    )
    stamp.write_text("format: one\n")
    r = evh(files, "migrate", "--check")
    check(
        "a malformed stamp is an invalid file",
        r.returncode == 1 and "ERROR (invalid-file)" in r.stderr,
        r.stderr[-200:],
    )

    db = base / "db"
    r = evh(base, "init", str(db), store="sqlite")
    r = evh(db, "migrate", "--check", store="sqlite")
    check(
        "in a SQLite project the stamp is in the database and --check holds",
        r.returncode == 0 and not (db / "data" / _format.NAME).exists(),
        (r.returncode, r.stderr[-300:]),
    )
    import sqlite3

    con = sqlite3.connect(db / "data" / "project.sqlite")
    con.execute("DELETE FROM files WHERE path = ?", (_format.NAME,))
    con.commit()
    con.close()
    r = evh(db, "migrate", store="sqlite")
    copies = list((db / "data").glob("project.sqlite.before-format-*"))
    check(
        "migrate copies a SQLite project's database before its first change, then stamps it",
        r.returncode == 0
        and len(copies) == 1
        and evh(db, "migrate", "--check", store="sqlite").returncode == 0,
        (r.returncode, r.stdout[-300:], r.stderr[-300:], copies),
    )

    numbers = [m.NUMBER for m in migrations.steps()]
    check(
        "the steps are numbered 1..n, the last this release's format",
        numbers == list(range(1, len(numbers) + 1)) and numbers[-1] == _format.FORMAT,
        numbers,
    )

    # Every released format's frozen project (tests/fixtures/formats/<n>/, made by that release's own code) reaches
    # this release's format, and its views give the numbers that release gave.
    import json

    def board(doc: dict) -> dict:
        """A leaderboard's numbers per arm: its quality and its length."""
        return {
            a["config_id"]: {k: a["metrics"].get(k) for k in ("overlap_f1", "output_words")}
            for g in doc["result"]["values"]["groups"]
            for a in g["arms"]
        }

    for fx in sorted((HARNESS / "tests" / "fixtures" / "formats").glob("[0-9]*")):
        proj = base / f"frozen-{fx.name}"
        shutil.copytree(fx / "data", proj / "data")
        old = int(fx.name)
        before = evh(proj, "migrate", "--check")
        steps_run = evh(proj, "migrate")
        after = evh(proj, "migrate", "--check")
        evh(proj, "dataset-materialize", "--dataset-id", "tickets_v1")
        lb = evh(proj, "leaderboard", "--dataset-id", "tickets_v1", "--json")
        want = board(json.loads((fx / "leaderboard-0.7.2.json").read_text())) if old == 0 else None
        got = board(json.loads(lb.stdout)) if lb.returncode == 0 else None
        check(
            f"the frozen format-{old} project is refused, migrates to format {_format.FORMAT}, and keeps its numbers",
            (before.returncode == 1) == (old < _format.FORMAT)
            and steps_run.returncode == 0
            and after.returncode == 0
            and (want is None or got == want),
            (before.returncode, steps_run.stderr[-300:], after.stderr[-200:], lb.stderr[-300:], got, want),
        )
finally:
    shutil.rmtree(base, ignore_errors=True)
sys.exit(summary())
