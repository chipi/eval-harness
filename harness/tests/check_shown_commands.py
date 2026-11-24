#!/usr/bin/env python3
"""Every `evh …` command the harness's own surfaces show a person to run exists and takes what it is shown with.

    python tests/check_shown_commands.py

check_commands.py checks the docs. A person also meets commands in the code: the Workbench's "the command this runs"
(workbench/*.js), the catalog and inspector pages (catalog_*.py, catalog_assets/*.js), and the CLI's own messages
(refusals, `next:` lines, NOTE and HINT lines, --help epilogs: strings in scripts/**/*.py). A command one of them
showed with a flag it never had (`evh prompt-diff --a X --b Y`: the ids are positional) stayed there until a reader
ran it. For each `evh <command> …` found in those files this checks, with check_commands.check_line:

  - the command exists (evaluation_harness.cli.COMMANDS) and every literal --flag is one its --help lists;
  - the number of positional arguments fits its usage (`a b` is two, `[NAME]` is optional), a flag that takes a value
    taking its value first.

It reads the text of the source files, so it has to guess where a command ends in a string. How sure it is of that
decides how much it checks:

  - Strong: the command follows a backtick, `<code>`, `$ ` or the start of a line. It ends at the closing backtick,
    `</code>`, a literal `\\n`, a shell operator (&& ; > # and a pipe), or the end of the line, and at two spaces or
    `: ` (a usage block's description column). Too many and too few arguments are both reported.
  - Quoted: it follows a quote and the string closes (or a `\\n` ends it) on the same line. Too few arguments are
    reported, and too many only of what looks like an argument (`<id>`, `NAME`, not `my_v1`): the text after a
    command in a message is often prose ("evh migrate writes the versions the lineage gives"), and plain words cannot
    be told from arguments.
  - Prose: anything else ("run evh export to ..."). Only the command name and its literal --flags are checked, the name
    only when it is a command or looks like one (has a hyphen, or is followed by a --flag).

What it does not check, and why:

  - A placeholder is a value, not a flag: `${…}`, `{x}`, `<id>`, `$VAR`, `[NAME]` (an optional argument), `…` and
    `...` (more of the same: the count can then only be too high). A flag that is built (`--${k}`) is skipped. A positional that is `${…}` or `{…}` can
    expand to any number of words, so the count is not checked then.
  - A command shown with no argument at all (`evh round-list`, `evh chart --svg F`) is a command's name, as often as a
    recipe ("`evh chart` draws it"): its flags are checked, its missing positional is not.
  - A command whose usage has sub-commands: its flags are checked, its positional count is not.
  - A line that says it is history (`was`, `removed`, `renamed`, `no longer`, `used to`, `gone`, `dropped`,
    `replaced`): a command that does not exist now is the point of the line.
  - A command whose name is followed by `:`, `)`, `,`, `*` or `<` (`evh data-*`, `evh goal-<verb>`, `evh x: what it
    does`): a name in a sentence, a family of commands, not something to run.
Exits 1 on any problem.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_commands import COMMANDS, HARNESS, REPO, check_line

SURFACES = [
    *sorted((HARNESS / "workbench").glob("*.js")),
    *sorted((HARNESS / "catalog_assets").glob("*.js")),
    *sorted((HARNESS / "scripts").rglob("*.py")),
]
HISTORY = re.compile(r"\b(?:was|were|removed|renamed|no longer|used to|gone|dropped|replaced)\b", re.I)
NAME = re.compile(r"evh ([a-z][a-z0-9-]*)(?![\w*])")
#: What ends a command whatever opened it. A quote is not here: `--text "..."` holds a value, and only a quote that
#: closes the host string ends one.
ENDERS = re.compile(r"`|</code>|</|\\n|\\\\n|&&|\s;|\s>\s|\s#\s")
FLAG = re.compile(r"(?<![\w$<{-])--[a-z][a-z0-9-]*")
STOP = {"|", "||", "&&", ";", ">", "#"}


def _usage(name: str) -> tuple[dict, list, bool]:
    """({flag: 'none'|'one'|'many'}, [(positional, required, variadic)], complex) from `evh <name> --help`."""
    r = subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), name, "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
    )
    out = r.stdout + r.stderr
    usage = re.search(r"usage:(.*?)\n\s*\n", out, re.S)
    use = " ".join(usage.group(1).split()) if usage else ""
    flags: dict = {}
    pos: list = []
    section = ""
    for ln in out.splitlines():
        if re.match(r"^\S.*:$", ln):
            section = ln.strip()
            continue
        m = re.match(r"^  (\S.*?)(?:\s{2,}|$)", ln)
        if not m or not section:
            continue
        head = m.group(1)
        if section.startswith("positional"):
            pos.append(head)
        else:
            for seg in head.split(", "):
                f = re.match(r"(--?[\w-]+)(?:[ =](.*))?$", seg)
                if f:
                    metavar = f.group(2)
                    flags[f.group(1)] = (
                        "none"
                        if not metavar
                        else "many"
                        if ("..." in metavar or metavar.startswith("["))
                        else "one"
                    )
    shown = []
    for p in pos:
        if p.startswith("{"):
            return flags, [], True
        bare = p.split()[0]
        required = f"[{bare}" not in use
        variadic = bool(re.search(rf"{re.escape(bare)}(?:\])? ?\[?\S*\.\.\.", use))
        shown.append((bare, required, variadic))
    return flags, shown, "(" in use


usage_of = cache(_usage)


def tokens(s: str) -> list:
    """The words of a command's tail, a placeholder or a quoted value kept whole."""
    pairs = {"{": "}", "[": "]", "(": ")", "<": ">"}
    out, i, n = [], 0, len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        j, quote = i, ""
        stack: list[str] = []
        while j < n and (stack or quote or not s[j].isspace()):
            c = s[j]
            if s.startswith("${", j):  # a template's own code, whatever quotes it holds
                depth, j = 0, j + 1
                while j < n:
                    depth += (s[j] == "{") - (s[j] == "}")
                    j += 1
                    if not depth:
                        break
                continue
            if quote:
                if c == quote:
                    quote = ""
            elif c in "\"'" and (j == i or s[j - 1] in "= "):
                quote = c
            elif c in "{[(" or (c == "<" and (j == i or s[j - 1] == "=")):
                stack.append(pairs[c])
            elif stack and c == stack[-1]:
                stack.pop()
            j += 1
        out.append(s[i:j])
        i = j
    return out


def check_args(name: str, args: list, strong: bool) -> list:
    """Problems with a command's positional count (the --flags are check_line's)."""
    flags, pos, cplx = usage_of(name)
    if cplx:
        return []
    need = sum(1 for _, req, _ in pos if req)
    top = None if any(v for _, _, v in pos) else len(pos)
    n = optional = marked = 0
    skip = more = False
    for t in args:
        if skip:
            skip = False
            continue
        if t in ("...", "…") or t.startswith("..."):
            more = True
            continue
        if re.fullmatch(r"--[a-z][a-z0-9-]*(?:=.*)?", t):
            kind = flags.get(t.split("=")[0], "unknown")
            if kind in ("many", "unknown"):
                return []
            skip = kind == "one" and "=" not in t
        elif t.startswith("-") and len(t) > 1:
            return []
        elif t.startswith(("[", "(")):
            optional += 1
        elif "{" in t or t.startswith("$"):
            return []
        else:
            n += 1
            marked += bool(re.fullmatch(r"<[^<>]*>|[A-Z][A-Z0-9_]*", t))
    if not n and not optional:
        return []
    sig = " ".join(p if req else f"[{p}]" for p, req, _ in pos) or "no arguments"
    if (n + optional < need and not more) or (top is not None and (n if strong else marked) > top):
        return [f"`evh {name}` takes {sig} (usage), shown with {n + optional} argument(s): {' '.join(args)}"]
    return []


def before_ok(before: str) -> bool:
    """Whether `evh` starts a word here (not `levh`, `x-evh`, a path), a literal `\\n` of a string counting as a break."""
    return before.endswith("\\n") or not (before[-1].isalnum() or before[-1] in "_-/.@")


def host_quote(tail: str, quote: str) -> tuple[str, bool]:
    """(the command before the quote that closes the string it is in, whether one did): a quote after a space or `=`
    opens a value (`--text "..."`), which holds its own quotes of the other kind."""
    inner = ""
    for i, c in enumerate(tail):
        if inner:
            inner = "" if c == inner else inner
        elif c == quote and not (
            i and tail[i - 1] in " =" and tail[i + 1 : i + 2] not in ("", " ", ",", ")")
        ):
            return tail[:i], True
        elif c in "\"'" and i and tail[i - 1] in " =":
            inner = c
    return tail, False


def commands_in(text: str) -> list:
    """(line, command text, strength) for each `evh <name> …` in a source text: 2 strong, 1 quoted, 0 prose."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if HISTORY.search(line):
            continue
        for m in NAME.finditer(line):
            start = m.start()
            before = line[:start]
            if before and not before_ok(before):
                continue
            tail = line[start:]
            if tail[m.end() - start : m.end() - start + 1] not in ("", " ", "`", "\\", '"', "'"):
                out.append((n, m.group(0), 0))  # `evh x:`, `evh x)`, `evh x,`: a name in a sentence
                continue
            nxt = re.search(r"\bevh [a-z]", tail[4:])
            if nxt:
                tail = tail[: 4 + nxt.start()]
            end = ENDERS.search(tail)
            cut = tail[: end.start()] if end else tail
            newline = before.endswith("\\n")
            ended_by_tag = end is not None and tail[end.start() :].startswith(("`", "</code>"))
            quote = before[-1] if before.endswith(('"', "'")) else ""
            if newline and not ended_by_tag:
                quote = next((c for c in reversed(before) if c in "\"'"), "")
            if not before.strip() or before.endswith(("`", "$ ", "<code>")) or (newline and ended_by_tag):
                strength = 2
            elif quote:
                cut, closed = host_quote(cut, quote)
                strength = 1 if closed or end else 0
            else:
                strength = 0
            cut = re.split(r"\s{2,}|:\s|:$", cut.strip())[0].rstrip("\\ ,.;")
            out.append((n, cut, strength))
    return out


def problems_of(cmd: str, strength: int) -> list:
    """What is wrong with one shown command."""
    words = [w for w in tokens(html.unescape(cmd)) if w.strip("\"'")]
    for k, w in enumerate(words):
        if w in STOP:
            words = words[:k]
            break
    if len(words) < 2:
        return []
    name = re.split(r"[^a-z0-9-]", words[1], maxsplit=1)[0]
    if name != words[1]:  # `evh x")`: a name at the end of a sentence in a string
        words, strength = words[:2], 0
    if name.endswith("-"):
        return []
    if name not in COMMANDS and not strength and "-" not in name and not FLAG.search(cmd):
        return []
    if name.startswith(("<", "$", "{", "[", "…", "...")):
        return []
    found = check_line(" ".join(["evh", name, *FLAG.findall(re.sub(r"\"[^\"]*\"|'[^']*'", "", cmd))]))
    if name in COMMANDS and strength:
        found += check_args(name, words[2:], strength == 2)
    return found


def self_check() -> list:
    """Each rule fires on a string that breaks it and stays quiet on one that does not."""
    cases = [
        ("WB.cmd(`evh prompt-diff --a <id> --b <id>`)", True),
        ("WB.cmd(`evh prompt-diff ${a} ${b}`)", False),
        ("WB.cmd(`evh prompt-diff <a> <b>`)", False),
        ("WB.cmd(`evh prompt-show --name ${name} --text\\nevh prompt-diff --a X --b Y`)", True),
        ("WB.cmd(`evh prompt-show --name ${name} --text\\nevh prompt-diff ${a} ${b}`)", False),
        ("'evh prompt-diff --a X --b Y'", True),
        ("'evh prompt-diff A'", True),
        ('print("next: evh prompt-diff A")', False),
        ('print("next: evh prompt-diff A B")', False),
        ('print("next: `evh prompt-diff A B C`")', True),
        ('print("next: evh nosuch-command x")', True),
        ("<code>evh leaderboard my_v1 --sort overlap_f1</code>", False),
        ("<code>evh leaderboard my_v1 --nope</code>", True),
        ("`evh leaderboard`", False),
        ("`evh leaderboard --wide`", False),
        ("`evh leaderboard a b`", True),
        ("`evh round-open --goal G --dataset D --budget-usd 5`", False),
        ("`evh round-open G --budget-usd 5`", True),
        ("`evh run ${arm} --resume ${id}`", False),
        ("and then evh prompt-diff shows the text", False),
        ('"evh prompt-diff shows the text of two versions"', False),
        ("the old evh prompt-diff --a was removed", False),
        ('`evh prompt-version --name ${n} --text "use --foo" --parent ${p}`', False),
        ("`evh prompt-diff --${k} x`", False),
        ("`evh data-*` and `evh goal-<verb>`", False),
        ('"evh rescore --goal G --round rN (re-score), or evh round-open --from rN"', False),
        ("`evh prompt-diff A B | less`", False),
    ]
    bad = []
    for line, want in cases:
        got = [p for _, c, s in commands_in(line) for p in problems_of(c, s)]
        if bool(got) != want:
            bad.append(f"self-check: {line!r} should {'' if want else 'not '}be reported (got {got})")
    return bad


def main() -> int:
    """Check every command the surfaces show."""
    bad, seen = self_check(), 0
    for f in SURFACES:
        for n, cmd, strength in commands_in(f.read_text(encoding="utf-8", errors="replace")):
            seen += 1
            bad += [f"{f.relative_to(REPO)}:{n}: {p}  [{cmd}]" for p in problems_of(cmd, strength)]
    for b in bad:
        print(f"  {b}")
    print(
        f"shown commands: {seen} `evh` command(s) in {len(SURFACES)} surface files, "
        + ("every command, flag and argument count fits" if not bad else f"{len(bad)} problem(s)")
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
