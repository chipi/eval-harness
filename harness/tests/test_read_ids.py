#!/usr/bin/env python3
"""A dataset id is checked for its spelling where ids are made, and only for being a name where one is read (PLAN 0.8.2).

    python tests/test_read_ids.py

A read of an id that exists is never refused for its spelling (a 0.8.2 project may hold accents, CJK or Cyrillic), while a
path in place of a name still is, on a read as on a write. A writer takes ASCII letters and digits under `_ids`' rule and
refuses any other letter, a control character, a space and anything path-like, naming the rule. The rule's table and its
schemas are tests/test_ascii_ids.py.
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
for ascii_id in ("tickets_v1", "a.b-c_d", "Tickets_V1", "9"):
    check(f"write: {ascii_id!r} is accepted by dataset_id_ok", not refused(_common.dataset_id_ok, ascii_id))
    check(
        f"write: {ascii_id!r} is accepted by plain_id_ok",
        not refused(lambda v: _common.plain_id_ok(v, "--run"), ascii_id),
    )
for bad in (
    "données_日本語_v1",
    "пункт_3",
    "été",
    "e\u0301te",
    "٣٤",
    "a b",
    "a\u00a0b",
    "a\u200bb",
    "a\u202eb",
    "a\tb",
    "a\x07b",
    "é/x",
    "é\\x",
    "é..x",
    "-é",
    "_é",
):
    check(f"write: {bad!r} is refused by dataset_id_ok", refused(_common.dataset_id_ok, bad))
    check(
        f"write: {bad!r} is refused by plain_id_ok", refused(lambda v: _common.plain_id_ok(v, "--run"), bad)
    )
for fn, name in (
    (_common.dataset_id_ok, "dataset_id_ok"),
    (lambda v: _common.plain_id_ok(v, "--run"), "plain_id_ok"),
):
    try:
        fn("été")
    except SystemExit as e:
        check(f"{name} names the ASCII rule for a non-ASCII id", "ASCII" in str(e), str(e))

sys.exit(summary())
