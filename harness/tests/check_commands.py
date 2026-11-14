#!/usr/bin/env python3
"""Every command the docs show still exists and takes the flags they pass it.

    python tests/check_commands.py

The GUIDE is run end to end (check_guide.py). The other docs (the RUNBOOK, INTEGRATION, the
READMEs) show commands with placeholders (`my_v1`, `<run_id>`), so they cannot be run, and
were checked by nothing: a renamed target or a dropped flag stayed in them until a reader
hit it. This checks, in every fenced block and inline code span of the current docs:

  - `evh <command>`: the command exists, and every --flag after it is one its --help lists;
  - `make <target>` (here or `make -C harness`): the target exists in one of the two
    Makefiles, every VAR=value names a variable that Makefile uses, and every --flag inside
    ARGS="..." is one the script behind the target accepts.

History is not checked: the research journal and the CHANGELOG describe commands as they
were when written. Nor is a proposal: an ADR or RFC whose status is Proposed or Draft describes commands
that do not exist yet; it is checked once accepted. Nor is a part of a shipped doc marked planned: a heading,
list item (with what is indented under it), table row or paragraph that says "(0.6.0, planned" describes work
still to be built, and is checked once the build takes the marker off. Exits 1 on any problem.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from functools import cache
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
HARNESS = HERE.parent
REPO = HARNESS.parent
from evaluation_harness.cli import COMMANDS  # noqa: E402

DOCS = [
    REPO / "README.md",
    HARNESS / "README.md",
    *sorted((HARNESS / "docs").glob("*.md")),
    *sorted(p for p in (REPO / "docs").rglob("*.md") if "papers" not in p.parts),
    *sorted((REPO / "examples").glob("*/README.md")),
    HARNESS / "project_kit" / "AGENTS.md",
]
SKIP = {HARNESS / "CHANGELOG.md"}
FENCE = re.compile(r"^```(\w*)")
PLANNED = re.compile(r"\(\d+\.\d+(?:\.\d+)?, planned\b")
ITEM = re.compile(r"^(\s*)(?:[-*]|\d+\.)\s")
INLINE = re.compile(r"`([^`\n]+)`")
TARGET = re.compile(r"^([A-Za-z][\w.-]*(?:[ \t]+[A-Za-z][\w.-]*)*)\s*:(?!=)", re.M)


def makefile(path: Path) -> tuple:
    """({target: [script paths its recipe runs]}, {variables it uses})."""
    text = path.read_text(encoding="utf-8")
    targets: dict = {}
    current: list = []
    for line in text.splitlines():
        m = TARGET.match(line)
        if m and not line.startswith("\t"):
            current = m.group(1).split()
            for t in current:
                targets.setdefault(t, [])
        elif line.startswith("\t") and current:
            for s in re.findall(r"(scripts/[\w]+\.py|site/[\w]+\.py|examples/[\w./-]+\.py)", line):
                for t in current:
                    targets[t].append((path.parent / s).resolve())
    return targets, set(re.findall(r"\$\((\w+)\)", text)) | set(re.findall(r"^(\w+)\s*[?:]?=", text, re.M))


HARNESS_MK = makefile(HARNESS / "Makefile")
ROOT_MK = makefile(REPO / "Makefile")


@cache
def flags_of(script: Path) -> frozenset:
    """Extract all --flags from a script's --help output."""
    r = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=120)
    return frozenset(re.findall(r"(--[a-z][a-z0-9-]*)", r.stdout + r.stderr)) | {"--help"}


def evh_flags(name: str) -> frozenset:
    """Extract all --flags from `evh <name> --help`: a command made from an operation of the model (RFC-032) shares
    its script with the others, and only evh tells it which it is."""
    r = subprocess.run(
        [sys.executable, str(HERE / "cli.py"), name, "--help"], capture_output=True, text=True, timeout=120
    )
    return frozenset(re.findall(r"(--[a-z][a-z0-9-]*)", r.stdout + r.stderr)) | {"--help"}


def commands_in(text: str) -> list:
    """Shell-ish command lines from fenced blocks (continuations joined) and inline spans."""
    out, lines, fence = [], text.splitlines(), None
    buf = ""
    for n, line in enumerate(lines, 1):
        f = FENCE.match(line.strip())
        if f:
            fence = None if fence is not None else f.group(1)
            continue
        if fence is not None and fence in ("", "bash", "sh", "shell", "console"):
            s = line.strip()
            if s.endswith("\\"):
                buf += s[:-1] + " "
                continue
            out.append((n, buf + s))
            buf = ""
        elif fence is None:
            out += [(n, m) for m in INLINE.findall(line)]
    return out


def planned_lines(text: str) -> set:
    """The line numbers (1-based) inside a part marked planned: a heading's section (to the next heading of its
    level or higher), a list item with the lines indented under it, a table row, or a paragraph."""
    lines = text.splitlines()
    out: set[int] = set()
    n = 0
    while n < len(lines):
        line = lines[n]
        head = re.match(r"^(#+)\s", line)
        if head:
            if PLANNED.search(line):
                end = next(
                    (
                        k
                        for k in range(n + 1, len(lines))
                        if (h := re.match(r"^(#+)\s", lines[k])) and len(h.group(1)) <= len(head.group(1))
                    ),
                    len(lines),
                )
                out.update(range(n + 1, end + 1))
                n = end
                continue
            n += 1
            continue
        if not line.strip():
            n += 1
            continue
        item = ITEM.match(line)
        end = n + 1
        if line.lstrip().startswith("|"):
            pass
        elif item:
            indent = len(item.group(1))
            while (
                end < len(lines)
                and lines[end].strip()
                and (len(lines[end]) - len(lines[end].lstrip())) > indent
            ):
                end += 1
        else:
            while (
                end < len(lines)
                and lines[end].strip()
                and not ITEM.match(lines[end])
                and not lines[end].startswith(("#", "|"))
            ):
                end += 1
        if any(PLANNED.search(x) for x in lines[n:end]):
            out.update(range(n + 1, end + 1))
        n = end
    return out


def check_line(cmd: str) -> list:
    """Check that all evh and make commands in a line are real and take valid flags."""
    problems = []
    for part in re.split(r"&&|\|\||;|\|", cmd):
        part = re.sub(r"^\s*(\$\s+)?([A-Z_]+=\S*\s+)*", "", part.split("#", 1)[0]).strip()
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        if not words:
            continue
        if words[0] == "evh" and len(words) > 1:
            name = words[1]
            if name.startswith("-"):
                continue
            if name not in COMMANDS:
                problems.append(f"`evh {name}`: no such command")
                continue
            ok = evh_flags(name)
            problems += [
                f"`evh {name} {w}`: {COMMANDS[name][0]} has no {w}"
                for w in words[2:]
                if w.startswith("--") and w.split("=")[0] not in ok
            ]
        elif words[0] == "make" and len(words) > 1:
            rest, mk = words[1:], None
            if rest[:2] == ["-C", "harness"]:
                rest, mk = rest[2:], HARNESS_MK
            if not rest or rest[0].startswith("-"):
                continue
            target, assigns = rest[0], rest[1:]
            if "=" in target or "<" in target or "…" in target or set(target) == {"."}:
                continue
            mks = [mk] if mk else [HARNESS_MK, ROOT_MK]
            hit = next((m for m in mks if target in m[0]), None)
            if hit is None:
                problems.append(f"`make {target}`: no such target")
                continue
            for a in assigns:
                var, _, val = a.partition("=")
                if not _ or not re.fullmatch(r"[A-Z_]+", var):
                    continue
                if var not in hit[1]:
                    problems.append(f"`make {target} {var}=…`: the Makefile never uses {var}")
                if var == "ARGS":
                    for w in val.split():
                        if (
                            w.startswith("--")
                            and hit[0][target]
                            and not any(w.split("=")[0] in flags_of(s) for s in hit[0][target] if s.is_file())
                        ):
                            problems.append(
                                f'`make {target} ARGS="{w}"`: '
                                f"{', '.join(s.name for s in hit[0][target])} has no {w}"
                            )
    return problems


def self_check() -> list:
    """Each rule must fire on a line that breaks it, and stay quiet on one that does not:
    a checker that reports nothing proves nothing until it is shown to report something."""
    cases = [
        ("evh pair-test --dataset-id x --nope", True),
        ("evh nosuch", True),
        ("make nosuch-target", True),
        ('make dataset-create DATASET_ID=x ARGS="--nope"', True),
        ("make leaderboard NOSUCHVAR=1", True),
        ('make dataset-create DATASET_ID=x ARGS="--fieldset t"', False),
        ("evh leaderboard --dataset-id x --sort overlap_f1", False),
        ("make -C harness ci", False),
    ]
    bad = [
        f"self-check: {line!r} should {'' if want else 'not '}be reported"
        for line, want in cases
        if bool(check_line(line)) != want
    ]
    doc = (
        "- shipped: `evh nosuch-a`\n"
        "- (0.6.0, planned) a new one: `evh nosuch-b`\n"
        "  indented under it: `evh nosuch-c`\n"
        "- shipped again: `evh nosuch-d`\n"
        "\n"
        "## A section (0.6.0, planned)\n"
        "\n"
        "`evh nosuch-e`\n"
        "\n"
        "### Under it: `evh nosuch-f`\n"
        "\n"
        "## Shipped\n"
        "\n"
        "| a row | `evh nosuch-g` |\n"
        "| a row (0.6.0, planned) | `evh nosuch-h` |\n"
    )
    skipped = planned_lines(doc)
    got = sorted(cmd.split()[1] for n, cmd in commands_in(doc) if n not in skipped)
    want_left = ["nosuch-a", "nosuch-d", "nosuch-g"]
    if got != want_left:
        bad.append(f"self-check: planned parts skipped wrongly: left {got}, want {want_left}")
    return bad


def main() -> int:
    """Check all command references in the docs still exist with valid flags."""
    bad, seen = self_check(), 0
    for doc in DOCS:
        if doc in SKIP or not doc.is_file():
            continue
        text = doc.read_text(encoding="utf-8")
        # A proposal names commands still to be built: an ADR's `**Status:** Proposed`, an RFC's
        # `- **Status**: Draft`, or one accepted and still to build (`Accepted …, (0.6.0, planned)`).
        if re.search(
            r"^(?:- )?\*\*Status(?::\*\*|\*\*:) (?:Proposed|Draft|Accepted.*\(\d+\.\d+(?:\.\d+)?, planned)",
            text,
            re.M,
        ):
            continue
        skipped = planned_lines(text)
        for n, cmd in commands_in(text):
            if n in skipped:
                continue
            if re.search(r"\b(evh|make)\s", cmd):
                seen += 1
            for p in check_line(cmd):
                bad.append(f"{doc.relative_to(REPO)}:{n}: {p}")
    for b in bad:
        print(f"  {b}")
    print(
        f"documented commands: {seen} make/evh command(s) in {len(DOCS)} docs, "
        + ("every target, command and flag exists" if not bad else f"{len(bad)} problem(s)")
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
