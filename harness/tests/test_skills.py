#!/usr/bin/env python3
"""The agent skills (harness/skills/, RFC-016): each is a valid Agent Skill, `evh skills-install` copies
them and keeps a changed copy unless --force, and every ```evh block in them runs, in order, in a fresh
tutorial project with the package installed from its wheel, so a skill cannot drift from the CLI."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
sys.path.insert(0, str(HARNESS / "tools"))  # _wheel, shared with the deploy
import _wheel  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._version import __version__  # noqa: E402

SKILLS = HARNESS / "skills"
#: The order a reader follows them; the later ones read what the first one made.
ORDER = ("evh-evaluate-a-system", "evh-compare-and-read", "evh-promote-with-evidence")
BLOCK = re.compile(r"^```evh\n(.*?)^```", re.S | re.M)


def front_matter(text: str) -> dict:
    """The YAML front matter's top-level `key: value` lines (and metadata's harness-version)."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    out: dict = {}
    for line in (m.group(1) if m else "").splitlines():
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"')
    return out


def main() -> int:
    found = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
    check("skills: the three of 0.6.x ship, and only those", found == sorted(ORDER), found)
    for name in found:
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        fm = front_matter(text)
        check(
            f"skills: {name} has a valid front matter (name = its folder, a description saying when to use it)",
            fm.get("name") == name
            and "Use when" in fm.get("description", "")
            and re.fullmatch(r"[a-z0-9-]+", name),
            fm,
        )
        check(
            f"skills: {name} names this release",
            fm.get("harness-version") == __version__,
            fm.get("harness-version"),
        )
        n = text.count("\n")
        check(f"skills: {name} is under 500 lines", n < 500, n)
        check(f"skills: {name} has commands to run", bool(BLOCK.findall(text)))

    tmp = Path(tempfile.mkdtemp(prefix="skills-check-"))
    try:
        site = _wheel.install(tmp / "site-packages")
        proj = tmp / "proj"
        proj.mkdir()
        env = {
            **os.environ,
            "PATH": f"{site / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}",
            "PYTHONPATH": str(site),
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_AUTHOR_NAME": "skills",
            "GIT_AUTHOR_EMAIL": "skills@example.invalid",
            "GIT_COMMITTER_NAME": "skills",
            "GIT_COMMITTER_EMAIL": "skills@example.invalid",
        }
        for k in ("EVAL_HOME", "EVAL_DATA_DIR", "OPENROUTER_API_KEY", "EVAL_MAX_COST_USD"):
            env.pop(k, None)

        def sh(script: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + script],
                cwd=proj,
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )

        r = sh("evh init --tutorial >/dev/null && git init -q && git add -A && git commit -qm start")
        check("skills: a fresh tutorial project", r.returncode == 0, r.stderr[-400:])

        r = sh("evh skills-install")
        installed = sorted(p.parent.name for p in (proj / ".claude/skills").glob("*/SKILL.md"))
        check(
            "skills-install: writes every skill into .claude/skills/",
            r.returncode == 0 and installed == found,
            r.stdout,
        )
        r = sh("evh skills-install")
        check(
            "skills-install: run again, every copy is current",
            "current" in r.stdout and "wrote" not in r.stdout,
            r.stdout,
        )
        edited = proj / ".claude/skills" / ORDER[0] / "SKILL.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "\nA project's own note.\n", encoding="utf-8")
        r = sh("evh skills-install")
        check(
            "skills-install: a copy changed after install is kept, and named",
            "kept" in r.stdout and "A project's own note." in edited.read_text(encoding="utf-8"),
            r.stdout,
        )
        r = sh("evh skills-install --force")
        check(
            "skills-install: --force replaces it",
            "updated" in r.stdout and "A project's own note." not in edited.read_text(encoding="utf-8"),
            r.stdout,
        )
        r = sh("evh skills-install --target agent-skills")
        check(
            "skills-install: --target writes anywhere",
            (proj / "agent-skills" / ORDER[0] / "SKILL.md").is_file(),
            r.stdout,
        )

        for name in ORDER:
            for i, block in enumerate(
                BLOCK.findall((SKILLS / name / "SKILL.md").read_text(encoding="utf-8")), 1
            ):
                r = sh(block)
                first = block.strip().splitlines()[0]
                check(
                    f"skills: {name} block {i} runs as written ({first[:60]})",
                    r.returncode == 0,
                    (r.stdout + r.stderr)[-800:],
                )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
