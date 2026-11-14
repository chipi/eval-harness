"""Which arm of an eval a system id is, shared by `examples/reproduce.py` and `site/figures.py`.

A system serves every dataset of its example (RFC-032 step 3), so ids lost the dataset token: `cnn_bart_l_n200_v1`
is `cnn_bart_l_v1`, and `cnn_glm_l_v2` where the merge found two different systems. Ids no merge touched
(SummEval's `se_openai_l_n100_v1`) keep a size token. Which runs belong to an eval is decided by its dataset, not by
the id."""

from __future__ import annotations

import re

_TAIL = re.compile(r"(?:_n\d+|_dm\d+)?_v\d+$")
#: A size token inside the id (`se_gemma_l_n100_pairwise_v1`) marks a variant of an arm, not an arm.
_INNER = re.compile(r"_(?:n|dm)\d+_")


def arm_of(prefix: str, cid: str) -> str | None:
    """The arm name of system id `cid` in an eval whose arms start with `prefix`, or None when it is not an arm."""
    if not cid.startswith(prefix):
        return None
    rest = cid[len(prefix) :]
    stem = _TAIL.sub("", rest)
    if stem == rest or _INNER.search(stem + "_"):
        return None
    return stem
