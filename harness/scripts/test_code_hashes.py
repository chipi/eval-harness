#!/usr/bin/env python3
"""Every scoring hash must move when the code it claims to cover moves. $0, no network.

    python scripts/test_code_hashes.py

WHY. Every hash here was `sha256(inspect.getsource(fn))`, which covers the `def` block
and nothing else. The regexes those parsers are driven by are module-level constants, so
editing `_BARE_KEY`, `_LEADIN`, `_PUNCT` or `_TOKEN` changed every score and left the
hash identical -- and the retrieval parser was in no hash at all. An external review
found all five at once. These assertions are the thing that would have caught them.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "examples" / "_shared"))

ok = []
def check(label, cond): ok.append((label, cond)); print(f"  {'ok  ' if cond else 'FAIL'} {label}")

import codehash  # noqa: E402
import extraction  # noqa: E402
import retrieval  # noqa: E402

# ── the helper itself ────────────────────────────────────────────────────────
def f(): return 1
check("code_digest: stable across calls", codehash.code_digest(f) == codehash.code_digest(f))
check("code_digest: a changed constant changes the digest",
      codehash.code_digest(f, consts={"x": re.compile("a")})
      != codehash.code_digest(f, consts={"x": re.compile("b")}))
check("code_digest: regex FLAGS count, not just the pattern",
      codehash.code_digest(f, consts={"x": re.compile("a")})
      != codehash.code_digest(f, consts={"x": re.compile("a", re.I)}))
check("code_digest: set order does not change the digest",
      codehash.code_digest(f, consts={"x": {"a", "b"}})
      == codehash.code_digest(f, consts={"x": {"b", "a"}}))

# ── the real hashes move when their constants move ───────────────────────────
def moves(mod, hash_fn, const_name, new_value):
    """Swap a module constant, take the hash, put it back."""
    before = hash_fn()
    old = getattr(mod, const_name)
    setattr(mod, const_name, new_value)
    try:
        after = hash_fn()
    finally:
        setattr(mod, const_name, old)
    return before != after

check("extraction: normalizer_sha256 covers _PUNCT",
      moves(extraction, extraction.normalizer_sha256, "_PUNCT", re.compile(r"[x]")))
check("extraction: normalizer_sha256 covers _ARTICLES",
      moves(extraction, extraction.normalizer_sha256, "_ARTICLES", ("zzz ",)))
check("extraction: scorer_sha256 covers _PUNCT too",
      moves(extraction, extraction.scorer_sha256, "_PUNCT", re.compile(r"[x]")))
check("retrieval: scorer_sha256 covers the CUT-OFFS",
      moves(retrieval, retrieval.scorer_sha256, "NDCG_AT", 99))

# THE ONE THAT WAS IN NO HASH AT ALL: the retrieval parser.
src_before = retrieval.scorer_sha256()
_orig = retrieval.parse_ranking
def _stub(text):  # a parser that returns something else entirely
    return ["different"]
retrieval.parse_ranking = _stub
try:
    check("retrieval: scorer_sha256 now covers parse_ranking",
          retrieval.scorer_sha256() != src_before)
finally:
    retrieval.parse_ranking = _orig

print(f"\n{sum(1 for _, c in ok if c)}/{len(ok)} passed")
sys.exit(0 if all(c for _, c in ok) else 1)
