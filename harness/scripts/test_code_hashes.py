#!/usr/bin/env python3
"""Every scoring hash must move when the code it claims to cover moves. $0, no network.

    python scripts/test_code_hashes.py

WHY. Every hash here was `sha256(inspect.getsource(fn))`, which covers the `def` block
and nothing else. The regexes those parsers are driven by are module-level constants, so
editing `_BARE_KEY`, `_LEADIN`, `_PUNCT` or `_TOKEN` changed every score and left the
hash identical -- and the retrieval parser was in no hash at all. An external review
found all five at once. These assertions are the thing that would have caught them.
"""
import pathlib
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

# ── the NER and classification adapters, which had no assertions here at all ──
#
# test_code_hashes covered the two shared scorers and nothing else, so the NER parser
# hash was free to stop covering the NER parser -- which is exactly what happened when
# round 2 moved the array extraction into `_balanced_arrays` and did not add it to the
# digest. Gutting that function left the hash byte-identical. Found by external review.
import importlib.util as _ilu  # noqa: E402


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 — an example whose deps are absent is a skip
        return None


_HERE = pathlib.Path(__file__).resolve().parents[2]
_ner = _load("ner_adapter_hashcheck", _HERE / "examples/ner-few-nerd/adapter.py")
if _ner is None:
    print("  --   NER adapter: skipped (its dependencies are not on this interpreter)")
else:
    check("NER: _parser_sha256 covers _BARE_KEY",
          moves(_ner, _ner._parser_sha256, "_BARE_KEY", re.compile(r"(zzz)(zzz)")))
    check("NER: _parser_sha256 covers _FENCE",
          moves(_ner, _ner._parser_sha256, "_FENCE", re.compile(r"zzz")))
    # The function, not just the constants. This is the one that regressed.
    check("NER: _parser_sha256 covers _balanced_arrays ITSELF",
          moves(_ner, _ner._parser_sha256, "_balanced_arrays", lambda body: []))
    check("NER: and _parse_entities itself",
          moves(_ner, _ner._parser_sha256, "_parse_entities", lambda text: None))

# The classification parser hash lives on the shared ClassificationTask, not on the
# example adapter, so it is checked directly against the module the adapters import.
import classification as _cls  # noqa: E402

_task = _cls.ClassificationTask(labels=("Alpha", "Beta"), default_label="Alpha")
check("classification: parser_sha256 covers the alias table",
      moves(_task, _task.parser_sha256, "_aliases", {"zzz": "a"}))
check("classification: parser_sha256 covers _MARKDOWN",
      moves(_cls, _task.parser_sha256, "_MARKDOWN", re.compile(r"zzz")))
check("classification: parser_sha256 covers _LEADIN",
      moves(_cls, _task.parser_sha256, "_LEADIN", re.compile(r"zzz")))
check("classification: and parse_label itself",
      moves(_cls.ClassificationTask, _task.parser_sha256, "parse_label",
            lambda self, text: None))

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
