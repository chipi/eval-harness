#!/usr/bin/env python3
"""Code identity (_codeid.py): documentation never moves a hash; behaviour always does.

    python tests/test_codeid.py

Both directions, because widening a hash until it stops complaining is the failure to avoid:
docstrings, comments, formatting and METRIC_DESCRIPTIONS leave it as it was; a changed
expression, constant, default or function changes it.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._codeid import content_sha256, source_sha256  # noqa: E402

BASE = '''"""An adapter."""
import re

PRIMARY_METRIC = "acc"
METRIC_DESCRIPTIONS = {"acc": "share right"}
_WORD = re.compile(r"\\\\w+")
THRESHOLD = 0.5


def score(output, reference):
    """Score one output."""
    # compare labels
    return {"acc": 1.0 if output.strip() == (reference or "").strip() else 0.0}
'''
h = source_sha256(BASE)


def same(label, text):
    check(f"documentation does not move the hash: {label}", source_sha256(text) == h)


def moves(label, text):
    check(f"behaviour moves the hash: {label}", source_sha256(text) != h)


same(
    "a docstring edited",
    BASE.replace('"""Score one output."""', '"""Score one output against its reference, 1 or 0."""'),
)
same("a module docstring edited", BASE.replace('"""An adapter."""', '"""An adapter for routing."""'))
same(
    "a comment added and edited",
    BASE.replace("# compare labels", "# compare the labels exactly\n    # (case matters)"),
)
same("formatting", BASE.replace("1.0 if output", "1.0  if  output"))
same("METRIC_DESCRIPTIONS edited", BASE.replace('"share right"', '"the share of items labelled right"'))
same("METRIC_DESCRIPTIONS removed", BASE.replace('METRIC_DESCRIPTIONS = {"acc": "share right"}\n', ""))
same(
    "METRIC_DESCRIPTIONS imported instead",
    BASE.replace(
        'METRIC_DESCRIPTIONS = {"acc": "share right"}\n', "from shared import METRIC_DESCRIPTIONS\n"
    ),
)
moves("another name imported", BASE + "\nfrom shared import THRESHOLDS\n")
moves("an expression", BASE.replace("output.strip() ==", "output.strip().lower() =="))
moves("a constant the code reads", BASE.replace("THRESHOLD = 0.5", "THRESHOLD = 0.6"))
moves("the primary metric", BASE.replace('PRIMARY_METRIC = "acc"', 'PRIMARY_METRIC = "f1"'))
moves("a new function", BASE + "\n\ndef helper():\n    return 1\n")
check("source that does not parse is hashed as its bytes", source_sha256("def (") != source_sha256("def ( "))

# A FIXED VALUE, measured identical on Python 3.11, 3.12 and 3.14 (2026-10-24). `ast.dump` gave
# different text for the same file on 3.11 and 3.14; a change here means the hash now depends on
# the interpreter, and every run measured on another version would look like another scorer.
GOLDEN = 'def f(x, *, y=2):\n    """doc"""\n    return [i for i in x if i] if y else {k: v for k, v in x}\n'
check(
    "the same source hashes the same on every Python version",
    source_sha256(GOLDEN) == "b146e602204af329444c41ba8d6288db6c54e6b96c8d07dfad780b4d2ebfcd7e",
)
check(
    "a YAML document's comments and key order do not move content_sha256",
    content_sha256({"b": 1, True: "x"}) == content_sha256({True: "x", "b": 1}),
)

sys.exit(summary())
