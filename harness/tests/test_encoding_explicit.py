#!/usr/bin/env python3
"""Every text a script, tool, test, example or the site reads or writes names its encoding. $0, offline.

  python tests/test_encoding_explicit.py

`open()`, `Path.read_text`, `Path.write_text`, `Path.open` and a subprocess run with `text=True` decode with the
locale's encoding when they are not told one: UTF-8 here, cp1252 on a Windows console, ASCII under LC_ALL=C. The
store matrix run under such a locale failed 133 test files, in the tests and in the harness. The guard walks every
Python file's syntax tree and names each such call (tests/_encoding_sites.py). ruff's PLW1514 cannot be this guard:
it flags a call only where it can prove the receiver is a `Path` (`Path(...).read_text()`, not `f.read_text()`
for an `f` it cannot see the type of) and has no rule for a subprocess, so it found 40 of the ~2,000 sites.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
ROOT = HARNESS.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
from _encoding_sites import find_sites  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

#: Directories that are not this repository's code: environments, build output, caches, a release's copy.
SKIP_DIRS = {".venv", ".build", ".git", "node_modules", "__pycache__", "_release", ".cache", ".mypy_cache"}

#: (file from the repository root, text on the line) -> why it stays without an encoding. A call that is not
#: here and has none fails; an entry that no longer matches a call fails too, so this list cannot go stale.
EXCEPTIONS = {
    (
        "examples/harbor/adapter.py",
        "subprocess.Popen(",
    ): "frozen scorer code: validate V10 fails every derived run when its hash moves (ruff.toml [format])",
    (
        "harness/scripts/_store.py",
        "path.open(mode)",
    ): "a stream the caller gave: a path-like that is not a pathlib.Path, opened as its own class opens it",
    (
        "harness/tests/test_store.py",
        '_store.open_file(data / "x.txt", mode)',
    ): "the modes (r+, w+, x, rb+) are the subject: the store refuses them before it opens or decodes anything",
    (
        "harness/tests/test_store_readonly.py",
        '_store.open_file(data / "o.txt", mode)',
    ): "the mode is the subject: a read-only store refuses a writer before it opens or decodes anything",
}

BAD = {
    "read_text()": "p.read_text()",
    "write_text()": "p.write_text('x')",
    "open(p)": "open(p)",
    "open(p, 'w')": "open(p, 'w')",
    "Path.open()": "p.open()",
    "Path.open('w')": "p.open('w')",
    "subprocess.run(text=True)": "subprocess.run(['x'], capture_output=True, text=True)",
    "Popen(universal_newlines=True)": "subprocess.Popen(['x'], universal_newlines=True)",
    "check_output(text=True)": "subprocess.check_output(['x'], text=True)",
    "NamedTemporaryFile('w')": "tempfile.NamedTemporaryFile('w')",
    "fdopen(fd, 'w')": "os.fdopen(fd, 'w')",
    "TextIOWrapper": "io.TextIOWrapper(raw)",
    "FileHandler": "logging.FileHandler(p)",
    "a call in a comprehension": "[q.read_text() for q in ps]",
    "a call nested in a call": "json.loads(p.read_text())",
}
FINE = {
    "read_text(encoding=)": "p.read_text(encoding='utf-8')",
    "write_text(encoding=)": "p.write_text('x', encoding='utf-8')",
    "open(encoding=)": "open(p, encoding='utf-8')",
    "read_text with the encoding positional": "p.read_text('utf-8-sig')",
    "write_text with the encoding positional": "p.write_text('x', 'utf-8')",
    "open(p, 'rb')": "open(p, 'rb')",
    "open(p, mode='wb')": "open(p, mode='wb')",
    "Path.open('rb')": "p.open('rb')",
    "open with the encoding positional": "open(p, 'w', -1, 'utf-8')",
    "run without text": "subprocess.run(['x'], capture_output=True)",
    "run(text=False)": "subprocess.run(['x'], text=False)",
    "run(text=True, encoding=)": "subprocess.run(['x'], text=True, encoding='utf-8')",
    "NamedTemporaryFile()": "tempfile.NamedTemporaryFile()",
    "NamedTemporaryFile('w', encoding=)": "tempfile.NamedTemporaryFile('w', encoding='utf-8')",
    "fdopen(fd, 'wb')": "os.fdopen(fd, 'wb')",
    "the store's own read_text": "_store.read_text(p)",
    "the test store's own write_text": "_runstore.write_text(proj, 'a', 'x')",
    "webbrowser.open": "webbrowser.open(url)",
    "a zip member": "zf.open('a')",
    "arguments passed on": "subprocess.run(cmd, **kw)",
}

for label, src in BAD.items():
    check(f"the guard flags {label}", len(find_sites(src + "\n")) == 1, find_sites(src + "\n"))
for label, src in FINE.items():
    check(f"the guard passes {label}", not find_sites(src + "\n"), find_sites(src + "\n"))

files = sorted(
    p
    for p in ROOT.rglob("*.py")
    if not SKIP_DIRS & set(p.relative_to(ROOT).parts) and "worktrees" not in p.relative_to(ROOT).parts
)
check("the guard reads this repository's Python files (not an empty tree)", len(files) > 400, len(files))

found: list[tuple[str, int, str, str]] = []
matched: set[tuple[str, str]] = set()
for p in files:
    rel = p.relative_to(ROOT).as_posix()
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    for line, _col, what in find_sites(text):
        shown = lines[line - 1].strip()
        key = next((k for k in EXCEPTIONS if k[0] == rel and k[1] in shown), None)
        if key:
            matched.add(key)
        else:
            found.append((rel, line, what, shown[:90]))

check(
    "every text read, write and text-mode subprocess names its encoding",
    not found,
    "\n    "
    + "\n    ".join(f"{f}:{ln} {w}  {s}" for f, ln, w, s in found[:25])
    + f"\n    ({len(found)} in all)",
)
check("every exception still matches a call", matched == set(EXCEPTIONS), set(EXCEPTIONS) - matched)

# infra's shell scripts carry Python of their own (`python3 - <<'PY'`), which the walk above never sees.
HEREDOC = re.compile(r"<<'PY'\n(.*?)\nPY\n", re.S)
embedded: list[str] = []
for sh in sorted((ROOT / "infra").rglob("*.sh")):
    src = sh.read_text(encoding="utf-8")
    for m in HEREDOC.finditer(src):
        first = src[: m.start(1)].count("\n") + 1
        embedded += [
            f"{sh.relative_to(ROOT).as_posix()}:{first + ln - 1} {w}"
            for ln, _c, w in find_sites(m.group(1) + "\n")
        ]
check("infra's embedded Python names its encoding too", not embedded, "\n    " + "\n    ".join(embedded))

# workflow_step.py prints a workflow's text as a script for bash: UTF-8 whatever the locale, not a crash.
with tempfile.TemporaryDirectory() as td:
    wf = Path(td) / "w.yml"
    wf.write_text(
        'jobs:\n  j:\n    steps:\n      - name: s\n        run: echo "a \u2014 b"\n', encoding="utf-8"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update(LC_ALL="C", LANG="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0")
    r = subprocess.run(
        [sys.executable, str(ROOT / "infra/deploy/workflow_step.py"), str(wf), "j", "s"],
        capture_output=True,
        env=env,
        check=False,
    )
check(
    "workflow_step.py prints a non-ASCII step as UTF-8 under LC_ALL=C",
    r.returncode == 0 and "\u2014".encode() in r.stdout,
    (r.returncode, r.stdout, r.stderr[-300:]),
)

sys.exit(summary())
