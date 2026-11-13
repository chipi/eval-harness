"""The numbered steps that bring a project's data from one format to the next (RFC-032).

Each module `mNNNN_<what>.py` moves the data from format NNNN-1 to NNNN and has:

- `NUMBER`: the format it brings the data to; `ABOUT`: one line for `evh migrate` and UPGRADING.md;
- `run(dry_run)`: what it changes, printed, and written unless `dry_run`.

A step works on the stored data, never through the current model's code, which moves on after it is written: a project
of any released format reaches the current one through every step in between. Steps are kept from 0.8.0 on.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType


def steps() -> list[ModuleType]:
    """Every step, in its number's order; their numbers run 1, 2, … without a gap."""
    mods = [
        importlib.import_module(f"{__name__}.{m.name}")
        for m in pkgutil.iter_modules(__path__)
        if m.name.startswith("m") and m.name[1:5].isdigit()
    ]
    mods.sort(key=lambda m: m.NUMBER)
    numbers = [m.NUMBER for m in mods]
    if numbers != list(range(1, len(mods) + 1)):
        raise RuntimeError(f"migration steps must be numbered 1..n without a gap: {numbers}")
    return mods
