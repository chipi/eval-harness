#!/usr/bin/env python3
"""An id a person names is ASCII (0.8.3, owner 2026-11-26): one rule, `_ids.IdRule`, for every kind; an id that is already on disk is still read.

    python tests/test_ascii_ids.py            (EVAL_STORE=files or sqlite)

The rule on a table of ids per kind; every JSON schema that patterns an id says what the rule says, in ASCII; a writer refuses
a non-ASCII id naming the rule; and a project that made such ids under 0.8.2 (written here by hand) is still read by the CLI
and validated, with a note naming the id and no failure.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format, _ids  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

RULES = (_ids.NAME, _ids.LOWER, _ids.SNAKE, _ids.SET)
#: (id, NAME, LOWER, SNAKE, SET): whether each rule takes it.
TABLE = [
    ("tickets_v1", True, True, True, True),
    ("Tickets_V1", True, False, False, False),
    ("a.b-c_d", True, True, False, True),
    ("a", True, True, True, True),
    ("9", True, True, True, True),
    ("données_v1", False, False, False, False),
    ("пункт_3", False, False, False, False),
    ("日本語", False, False, False, False),
    ("٣٤", False, False, False, False),
    ("ａｂｃ", False, False, False, False),
    ("été", False, False, False, False),
    ("e\u0301te", False, False, False, False),
    ("a b", False, False, False, False),
    ("a\u00a0b", False, False, False, False),
    ("a\u200bb", False, False, False, False),
    ("a\tb", False, False, False, False),
    ("a\nb", False, False, False, False),
    ("a\n", False, False, False, False),
    ("a/b", False, False, False, False),
    ("a\\b", False, False, False, False),
    ("a%2Fb", False, False, False, False),
    ("..", False, False, False, False),
    ("a..b", False, False, False, False),
    (".hidden", False, False, False, False),
    ("-x", False, False, False, False),
    ("_x", False, False, False, False),
    ("", False, False, False, False),
]
for ident, *want in TABLE:
    for rule, w in zip(RULES, want, strict=True):
        got = rule.problem(ident)
        check(f"{rule!r}: {ident!r} is {'an id' if w else 'refused'}", (got is None) == w, got or "accepted")
check("the length limit is kept", _ids.SET.ok("a" * 100) and not _ids.SET.ok("a" * 101))
check("an id is never a path or a non-string", not _ids.NAME.ok(None) and not _ids.NAME.ok(5))
check(
    "a refusal says the rule: ASCII letters and digits",
    all("ASCII" in _ids.NAME.says() and "ASCII" in r.says() for r in RULES),
    _ids.NAME.says(),
)

SCHEMAS = HARNESS / "schemas"
#: (schema file, the end of the pattern's place in the schema, rule)
ID_PATTERNS = [
    ("capture.schema.json", ("properties", "capture_id"), _ids.NAME),
    ("dataset.schema.json", ("^", "properties", "dataset_id"), _ids.NAME),
    ("dataset.schema.json", ("properties", "derived_from", "properties", "dataset_id"), _ids.NAME),
    ("dataset.schema.json", ("properties", "fieldset"), _ids.SNAKE),
    ("fieldset.schema.json", ("properties", "fieldset_id"), _ids.SNAKE),
    ("failure-modes.schema.json", ("properties", "failure_modes_id"), _ids.SET),
    ("goal.schema.json", ("properties", "goal_id"), _ids.SNAKE),
    ("label-set.schema.json", ("properties", "set"), _ids.SET),
    ("tag-set.schema.json", ("properties", "set"), _ids.SET),
    ("model.schema.json", ("properties", "model_id"), _ids.LOWER),
    ("scorer.schema.json", ("properties", "system"), _ids.NAME),
    ("system.schema.json", ("properties", "system_id"), _ids.NAME),
    ("system.schema.json", ("properties", "deployment"), _ids.LOWER),
    ("system.schema.json", ("properties", "expect_identical_to"), _ids.NAME),
]


def walk(node, trail=()):
    if isinstance(node, dict):
        if isinstance(node.get("pattern"), str):
            yield trail, node["pattern"]
        for k, v in node.items():
            yield from walk(v, (*trail, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, (*trail, str(i)))


def patterns_at(doc, keys):
    """The patterns at `keys`: from the schema's root when it starts with "^", else wherever its end is `keys`."""
    if keys[0] == "^":
        return [p for trail, p in walk(doc) if trail == keys[1:]]
    return [p for trail, p in walk(doc) if trail[-len(keys) :] == keys]


for fname, keys, rule in ID_PATTERNS:
    doc = json.loads((SCHEMAS / fname).read_text(encoding="utf-8"))
    pats = patterns_at(doc, keys)
    where = f"{fname} {'/'.join(keys)}"
    check(
        f"{where}: the pattern is the rule's ({rule!r})", pats == [rule.pattern], f"{pats} vs {rule.pattern}"
    )
    check(
        f"{where}: the pattern is ASCII only",
        len(pats) == 1 and not re.search(r"\\[wWdD]", pats[0]),
        str(pats),
    )
    if len(pats) != 1:
        continue
    rx = re.compile(pats[0])
    for ident, *_ in TABLE:
        check(
            f"{where}: {ident!r} is {'accepted' if rule.ok(ident) else 'refused'}, as the rule says",
            (rx.fullmatch(ident) is not None) == rule.ok(ident),
        )

STORE = os.environ.get("EVAL_STORE") or "files"
proj = Path(tempfile.mkdtemp(prefix="evh-ascii-ids-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-ascii-ids", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


DS, SYS, GOAL = "données_日本語_v1", "sÿstème_日本語_v1", "but_été"
try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "config.yaml").write_text(f"store: {STORE}\n", encoding="utf-8")
    for n, t in (("a_1", "billing"), ("b_2", "shipping")):
        _runstore.write_text(proj, f"sources/tickets_v1/{n}.txt", t)
    (proj / "scores.jsonl").write_text(
        "".join(json.dumps({"item_id": i, "wer": 0.1}) + "\n" for i in ("a_1", "b_2")), encoding="utf-8"
    )

    # Writers refuse a non-ASCII id, naming the rule, and write nothing.
    r = evh("dataset-create", "--dataset-id", DS, "--source-dir", "data/sources/tickets_v1")
    check(
        "dataset-create refuses a non-ASCII id, naming ASCII",
        r.returncode != 0 and "ASCII" in r.stderr and "Traceback" not in r.stderr,
        r.stdout + r.stderr,
    )
    check("it wrote no record", not _runstore.exists(proj, f"datasets/{DS}.json"))
    r = evh("system-new", SYS, "--set", "params.provider=echo")
    check(
        "system-new refuses a non-ASCII id, naming ASCII",
        r.returncode != 0 and "ASCII" in r.stderr and "Traceback" not in r.stderr,
        r.stdout + r.stderr,
    )
    check("it wrote no record either", not _runstore.exists(proj, f"systems/{SYS}.yaml"))

    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "data/sources/tickets_v1")
    check("an ASCII dataset is made", r.returncode == 0, r.stdout + r.stderr)
    r = evh("system-new", "echo_v1", "--set", "params.provider=echo")
    check("an ASCII system is made", r.returncode == 0, r.stdout + r.stderr)
    r = evh(
        "import-run", "--dataset-id", "tickets_v1", "--system-id", "echo_v1", "--run-id", "série_1",
        "--scores", "scores.jsonl", "--primary-metric", "wer", "--asc", "--build-ref", "t", "--source", "test",
        "--scorer-id", "wer",
    )  # fmt: skip
    check(
        "import-run refuses a non-ASCII --run-id, naming ASCII",
        r.returncode != 0 and "ASCII" in r.stderr and "Traceback" not in r.stderr,
        r.stdout + r.stderr,
    )

    # What 0.8.2 made: the same records under non-ASCII ids, written by hand.
    ds = json.loads(_runstore.read_text(proj, "datasets/tickets_v1.json"))
    _runstore.write_text(
        proj,
        f"datasets/{DS}.json",
        json.dumps({**ds, "dataset_id": DS}, ensure_ascii=False, indent=2) + "\n",
    )
    _runstore.write_text(
        proj,
        f"systems/{SYS}.yaml",
        f"system_id: {SYS}\nparams:\n  provider: echo\n  sentences: 1\n",
    )
    _runstore.write_text(
        proj,
        f"goals/{GOAL}.yaml",
        f"goal_id: {GOAL}\nschema_version: '0.1'\ntitle: a goal\nstatement: A goal made under 0.8.2.\n"
        f"decision: None.\nstatus: active\nsuccess_criteria:\n  primary:\n    measure: output_words\n"
        f"    direction: higher\ndatasets:\n  - {{dataset_id: {DS}, role: validation}}\n",
    )
    for what, args, want in (
        ("dataset-show", ("dataset-show", DS, "--json"), DS),
        ("dataset-list", ("dataset-list", "--json"), DS),
        ("system-show", ("system-show", SYS), SYS),
        ("system-list", ("system-list", "--json"), SYS),
    ):
        r = evh(*args)
        check(
            f"{what} reads a record that has a non-ASCII id",
            r.returncode == 0 and want in r.stdout and "Traceback" not in r.stderr,
            r.stdout[-300:] + r.stderr[-300:],
        )
    r = evh("system-set", SYS, "--set", "params.sentences=2")
    check(
        "an edit of a record with a non-ASCII id is refused by name, not a traceback",
        r.returncode != 0 and "ASCII" in r.stderr and "Traceback" not in r.stderr,
        r.stdout + r.stderr,
    )
    r = evh("validate")
    out = r.stdout + r.stderr
    check(
        "validate does not fail on them and does not crash",
        r.returncode in (0, 6) and "FAIL" not in out and "Traceback" not in out,
        out[-600:],
    )
    check(
        "validate names each as a note",
        all(i in out for i in (DS, SYS, GOAL)) and "ASCII" in out,
        out[-600:],
    )
    r = evh(
        "import-run", "--dataset-id", "tickets_v1", "--system-id", "echo_v1", "--run-id", "run_1",
        "--scores", "scores.jsonl", "--primary-metric", "wer", "--asc", "--build-ref", "t", "--source", "test",
        "--scorer-id", "wer",
    )  # fmt: skip
    check("an ASCII run is imported", r.returncode == 0, r.stdout + r.stderr)
    r = evh("catalog", "--out", str(proj / "site"))
    check("the catalog builds over them", r.returncode == 0, (r.stdout + r.stderr)[-400:])
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
