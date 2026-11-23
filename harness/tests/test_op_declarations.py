#!/usr/bin/env python3
"""What a decision or a work operation declares, and the command line made from it (RFC-032 step 9 P3, step 1).

    python tests/test_op_declarations.py

Every operation that runs as a job declares its locks, a route that is a POST, its why (a decision's reason is a required
input, unless it has none), parts that fill required inputs, and a word on every input that names a file: it is an upload,
an artifact, or only the command line's; a text that offers `path.py:Class` or `@file` has a pattern. No two routes can
match one request. Each rule is shown to fail on an operation planted with exactly that defect. The command line: the
route's parts are named required options, a positional is refused, `--inputs-file` takes every input from a file, and what
the schema says (defaults, choices, a short option, nargs, an exclusive group, a metavar) is what argparse does.
"""

import ast
import contextlib
import io
import json
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _job_ops
import _job_ops
from evaluation_harness import _jsonout
from evaluation_harness._check import check, summary
from evaluation_harness.ops import OPS, cli, locks
from evaluation_harness.ops.declarations import problems, route_overlaps

JOBS = [op for op in OPS.values() if op.is_job()]
by_name = {op.name: op for op in JOBS}
check(
    "the two pilots are operations that run as jobs: cost-report (work) and round-close (decision)",
    by_name.get("cost-report") is not None
    and by_name["cost-report"].kind == "work"
    and by_name.get("round-close") is not None
    and by_name["round-close"].kind == "decision",
    sorted(by_name),
)
bad = {op.name: problems(op) for op in JOBS if problems(op)}
check("every decision and work operation is declared as a job must be", not bad, bad)
check(
    "no two routes can match one request (same method, same shape, a placeholder on either side)",
    not route_overlaps(list(OPS.values())),
    route_overlaps(list(OPS.values())),
)
check(
    "the synthetic operations of these tests are declared as well (a feature each pilot lacks)",
    all(not problems(op) for op in _job_ops.ALL),
    {op.name: problems(op) for op in _job_ops.ALL if problems(op)},
)

# ── each rule fails on the defect it guards ────────────────────────────────────────────────────────────────────────
close, report = by_name["round-close"], by_name["cost-report"]


def inputs_plus(op, **extra):
    return replace(op, inputs={**op.inputs, **extra})


def says(op, needle: str) -> bool:
    return any(needle in p for p in problems(op))


mutants = {
    "locks never declared": (replace(close, locks=None, locks_fn=""), "locks: not declared"),
    "a lock template naming an input there is not": (
        replace(close, locks=(("goal:{nope}", True),)),
        "which is not an input",
    ),
    "a method other than POST": (replace(report, method="PUT"), "a job is started by POST"),
    "no route": (replace(report, route=""), "a job needs a resource route"),
    "a decision with no why": (replace(close, why=""), "names the required input that is its reason"),
    "a why that is not an input": (replace(close, why="nope"), "a decision's reason is a required input"),
    "a why that is optional": (
        replace(close, required=("goal", "round")),
        "a decision's reason is a required input",
    ),
    "a part that fills an optional input": (
        replace(close, required=("goal", "conclusion")),
        "which is not required",
    ),
    "a part that fills no input": (
        replace(close, route="/goals/{goal}/rounds/{nope}/close"),
        "is not an input",
    ),
    "a positional on a job": (replace(close, positional=("goal",)), "named options only"),
    "an input named like a file with no word on it": (
        inputs_plus(report, scorer_file={"type": "string"}),
        "say how a call carries it",
    ),
    "an input named out": (inputs_plus(report, out={"type": "string"}), "say how a call carries it"),
    "a path-format input": (
        inputs_plus(report, where={"type": "string", "format": "path"}),
        "say how a call carries it",
    ),
    "an x-file that is not upload or artifact": (
        inputs_plus(report, sheet={"type": "string", "x-file": "path"}),
        "one of upload, artifact",
    ),
    "an x-ref that is not a system": (inputs_plus(report, who={"type": "string", "x-ref": "model"}), "x-ref"),
    "a text that offers path.py:Class with no pattern": (
        inputs_plus(report, importer={"type": "string", "description": "a name or path.py:Class"}),
        "has no pattern",
    ),
    "a text that offers @file with no pattern": (
        inputs_plus(report, query={"type": "string", "description": "JSON, or @file"}),
        "has no pattern",
    ),
    "by as an input": (inputs_plus(report, by={"type": "string"}), "never an input"),
    "an input named like what the call itself carries (for: who an agent acts for)": (
        inputs_plus(report, **{"for": {"type": "array", "items": {"type": "string"}}}),
        "never an input",
    ),
    "an x-flag that is no option": (
        inputs_plus(report, targets={"type": "string", "x-flag": "for"}),
        "an option, --like-this",
    ),
    "a boolean that defaults to true": (
        inputs_plus(report, flag={"type": "boolean", "default": True}),
        "only turns on",
    ),
    "a run that cannot be loaded": (replace(report, run="evaluation_harness.nope:body"), "cannot be loaded"),
}
for what, (mutant, needle) in mutants.items():
    got = problems(mutant)
    check(f"the declaration test fails on {what}", says(mutant, needle), got)

# a defect no mutant above names must still pass: a hidden input, and an upload, are the allowed ways.
check(
    "an input that names a file passes when it is an upload, an artifact or only the command line's",
    not problems(inputs_plus(report, sheet={"type": "string", "x-file": "upload"}))
    and not problems(inputs_plus(report, out={"type": "string", "x-file": "artifact"}))
    and not problems(replace(inputs_plus(report, source_dir={"type": "string"}), tool_hidden=("source_dir",)))
    and not problems(
        inputs_plus(
            report, importer={"type": "string", "pattern": "^[a-z]+$", "description": "a name, not path.py:C"}
        )
    ),
)

twin = replace(close, name="round-close-twin", route="/goals/{g}/rounds/{r}/close")
get_twin = replace(twin, method="GET")
check(
    "the route-collision test fails on a second route that differs only in its placeholders' names",
    bool(route_overlaps([close, twin])) and not route_overlaps([close, get_twin]),
    route_overlaps([close, twin]),
)
literal = replace(close, name="round-close-lit", route="/goals/{goal}/rounds/r1/close")
check(
    "and on a route that a placeholder would swallow (a literal where the other has a part)",
    bool(route_overlaps([close, literal])),
)
check(
    "a route that differs in a word does not collide, nor does the same path under another method",
    not route_overlaps([close, replace(close, name="x", route="/goals/{goal}/rounds/{round}/open")])
    and not route_overlaps([close, replace(close, name="x", method="PATCH")]),
)

# ── the MCP server's own list of what is no tool ───────────────────────────────────────────────────────────────────────


def manual_not_tools(source: str) -> set[str]:
    """The names in mcp_server.py's hand-written NOT_TOOLS dictionary (what `NOT_TOOLS.update` adds from the operations
    is not in it)."""
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", "") == "NOT_TOOLS" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            return {str(k.value) for k in node.value.keys if isinstance(k, ast.Constant)}
    raise AssertionError("no NOT_TOOLS dictionary in mcp_server.py")


mcp_source = (Path(__file__).resolve().parents[1] / "scripts" / "mcp_server.py").read_text(encoding="utf-8")
check(
    "the MCP server's hand-written NOT_TOOLS names no operation (an operation is a tool, or not one, by its kind)",
    not manual_not_tools(mcp_source) & set(OPS),
    sorted(manual_not_tools(mcp_source) & set(OPS)),
)
planted_source = mcp_source.replace("NOT_TOOLS = {\n", 'NOT_TOOLS = {\n    "round-close": "a decision",\n', 1)
check(
    "that check fails on a hand-written entry for an operation",
    manual_not_tools(planted_source) & set(OPS) == {"round-close"},
)

# ── the lock function ──────────────────────────────────────────────────────────────────────────────────────────────
sp = _job_ops.SPEND
held = dict(locks.locks_for(sp, {"system": "s1", "dataset": "d1"}))
check(
    "locks: a template's inputs fill its key, exclusive or shared, the function adds its own, `project` is shared",
    held == {"system:s1": True, "dataset:d1": False, "extra:s1": True, "project": False},
    held,
)
held = dict(locks.locks_for(sp, {"system": "s1"}))
check(
    "locks: a template whose input the call does not give is left out",
    "dataset:d1" not in held and held.get("system:s1") is True and "dataset:None" not in held,
    held,
)
check(
    "locks: a list stands for its first value, the keys come sorted",
    [k for k, _ex in locks.locks_for(sp, {"system": ["s2", "s1"], "dataset": ""})]
    == ["extra:['s2', 's1']", "project", "system:s2"],
    locks.locks_for(sp, {"system": ["s2", "s1"], "dataset": ""}),
)
check(
    "locks: a migration holds the whole project exclusive; a job that writes nothing holds the project shared",
    locks.locks_for(_job_ops.MIGRATE, {}) == [("project", True)]
    and locks.locks_for(_job_ops.PLAIN, {}) == [("project", False)]
    and locks.locks_for(report, {"dataset_id": "d"}) == [("project", False)],
)
check(
    "locks: round-close holds its goal exclusive, whatever the round",
    locks.locks_for(close, {"goal": "g", "round": "r1", "conclusion": "a b c"})
    == [("goal:g", True), ("project", False)],
    locks.locks_for(close, {"goal": "g", "round": "r1", "conclusion": "a b c"}),
)
# the locks mutant: a template that forgets `exclusive` is caught by a pair of jobs that would then run together.
shared = replace(close, locks=(("goal:{goal}", False),))
check(
    "locks: the check on round-close's exclusivity fails on a lock declared shared",
    locks.locks_for(shared, {"goal": "g"}) != [("goal:g", True), ("project", False)],
)

# ── the route's parts ──────────────────────────────────────────────────────────────────────────────────────────────
check(
    "a route's body is the inputs its parts do not fill; the job schema has them all",
    set(close.schema()["properties"])
    == {"conclusion", "promote", "confirm_extra_look", "override_no_evidence"}
    and set(close.job_schema()["properties"]) == set(close.inputs)
    and set(close.schema()["required"]) == {"conclusion"},
    (close.schema()["properties"].keys(), close.schema()["required"]),
)
check(
    "a part is mapped to an input, by name by default, by `parts` otherwise, built by parts_fn when it is composite",
    close.route_inputs({"goal": "g", "round": "r1"}) == {"goal": "g", "round": "r1"}
    and replace(close, parts={"goal": "goal", "round": "round"}).part_inputs()
    == {"goal": "goal", "round": "round"}
    and _job_ops.DECIDE.route_inputs({"goal": "g", "study": "s"}) == {"study": "g/s"},
)
check(
    "a part mapped to another input: the body is the inputs left over",
    replace(
        close,
        parts={"goal": "goal", "round": "round"},
        inputs={**close.inputs, "round_id": {"type": "string"}},
    )
    .schema()["properties"]
    .keys()
    == {"conclusion", "promote", "confirm_extra_look", "override_no_evidence", "round_id"},
)

# ── the command line ───────────────────────────────────────────────────────────────────────────────────────────────


def parse(op, *argv, strict: bool = True):
    """(namespace, None) or (None, the exit code and what argparse said) of an op's parser on this line."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            return cli.parser(op, strict).parse_args(list(argv)), None
        except SystemExit as exc:
            return None, (exc.code, err.getvalue())


ns, _ = parse(close, "--goal", "g", "--round", "r1", "--conclusion", "it showed three things")
check(
    "evh round-close takes its route's parts as named options",
    ns is not None and (ns.goal, ns.round, ns.conclusion) == ("g", "r1", "it showed three things"),
)
ns, err = parse(close, "g", "r1", "--conclusion", "it showed three things")
check(
    "the positional form (evh round-close G r1 ...) is refused, as a missing option and not read as the parts",
    ns is None and err and err[0] == 2 and "--goal" in err[1],
    err,
)
ns, err = parse(close, "G", "--goal", "g", "--round", "r1", "--conclusion", "a b c")
check(
    "and a positional beside the named options is refused as unrecognized",
    ns is None and err and err[0] == 2 and "unrecognized arguments: G" in err[1],
    err,
)
as_read = replace(
    close,
    kind="edit",
    inputs={k: v for k, v in close.inputs.items() if k not in ("goal", "round")},
    required=("conclusion",),
)
ns, _ = parse(as_read, "g", "r1", "--conclusion", "a b c")
check(
    "the same line is accepted by a read or an edit's parser, which takes its parts as positionals: "
    "so the refusal above is the job parser's, not argparse's in general",
    ns is not None and (ns.goal, ns.round) == ("g", "r1"),
)
ns, err = parse(close, "--goal", "g", "--round", "r1")
check(
    "a missing required option is refused (exit 2)",
    ns is None and err[0] == 2 and "--conclusion" in err[1],
    err,
)
ns, err = parse(close, "--inputs-file", "/x/inputs.json")
ns2, _ = parse(close, "--inputs-file", "/x/inputs.json", strict=False)
check(
    "--inputs-file: a job's parser takes it, hidden from the help; main parses a line that has it with the other options "
    "not required, since the file gives them",
    "--inputs-file" not in cli.parser(close).format_help()
    and err is not None
    and ns2 is not None
    and ns2.inputs_file == "/x/inputs.json",
    (err, ns2),
)
a_read = next(o for o in OPS.values() if o.kind == "read" and not o.required and not o.positional)
ns, err = parse(a_read, *["x"] * len(a_read.path_params()), "--inputs-file", "f")
check(
    "a read has no --inputs-file",
    ns is None and err and "unrecognized arguments" in err[1],
    (a_read.name, err),
)

ns, _ = parse(OPS["pick"], "--dataset-id", "d", "--item", "i", "--for", "x", "--for", "y")
check(
    "x-flag: pick's option --for is the input `targets` (the call's own `for` is who an agent acts for)",
    ns is not None
    and ns.targets == ["x", "y"]
    and "for" not in OPS["pick"].inputs
    and "targets" in OPS["pick"].inputs,
    ns,
)
ns, err = parse(
    replace(
        OPS["pick"],
        inputs={**OPS["pick"].inputs, "targets": {**OPS["pick"].inputs["targets"], "x-flag": None}},
    ),
    "--dataset-id",
    "d",
    "--item",
    "i",
    "--for",
    "x",
)
check(
    "and without it the option is --targets: --for is refused",
    ns is None and err is not None and err[0] == 2,
    err,
)

# the schema made argparse
spend = _job_ops.SPEND
ns, _ = parse(spend, "--system", "s1")
check(
    "a default in the schema is argparse's default (and a boolean flag is off, a list empty)",
    ns is not None and ns.repeat == 1 and ns.kind is None,
    vars(ns) if ns else None,
)
ns, err = parse(spend, "--system", "s1", "--kind", "z")
check("an enum is argparse's choices", ns is None and err[0] == 2 and "invalid choice" in err[1], err)
ns, err = parse(spend, "--system", "s1", "--name", "x", "--kind", "a")
check("an exclusive group: two of its members are refused", ns is None and "not allowed with" in err[1], err)
ns, _ = parse(spend, "--system", "s1", "--name", "x")
check("and one of them is accepted", ns is not None and ns.name == "x")
nargs_op = replace(
    _job_ops.PLAIN,
    inputs={
        "systems": {"type": "array", "items": {"type": "string"}, "x-nargs": "+"},
        "tag": {"type": "array", "items": {"type": "string"}, "x-metavar": "TAG"},
        "from": {"type": "string", "x-short": "-f", "x-metavar": "DATASET_ID"},
    },
    required=("systems",),
)
ns, _ = parse(nargs_op, "--systems", "a", "b", "c", "--tag", "x", "--tag", "y", "-f", "d1")
check(
    "x-nargs '+' is one option and its values, an array without it is repeatable, x-short a short option, "
    "an input named `from` is its own destination",
    ns is not None and ns.systems == ["a", "b", "c"] and ns.tag == ["x", "y"] and getattr(ns, "from") == "d1",
    vars(ns) if ns else None,
)
no_plus = replace(
    nargs_op, inputs={**nargs_op.inputs, "systems": {"type": "array", "items": {"type": "string"}}}
)
ns, err = parse(no_plus, "--systems", "a", "b", "c")
check(
    "without x-nargs the same line is refused: the three values would not be one option's (the feature is what parses it)",
    ns is None and "unrecognized arguments" in err[1],
    err,
)
check(
    "an x-metavar is the help's metavar",
    "-f DATASET_ID" in cli.parser(nargs_op).format_help()
    and "--tag TAG" in cli.parser(nargs_op).format_help(),
)
ns, err = parse(nargs_op, "--tag", "x")
check("a required array is required", ns is None and "--systems" in err[1], err)

# ── what the supervisor starts a job's command with ────────────────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmp:
    f = Path(tmp) / "inputs.json"
    f.write_text(
        json.dumps({"goal": "g", "round": "r1", "conclusion": "three whole words"}), encoding="utf-8"
    )
    ok = cli._inputs_file(close, str(f))
    g = Path(tmp) / "s.json"
    g.write_text(json.dumps({"system": "s"}), encoding="utf-8")
    check(
        "--inputs-file: the inputs of the file, the schema's defaults filled",
        ok == {"goal": "g", "round": "r1", "conclusion": "three whole words"}
        and cli._inputs_file(_job_ops.SPEND, str(g)) == {"system": "s", "repeat": 1},
        ok,
    )
    refusals: dict[str, str | None] = {}
    for what, doc in {
        "an input the operation does not take": {
            "goal": "g",
            "round": "r",
            "conclusion": "a b c",
            "adapter": "x",
        },
        "a required input missing": {"goal": "g", "round": "r"},
        "not a JSON object": ["g"],
    }.items():
        f.write_text(json.dumps(doc), encoding="utf-8")
        try:
            cli._inputs_file(close, str(f))
            refusals[what] = None
        except SystemExit as exc:
            refusals[what] = str(exc)
    f.write_text("{not json", encoding="utf-8")
    try:
        cli._inputs_file(close, str(f))
        refusals["a file that is not JSON"] = None
    except SystemExit as exc:
        refusals["a file that is not JSON"] = str(exc)
check(
    "--inputs-file refuses an input the operation does not take, a missing required one, anything but an object, "
    "and a file that is not JSON",
    all(v and v.startswith("ERROR (bad-argument)") for v in refusals.values()) and len(refusals) == 4,
    refusals,
)

with tempfile.TemporaryDirectory() as tmp:
    f = Path(tmp) / "inputs.json"
    f.write_text(
        json.dumps({"goal": "g", "round": "r1", "conclusion": "three whole words"}), encoding="utf-8"
    )
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        try:
            cli.main(close, ["--inputs-file", str(f), "--goal", "g"])
            code = None
        except SystemExit as exc:
            code = exc.code
check(
    "a line with --inputs-file and an input of its own is refused: the inputs come from one place",
    code == 2 and "takes every input from the file" in err.getvalue(),
    (code, err.getvalue()),
)


def run_live(collect=None) -> tuple[bool, dict, int]:
    """Run the synthetic job command as the supervisor starts it (--json): (whether its first line was in the log while it
    still ran, its envelope, its exit code). `collect` replaces `_jsonout.collect` for the run (a defect planted)."""
    real_collect, real_err = _jsonout.collect, sys.stderr
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "log"
        sys.stderr = open(log, "w", buffering=1, encoding="utf-8")  # noqa: SIM115 -- closed below
        if collect is not None:
            _jsonout.collect = collect(real_collect)
        out, code = io.StringIO(), []

        def go() -> None:
            with contextlib.redirect_stdout(out):
                code.append(cli.main(_job_ops.LIVE, ["--json"]))

        t = threading.Thread(target=go)
        t.start()
        early, end = False, time.monotonic() + 1.3
        while time.monotonic() < end and t.is_alive():
            text = log.read_text(encoding="utf-8")
            if "first" in text and "second" not in text:
                early = True
                break
            time.sleep(0.05)
        t.join()
        sys.stderr.close()
        sys.stderr, _jsonout.collect = real_err, real_collect
    return early, json.loads(out.getvalue()), code[0]


early, envelope, code = run_live()
check(
    "a job's command prints to its log as it goes (stderr, live) and its envelope after: the first line is in the log "
    "while the body still runs, the envelope has both",
    early
    and code == 0
    and envelope["command"] == "t-live"
    and [ln for b in envelope["result"]["blocks"] for ln in b["lines"]] == ["first", "second"],
    (early, envelope, code),
)
early_bad, envelope_bad, _ = run_live(
    lambda real: lambda name, enabled=True, live=None: real(name, enabled, None)
)
check(
    "that check fails on a body collected without `live` (the log would be empty until the job ends)",
    not early_bad and envelope_bad["command"] == "t-live",
    early_bad,
)

sys.exit(summary())
