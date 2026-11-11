"""Import a system's modules from one version's copy (RFC-030), for a replay adapter.

    from evaluation_harness import _codeload
    filing, = _codeload.use(Path(params["code"]["path"]) / "mvp", ["filing"]).values()

Every module loaded from another version's copy (anything under `.build/code/` outside this commit's copy, its
subpackages included) is dropped first, with its folder taken off `sys.path`, so the import is this commit's.
Module-level state does not survive a switch: what a system keeps across items lives in files or in the adapter.
A copy whose loaded modules include a C extension is refused at the switch: an extension cannot be unloaded.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import importlib
import sys
from pathlib import Path
from typing import Any

from evaluation_harness import _common

EXTENSIONS = (".so", ".pyd", ".dylib")


def copies_root() -> Path:
    """.build/code/: every code record's copies."""
    return (_common.ROOT / ".build" / "code").resolve()


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def version_of(path: Path) -> Path | None:
    """The commit copy (.build/code/<model_id>/<commit>) a path lies in, or None."""
    root = copies_root()
    p = Path(path).resolve()
    if not _under(p, root):
        return None
    parts = p.relative_to(root).parts
    return root / parts[0] / parts[1] if len(parts) >= 2 else None


def drop_others(keep: Path | None) -> list[str]:
    """Forget every module loaded from a copy other than `keep` (a commit copy), and take those folders off sys.path.
    Returns the module names dropped. Dies when one is a C extension."""
    root = copies_root()
    dropped = []
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None)
        if not f:
            continue
        fp = Path(f).resolve()
        if not _under(fp, root) or (keep is not None and _under(fp, keep)):
            continue
        if fp.suffix in EXTENSIONS:
            _common.die(
                f"replay: {name} ({fp}) is a compiled extension and cannot be unloaded to switch versions; a replay "
                "runs pure-Python systems only",
                "not-allowed",
            )
        del sys.modules[name]
        dropped.append(name)
    sys.path[:] = [
        x
        for x in sys.path
        if not (
            x and _under(Path(x).resolve(), root) and (keep is None or not _under(Path(x).resolve(), keep))
        )
    ]
    importlib.invalidate_caches()
    return dropped


def use(path: Path, modules: list[str]) -> dict[str, Any]:
    """{name: module} for `modules`, imported from `path` (a folder inside one commit's copy)."""
    p = Path(path).resolve()
    keep = version_of(p)
    if keep is None:
        _common.die(f"replay: {p} is not inside a commit's copy under {copies_root()}", "bad-argument")
    drop_others(keep)
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    return {m: importlib.import_module(m) for m in modules}
