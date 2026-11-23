#!/usr/bin/env python3
"""Upgrade over an install: the previous release's wheel, a project on it, then this tree's build over it.

    python tests/check_upgrade_install.py                  # PASS / FAIL, exits non-zero on a failure
    python tests/check_upgrade_install.py --previous v0.8.0  # name the release to upgrade from
    python tests/check_upgrade_install.py --keep           # leave the scratch folder, and print it

What UPGRADING says a user does, done in a throwaway venv: install the previous release's wheel (the
latest GitHub Release, read-only: `gh release download`), make a project with its `evh init`, one per
store (`files`, `sqlite`), the tutorial and three runs on the offline echo provider; build this tree's
wheel with the documented command (`python -m build harness`, RELEASING.md); install it over the
previous one; then, in each project, `evh --version`, `evh migrate --check`, `evh migrate --dry-run`,
`evh validate`, `evh runs-list` and `evh leaderboard` must exit 0 and say the new version and the data
format. The runs made by the old release must still be listed.

A project whose data format is older than this tree's is told to migrate (`migrate --check` refuses, the
dry run lists the steps), migrates, and is checked again; one on the same format needs nothing.

UPGRADING also says a plain `pip install` of a new build that reports the SAME version as the installed one
keeps the old code ("already installed with the same version"), so a pin moved from one commit to another
needs `--force-reinstall --no-deps`. This checks that claim on the wheel, and on a git pin of two commits of
this checkout (`git+file://`, so it needs no network beyond the package index), when this tree's version is the
previous release's; when the versions differ it checks that a plain install does upgrade.

Needs the network (the package index for the wheels' dependencies and `build`, GitHub for the release) and
`gh` authenticated, so it is a release gate and not part of `make test`: `make upgrade-check`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
REPO = HARNESS.parent
sys.path.insert(0, str(HARNESS / "tools"))
import _wheel  # noqa: E402  (its INPUTS: what pyproject.toml builds the package from)

SLUG = "chipi/eval-harness"
STORES = ("files", "sqlite")
SYSTEMS = ("tickets_lead1_v1", "tickets_lead2_v1", "tickets_author_v1")
FAILED: list[str] = []


def ok(cond: bool, what: str, detail: str = "") -> bool:
    """Print one check; remember a failure."""
    print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    if not cond:
        FAILED.append(what)
        if detail:
            print("       " + detail.strip().replace("\n", "\n       ")[-900:])
    return cond


def sh(cmd: list, cwd: Path | None = None, env: dict | None = None, timeout: int = 900):
    """Run a command, both streams captured together."""
    r = subprocess.run(
        [str(c) for c in cmd], cwd=cwd, env=env, text=True, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )  # fmt: skip
    return r.returncode, r.stdout


def must(cmd: list, cwd: Path | None = None, env: dict | None = None, timeout: int = 900) -> str:
    """Run a step the check cannot go on without; stop with its output when it fails."""
    code, out = sh(cmd, cwd, env, timeout)
    if code:
        raise SystemExit(f"FAIL: {' '.join(map(str, cmd))} exited {code}:\n{out[-1500:]}")
    return out


def first(pattern: str, text: str, flags: int = 0) -> str:
    """The first group of a pattern that must match."""
    m = re.search(pattern, text, flags)
    if not m:
        raise SystemExit(f"FAIL: {pattern!r} is not in {text[:200]!r}")
    return m.group(1)


def tree_version() -> str:
    """The version this tree reports."""
    return first(r'__version__ = "([^"]+)"', (HARNESS / "scripts/_version.py").read_text())


def tree_format() -> int:
    """The data format this tree reads."""
    return int(first(r"^FORMAT = (\d+)", (HARNESS / "scripts/_format.py").read_text(), re.M))


def package_digest(files: dict) -> str:
    """One hash of {relative path: bytes}."""
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + hashlib.sha256(files[name]).digest())
    return h.hexdigest()[:12]


def wheel_digest(whl: Path) -> tuple:
    """(digest, {path: bytes}) of the package folder a wheel holds."""
    with zipfile.ZipFile(whl) as z:
        files = {
            n: z.read(n) for n in z.namelist() if n.startswith("evaluation_harness/") and not n.endswith("/")
        }
    return package_digest(files), files


def installed_digest(venv: Path, names: list) -> str:
    """The digest of the same files as installed in the venv (a file that is not there counts as empty)."""
    site = next((venv / "lib").glob("python*/site-packages"))
    return package_digest({n: (site / n).read_bytes() if (site / n).is_file() else b"" for n in names})


def pinned_commit(venv: Path) -> str:
    """The commit a git install records (direct_url.json), '' when it is not one."""
    site = next((venv / "lib").glob("python*/site-packages"))
    for p in site.glob("evaluation_harness-*.dist-info/direct_url.json"):
        return json.loads(p.read_text()).get("vcs_info", {}).get("commit_id", "")
    return ""


def make_project(proj: Path, store: str, evh: Path, env: dict) -> list:
    """A project on `store` with the tutorial and three runs, under git; the ids of its runs."""
    proj.mkdir()
    must([evh, "init", "--store", store, "--tutorial"], proj, env)
    must(["git", "init", "-q"], proj, env)
    must(["git", "add", "-A"], proj, env)
    must(["git", "commit", "-qm", "the tutorial kit"], proj, env)
    must([evh, "dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets"], proj, env)
    must([evh, "dataset-materialize", "--dataset-id", "tickets_v1"], proj, env)
    for s in SYSTEMS:  # data-put works in both stores
        f = f"{s}.yaml"
        must([evh, "data-put", "--path", f"systems/{f}", "--file", f"tutorial/systems/{f}"], proj, env)
    must(["git", "add", "-A"], proj, env)
    must(["git", "commit", "-qm", "the systems", "--allow-empty"], proj, env)
    for s in SYSTEMS:
        must([evh, "run", "--system", s, "--dataset", "tickets_v1"], proj, env)
    out = must([evh, "runs-list"], proj, env)
    return re.findall(r"^(tickets_\w+_\d{8}T\d{6}Z)\s", out, re.M)


def read_commands(
    proj: Path, evh: Path, env: dict, version: str, fmt: int, run_ids: list, label: str
) -> None:
    """The six reads UPGRADING ends on: exit 0, the version, the data format, the old runs."""
    code, out = sh([evh, "--version"], proj, env)
    ok(code == 0 and out.strip() == version, f"{label}: evh --version is {version}", out)
    code, out = sh([evh, "migrate", "--check"], proj, env)
    have = re.search(r"data format (\d+); this release reads (\d+)", out)
    ok(
        have is not None and int(have.group(2)) == fmt,
        f"{label}: migrate --check says 'data format N; this release reads {fmt}'",
        out,
    )
    if have and int(have.group(1)) == fmt:
        ok(code == 0, f"{label}: migrate --check exits 0 (the data is on format {fmt})", out)
        code, out = sh([evh, "migrate", "--dry-run"], proj, env)
        ok(code == 0 and "nothing to do" in out, f"{label}: migrate --dry-run: nothing to do", out)
    elif have:
        ok(
            code != 0,
            f"{label}: migrate --check refuses format {have.group(1)} (this release reads {fmt})",
            out,
        )
        code, out = sh([evh, "migrate", "--dry-run"], proj, env)
        ok(
            code == 0 and "would bring the data to format" in out,
            f"{label}: migrate --dry-run lists the steps",
            out,
        )
        code, out = sh([evh, "migrate"], proj, env)
        ok(code == 0 and f"format {fmt}" in out, f"{label}: migrate brings the data to format {fmt}", out)
        code, out = sh([evh, "migrate", "--check"], proj, env)
        ok(
            code == 0 and f"data format {fmt}; this release reads {fmt}" in out,
            f"{label}: migrate --check exits 0 after it",
            out,
        )
    code, out = sh([evh, "validate"], proj, env)
    ok(code == 0 and "VALIDATION PASSED" in out, f"{label}: validate passes", out)
    code, out = sh([evh, "runs-list"], proj, env)
    ok(
        code == 0 and all(r in out for r in run_ids),
        f"{label}: runs-list exits 0 and lists the {len(run_ids)} runs of the old release",
        out,
    )
    code, out = sh([evh, "leaderboard", "tickets_v1"], proj, env)
    ok(code == 0 and "tickets_author_v1" in out, f"{label}: leaderboard tickets_v1 exits 0", out)


def check_pin_claim(tmp: Path, env: dict, prev: str) -> None:
    """A git pin moved to another commit: a plain install keeps the old code when the version is the same."""
    head = must(["git", "rev-parse", "HEAD"], REPO, env).strip()
    base = must(["git", "rev-list", "-n", "1", prev], REPO, env).strip()
    old_version = first(
        r'__version__ = "([^"]+)"', must(["git", "show", f"{base}:harness/scripts/_version.py"], REPO, env)
    )
    venv = tmp / "pin-venv"
    must([sys.executable, "-m", "venv", venv], env=env)
    pip = venv / "bin/pip"
    url = lambda sha: f"git+file://{REPO}@{sha}#subdirectory=harness"  # noqa: E731  (the bare URL: older pips refuse a host-less one after "name @")
    must([pip, "install", "-q", url(base)], env=env)
    ok(pinned_commit(venv) == base, f"pin: installed at {prev} ({base[:9]})")
    code, out = sh([pip, "install", url(head)], env=env)
    kept = pinned_commit(venv) == base
    if old_version == tree_version():
        ok(
            code == 0 and kept and "already satisfied" in out.lower(),
            f"pin: a plain pip install of {head[:9]}, which reports the same version {old_version}, keeps {base[:9]}",
            out,
        )
        must([pip, "install", "-q", "--force-reinstall", "--no-deps", url(head)], env=env)
        ok(
            pinned_commit(venv) == head,
            "pin: --force-reinstall --no-deps moves the install to the new commit",
        )
    else:
        ok(
            code == 0 and pinned_commit(venv) == head,
            f"pin: versions differ ({old_version} to {tree_version()}), a plain pip install moves it",
            out,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--previous", help="the release tag to upgrade from (default: the latest GitHub Release)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder and print it")
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="evh-upgrade-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EVAL_", "PYTHON", "VIRTUAL_ENV"))}
    env.update(
        EVH_ACTOR="person:reader", PYTHONDONTWRITEBYTECODE="1", GIT_AUTHOR_NAME="upgrade",
        GIT_AUTHOR_EMAIL="upgrade@example.invalid", GIT_COMMITTER_NAME="upgrade",
        GIT_COMMITTER_EMAIL="upgrade@example.invalid",
    )  # fmt: skip
    try:
        prev = (
            args.previous
            or json.loads(
                must(
                    [
                        "gh",
                        "release",
                        "list",
                        "-R",
                        SLUG,
                        "--exclude-drafts",
                        "--limit",
                        "1",
                        "--json",
                        "tagName",
                    ],
                    env=env,
                )
            )[0]["tagName"]
        )
        print(
            f"upgrade over an install: {prev} (the release) to this tree ({tree_version()}, data format {tree_format()})"
        )
        dl = tmp / "release"
        must(["gh", "release", "download", prev, "-R", SLUG, "-p", "*.whl", "-D", dl], env=env)
        old_whl = next(dl.glob("*.whl"))

        venv = tmp / "venv"
        must([sys.executable, "-m", "venv", venv], env=env)
        pip, evh = venv / "bin/pip", venv / "bin/evh"
        must([pip, "install", "-q", old_whl], env=env)
        old_version = prev.removeprefix("v")
        ok(
            must([evh, "--version"], env=env).strip() == old_version,
            f"before: evh --version is {old_version}",
        )

        projects, runs = {}, {}
        for store in STORES:
            projects[store] = tmp / f"proj-{store}"
            runs[store] = make_project(projects[store], store, evh, env)
            ok(
                len(runs[store]) == len(SYSTEMS),
                f"before: a {store} project on {prev} with {len(SYSTEMS)} runs",
                str(runs[store]),
            )
        have_fmt = {}
        for store in STORES:
            m = re.search(r"data format (\d+)", must([evh, "migrate", "--check"], projects[store], env))
            have_fmt[store] = int(m.group(1)) if m else -1

        # This tree's wheel, with the command RELEASING.md and the workflows use, on a copy of what it builds from
        # (the checkout gets no build/ or egg-info), by a `build` of its own: nothing is installed into a shared one.
        src = tmp / "src" / "harness"
        for name in _wheel.INPUTS:
            p = HARNESS / name
            if p.is_dir():
                shutil.copytree(p, src / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                src.mkdir(parents=True, exist_ok=True)
                shutil.copy(p, src / name)
        bvenv = tmp / "build-venv"
        must([sys.executable, "-m", "venv", bvenv], env=env)
        must([bvenv / "bin/pip", "install", "-q", "build"], env=env)
        must([bvenv / "bin/python", "-m", "build", src, "--outdir", tmp / "dist"], env=env)
        new_whl = next((tmp / "dist").glob("*.whl"))
        new_sum, new_files = wheel_digest(new_whl)
        old_sum, old_files = wheel_digest(old_whl)
        names = sorted(set(new_files) | set(old_files))
        same_version = old_version == tree_version()
        ok(old_sum != new_sum, f"the two wheels hold different code ({old_sum} and {new_sum})")
        ok(
            installed_digest(venv, sorted(old_files)) == old_sum,
            "before: the install holds the release's code",
        )

        # A plain `pip install` over it, as a person who moves a pin does.
        code, out = sh([pip, "install", new_whl], env=env)
        if same_version:
            ok(
                code == 0
                and "already installed with the same version" in out
                and installed_digest(venv, sorted(old_files)) == old_sum,
                f"a plain pip install of a build that reports {old_version} again keeps the old code (UPGRADING)",
                out,
            )
            must([pip, "install", "-q", "--force-reinstall", "--no-deps", new_whl], env=env)
        else:
            ok(code == 0, f"pip install of the new wheel over {old_version} exits 0", out)
        ok(installed_digest(venv, names) == package_digest({n: new_files.get(n, b"") for n in names}),
           "after: the install holds this tree's code")  # fmt: skip

        for store in STORES:
            read_commands(
                projects[store],
                evh,
                env,
                tree_version(),
                tree_format(),
                runs[store],
                f"{store} (format {have_fmt[store]})",
            )

        check_pin_claim(tmp, env, prev)
    finally:
        if args.keep:
            print(f"kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"UPGRADE-INSTALL: {'FAIL (' + str(len(FAILED)) + ')' if FAILED else 'PASS'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
