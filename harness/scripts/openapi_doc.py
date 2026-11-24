#!/usr/bin/env python3
"""evh openapi: the API's OpenAPI 3.1 description, made from the operations (ops/openapi.py)."""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import sys

from evaluation_harness.ops.openapi import main

if __name__ == "__main__":
    from evaluation_harness._console import degrade_unencodable

    degrade_unencodable()
    sys.exit(main())
