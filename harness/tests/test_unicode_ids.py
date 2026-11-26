#!/usr/bin/env python3
"""An id a person names may be spelled in any script (0.8.2, owner 2026-11-26): one rule, `_ids.IdRule`, for every kind.

    python tests/test_unicode_ids.py            (EVAL_STORE=files or sqlite)

The rule on a table of ids: letters and digits of any script and the kind's punctuation pass; whitespace, control and format
characters, path separators, `..`, a leading `.` `-` `_`, capitals where the kind is lowercase and a spelling that is not
Unicode NFC are refused (the NFC form named). Every JSON schema that patterns an id says the same as the rule on that table,
except where a regular expression cannot (NFC, a non-ASCII capital, a trailing newline: the schema is never stricter), and
no other schema pattern spells ASCII letters without being named here. In a throwaway project, in the store the suite runs
in: a dataset, a system and a run with a unicode id are made and read back (CLI, the API by a percent-encoded id), the
catalog export names its pages by the id's letters, and an id that is not NFC is refused by the writer.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli, _serve
import _cli  # noqa: E402
import _runstore  # noqa: E402
import _serve  # noqa: E402
from evaluation_harness import _format, _ids  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

NFD = unicodedata.normalize("NFD", "été")
#: (id, NAME, LOWER, SNAKE): what each rule says; None: the NFC check or a regular expression's limit decides, see LOOSE.
TABLE = [
    ("tickets_v1", True, True, True),
    ("Tickets_V1", True, False, False),
    ("données_日本語_v1", True, True, True),
    ("пункт_3", True, True, True),
    ("ПУНКТ_3", True, False, False),
    ("été", True, True, True),
    ("日本語", True, True, True),
    ("٣٤", True, True, True),
    ("ａｂｃ", True, True, True),
    ("a.b-c_d", True, True, False),
    ("ǅ", True, False, False),
    ("İ", True, False, False),
    ("a", True, True, True),
    (NFD, False, False, False),
    ("\u212b", False, False, False),
    ("a b", False, False, False),
    ("a\u00a0b", False, False, False),
    ("a\u200bb", False, False, False),
    ("a\u200db", False, False, False),
    ("a\u202eb", False, False, False),
    ("a\tb", False, False, False),
    ("a\nb", False, False, False),
    ("a\n", False, False, False),
    ("a\0b", False, False, False),
    ("a\x7fb", False, False, False),
    ("a/b", False, False, False),
    ("a\\b", False, False, False),
    ("a%2Fb", False, False, False),
    ("名前:x", False, False, False),
    ("..", False, False, False),
    ("a..b", False, False, False),
    (".hidden", False, False, False),
    ("-x", False, False, False),
    ("_x", False, False, False),
    ("", False, False, False),
]
RULES = (_ids.NAME, _ids.LOWER, _ids.SNAKE)
for ident, *want in TABLE:
    for rule, w in zip(RULES, want, strict=True):
        got = rule.problem(ident)
        check(
            f"{rule!r}: {ident!r} is {'an id' if w else 'refused'}",
            (got is None) == w,
            got or "accepted",
        )
check(
    "a non-NFC id is refused naming the NFC form",
    "'été'" in (_ids.NAME.problem(NFD) or "") and "NFC" in (_ids.NAME.problem(NFD) or ""),
    _ids.NAME.problem(NFD),
)
check("a control character is named as one", "control" in (_ids.NAME.problem("a\x07b") or ""))
check("a path is named as one", "separator" in (_ids.NAME.problem("a/b") or ""))
check("the length limit is kept", _ids.SET.ok("é" * 100) and not _ids.SET.ok("é" * 101))
check("an id is never a path or a non-string", not _ids.NAME.ok(None) and not _ids.NAME.ok(5))

# The schemas: every pattern that names an id is the rule's, and says what the rule says.
SCHEMAS = HARNESS / "schemas"
#: (schema file, the keys to the pattern: the end of its place in the schema, rule)
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
#: Patterns that spell ASCII letters and are not an id a person names: an item or field name, a prompt's path, a URL.
NOT_IDS = {
    ("dataset.schema.json", "source_url"),
    ("failure-modes.schema.json", "id"),
    ("fieldset.schema.json", "name"),
    ("prompt-version.schema.json", "id"),
}


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


def loosened(ident, rule):
    """The rule refuses it and a regular expression cannot say why."""
    return (
        unicodedata.normalize("NFC", ident) != ident
        or (rule.lower and not ident.isascii())
        or ident.endswith("\n")
    )


for fname, keys, rule in ID_PATTERNS:
    doc = json.loads((SCHEMAS / fname).read_text(encoding="utf-8"))
    pats = patterns_at(doc, keys)
    where = f"{fname} {'/'.join(keys)}"
    check(
        f"{where}: the pattern is the rule's ({rule!r})", pats == [rule.pattern], f"{pats} vs {rule.pattern}"
    )
    rx = re.compile(pats[0])
    for ident, *_ in TABLE:
        said = rule.ok(ident)
        matched = rx.search(ident) is not None
        if said:
            check(f"{where}: {ident!r}, an id, is accepted", matched)
        elif not loosened(ident, rule):
            check(f"{where}: {ident!r}, refused, is refused", not matched)
        else:
            check(f"{where}: {ident!r} is refused by the rule", not said)
stray = []
for f in sorted(SCHEMAS.glob("*.json")):
    for trail, pat in walk(json.loads(f.read_text(encoding="utf-8"))):
        if re.search(r"\[(A-Za-z0-9|a-z0-9)", pat) and (f.name, trail[-1]) not in NOT_IDS:
            stray.append(f"{f.name} {'/'.join(trail)}: {pat}")
check("no schema pattern spells an id in ASCII letters, but the rule's", not stray, "; ".join(stray))

# A throwaway project, in the store the suite runs in.
STORE = os.environ.get("EVAL_STORE") or "files"
proj = Path(tempfile.mkdtemp(prefix="evh-unicode-ids-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-unicode-ids", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


DS = "données_日本語_v1"
SYS = "sÿstème_日本語_v1"
RUN = "série_日本語_1"
try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "config.yaml").write_text(f"store: {STORE}\n", encoding="utf-8")
    for n, t in (("élément_1", "billing"), ("項目_2", "shipping")):
        _runstore.write_text(proj, f"sources/{DS}/{n}.txt", t)
    r = evh("dataset-create", "--dataset-id", DS)
    check(f"a dataset with the id {DS!r} is made", r.returncode == 0, r.stdout + r.stderr)
    check(
        "its record is in the store under that name",
        _runstore.exists(proj, f"datasets/{DS}.json")
        and json.loads(_runstore.read_text(proj, f"datasets/{DS}.json"))["dataset_id"] == DS,
    )
    r = evh("dataset-show", DS, "--json")
    check("dataset-show reads it back by its id", r.returncode == 0 and DS in r.stdout, r.stdout + r.stderr)

    r = evh("system-new", SYS, "--set", "params.provider=echo")
    check(f"a system with the id {SYS!r} is made", r.returncode == 0, r.stdout + r.stderr)
    r = evh("system-show", SYS)
    check("system-show reads it back by its id", r.returncode == 0 and SYS in r.stdout, r.stdout + r.stderr)

    (proj / "scores.jsonl").write_text(
        "".join(
            json.dumps({"item_id": i, "wer": 0.1 * k}) + "\n" for k, i in enumerate(("élément_1", "項目_2"))
        ),
        encoding="utf-8",
    )
    r = evh(
        "import-run", "--dataset-id", DS, "--system-id", SYS, "--run-id", RUN, "--scores", "scores.jsonl",
        "--primary-metric", "wer", "--asc", "--build-ref", "t", "--source", "test", "--scorer-id", "wer",
    )  # fmt: skip
    check(f"a run with the id {RUN!r} is imported", r.returncode == 0, r.stdout + r.stderr)
    check("its folder is in the store under that name", _runstore.exists(proj, f"runs/{RUN}/run.json"))
    r = evh("runs-list", "--json")
    check("runs-list names it", r.returncode == 0 and RUN in r.stdout, r.stdout + r.stderr)

    for bad, why in ((NFD, "NFC"), ("a b", "space"), ("a\u200bb", "control or format"), ("a/b", "separator")):
        r = evh("dataset-create", "--dataset-id", bad, "--source-dir", f"data/sources/{DS}")
        check(
            f"dataset-create refuses {bad!r} ({why})",
            r.returncode != 0 and why in r.stderr and not _runstore.exists(proj, f"datasets/{bad}.json"),
            r.stdout + r.stderr,
        )
    r = evh("import-run", "--dataset-id", DS, "--system-id", NFD, "--scores", "scores.jsonl", "--primary-metric", "wer",
            "--asc", "--build-ref", "t", "--source", "test", "--scorer-id", "wer")  # fmt: skip
    check(
        "import-run refuses a --system-id that is not NFC, naming the NFC form",
        r.returncode != 0 and "NFC" in r.stderr and "'été'" in r.stderr,
        r.stderr,
    )

    # URLs: the API routes the id, percent-encoded.
    srv, port, _out = _serve.start(proj, env)
    try:
        tok = (proj / ".build" / "api-token").read_text(encoding="utf-8").strip()

        def get(path):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}", headers={"Authorization": f"Bearer {tok}"}
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - this test's own server  # nosec B310
                    return resp.status, json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                return exc.code, {"error": exc.read().decode()[:200]}

        for kind, ident in (("datasets", DS), ("systems", SYS)):
            status, body = get(f"/api/v1/{kind}/{urllib.parse.quote(ident, safe='')}")
            check(
                f"GET /api/v1/{kind}/<percent-encoded id> answers",
                status == 200 and ident in json.dumps(body, ensure_ascii=False),
                f"{status} {str(body)[:200]}",
            )
        status, body = get(f"/api/v1/datasets/{urllib.parse.quote(NFD, safe='')}")
        check(
            "a non-NFC id in a URL is not found, never a traceback",
            status in (400, 404) and "Traceback" not in json.dumps(body),
            f"{status} {str(body)[:200]}",
        )
    finally:
        _serve.stop(srv, proj)

    # The catalog export: pages named by the id's letters, one page each.
    out = proj / "site"
    r = evh("catalog", "--out", str(out))
    check("the catalog builds with unicode ids", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    pages = sorted(p.name for p in (out / "d").glob("*.html")) if (out / "d").is_dir() else []
    check("the export names the dataset's page by its letters", f"{DS}.html" in pages, str(pages))
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
