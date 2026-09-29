"""Hash the code that decides a score — functions AND the constants they read.

WHY THIS EXISTS AS A SHARED HELPER

  Every scoring hash in this repo was written as `sha256(inspect.getsource(fn))`, and
  that covers strictly less than it appears to. A parser is its function *plus* the
  module-level regexes the function references; `getsource` returns only the `def`
  block, so editing `_BARE_KEY` or `_PUNCT` changed the score and left the hash
  identical -- the precise failure the hash was added to prevent.

  An external review found this in four places at once (the classification parser, the
  NER parser, the extraction normaliser, the retrieval tokeniser) and found the
  retrieval *parser* covered by no hash at all. One helper, used everywhere, is the
  only way this stays fixed: a scattered idiom drifts again the moment someone adds a
  fifth scorer.

USAGE

    _PUNCT = re.compile(r"[^\w\s]")
    def normalize(s): ...
    def normalizer_sha256() -> str:
        return code_digest(normalize, consts={"_PUNCT": _PUNCT})

  Pass every module-level name the functions actually read. There is no way to discover
  that automatically that is worth trusting -- `__code__.co_names` misses closures and
  includes builtins -- so it is declared, and a missed constant is a real hole. The
  compensating control is that `code_digest` is used in exactly one shape everywhere,
  so a reviewer can check the argument list against the function body in one glance.
"""

from __future__ import annotations

import hashlib
import inspect
from typing import Any, Callable, Dict, Iterable, Union


def _stable(value: Any) -> str:
    """A repr that is stable across processes for the kinds of constant used here.

    `repr` of a compiled regex includes its pattern, which is what matters. Sets and
    dicts are sorted, because their repr order is not guaranteed to be stable across
    versions and a hash that changes without the code changing is worse than no hash.
    """
    import re as _re

    if isinstance(value, _re.Pattern):
        return f"re({value.pattern!r},{value.flags})"
    if isinstance(value, (set, frozenset)):
        return "{" + ",".join(sorted(_stable(v) for v in value)) + "}"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k!r}:{_stable(v)}" for k, v in sorted(value.items())) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable(v) for v in value) + "]"
    return repr(value)


def code_digest(*fns: Union[Callable, Iterable[Callable]],
                consts: Dict[str, Any] | None = None) -> str:
    """sha256 over the source of every function plus every declared constant.

    Functions are hashed in the order given and constants by sorted name, so the digest
    depends on the code and not on how the call was written.
    """
    flat: list = []
    for f in fns:
        if callable(f):
            flat.append(f)
        else:
            flat.extend(f)
    h = hashlib.sha256()
    for f in flat:
        h.update(inspect.getsource(f).encode())
        h.update(b"\x1e")
    for name in sorted(consts or {}):
        h.update(name.encode())
        h.update(b"\x00")
        h.update(_stable((consts or {})[name]).encode())
        h.update(b"\x1e")
    return h.hexdigest()
