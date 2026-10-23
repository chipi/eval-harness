"""Import a file as a module: what each example's calibrate.py and human_ceiling.py did by hand.

from modules import load_module
adapter = load_module(HERE / "adapter.py", "ag_adapter")
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def load_module(path: Path, name: str, reuse: bool = False) -> Any:
    """The file at `path` as module `name`, registered in sys.modules before it runs (a
    module-level @dataclass looks itself up there). With `reuse`, a module already loaded under
    that name is returned as it is."""
    if reuse and name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
