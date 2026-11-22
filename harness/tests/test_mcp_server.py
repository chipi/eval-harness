#!/usr/bin/env python3
"""Assertions for `evh mcp` (RFC-018), through the official SDK's own stdio client.

    python tests/test_mcp_server.py

In a throwaway project built from the tutorial ($0, offline): the server lists exactly the read
operations (named as the command line and the API name them), each annotated read-only, none taking --adapter or --json; a tool
answers the operation's result, the envelope `evh <operation> --json` prints, as structured content; an unknown argument is
refused before anything runs; an operation's refusal comes back as an error with its message; the public flag of a call hides
what a public server must not show; and every evh command is either a tool or listed, with a reason, as not one.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness import ops as _ops  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402
from evaluation_harness.mcp_server import AGENT_TOOLS, NOT_TOOLS, tools_for  # noqa: E402

try:
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError as exc:  # the package depends on mcp; a checkout's venv may predate it
    print(
        f"  FAIL test_mcp_server: {exc}: mcp is a dependency of the package (pip install -r requirements.txt)"
    )
    sys.exit(1)

proj = Path(tempfile.mkdtemp(prefix="evh-mcp-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-mcp")
env.pop("EVAL_DATA_DIR", None)


import _cli  # noqa: E402


def evh(*args):
    return _cli.run(proj, env, *args)


READ_TOOLS = {op.name for op in _ops.of_kind("read")}
TOOLS = READ_TOOLS | set(AGENT_TOOLS)
check(
    "every evh command is a tool (a read operation, or the agent sampler's two) or not one, with a reason; none is both",
    TOOLS | set(NOT_TOOLS) == set(COMMANDS)
    and not TOOLS & set(NOT_TOOLS)
    and not READ_TOOLS & set(AGENT_TOOLS),
    f"neither: {sorted(set(COMMANDS) - TOOLS - set(NOT_TOOLS))}; unknown: {sorted((TOOLS | set(NOT_TOOLS)) - set(COMMANDS))}",
)

try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    # The tutorial's fields: area and plan are public, deadline is not.
    (data / "fields").mkdir()
    for f in sorted((KIT / "fields").iterdir()):
        _runstore.write_text(proj, f"fields/{f.name}", f.read_text())
    r = evh(
        "dataset-create",
        "--dataset-id",
        "tickets_v1",
        "--source-dir",
        "tutorial/tickets",
        "--fieldset",
        "tickets",
        "--fields",
        str(KIT / "ticket_fields.csv"),
    )
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset", r.returncode == 0, r.stderr[-300:])
    r = evh(
        "label-import",
        "--sheet",
        str(KIT / "gold"),
        "--dataset-id",
        "tickets_v1",
        "--set",
        "owner_gold",
        "--by",
        "owner",
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "owner_gold",
            "--tier",
            "gold",
            "--reason",
            "The kit's hand-written summaries decide.",
            "--by",
            "owner",
        )
    )
    check("setup: the kit's gold, imported and promoted", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    _runstore.write_text(
        proj, "systems/tickets_lead2_v1.yaml", (KIT / "systems" / "tickets_lead2_v1.yaml").read_text()
    )
    r = evh("run", "--system", "tickets_lead2_v1", "--dataset", "tickets_v1", "--goal", "tickets_summary")
    check("setup: one run", r.returncode == 0, r.stderr[-300:])
    said = r.stdout.splitlines()
    wrote = next((n for n, ln in enumerate(said) if ln.startswith("wrote 1 run(s) to ")), -1)
    check(
        "run: prints the id of each run it wrote, on the lines after 'wrote N run(s)'",
        wrote >= 0 and said[wrote + 1].startswith("  run tickets_lead2_v1_"),
        r.stdout[-300:],
    )
    # The second arm, through --json: progress on stderr, one envelope on stdout.
    _runstore.write_text(
        proj,
        "systems/tickets_lead1_v1.yaml",
        (KIT / "systems" / "tickets_lead1_v1.yaml").read_text(),
    )
    lead1 = ("run", "--system", "tickets_lead1_v1", "--dataset", "tickets_v1", "--goal", "tickets_summary")
    dry = evh(*lead1, "--dry-run", "--json")
    dry_values = json.loads(dry.stdout)["result"]["values"] if dry.returncode == 0 else {}
    check(
        "run --dry-run --json: the projection as values, nothing written",
        (dry_values.get("dry_run") or {}).get("items") == 6
        and dry_values["dry_run"]["api_calls"] == 6
        and dry_values["dry_run"]["system_id"] == "tickets_lead1_v1"
        and "runs" not in dry_values
        and not any(n.startswith("tickets_lead1_v1_") for n in _runstore.listdir(proj, "runs")),
        dry.stdout[-300:] + dry.stderr[-300:],
    )
    r = evh(*lead1, "--json")
    made = (
        json.loads(r.stdout)["result"]["values"]["runs"]
        if r.returncode == 0 and r.stdout.count("\n") == 1
        else []
    )
    check(
        "run --json: stdout is one envelope with the run (id, system, dataset, dir, items, cost, cap); progress is on stderr",
        len(made) == 1
        and made[0]["run_id"].startswith("tickets_lead1_v1_")
        and (made[0]["system_id"], made[0]["dataset_id"], made[0]["n_items"])
        == ("tickets_lead1_v1", "tickets_v1", 6)
        and made[0]["total_cost_usd"] in (0, 0.0, None)
        and made[0]["capped_at"] is None
        and _runstore.exists(proj, Path(made[0]["dir"]).relative_to(proj / "data").as_posix())
        and "wrote 1 run(s) to" in r.stderr
        and f"  run {made[0]['run_id']}" in r.stderr,
        r.stdout[-300:] + r.stderr[-300:],
    )

    # A PUBLIC SERVER'S comparison SEES ONLY PUBLIC FIELDS. The server answers in its own process, with the public flag of
    # the call: a --where or --by on a field not marked public is refused instead of answering with its values through the
    # counts (0.5.0). The operation, answered as the server answers it:
    from evaluation_harness import mcp_server as ms
    from evaluation_harness import ops
    from evaluation_harness.model.entity import Problem

    os.environ.clear()
    os.environ.update(env)
    ms.use_project(proj)

    for arguments, public, ok, label in (
        ({"runs": "tickets_lead2_v1", "by": "deadline"}, True, False, "a hidden field (by) is refused"),
        (
            {"runs": "tickets_lead2_v1", "where": ["deadline:yes"]},
            True,
            False,
            "a hidden field (where) is refused",
        ),
        ({"runs": "tickets_lead2_v1", "by": "area"}, True, True, "a public field still breaks it down"),
        (
            {"runs": "tickets_lead2_v1", "by": "deadline"},
            False,
            True,
            "a local server still sees every field",
        ),
    ):
        try:
            said = json.dumps(ms.run_op(ops.get("comparison-show"), arguments, public))
            refused = False
        except Problem as exc:
            said, refused = str(exc), True
        check(
            f"comparison-show {'--public' if public else 'local'}: {label}",
            refused != ok
            and (ok or ("deadline" in said and "True" not in said and '"breakdown"' not in said)),
            said[-300:],
        )

    async def session():
        params = StdioServerParameters(
            command=sys.executable, args=[str(HERE / "cli.py"), "mcp"], cwd=str(proj), env=env
        )
        async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            by = {t.name: t for t in tools}
            check(
                "tools: the read operations, named as the command line and the API name them, and the agent sampler's study-ask and study-tell (a local server)",
                sorted(by) == sorted(TOOLS),
                sorted(by),
            )
            check(
                "tools: each read-only but the agent sampler's two (RFC-029), none destructive",
                all(
                    bool(t.annotations.read_only_hint) == (t.name not in AGENT_TOOLS)
                    and not t.annotations.destructive_hint
                    for t in tools
                ),
            )
            check(
                "tools: no schema takes --adapter or --json",
                not any({"adapter", "json"} & set(t.input_schema.get("properties", {})) for t in tools),
            )
            check(
                "tools: the schema comes from the operation (dataset-list: tag, period; the parts of its route are required)",
                {"tag", "period"} <= set(by["dataset-list"].input_schema["properties"])
                and by["dataset-show"].input_schema["required"] == ["dataset"],
                by["dataset-list"].input_schema,
            )
            res = await s.call_tool("dataset-list", {})
            want = evh("dataset-list", "--json").stdout
            check(
                "dataset-list: the operation's own result, the envelope the command line and the API give, as structured content",
                not res.is_error
                and json.loads(res.content[0].text) == json.loads(want)
                and res.structured_content == json.loads(want)
                and (res.structured_content or {}).get("command") == "dataset-list",
                res.content[0].text[:300],
            )
            check(
                "dataset-list: its rows as data",
                any(d_.get("dataset") == "tickets_v1" for d_ in res.structured_content["result"]["datasets"]),
                res.structured_content["result"],
            )
            res = await s.call_tool("dataset-show", {"dataset": "tickets_v1"})
            check(
                "dataset-show: the part of the route is an argument, the answer the one dataset's",
                not res.is_error and res.structured_content["result"]["dataset"] == "tickets_v1",
                res.content[0].text[:200],
            )
            props = set(by["sheet-show"].input_schema["properties"])
            check(
                "sheet-show: the sheet's options are in its schema; the ones that write a file (the CSV and its fill) are not: sheet-export is a command",
                {
                    "dataset",
                    "runs",
                    "wrong_against",
                    "new_vs",
                    "split",
                    "unlabelled",
                    "scores_only",
                    "metric",
                    "label",
                }
                <= props
                and not {"csv", "fill", "choices", "seed", "rubric", "scale"} & props
                and "sheet-export" not in by,
                str(sorted(props)),
            )
            check(
                "comparison-show, -crosstab and -items: the comparison, the crosstab and the items' outputs are in the local tools",
                {"runs", "round", "label", "baseline", "analysis", "where", "by"}
                <= set(by["comparison-show"].input_schema["properties"])
                and {"runs", "crosstab", "group", "group_match", "max_ids"}
                <= set(by["comparison-crosstab"].input_schema["properties"])
                and {"runs", "disagree", "max_chars"}
                <= set(by["comparison-items"].input_schema["properties"]),
            )
            res = await s.call_tool("label-set-list", {"dataset": "tickets_v1"})
            want = evh("label-set-list", "tickets_v1", "--json").stdout
            check(
                "label-set-list: a read tool, its schema the operation's inputs, its answer the command's JSON",
                {"contested"} == set(by["label-set-list"].input_schema["properties"]) - {"dataset"}
                and not res.is_error
                and json.loads(res.content[0].text) == json.loads(want)
                and res.structured_content == json.loads(want),
                res.content[0].text[:300],
            )
            # The statistics and the runs: tools that answer with the command's own --json.
            ids = {
                r_["system_id"]: r_["run_id"]
                for r_ in json.loads(evh("runs-list", "--json").stdout)["result"]["runs"]
            }
            asked = {
                "runs-list": ({}, ["runs-list"]),
                "leaderboard": ({"dataset": "tickets_v1"}, ["leaderboard", "tickets_v1"]),
                "pair-test": (
                    {"dataset": "tickets_v1", "a": "tickets_lead2_v1", "b": "tickets_lead1_v1"},
                    ["pair-test", "tickets_v1", "--a", "tickets_lead2_v1", "--b", "tickets_lead1_v1"],
                ),
                "family-test": (
                    {"dataset": "tickets_v1", "a": "tickets_lead2_v1", "against": "tickets_lead"},
                    ["family-test", "tickets_v1", "--a", "tickets_lead2_v1", "--against", "tickets_lead"],
                ),
                "run-compare": (
                    {"baseline": ids["tickets_lead1_v1"], "candidate": ids["tickets_lead2_v1"]},
                    [
                        "run-compare",
                        "--baseline",
                        ids["tickets_lead1_v1"],
                        "--candidate",
                        ids["tickets_lead2_v1"],
                    ],
                ),
                "round-list": ({"goal": "tickets_summary"}, ["round-list", "tickets_summary"]),
            }
            for tool, (arguments, argv) in asked.items():
                res = await s.call_tool(tool, arguments)
                want = json.loads(evh(*argv, "--json").stdout)
                got = json.loads(res.content[0].text) if not res.is_error else {}
                check(
                    f"{tool}: a read tool whose answer is the command's --json, as structured content",
                    not res.is_error
                    and got == want
                    and res.structured_content == want
                    and want["command"] == tool
                    and ("values" in want["result"] or tool in ("runs-list", "round-list")),
                    res.content[0].text[:300],
                )
            pv = json.loads((await s.call_tool("pair-test", asked["pair-test"][0])).content[0].text)[
                "result"
            ]["values"]
            check(
                "pair-test: the pair's numbers by name (exact over 6 items, 3 differ in lead2's favour)",
                (pv["a"], pv["b"], pv["n"], pv["method"])
                == ("tickets_lead2_v1", "tickets_lead1_v1", 6, "exact")
                and abs(pv["p"] - 3 / 32) < 1e-9
                and pv["verdict"] == "NOT-SIGNIFICANT",
                pv,
            )
            for tool in ("pair-test", "family-test"):
                props = set(by[tool].input_schema["properties"])
                check(
                    f"{tool}: its schema has no input naming a path of the server's (items)",
                    {"a", "permutations"} <= props and "items" not in props,
                    sorted(props),
                )
            check(
                "pair-test: b_dataset (a dataset id) is offered, for two versions of one dataset",
                "b_dataset" in by["pair-test"].input_schema["properties"]
                and "b_dataset" not in by["family-test"].input_schema["properties"],
                sorted(by["pair-test"].input_schema["properties"]),
            )
            for bad, want in (("../outside", "not a dataset id"), ("tickets_v1", "itself")):
                res = await s.call_tool("pair-test", {**asked["pair-test"][0], "b_dataset": bad})
                check(
                    f"pair-test b_dataset={bad}: refused with the command's message, nothing as an answer",
                    res.is_error and want in res.content[0].text,
                    res.content[0].text[:300],
                )
            res = await s.call_tool("rank-stability", {"dataset": "tickets_v1"})
            check(
                "rank-stability: two arms cannot be ranked: an error with the message, nothing as an answer",
                res.is_error and "need at least 3 to rank" in res.content[0].text,
                res.content[0].text[:300],
            )
            res = await s.call_tool(
                "run-compare", {"baseline": "../outside", "candidate": ids["tickets_lead2_v1"]}
            )
            check(
                "run-compare: a run id that is a path is refused, nothing outside the runs folder is read",
                res.is_error
                and "TOPSECRET" not in res.content[0].text
                and "not a path" in res.content[0].text,
                res.content[0].text[:300],
            )
            res = await s.call_tool("dataset-list", {"bogus": 1})
            check(
                "an unknown argument is refused before anything runs",
                res.is_error and "unknown argument" in res.content[0].text,
                res.content[0].text,
            )
            listed = {t.name: t for t in (await s.list_tools()).tools}
            res = await s.call_tool("comparison-show", {})
            check(
                "comparison-show's schema says it needs runs or round, and a call with neither is refused in those words "
                "before anything runs",
                listed["comparison-show"].input_schema.get("anyOf")
                == [{"required": ["runs"]}, {"required": ["round"]}]
                and res.is_error
                and "one of runs, round is needed" in res.content[0].text,
                (listed["comparison-show"].input_schema.get("anyOf"), res.content[0].text[:200]),
            )
            res = await s.call_tool("goal-leaderboard", {"goal": "no_such_goal"})
            check(
                "an operation's refusal is an error, with its kind and message",
                res.is_error
                and "no_such_goal" in res.content[0].text
                and "ERROR (not-found)" in res.content[0].text,
                res.content[0].text[:300],
            )
            res = await s.call_tool("validate", {})
            check(
                "validate: answers, the verdict as data (its checks passed or named)",
                not res.is_error
                and "passed" in res.structured_content["result"]["values"]
                and "V1" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("run-promote", {})
            check(
                "a command that is not a tool is refused",
                res.is_error and "no tool" in res.content[0].text,
                res.content[0].text,
            )
            # Values are data, never a way past the schema (an independent review's two holes).
            (proj / "outside.json").write_text('{"secret": "TOPSECRET"}')
            for bad in ["../outside", str(proj / "outside"), "..", "a/b"]:
                res = await s.call_tool("dataset-items", {"dataset": bad})
                check(
                    f"dataset-items: a path as the id is refused ({bad[:20]!r}), nothing outside data/ is read",
                    res.is_error
                    and "TOPSECRET" not in res.content[0].text
                    and "not a dataset id" in res.content[0].text,
                    res.content[0].text[:200],
                )
            res = await s.call_tool("comparison-show", {"runs": "--item"})
            check(
                "a value that starts with '-' is a value: it names no arm, and is not read as an option",
                res.is_error and "no arm with that id" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("dataset-show", {"dataset": ["tickets_v1", "x"]})
            check(
                "a list for an input that takes one value is refused",
                res.is_error and "is not of type 'string'" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("leaderboard", {"dataset": "tickets_v1", "asc": "false"})
            check(
                "a flag given as the string 'false' is refused, not read as on",
                res.is_error and "is not of type 'boolean'" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("dataset-show", {"dataset": "a\u0000b"})
            check(
                "a NUL byte in a value is refused before anything runs",
                res.is_error and "NUL" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("dataset-show", {"dataset": "x" * 600})
            check(
                "an over-long value is refused before anything runs",
                res.is_error and "characters" in res.content[0].text,
                res.content[0].text[:200],
            )
            res = await s.call_tool("search", {"text": ["tickets_v1"]})
            check(
                "search: its words, the answer found",
                not res.is_error and "tickets_v1" in res.content[0].text,
                res.content[0].text[:200],
            )

    anyio.run(session)

    async def public_session():
        params = StdioServerParameters(
            command=sys.executable, args=[str(HERE / "cli.py"), "mcp", "--public"], cwd=str(proj), env=env
        )
        async with stdio_client(params) as (rd, wr), ClientSession(rd, wr) as s:
            await s.initialize()
            by = {t.name: t for t in (await s.list_tools()).tools}
            check(
                "--public: the statistics are tools; validate, and every tool that shows a file, an item's text or an output, are not",
                {"leaderboard", "pair-test", "family-test", "rank-stability", "run-compare", "round-list"}
                <= set(by)
                and not {
                    "validate",
                    "data-ls",
                    "data-show",
                    "sheet-show",
                    "comparison-item",
                    "comparison-items",
                    "exposure",
                    "sealed-counts",
                    "label-mutants",
                    "label-coverage-show",
                }
                & set(by)
                and sorted(by) == sorted(tools_for(True)),
                sorted(by),
            )
            pub = set(by["comparison-crosstab"].input_schema["properties"])
            check(
                "--public comparison-crosstab: the crosstab of two scores is offered; --group (recorded texts) is not",
                {"crosstab", "max_ids"} <= pub and not {"group", "group_match"} & pub,
                sorted(pub),
            )
            check(
                "--public dataset-items: one item's text is not offered",
                "item" not in by["dataset-items"].input_schema["properties"],
            )
            held = {
                "pair-test": {"permutations", "items"},
                "family-test": {"permutations", "items"},
                "rank-stability": {"draws"},
            }
            check(
                "--public: how long a statistic runs (permutations, draws) is not the caller's to set",
                all(not held[t] & set(by[t].input_schema["properties"]) for t in held),
                {t: sorted(by[t].input_schema["properties"]) for t in held},
            )
            res = await s.call_tool(
                "pair-test", {"dataset": "tickets_v1", "a": "tickets_lead2_v1", "b": "tickets_lead1_v1"}
            )
            check(
                "--public pair-test: numbers and ids only (no item text, no output)",
                not res.is_error
                and not any(k in res.content[0].text for k in ("t01_login", "area", "deadline", "TOPSECRET")),
                res.content[0].text[:300],
            )
            res = await s.call_tool("comparison-show", {"runs": "tickets_lead2_v1", "by": "deadline"})
            check(
                "--public comparison-show: a field not marked public is refused, by the call's own flag",
                res.is_error and "deadline" in res.content[0].text,
                res.content[0].text[:300],
            )

    anyio.run(public_session)
    from evaluation_harness._cmdline import public_error

    tb = "Traceback (most recent call last):\n  File \"/srv/evals/releases/abc/pkg/x.py\", line 1\nKeyError: 'x'"
    check(
        "public: a crash is told as an internal error, no traceback or path",
        "internal error" in public_error(tb, proj) and "/srv" not in public_error(tb, proj),
    )
    msg = f"ERROR: no profile for d ({proj}/data/profiles/d.json): write one"
    check(
        "public: a refusal keeps its message, without the server's paths",
        public_error(msg, proj).startswith("ERROR: no profile for d")
        and str(proj) not in public_error(msg, proj),
        public_error(msg, proj),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
