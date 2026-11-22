"""A test's temporary folders: made under one root, removed when the test's process ends.

    import _tmp
    proj = Path(_tmp.mkdtemp(prefix="evh-mine-"))

`tempfile.mkdtemp`'s twin (it returns the path as a string), with the folder removed at exit, whatever the test
did: 16 test files made folders they never removed, and 1,485 of them filled the machine's shared /tmp (2026-11-19).
The root is TMPDIR when it is set. tools/store_matrix.py gives each test file a TMPDIR of its own under
~/.cache/evh-tests; the self-test points its own at `root()` there: on the main disk, outside /tmp and outside any git
repository, since a project made inside a worktree reads as git-ignored to the tests that ask git.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path


def root() -> Path:
    """Where the self-test points TMPDIR when the caller has not: ~/.cache/evh-tests/tmp, beside the folders
    store_matrix makes. Made if missing."""
    base = Path.home() / ".cache" / "evh-tests" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    return base


def use_root() -> None:
    """Point this process's temporary folders, and its children's, at `root()`, unless TMPDIR is already set."""
    if not os.environ.get("TMPDIR"):
        os.environ["TMPDIR"] = str(root())
        tempfile.tempdir = None  # gettempdir reads TMPDIR again


def mkdtemp(prefix: str = "evh-", suffix: str = "") -> str:
    """A new folder (tempfile.mkdtemp), removed when this process exits."""
    path = tempfile.mkdtemp(prefix=prefix, suffix=suffix)
    atexit.register(shutil.rmtree, path, True)
    return path
