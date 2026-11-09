"""Who acted (RFC-027 D1): a person, or an agent and the person it acted for, on every record a command writes.

    evh run-promote --run R --reason "..." --by person:ana
    EVH_ACTOR=agent:fleet EVH_FOR=person:ana evh run --config c.yaml

The actor is a recorded claim, not an identity: `from` says where it came from (`flag`, `environment`, `terminal`,
`migration`). In order: a command's `--by` (`person:NAME`, `agent:NAME`, or a bare name, a person); else `EVH_ACTOR`,
with `EVH_FOR` required for an agent; else the operating-system user, a `person` when stdin is a terminal and
`unknown` when it is not (an agent's shell, a script, CI, a job). A decision (promote, roll back, close a round,
unseal) refuses an `unknown` actor.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Any

from evaluation_harness._common import die

TYPES = ("person", "agent")
_FLAG: list[str] = []  # the value of this process's --by, set by the option's action


class _By(argparse.Action):
    """`--by`: kept as the command's own value and as this process's actor."""

    def __call__(self, parser: Any, namespace: Any, values: Any, _option: Any = None) -> None:
        setattr(namespace, self.dest, values)
        _FLAG[:] = [str(values)]
        # The commands this one starts (sweep's runs, round-close's promotion) act for the same actor.
        if str(values).strip():
            kind, name = _parse(str(values), "--by")
            os.environ["EVH_ACTOR"] = f"{kind}:{name}"


def add_by(
    ap: argparse.ArgumentParser, help: str | None = None, required: bool = False, default: Any = None
) -> None:
    """Give a writing command `--by` (who acted): `person:NAME`, `agent:NAME` (with EVH_FOR), or a bare name."""
    ap.add_argument(
        "--by",
        action=_By,
        required=required,
        default=default,
        help=help
        or "who acted: person:NAME, or agent:NAME with EVH_FOR=person:NAME (default: EVH_ACTOR, else this "
        "terminal's user; with no terminal, unknown)",
    )


def _parse(text: str, where: str) -> tuple[str, str]:
    kind, sep, name = text.strip().partition(":")
    if not sep:
        return "person", text.strip()
    if kind not in TYPES or not name.strip():
        die(f"{where} {text!r}: person:NAME or agent:NAME", "bad-argument")
    return kind, name.strip()


def _os_user() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return "unknown"


def actor() -> dict[str, Any]:
    """This process's actor: {"type", "name", "for", "from"} (`for` only for an agent)."""
    flag = _FLAG[0] if _FLAG else None
    env = os.environ.get("EVH_ACTOR", "").strip()
    if flag:
        kind, name = _parse(flag, "--by")
        source = "flag"
    elif env:
        kind, name = _parse(env, "EVH_ACTOR")
        source = "environment"
    else:
        terminal = sys.stdin is not None and sys.stdin.isatty()
        return {"type": "person" if terminal else "unknown", "name": _os_user(), "from": "terminal"}
    out: dict[str, Any] = {"type": kind, "name": name, "from": source}
    if kind == "agent":
        whom = os.environ.get("EVH_FOR", "").strip()
        if not whom:
            die(
                f"an agent ({name}) acts for a person: set EVH_FOR=person:NAME (the operator who asked for this task)",
                "bad-argument",
            )
        k, n = _parse(whom, "EVH_FOR")
        if k != "person":
            die(f"EVH_FOR {whom!r}: an agent acts for a person (person:NAME)", "bad-argument")
        out["for"] = n
    return out


def require_named(what: str) -> dict[str, Any]:
    """The actor of a decision: refused when unknown (owner, 2026-11-09), saying how to name one."""
    a = actor()
    if a["type"] == "unknown":
        die(
            f"{what} is a decision and needs who made it: pass --by person:NAME, or set EVH_ACTOR=person:NAME (an "
            "agent: EVH_ACTOR=agent:NAME with EVH_FOR=person:NAME, the operator who asked). With no terminal the "
            f"harness cannot tell who you are (it saw {a['name']!r}).",
            "not-allowed",
        )
    return a
