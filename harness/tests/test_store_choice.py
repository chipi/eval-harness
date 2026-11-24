#!/usr/bin/env python3
"""A project names its store, and there is no default (owner decision 2026-11-15).

    python tests/test_store_choice.py

`evh init` without `--store files|sqlite` is `ERROR (bad-argument)` that explains both choices as equals and names
`evh data-migrate`, and changes nothing (nothing is created, with or without EVAL_STORE set); an unknown store is refused the
same way. With either store init writes `store: <choice>` into config.yaml, and the project works in that store with no
EVAL_STORE: files has its datasets as files under data/, sqlite has data/project.sqlite and none. Init again with the same
store keeps config.yaml; with the other store it is a mismatch, config.yaml unchanged; a config.yaml that names none keeps
its other settings and gains the line. A project whose config.yaml names no store (or has no config.yaml) is refused by a
command that reads its data, as `not-configured`, with the same explanation; `EVAL_STORE` overrides the file, and an
unknown one is refused. Outside any project `--version`, `--help`, `init --help`, `licences` and `skills-install` work.
`_release.py copy-data` needs `--store` and a files release names `store: files`.
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
from evaluation_harness._check import check, summary  # noqa: E402

base = Path(tempfile.mkdtemp(prefix="evh-storechoice-"))
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}


sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _cli
import _cli  # noqa: E402


def evh(cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    """`evh <args>` run in `cwd`, which is the project (EVAL_HOME), with no store setting but the ones given."""
    e = {**CLEAN, "EVAL_HOME": str(cwd), "EVAL_BUILD_REF": "test-store-choice", **env}
    return _cli.run(cwd, e, *args, timeout=300)


def explains(text: str) -> bool:
    """Both stores named with their two lines each, and the command that switches."""
    return all(
        w in text
        for w in (
            "files",
            "kept in git",
            "sqlite",
            "data/project.sqlite",
            "leaves it out of git",
            "evh data-migrate",
        )
    )


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


try:
    # init without --store: refused, kind named, both choices explained, nothing written
    for label, extra in (("", {}), (" (EVAL_STORE set)", {"EVAL_STORE": "files"})):
        target = base / f"refused{len(extra)}"
        r = evh(base, "init", str(target), **extra)
        check(
            f"init without --store{label}: exit 1, ERROR (bad-argument), both stores explained, data-migrate named",
            r.returncode == 1 and r.stderr.startswith("ERROR (bad-argument)") and explains(r.stderr),
            (r.returncode, r.stderr[-300:]),
        )
        check(f"init without --store{label}: nothing is created", not target.exists(), tree(base))
    here = base / "empty"
    here.mkdir()
    r = evh(here, "init")
    check(
        "init without --store in a folder: the folder stays empty",
        r.returncode == 1 and tree(here) == [],
        tree(here),
    )
    r = evh(here, "init", "--store", "both")
    check(
        "init --store <not a store>: ERROR (bad-argument), nothing written",
        r.returncode == 1 and r.stderr.startswith("ERROR (bad-argument)") and tree(here) == [],
        (r.stderr[-200:], tree(here)),
    )
    r = evh(here, "init", "--help")
    check(
        "init --help (in a folder that is no project): exit 0, says --store is required, explains both stores",
        r.returncode == 0 and "--store" in r.stdout and "required" in r.stdout and explains(r.stdout),
        (r.returncode, r.stderr[-300:]),
    )

    # each store: config.yaml, and the project works in it with no EVAL_STORE
    made = {}
    for store in ("files", "sqlite"):
        proj = base / store
        r = evh(base, "init", str(proj), "--store", store, "--tutorial")
        made[store] = proj
        cfg = proj / "config.yaml"
        check(
            f"init --store {store}: exit 0, config.yaml says `store: {store}`",
            r.returncode == 0
            and cfg.is_file()
            and cfg.read_text(encoding="utf-8").startswith(f"store: {store}"),
            (r.returncode, r.stderr[-300:], cfg.read_text(encoding="utf-8") if cfg.is_file() else None),
        )
        r = evh(proj, "dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
        check(
            f"{store}: a dataset is made with no EVAL_STORE", r.returncode == 0, (r.stdout + r.stderr)[-300:]
        )
        r = evh(proj, "data-ls")
        check(
            f"{store}: data-ls names the store",
            r.returncode == 0 and f"store: {store}" in r.stdout,
            r.stdout[:200],
        )
        r = evh(proj, "validate")
        check(f"{store}: validate passes", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check(
        "files: the dataset is a file under data/, no database",
        (made["files"] / "data/datasets/tickets_v1.json").is_file()
        and not (made["files"] / "data/project.sqlite").exists(),
    )
    check(
        "sqlite: the data is in data/project.sqlite, no dataset file under data/",
        (made["sqlite"] / "data/project.sqlite").is_file()
        and not (made["sqlite"] / "data/datasets").exists(),
    )
    check(
        "the .gitignore leaves data/project.sqlite out of git",
        "data/project.sqlite*" in (made["sqlite"] / ".gitignore").read_text(encoding="utf-8"),
    )

    # init again
    before = (made["files"] / "config.yaml").read_text(encoding="utf-8")
    r = evh(base, "init", str(made["files"]), "--store", "files")
    check(
        "init again with the same store: exit 0, config.yaml kept",
        r.returncode == 0
        and "config.yaml" in r.stdout
        and (made["files"] / "config.yaml").read_text(encoding="utf-8") == before,
        (r.returncode, r.stdout[-300:]),
    )
    r = evh(base, "init", str(made["files"]), "--store", "sqlite")
    check(
        "init with the other store: ERROR (mismatch), config.yaml unchanged, names data-migrate",
        r.returncode == 1
        and r.stderr.startswith("ERROR (mismatch)")
        and "data-migrate" in r.stderr
        and (made["files"] / "config.yaml").read_text(encoding="utf-8") == before,
        (r.returncode, r.stderr[-300:]),
    )
    other = base / "other"
    other.mkdir()
    (other / "config.yaml").write_text("catalog:\n  publish: [prompts]\n", encoding="utf-8")
    r = evh(base, "init", str(other), "--store", "sqlite")
    text = (other / "config.yaml").read_text(encoding="utf-8")
    check(
        "init in a project whose config.yaml names no store: its settings kept, the store line added",
        r.returncode == 0
        and text.startswith("catalog:\n  publish: [prompts]\n")
        and "\nstore: sqlite" in text,
        (r.returncode, text),
    )

    # a plain init (no --tutorial) writes an example of a judge prompt, keeps one that is there, and it names its dimensions
    example = "prompts/judge_prompt_example.txt"
    from evaluation_harness import judge_score as js

    for store in ("files", "sqlite"):
        plain = base / f"plain-{store}"
        r = evh(base, "init", str(plain), "--store", store)
        text = (plain / example).read_text(encoding="utf-8") if (plain / example).is_file() else ""
        dims = ["correctness", "completeness"]
        check(
            f"plain init --store {store}: writes {example}, which names its dimensions",
            r.returncode == 0
            and js.unnamed_dimensions({"task": {"dimensions": dims}}, text) == []
            and "{n}" in text,
            (r.returncode, r.stderr[-300:], text[:200]),
        )
        (plain / example).write_text("mine\n", encoding="utf-8")
        r = evh(base, "init", str(plain), "--store", store)
        check(
            f"plain init --store {store} again: the example prompt that is there is kept",
            r.returncode == 0 and (plain / example).read_text(encoding="utf-8") == "mine\n",
            (r.returncode, r.stdout[-300:]),
        )

    # a project that names none is refused
    for label, cfgtext in (
        ("no config.yaml", None),
        ("a config.yaml with no store", "catalog:\n  publish: []\n"),
    ):
        proj = base / ("none-" + str(len(label)))
        (proj / "data").mkdir(parents=True)
        if cfgtext is not None:
            (proj / "config.yaml").write_text(cfgtext, encoding="utf-8")
        r = evh(proj, "data-ls")
        check(
            f"a project with {label}: a data command is ERROR (not-configured) with the explanation",
            r.returncode == 1 and r.stderr.startswith("ERROR (not-configured)") and explains(r.stderr),
            (r.returncode, r.stderr[-300:]),
        )
        check(
            f"a project with {label}: it wrote nothing",
            tree(proj) == (["config.yaml", "data"] if cfgtext else ["data"]),
            tree(proj),
        )
        r = evh(proj, "validate")
        check(
            f"a project with {label}: validate refuses too",
            r.returncode != 0 and "not-configured" in r.stderr,
            (r.returncode, r.stderr[-200:]),
        )
        r = evh(proj, "data-ls", EVAL_STORE="files")
        check(
            f"a project with {label}: EVAL_STORE names the store, the command runs",
            r.returncode == 0,
            (r.stdout + r.stderr)[-300:],
        )

    # EVAL_STORE wins over the file
    r = evh(made["files"], "data-ls", EVAL_STORE="sqlite")
    check(
        "EVAL_STORE overrides config.yaml",
        r.returncode == 0 and "store: sqlite" in r.stdout,
        (r.stdout + r.stderr)[-300:],
    )
    r = evh(made["files"], "data-ls", EVAL_STORE="tape")
    check(
        "EVAL_STORE with a name that is no store: ERROR (bad-argument)",
        r.returncode == 1 and r.stderr.startswith("ERROR (bad-argument)"),
        r.stderr[-200:],
    )
    (base / "badcfg" / "data").mkdir(parents=True)
    (base / "badcfg" / "config.yaml").write_text("store: tape\n", encoding="utf-8")
    r = evh(base / "badcfg", "dataset-list")
    check(
        "a config.yaml naming a store that is none: ERROR (invalid-file)",
        r.stderr.startswith("ERROR (invalid-file)"),
        r.stderr[-200:],
    )

    # outside a project, what touches no data works
    nowhere = base / "nowhere"
    nowhere.mkdir()
    for args in (
        ("--version",),
        ("--help",),
        ("licences",),
        ("skills-install", "--target", str(nowhere / "skills")),
    ):
        r = evh(nowhere, *args)
        check(
            f"outside a project, `evh {' '.join(args[:1])}` works: exit 0, no store refusal",
            r.returncode == 0 and "names no store" not in r.stderr,
            (r.returncode, r.stderr[-300:]),
        )
    check(
        "outside a project, skills-install wrote its skills",
        (nowhere / "skills/evh-evaluate-a-system/SKILL.md").is_file(),
    )
    r = evh(nowhere, "env-check")
    check(
        "outside a project, env-check is not refused for a store",
        "names no store" not in r.stderr,
        r.stderr[-300:],
    )

    # a release names its store too
    src = base / "relsrc"
    r = evh(base, "init", str(src), "--store", "files")
    git = {
        **CLEAN,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for git_args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "p", "--no-gpg-sign"]):
        subprocess.run(["git", *git_args], cwd=src, env=git, check=True, capture_output=True, timeout=60)
    copy = [sys.executable, str(HERE / "_release.py"), "copy-data", str(src / "data"), str(base / "rel/data")]
    env = {**CLEAN, "EVAL_HOME": str(src)}
    r = subprocess.run(copy, cwd=src, env=env, capture_output=True, text=True, timeout=300, encoding="utf-8")
    check(
        "copy-data without --store: usage error",
        r.returncode == 2 and "--store" in r.stderr,
        (r.returncode, r.stderr[-200:]),
    )
    r = subprocess.run(
        [*copy, "--store", "files"],
        cwd=src,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
    )
    check(
        "copy-data --store files: the release's config.yaml says `store: files`",
        r.returncode == 0 and (base / "rel/config.yaml").read_text(encoding="utf-8") == "store: files\n",
        (r.returncode, r.stderr[-300:]),
    )
finally:
    shutil.rmtree(base, ignore_errors=True)

sys.exit(summary())
