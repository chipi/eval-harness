#!/usr/bin/env python3
"""A dataset id is checked for its spelling where ids are made, and only for being a name where one is read (PLAN 0.8.2).

    python tests/test_read_ids.py

A read of an id that exists is never refused for its spelling (accents, CJK, Cyrillic: tests/fixtures/shapes/unicode), while
a path in place of a name still is, on a read as on a write. A writer takes the same spellings (owner, 2026-11-26): letters
and digits of any script under `_ids`' rule; it refuses a spelling that is not Unicode NFC (naming the NFC form), a control or
format character, a space and anything path-like. The rule's table and its use in the stores are tests/test_unicode_ids.py.
"""

import os
import sys
import tempfile
import unicodedata
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
for unicode_id in ("données_日本語_v1", "пункт_3", "été", "ПУНКТ_3", "٣٤"):
    check(
        f"write: {unicode_id!r} is accepted by dataset_id_ok", not refused(_common.dataset_id_ok, unicode_id)
    )
    check(
        f"write: {unicode_id!r} is accepted by plain_id_ok",
        not refused(lambda v: _common.plain_id_ok(v, "--run"), unicode_id),
    )
nfd = unicodedata.normalize("NFD", "été")
for bad in (
    nfd,
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
        fn(nfd)
    except SystemExit as e:
        check(f"{name} names the NFC form of a non-NFC id", "NFC" in str(e) and "'été'" in str(e), str(e))

sys.exit(summary())
