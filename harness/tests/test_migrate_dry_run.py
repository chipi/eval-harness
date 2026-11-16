#!/usr/bin/env python3
"""`evh migrate --dry-run` of a project several formats behind (RFC-032).

    python tests/test_migrate_dry_run.py

Each step reads what an earlier one writes, so a dry run runs the real steps on a scratch copy of the project (in its
own `.build/`) and deletes it. On a copy of tests/fixtures/formats/0 (format 0, so every step has work): the dry run's
counts for every step are the real migration's, every byte of the project is as it was after it (no `.build/` left),
and it names the copy. A project whose config.yaml names a config folder (outside data/) gets the same counts, and the
folder is untouched. A step that refuses refuses in the dry run, with the project's own paths in the message, and the
project untouched; a project already at this release's format has nothing to dry-run.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
FIXTURE = HARNESS / "tests" / "fixtures" / "formats" / "0" / "data"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _format, migrations  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

base = Path(tempfile.mkdtemp(prefix="evh-dry-run-"))


def evh(proj: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "EVAL_DATA_DIR"}
    env.update(EVAL_HOME=str(proj), EVAL_STORE="files", EVAL_BUILD_REF="test-dry-run")
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def tree(proj: Path) -> dict[str, str]:
    """Every file's path and sha256, and every folder: the project to the byte."""
    out = {}
    for p in sorted(proj.rglob("*")):
        rel = p.relative_to(proj).as_posix()
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return out


def step_lines(stdout: str, proj: Path) -> list[str]:
    """What each step printed, as a function of the step alone: every line from the first `N: ` step line on, but the
    summary line, the project's path (step 1 names the folder it works on) written <project>."""
    lines = stdout.replace(str(proj), "<project>").splitlines()
    first = next(i for i, ln in enumerate(lines) if re.match(r"\d+: ", ln))
    return [ln for ln in lines[first:] if not ln.startswith(("would bring", "brought"))]


def project(name: str, config_dir: bool = False) -> Path:
    p = base / name
    shutil.copytree(FIXTURE, p / "data")
    if config_dir:
        configs = p / "projects" / "x" / "configs"
        configs.parent.mkdir(parents=True)
        shutil.move(str(p / "data" / "configs"), str(configs))
        (p / "data" / "validate.json").write_text('{\n  "configs": []\n}\n')
        (p / "config.yaml").write_text("store: files\nconfigs:\n  - projects/x/configs\n")
    return p


try:
    dry_p, real_p = project("dry"), project("real")
    before = tree(dry_p)
    dry = evh(dry_p, "migrate", "--dry-run")
    after = tree(dry_p)
    real = evh(real_p, "migrate")
    check(
        "the dry run of a format-0 project succeeds and says where its copy was (inside the project's .build/)",
        dry.returncode == 0 and "dry run on a copy of the data in" in dry.stdout and "/.build/" in dry.stdout,
        (dry.returncode, dry.stdout[-300:], dry.stderr[-500:]),
    )
    check(
        "the real migration of the same data succeeds",
        real.returncode == 0,
        (real.returncode, real.stderr[-500:]),
    )
    want = step_lines(real.stdout, real_p)
    got = step_lines(dry.stdout, dry_p)
    heads = [ln.split(":")[0] for ln in got if re.match(r"\d+: ", ln)]
    check(
        "the dry run's lines for every step are the real migration's, and every step of this release ran",
        got == want and heads == [str(m.NUMBER) for m in migrations.steps()],
        (heads, got, want),
    )
    check(
        "the dry run ends 'would bring the data to format N' for the release's N",
        dry.stdout.strip().endswith(f"would bring the data to format {_format.FORMAT}"),
        dry.stdout[-200:],
    )
    check(
        "the project is byte for byte as it was after the dry run: no file changed, added or removed, no .build/ left",
        after == before and not (dry_p / ".build").exists(),
        sorted(set(after.items()) ^ set(before.items()))[:6],
    )
    check(
        "the project is still at format 0 after the dry run, and the real migration of it then reaches this release's",
        _format.data_format(dry_p / "data") == 0
        and evh(dry_p, "migrate").returncode == 0
        and evh(dry_p, "migrate", "--check").returncode == 0,
    )

    # config.yaml's config folder is read and written by steps 2 and 3: it is copied, and stays as it was
    cd_dry, cd_real = project("cfgdir-dry", True), project("cfgdir-real", True)
    before = tree(cd_dry)
    dry = evh(cd_dry, "migrate", "--dry-run")
    real = evh(cd_real, "migrate")
    check(
        "a project whose configs sit in a folder config.yaml names: the dry run's counts are the real migration's, the project (config folder and config.yaml too) untouched",
        dry.returncode == 0
        and real.returncode == 0
        and step_lines(dry.stdout, cd_dry) == step_lines(real.stdout, cd_real)
        and tree(cd_dry) == before,
        (dry.returncode, dry.stderr[-400:], real.returncode, real.stderr[-400:]),
    )

    # a refusal: the dry run refuses where the migration does, naming the project's paths, writing nothing
    bad = project("bad")
    (bad / "data" / "models").mkdir()
    (bad / "data" / "models" / "m1.yaml").write_text(
        "model_id: m1\ndeployments:\n  - id: a\n  - id: b\nsmokes:\n  tickets_lead1_v1:\n    ok: true\n"
    )
    before = tree(bad)
    d = evh(bad, "migrate", "--dry-run")
    untouched = tree(bad) == before and not (bad / ".build").exists()
    r = evh(bad, "migrate")
    refusal = d.stderr[d.stderr.index("ERROR") :].strip() if "ERROR" in d.stderr else ""
    check(
        "a step that refuses refuses in the dry run as in the migration (exit 1, the same message), the project untouched",
        d.returncode == r.returncode == 1
        and refusal
        and refusal == r.stderr[r.stderr.index("ERROR") :].strip()
        and "smoke's deployment is not known" in d.stderr
        and untouched,
        (d.returncode, d.stderr[-400:], r.returncode, r.stderr[-400:]),
    )

    done = evh(real_p, "migrate", "--dry-run")
    check(
        "a project at this release's format has nothing to dry-run, and no copy is made",
        done.returncode == 0 and "nothing to do" in done.stdout and not (real_p / ".build").exists(),
        done.stdout[-200:],
    )
finally:
    shutil.rmtree(base, ignore_errors=True)
sys.exit(summary())
