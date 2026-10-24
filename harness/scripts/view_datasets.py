#!/usr/bin/env python3
"""evh datasets: see catalog_views.py."""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import sys

from evaluation_harness.catalog_views import run

if __name__ == "__main__":
    sys.exit(run("datasets"))
