#!/usr/bin/env python3
"""A dataset id is checked for its spelling where ids are made, and only for being a name where one is read (PLAN 0.8.2).

    python tests/test_read_ids.py

A project's data may hold ids no command here writes (accents, CJK, Cyrillic: tests/fixtures/shapes/unicode); a read of
one that exists is never refused for its spelling, while a path in place of a name still is, on a read as on a write.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["EVAL_HOME"] = tempfile.mkdtemp(prefix="evh-readids-")
from evaluation_harness import _common
from evaluation_harness._check import check, summary


def refused(fn, value) -> bool:
    try:
        fn(value)
    except SystemExit:
        return True
    return False


for ok in ("données_日本語_v1", "пункт_3", "tickets_v1", "a.b-c_d"):
    check(f"read: {ok!r} is a name", not refused(_common.dataset_id_read_ok, ok))
for bad in ("../x", "a/b", "a\\b", "..", "a..b", ".hidden", "", "a\0b", "/etc/passwd"):
    check(f"read: {bad!r} is not a name", refused(_common.dataset_id_read_ok, bad))
    check(f"write: {bad!r} stays refused", refused(_common.dataset_id_ok, bad))
for unicode_id in ("données_日本語_v1", "пункт_3", "été"):
    check(
        f"write: {unicode_id!r} stays refused where ids are made", refused(_common.dataset_id_ok, unicode_id)
    )
    check(
        f"write: {unicode_id!r} is refused by plain_id_ok too",
        refused(lambda v: _common.plain_id_ok(v, "--run"), unicode_id),
    )

sys.exit(summary())
