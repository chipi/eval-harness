#!/usr/bin/env python3
"""Audit every example's uv.lock for the platforms the examples run on. Report only.

    python examples/audit_locks.py          (make audit-locks)

A lock is universal: one line per platform fork, each with an environment marker, and pip-audit
evaluates those markers against the machine it runs on. This resolves the markers for each
platform below first and audits each set, so the result does not depend on where it runs.
Intel macOS is not audited: torch stops at 2.2.2 there, so its fork cannot be patched.
An advisory accepted on purpose is listed in ACCEPTED with the reason and printed as such.
Needs uv; exits 0 whatever it finds: upgrading a pin changes the instrument.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import Requirement

HERE = Path(__file__).resolve().parent
AUDIT = Path(sys.executable).parent / "pip-audit"
PY = {
    "python_version": "3.11",
    "python_full_version": "3.11.9",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
}
PLATFORMS = {
    "linux x86_64": {
        "sys_platform": "linux",
        "platform_machine": "x86_64",
        "os_name": "posix",
        "platform_system": "Linux",
    },
    "macOS arm64": {
        "sys_platform": "darwin",
        "platform_machine": "arm64",
        "os_name": "posix",
        "platform_system": "Darwin",
    },
}
#: (example, package): why its advisories are kept.
ACCEPTED = {
    ("ner-few-nerd", "transformers"): "span-marker has no transformers 5 release (see its pyproject)",
}


def pins_for(lines: list[str], env: dict) -> list[str]:
    """The `name==version` pins whose marker holds on this platform."""
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith(("#", "-")):
            continue
        req = Requirement(ln)
        if req.marker is None or Marker(str(req.marker)).evaluate({**PY, **env}):
            out.append(f"{req.name}{req.specifier}")
    return out


def audit(pins: list[str]) -> dict[str, int]:
    """{"name version": advisory count} for the vulnerable pins."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write("\n".join(pins) + "\n")
    r = subprocess.run(
        [str(AUDIT), "-r", fh.name, "--no-deps", "--disable-pip", "--progress-spinner", "off", "-f", "json"],
        capture_output=True,
        text=True,
    )
    Path(fh.name).unlink()
    deps = json.loads(r.stdout or "{}").get("dependencies", [])
    return {f"{d['name']} {d['version']}": len(d["vulns"]) for d in deps if d.get("vulns")}


def main() -> int:
    """Print each example's advisories per platform."""
    for lock in sorted(HERE.glob("*/uv.lock")):
        exported = subprocess.run(
            [
                "uv",
                "export",
                "--frozen",
                "--all-extras",
                "--no-hashes",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "-q",
            ],
            cwd=lock.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        for name, env in PLATFORMS.items():
            found = audit(pins_for(exported, env))
            shown = []
            for pin, n in found.items():
                why = ACCEPTED.get((lock.parent.name, pin.split()[0]))
                shown.append(f"{pin} ({n}, accepted: {why})" if why else f"{pin} ({n})")
            print(f"{lock.parent.name:30} {name:13} " + (", ".join(shown) or "clean"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
