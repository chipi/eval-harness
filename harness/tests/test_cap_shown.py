#!/usr/bin/env python3
"""A spending cap has three meanings, and every command prints them one way (`_spend.shown`).

  python tests/test_cap_shown.py

- no cap, a cap of 0 (spend nothing: only what is known to be free runs) and an amount are three different lines;
- no command formats a cap itself: a test of the cap's truth printed a cap of 0 as none in `evh run --dry-run` and
  `evh env-check` (the homelab bake-off on v0.8.0), while the judges' dry runs printed it right.
"""

import io
import re
import sys
import tokenize
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _spend  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

check("no cap is NONE", _spend.shown(None) == "NONE", _spend.shown(None))
check(
    "a cap of 0 is $0.00 that spends nothing, a negative one too",
    all("$0.00" in _spend.shown(c) and "spend nothing" in _spend.shown(c) for c in (0, 0.0, -1.0)),
    [_spend.shown(c) for c in (0, 0.0, -1.0)],
)
check(
    "an amount is its dollars",
    _spend.shown(0.5) == "$0.50" and _spend.shown(12) == "$12.00",
    _spend.shown(0.5),
)

# Formatting a cap anywhere else is how the two drifted apart: `if cap` read 0 as none.
#: `cap` names a spending cap only (a capture is `capture`, a token limit `reply_cap`), so its truth is never asked.
FORMATTED = re.compile(r"\{\s*cap(?:_usd)?\s*:\s*\.\d+f\s*\}")
CAPS = {"cap", "cap_usd"}
ASKS = {"if", "elif", "and", "or", "not"}
ENDS = {":", ")", "]", ",", "else", "and", "or", "if"}


def truth_tests(src: str) -> list[int]:
    """Lines where code asks a cap's truth (`if cap`, `cap or x`, `x if cap else y`), from the tokens, not the text."""
    toks = [
        t
        for t in tokenize.generate_tokens(io.StringIO(src).readline)
        if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT)
    ]
    out = []
    for i, t in enumerate(toks):
        if t.type != tokenize.NAME or t.string not in CAPS:
            continue
        before = toks[i - 1].string if i else ""
        after = toks[i + 1].string if i + 1 < len(toks) else ""
        after_newline = i + 1 < len(toks) and toks[i + 1].type == tokenize.NEWLINE
        if (before in ASKS and (after in ENDS or after_newline)) or after in ("or", "if"):
            out.append(t.start[0])
    return out


found = []
for p in sorted((HARNESS / "scripts").rglob("*.py")):
    if p.name == "_spend.py":
        continue
    src = p.read_text(encoding="utf-8")
    lines = src.splitlines()
    rel = p.relative_to(HARNESS)
    found += [f"{rel}:{n}: {line.strip()}" for n, line in enumerate(lines, 1) if FORMATTED.search(line)]
    found += [f"{rel}:{n}: {lines[n - 1].strip()}" for n in truth_tests(src)]
check("no command formats a spending cap itself: they print _spend.shown", not found, found)

sys.exit(summary())
