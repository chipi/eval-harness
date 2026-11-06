#!/usr/bin/env python3
"""A changed rubric says what it replaced and why (PLAN_0.8.0 C3): a scorer's `supersedes` and `why`.

    python tests/test_scorer_supersedes.py

A copy of a committed scorer in a scratch directory: superseding a scorer that is there, with a sentence, passes
validate's scorer check (V13); superseding one that is not, a one-word reason, or a reason with nothing superseded
are each named.
"""

import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.validate_tree import scorer_problems  # noqa: E402

SRC = HARNESS / "data" / "scorers"
base = "judge-summ-v1"
with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    shutil.copy(SRC / f"{base}.yaml", d / f"{base}.yaml")
    for extra in SRC.glob(f"{base}*"):
        if extra.suffix != ".yaml":
            shutil.copy(extra, d / extra.name)
    text = (SRC / f"{base}.yaml").read_text()

    def with_(lines: str) -> list:
        (d / "next-v2.yaml").write_text(text.replace(f"scorer_id: {base}", "scorer_id: next-v2") + lines)
        return [p for p in scorer_problems(d) if p.startswith("next-v2.yaml")]

    good = with_(f"supersedes: {base}\nwhy: the rubric now asks for one sentence, after long answers won\n")
    check("supersedes a scorer that is here, with a sentence: no problem", good == [], good)
    gone = with_("supersedes: no-such-scorer\nwhy: the rubric changed after we read the outputs\n")
    check("superseding a scorer that is not here is named", any("not a scorer here" in p for p in gone), gone)
    short = with_(f"supersedes: {base}\nwhy: better\n")
    check("a one-word reason is refused", any("must be a sentence" in p for p in short), short)
    lone = with_("why: the rubric changed after we read the outputs\n")
    check("a reason with nothing superseded is named", any("without `supersedes`" in p for p in lone), lone)
sys.exit(summary())
