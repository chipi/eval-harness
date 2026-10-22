"""The package as `pip install` lays it out, for the tests that run the installed tool.

Tests of `evh` used to copy scripts/, schemas/ and the rest into a fake site-packages. A copy
takes every file in those folders, so a file that pyproject.toml's package-data leaves out
(a new schema, a new tutorial file) would pass every test and be missing from what users get.
This builds the real wheel from pyproject.toml and installs it, without its dependencies (the
interpreter running the test has them), into a directory the test puts on PYTHONPATH.

The build runs on a copy of the packaging inputs in a temporary directory, never in the
checkout, so it leaves no build/ or *.egg-info behind and two tests can build at once.
"""

from __future__ import annotations

import atexit
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent
#: What pyproject.toml builds the package from.
INPUTS = ("pyproject.toml", "README.md", "scripts", "schemas", "catalog_assets", "tutorial")
_BUILT: dict = {}


def wheel() -> Path:
    """The wheel built from this checkout, once per process."""
    if "path" in _BUILT:
        return _BUILT["path"]
    src = Path(tempfile.mkdtemp(prefix="evh-wheel-src-"))
    out = Path(tempfile.mkdtemp(prefix="evh-wheel-"))
    atexit.register(shutil.rmtree, out, True)
    try:
        for name in INPUTS:
            p = HARNESS / name
            if p.is_dir():
                shutil.copytree(p, src / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy(p, src / name)
        base = [sys.executable, "-m", "pip", "wheel", "-q", "--no-deps", "-w", str(out), str(src)]
        # Offline first, with the setuptools already installed; an isolated build fetches it.
        r = subprocess.run(base[:4] + ["--no-build-isolation"] + base[4:], capture_output=True, text=True)
        if r.returncode:
            r = subprocess.run(base, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"building the wheel failed:\n{r.stdout}{r.stderr}")
    finally:
        shutil.rmtree(src, ignore_errors=True)
    _BUILT["path"] = next(out.glob("*.whl"))
    return _BUILT["path"]


def install(target: Path) -> Path:
    """Install the wheel into `target` (a site-packages for PYTHONPATH) and return it."""
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--no-index",
                        "--target", str(target), str(wheel())], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"installing the wheel failed:\n{r.stdout}{r.stderr}")
    return target
