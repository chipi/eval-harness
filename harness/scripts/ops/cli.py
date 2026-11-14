"""The command-line surface of an operation (RFC-032): its parser made from its inputs, its answer printed as text or,
with --json, as the envelope every command gives. The route's parts are positionals; a property of type object is
KEY=VALUE pairs (the value read as YAML, as `data-put --set` reads it), an array is a repeatable option, a boolean a
flag. A write takes --by (who acted, RFC-027)."""

from __future__ import annotations

import argparse
import json
from typing import Any

from evaluation_harness.ops.registry import Op


def parser(op: Op) -> argparse.ArgumentParser:
    """The command's parser, made from the operation."""
    ap = argparse.ArgumentParser(prog=f"evh {op.name}", description=op.about)
    for p in op.path_params():
        ap.add_argument(p, help=f"the {p}'s id")
    for name, spec in op.inputs.items():
        flag = f"--{name.replace('_', '-')}"
        help_ = spec.get("description", "")
        t = spec.get("type")
        if t == "object":
            ap.add_argument(
                flag, action="append", default=[], metavar="KEY=VALUE", help=help_ + " (repeatable)"
            )
        elif t == "array":
            ap.add_argument(flag, action="append", default=[], metavar="KEY", help=help_ + " (repeatable)")
        elif t == "boolean":
            ap.add_argument(flag, action="store_true", help=help_)
        else:
            ap.add_argument(
                flag, type=int if t == "integer" else str, required=name in op.required, help=help_
            )
    if op.kind != "read":
        from evaluation_harness._actor import add_by  # noqa: PLC0415

        add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="the answer as one JSON object (the envelope every --json command gives)",
    )
    return ap


def _pairs(items: list[str]) -> dict[str, Any]:
    import yaml  # noqa: PLC0415
    from evaluation_harness import _common, _settings_form  # noqa: PLC0415

    out: dict[str, Any] = {}
    for raw in items:
        key, sep, value = raw.partition("=")
        if not sep or not key.strip():
            _common.die(f"{raw!r}: KEY=VALUE", "bad-argument")
        try:
            out[key.strip()] = _settings_form.plain(yaml.safe_load(value)) if value.strip() else ""
        except yaml.YAMLError:
            out[key.strip()] = value
    return out


def main(op: Op, argv: list[str] | None = None) -> int:
    """Run the operation as a command."""
    from evaluation_harness import _common  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    args = parser(op).parse_args(argv)
    kwargs: dict[str, Any] = {p: getattr(args, p) for p in op.path_params()}
    for name, spec in op.inputs.items():
        v = getattr(args, name.replace("-", "_"))
        if spec.get("type") == "object":
            v = _pairs(v)
        if v not in (None, [], {}) or name in op.required:
            kwargs[name] = v
    if op.kind != "read":
        from evaluation_harness import _actor  # noqa: PLC0415

        a = _actor.actor()
        kwargs["by"] = f"{a['type']}:{a['name']}"
    try:
        result = op.call(**kwargs)
    except Problem as exc:
        _common.die(str(exc), exc.kind)
    if args.json:
        print(json.dumps({"command": op.name, "version": __version__, "result": result}, ensure_ascii=False))
    else:
        print(op.say(result))
    return 0
