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
        kind = {"integer": int, "number": float}.get(t, str)
        if name in op.positional:
            many = t == "array"
            ap.add_argument(
                name,
                nargs=("+" if name in op.required else "*")
                if many
                else (None if name in op.required else "?"),
                type=kind if not many else str,
                choices=spec.get("enum"),
                help=help_,
            )
        elif t == "array" and spec.get("items", {}).get("type") == "object":
            from evaluation_harness import _outcome_join  # noqa: PLC0415

            _outcome_join.add_arguments(ap)  # --outcomes CAPTURE, each with the options after it
        elif t == "object":
            ap.add_argument(
                flag, action="append", default=[], metavar="KEY=VALUE", help=help_ + " (repeatable)"
            )
        elif t == "array":
            ap.add_argument(flag, action="append", default=[], metavar="KEY", help=help_ + " (repeatable)")
        elif t == "boolean":
            ap.add_argument(flag, action="store_true", help=help_)
        else:
            ap.add_argument(flag, type=kind, required=name in op.required, help=help_)
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
    from evaluation_harness import _common, _outcome_join  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    args = parser(op).parse_args(_outcome_join.argv(argv))  # a window `--within -1m,+15m` is one value
    kwargs: dict[str, Any] = {p: getattr(args, p) for p in op.path_params()}
    for name, spec in op.inputs.items():
        v = getattr(args, name.replace("-", "_"))
        if spec.get("type") == "array" and spec.get("items", {}).get("type") == "object":
            v = _outcome_join.outcomes_from_argv(argv)
        elif spec.get("type") == "object":
            v = _pairs(v)
        if v not in (None, [], {}) or name in op.required:
            kwargs[name] = v
    if op.kind != "read":
        from evaluation_harness import _actor  # noqa: PLC0415

        a = _actor.actor()
        kwargs["by"] = f"{a['type']}:{a['name']}"
    try:
        if op.printer and not args.json:
            return op.print_text(**kwargs)
        result = op.call(**kwargs)
    except Problem as exc:
        _common.die(str(exc), exc.kind)
    if args.json:
        print(json.dumps({"command": op.name, "version": __version__, "result": result}, ensure_ascii=False))
    else:
        print(op.say(result))
    return op.exit_code(result)
