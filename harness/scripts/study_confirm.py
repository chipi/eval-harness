#!/usr/bin/env python3
"""evh study-confirm: see _study_cmd.py."""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import sys

from evaluation_harness._study_cmd import run

if __name__ == "__main__":
    sys.exit(run("confirm"))
