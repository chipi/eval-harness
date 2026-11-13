#!/usr/bin/env python3
"""Labels from what happened later (RFC-031 L1-L3, X3): an outcome from another capture, two dates per label, a
relabel that only adds, labels that hold only under production's action, items gone from the source.

    python tests/test_outcome_labels.py

In a throwaway project from the tutorial ($0, offline). A capture of decisions (each with a fingerprint, its first-seen
time and production's action) and a capture of issues, joined by fingerprint within -1m,+15m of the decision under one
name the rules read (`--outcomes-as iss`), the first-seen time as identity: an issue in the window labels "file" (only
under production's action), none for 14 days labels "dismiss"; an issue made two hours later is no match; an issue whose
first-seen differs (an id reused) makes the item "gone from the source, or its id reused", never labelled.
label-coverage counts it all; label-from-capture writes the dates and the action. A later read: the young item has
matured, another recurred: a relabel keeps two, adds one, marks one changed after maturing; a label no rule gives any
more is refused unless kept. A capture of the objects the items name, missing two: those are gone. Production's own
arm scores every labelled item; a variant that acted otherwise is not scored on the action-bound one, and says so.
X1: the labeller's mutants (built in, and a project's): the ones that move labels are killed, the survivors named.
"""

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

KIT = HERE.parent / "tutorial"
proj = Path(tempfile.mkdtemp(prefix="evh-outlabels-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-outlabels", EVH_ACTOR="person:ana")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVH_FOR"):
    env.pop(k, None)
NOW = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
DAY, MIN = _dt.timedelta(days=1), _dt.timedelta(minutes=1)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def said(r):
    return r.stdout + r.stderr


def capture(name, rows):
    (proj / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    query = json.dumps({"path": f"{name}.jsonl"})
    return evh("capture", "--importer", "jsonl", "--query", query, "--capture", name)


def labels_doc(name):
    return _runstore.read_json(proj, f"labels/tickets_v1/{name}/labels.json")


def join(cap):
    return [
        *("--outcomes", cap, "--outcomes-as", "iss", "--join", "fp=fp"),
        *("--within", "-1m,+15m", "--identity", "first_seen=first_seen"),
    ]


def values(r):
    return json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}


BASE = ("--dataset-id", "tickets_v1", "--map", "rules.yaml")
try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    evh("dataset-materialize", "--dataset-id", "tickets_v1")
    items = sorted(p.stem for p in (proj / "tutorial" / "tickets").glob("*.txt"))
    t = {0: NOW - 30 * DAY, 1: NOW - 3 * DAY, 2: NOW - 30 * DAY, 3: NOW - 30 * DAY, 4: NOW - 30 * DAY}
    acts = {0: "file", 1: "dismiss", 2: "dismiss", 3: "dismiss", 4: "dismiss"}

    def decision(i, when=None):
        return {
            "id": items[i],
            "created_at": iso(when or t[i]),
            "fp": f"fp{i}",
            "first_seen": f"s{i}",
            "action": acts.get(i, "dismiss"),
            "body": "x",
        }

    def issue(iid, i, after, first_seen=None, reason="completed", closed=None):
        return {
            "id": iid,
            "created_at": iso(t[i] + after),
            "fp": f"fp{i}",
            "first_seen": first_seen or f"s{i}",
            "state_reason": reason,
            "closed_at": iso(closed or t[i] + DAY),
        }

    decisions = [decision(i) for i in range(5)]  # items[5] is not in the capture
    issues = [
        issue("is0", 0, 5 * MIN, closed=t[0] + 2 * DAY),  # in the window: file
        issue("is2", 2, 120 * MIN),  # two hours later: no match, so item 2 has no issue
        issue("is4", 4, MIN, first_seen="another"),  # the id reused: gone
    ]
    r1, r2 = capture("dec", decisions), capture("iss", issues)
    check("setup: two captures", r1.returncode == r2.returncode == 0, said(r1)[-300:] + said(r2)[-300:])
    (proj / "rules.yaml").write_text(
        "- {when: {iss.state_reason: completed}, date: iss.closed_at, under: action, label: file}\n"
        "- {when: {iss.count: 0}, min_age_days: 14, label: dismiss}\n"
    )
    r = evh("label-coverage", *BASE, "--capture", "dec", *join("iss"), "--json")
    check(
        "label-coverage --outcomes: joined by key, window and identity; gone and not mature counted apart",
        values(r).get("counts")
        == {"labelled": 3, "skipped": 0, "not_mature": 1, "unmatched": 0, "no_record": 1, "gone": 1},
        said(r)[-600:],
    )
    r = evh("label-from-capture", *BASE, "--capture", "dec", "--set", "s1", *join("iss"))
    check(
        "label-from-capture: a rule with under: action needs --action-field",
        r.returncode != 0 and "--action-field" in said(r) and "Traceback" not in said(r),
        said(r)[-300:],
    )
    r = evh(
        "label-from-capture",
        *BASE,
        "--capture",
        "dec",
        "--set",
        "s1",
        *join("iss"),
        "--action-field",
        "action",
    )
    doc = labels_doc("s1") if r.returncode == 0 else {}
    rows = doc.get("items") or {}
    r0, r2_ = rows.get(items[0]) or {}, rows.get(items[2]) or {}
    check(
        "the set: three labels with their dates, the action-bound one with production's action; the gone named",
        sorted(rows) == [items[0], items[2], items[3]]
        and r0.get("under_action") == "file"
        and r0.get("happened_at", "")[:10] == iso(t[0] + 2 * DAY)[:10]
        and r0.get("knowable_at") == r0.get("happened_at")
        and "under_action" not in r2_
        and r2_.get("knowable_at", "")[:10] == iso(t[2] + 14 * DAY)[:10]
        and doc["source"].get("gone") == 1
        and doc["source"].get("not_mature") == 1
        and sorted(doc.get("gone") or {}) == [items[4]]
        and doc["source"]["outcomes"][0]["join"] == "fp=fp"
        and doc["source"]["outcomes"][0]["within"] == "-1m,+15m"
        and doc["source"]["outcomes"][0]["as"] == "iss"
        and len(doc["source"]["outcomes"][0]["capture_sha256"]) == 64
        and bool(doc["source"].get("as_of")),
        said(r)[-400:] + json.dumps(doc)[-700:],
    )

    # The fleet's beta (F4): labels read from two outside systems at once (GitHub's close reason, GlitchTip's
    # recurrence), each --outcomes with its own options, each read by the rules under its own name.
    capture("gtrec", [{"id": "g3", "created_at": iso(t[3] + MIN), "fp": "fp3", "recurred": True}])
    (proj / "rules2.yaml").write_text(
        "- {when: {gt.recurred: true}, label: escalate}\n"
        "- {when: {iss.state_reason: completed}, date: iss.closed_at, label: file}\n"
        "- {when: {iss.count: 0}, min_age_days: 14, label: dismiss}\n"
    )
    two = [*join("iss"), "--outcomes", "gtrec", "--outcomes-as", "gt", "--join", "fp=fp"]
    r = evh("label-from-capture", "--dataset-id", "tickets_v1", "--map", "rules2.yaml", "--capture", "dec",
            "--set", "s_two", *two)  # fmt: skip
    two_doc = labels_doc("s_two") if r.returncode == 0 else {}
    two_labels = {
        i: _runstore.read_text(proj, f"labels/tickets_v1/s_two/{i}.txt").strip()
        for i in (two_doc.get("items") or {})
    }
    check(
        "two --outcomes: each joined by its own options, the rules read both; both captures recorded",
        two_labels.get(items[3]) == "escalate"
        and two_labels.get(items[0]) == "file"
        and [o.get("as") for o in (two_doc.get("source") or {}).get("outcomes") or []] == ["iss", "gt"]
        and [o.get("within") for o in two_doc["source"]["outcomes"]] == ["-1m,+15m", None],
        said(r)[-400:] + json.dumps(two_labels),
    )
    r = evh("label-coverage", *BASE, "--capture", "dec", "--outcomes-as", "iss", "--join", "fp=fp",
            "--within=-1m,+15m", "--identity", "first_seen=first_seen", "--outcomes", "iss", "--json")  # fmt: skip
    check(
        "one --outcomes: its options are its own wherever they stand (the MCP server writes them in name order)",
        values(r).get("counts")
        == {"labelled": 3, "skipped": 0, "not_mature": 1, "unmatched": 0, "no_record": 1, "gone": 1},
        said(r)[-400:],
    )
    r = evh("label-coverage", *BASE, "--capture", "dec", "--outcomes", "iss", "--join", "fp=fp",
            "--outcomes", "gtrec", "--join", "fp=fp", "--outcomes-as", "iss")  # fmt: skip
    check(
        "two --outcomes read under one name are refused, naming it",
        r.returncode != 0 and "same name (iss)" in said(r),
        said(r)[-300:],
    )
    r = evh(
        "label-mutants",
        "--dataset-id",
        "tickets_v1",
        "--map",
        "rules2.yaml",
        "--capture",
        "dec",
        *two,
        "--json",
    )
    names2 = [
        m["mutant"]
        for m in (json.loads(r.stdout)["result"]["values"] if r.stdout.strip() else {}).get("mutants") or []
    ]
    check(
        "label-mutants over two joins: the windowed one's window moved, named by the capture it belongs to",
        any(n.startswith("the join's window moved an hour later (iss)") for n in names2)
        and not any("(gt)" in n and "window" in n for n in names2),
        said(r)[-400:],
    )

    # A later read: item 1 has matured (no issue for 14 days), item 2 recurred inside the window.
    capture("dec2", [decision(i, NOW - 20 * DAY if i == 1 else None) for i in range(5)])
    capture("iss2", [*issues, issue("is2b", 2, 3 * MIN, closed=NOW - DAY)])
    r = evh("label-coverage", *BASE, "--capture", "dec2", *join("iss2"), "--from-set", "s1", "--json")
    rel = values(r).get("relabel") or {}
    check(
        "label-coverage --from-set: what a relabel would add and change today",
        rel.get("would_add") == 1 and rel.get("would_change") == 1 and rel.get("no_longer_given") == 0,
        said(r)[-500:],
    )
    r = evh(
        "label-from-capture", *BASE, "--capture", "dec2", "--set", "s2", *join("iss2"),
        "--action-field", "action", "--from-set", "s1",
    )  # fmt: skip
    doc2 = labels_doc("s2") if r.returncode == 0 else {}
    rows2 = doc2.get("items") or {}
    relabel = (doc2.get("source") or {}).get("relabel") or {}
    check(
        "a relabel: keeps two, adds the matured one, marks the recurred one changed after maturing",
        (relabel.get("kept"), relabel.get("added"), relabel.get("changed_after_maturing")) == (2, 1, 1)
        and (rows2.get(items[2]) or {}).get("changed_after_maturing", {}).get("from") == "dismiss"
        and items[1] in rows2
        and "1 changed after maturing" in said(r),
        said(r)[-500:] + json.dumps(doc2.get("source"))[-400:],
    )
    capture("iss3", [issue("is0", 0, 5 * MIN, reason="not_planned"), *issues[1:]])
    again = (
        "label-from-capture",
        *BASE,
        "--capture",
        "dec",
        "--set",
        "s3",
        *join("iss3"),
        "--action-field",
        "action",
    )
    r = evh(*again, "--from-set", "s1")
    check(
        "a relabel: a label no rule gives any more is refused, never dropped silently",
        r.returncode != 0 and "a label never vanishes silently" in said(r),
        said(r)[-300:],
    )
    r = evh(*again, "--from-set", "s1", "--keep-vanished")
    check(
        "--keep-vanished keeps it, and says so",
        r.returncode == 0 and "no longer given today, kept" in said(r),
        said(r)[-300:],
    )

    # X3: a capture holding the very objects the items name (GlitchTip's issues): a fingerprint none carries is gone.
    capture("gt", [{"id": f"g{i}", "created_at": iso(t[i]), "fp": f"fp{i}", "body": "x"} for i in (0, 1, 2)])
    r = evh(
        "label-coverage",
        *BASE,
        "--capture",
        "dec",
        "--outcomes",
        "gt",
        "--join",
        "fp=fp",
        "--gone-if-missing",
        "--json",
    )
    check(
        "--gone-if-missing: an item whose object the source no longer holds is gone, never labelled",
        (values(r).get("counts") or {}).get("gone") == 2
        and (values(r).get("counts") or {}).get("labelled") == 0,
        said(r)[-400:],
    )

    # L3: production's own arm scores the action-bound item; a variant that acted otherwise does not.
    later = {
        "id": items[5],
        "created_at": iso(NOW),
        "fp": "fp5",
        "first_seen": "s5",
        "action": "dismiss",
        "body": "x",
    }
    capture("decall", [*decisions, later])
    r = evh(
        "arm-from-capture",
        "--dataset-id",
        "tickets_v1",
        "--capture",
        "decall",
        "--as",
        "prod_v1",
        "--field",
        "action",
    )
    _runstore.write_text(
        proj,
        "systems/echo_v1.yaml",
        "system_id: echo_v1\nparams:\n  provider: echo\n",
    )
    r2 = evh("run", "--system", "echo_v1", "--dataset", "tickets_v1")
    check(
        "setup: production's arm and an echo variant",
        r.returncode == r2.returncode == 0,
        said(r)[-300:] + said(r2)[-300:],
    )
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "s1")
    check(
        "rescore against the set: the variant is not scored on the action-bound item, and says so; production is",
        r.returncode == 0
        and said(r).count("not scorable under this variant") == 1
        and "echo_v1" in said(r).split("not scorable under this variant")[0].rsplit("note:", 1)[-1],
        said(r)[-800:],
    )
    _runstore.write_text(
        proj,
        "systems/echo_l_v1.yaml",
        "system_id: echo_l_v1\nparams:\n  provider: echo\n",
    )
    r = evh("run", "--system", "echo_l_v1", "--dataset", "tickets_v1", "--labels", "s1")
    check(
        "run --labels: a variant run says the item it is not scored on, and records it",
        r.returncode == 0 and "1 item(s) not scorable under this variant" in said(r),
        said(r)[-500:],
    )
    # X1: the labeller mutation-tested.
    (proj / "mut.py").write_text(
        "def mutants(rules):\n"
        "    out = [dict(r) for r in rules]\n"
        "    out[0] = {**out[0], 'when': {'iss.closed_at': 'completed'}}\n"
        "    return [('the close reason read from the wrong field', out)]\n"
    )
    r = evh("label-mutants", "--dataset-id", "tickets_v1", "--capture", "dec", "--map", "rules.yaml", *join("iss"),
            "--mutants", "mut.py", "--json")  # fmt: skip
    try:
        mv = json.loads(r.stdout)["result"]["values"]
    except ValueError:
        mv = {}
    names = {m["mutant"]: m["moved"] for m in mv.get("mutants") or []}
    check(
        "label-mutants: 7 mutants; the field, window and project mutants kill; the age shifts and the swap survive "
        "(the labelled items are far from the window's edge, and the two rules never take the same item), exit 6",
        r.returncode == 6
        and len(names) == 7
        and sorted(mv.get("survived") or []) == sorted(n for n, k in names.items() if k == 0)
        and len(mv.get("survived") or []) == 3
        and all("min_age_days" in n or "swapped" in n for n in mv.get("survived") or [])
        and names.get("the close reason read from the wrong field (the project's)", 0) > 0
        and any("window moved" in n and k > 0 for n, k in names.items()),
        said(r)[-900:],
    )
    # The fleet's beta (F6): a join mutant with a key the harness does not read ran the unchanged join and was
    # reported SURVIVED. Refused now, the key named.
    (proj / "mut_bad.py").write_text(
        "def join_mutants(join):\n    return [('the item side keyed on the wrong field', {**join, 'item_field': 'ticket'})]\n"
    )
    r = evh("label-mutants", "--dataset-id", "tickets_v1", "--capture", "dec", "--map", "rules.yaml", *join("iss"),
            "--mutants", "mut_bad.py")  # fmt: skip
    check(
        "label-mutants: a project join mutant with a key the harness does not read is refused, the key named",
        r.returncode not in (0, 6) and "item_field" in said(r) and "SURVIVED" not in said(r),
        said(r)[-500:],
    )
    r = evh("validate")
    check("validate passes with the new label fields", r.returncode == 0, r.stdout[-600:])
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
