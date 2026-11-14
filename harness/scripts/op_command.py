#!/usr/bin/env python3
"""`evh <command>` for a command made from an operation of the model (RFC-032): which one is EVH_COMMAND, set by evh."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import os
import sys

from evaluation_harness import ops
from evaluation_harness.ops import cli


def main() -> int:
    """Run the operation evh named."""
    op = ops.get(os.environ.get("EVH_COMMAND", ""))
    if op is None:
        print(
            "op_command.py runs through evh <command>, which names the operation (EVH_COMMAND)",
            file=sys.stderr,
        )
        return 2
    return cli.main(op)


if __name__ == "__main__":
    raise SystemExit(main())
