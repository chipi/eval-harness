"""The command-line surface of an operation (RFC-032): its parser made from its inputs, its answer printed as text or,
with --json, as the envelope every command gives. The route's parts are positionals of a read or an edit; a property of
type object is KEY=VALUE pairs (the value read as YAML, as `data-put --set` reads it), an array is a repeatable option
(`x-nargs: "+"`: one option followed by its values), a boolean a flag. A write takes --by (who acted, RFC-027).

A decision or a work operation (a job, P3) takes everything as named options, the route's parts too (`evh round-close
--goal G --round r1 --conclusion ...`): a part is never a positional. Its options are the inputs' schema made argparse:
`default`, `enum` (choices), `x-short` (a short option), `x-metavar`, `x-nargs`, `exclusive` groups. What the schema
requires is required by argparse, except when the line has `--inputs-file FILE`, a hidden option that takes every input
from a JSON file (the way a job's supervisor starts the command): then the file is checked for them instead."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evaluation_harness.ops.registry import Op


def _flag(name: str) -> str:
    return f"--{name.replace('_', '-')}"


def parser(op: Op, strict: bool = True) -> argparse.ArgumentParser:
    """The command's parser, made from the operation. `strict` false: a job's required options are not required of the
    line (they come from its --inputs-file)."""
    job = op.is_job()
    ap = argparse.ArgumentParser(prog=f"evh {op.name}", description=op.about)
    if not job:
        for p in op.path_params():
            ap.add_argument(p, help=f"the {p}'s id")
    groups: dict[str, Any] = {}
    for names in op.exclusive:
        group = ap.add_mutually_exclusive_group()
        groups.update(dict.fromkeys(names, group))
    for name, spec in op.inputs.items():
        target = groups.get(name, ap)
        flags = [*([spec["x-short"]] if spec.get("x-short") else []), _flag(name)]
        help_ = spec.get("description", "")
        t = spec.get("type")
        kind = {"integer": int, "number": float}.get(t, str)
        metavar = spec.get("x-metavar")
        choices = spec.get("enum") if job else None
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
            target.add_argument(
                *flags,
                dest=name,
                action="append",
                default=[],
                metavar="KEY=VALUE",
                help=help_ + " (repeatable)",
            )
        elif t == "array" and spec.get("x-nargs") == "+":
            target.add_argument(
                *flags,
                dest=name,
                nargs="+",
                metavar=metavar,
                required=job and name in op.required and strict,
                help=help_,
            )
        elif t == "array":
            target.add_argument(
                *flags,
                dest=name,
                action="append",
                default=[],
                metavar=metavar or "KEY",
                required=job and name in op.required and strict,
                help=help_ + " (repeatable)",
            )
        elif t == "boolean":
            target.add_argument(*flags, dest=name, action="store_true", help=help_)
        else:
            target.add_argument(
                *flags,
                dest=name,
                type=kind,
                required=name in op.required and strict,
                default=spec.get("default") if job else None,
                choices=choices,
                metavar=metavar,
                help=help_,
            )
    if op.kind != "read":
        from evaluation_harness._actor import add_by  # noqa: PLC0415

        add_by(ap)
    if job:
        ap.add_argument("--inputs-file", dest="inputs_file", help=argparse.SUPPRESS)
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


def _inputs_file(op: Op, path: str) -> dict[str, Any]:
    """The inputs a job's supervisor wrote for the command: its defaults filled, nothing it does not take."""
    from evaluation_harness import _common, _store  # noqa: PLC0415

    try:
        given = json.loads(_store.read_text(Path(path)))
    except (OSError, ValueError) as exc:
        _common.die(f"--inputs-file {path}: {exc}", "bad-argument")
    if not isinstance(given, dict):
        _common.die(f"--inputs-file {path}: a JSON object keyed by the input's name", "bad-argument")
    unknown = sorted(set(given) - set(op.inputs))
    if unknown:
        _common.die(f"--inputs-file: not inputs of {op.name}: {', '.join(unknown)}", "bad-argument")
    inputs = op.with_defaults(given)
    missing = [k for k in op.required if k not in inputs]
    if missing:
        _common.die(f"--inputs-file: {op.name} needs {', '.join(missing)}", "bad-argument")
    return inputs


def _job_inputs(op: Op, ap: argparse.ArgumentParser, args: argparse.Namespace) -> dict[str, Any]:
    """A job's inputs from its options, or from its --inputs-file; what the schema requires, checked here."""
    given = {n: getattr(args, n) for n in op.inputs}
    if args.inputs_file:
        also = [_flag(n) for n, v in given.items() if v != ap.get_default(n)]
        if also:
            ap.error(f"--inputs-file takes every input from the file: not also {', '.join(also)}")
        return _inputs_file(op, args.inputs_file)
    inputs: dict[str, Any] = {}
    for name, spec in op.inputs.items():
        v = _pairs(given[name]) if spec.get("type") == "object" else given[name]
        if v not in (None, [], {}) or name in op.required:
            inputs[name] = v
    if op.one_of and not any(given[n] not in (None, [], {}, False) for n in op.one_of):
        ap.error(f"one of {', '.join(_flag(n) for n in op.one_of)} is needed")
    return inputs


def _run_job(op: Op, ap: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """A decision or a work operation as a command: its body prints (live on stderr under --json, so a job's log
    follows it) and answers the exit code; --json prints the envelope after."""
    from evaluation_harness import _common, _jsonout  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    inputs = _job_inputs(op, ap, args)
    try:
        with _jsonout.collect(op.name, args.json, live=sys.stderr):
            return op.body(**inputs)
    except Problem as exc:
        _common.die(str(exc), exc.kind)


def main(op: Op, argv: list[str] | None = None) -> int:
    """Run the operation as a command."""
    from evaluation_harness import _common, _outcome_join  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    line = _outcome_join.argv(argv)  # a window `--within -1m,+15m` is one value
    ap = parser(op, strict=not any(a == "--inputs-file" or a.startswith("--inputs-file=") for a in line))
    args = ap.parse_args(line)
    if op.is_job():
        return _run_job(op, ap, args)
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
