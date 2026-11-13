#!/usr/bin/env python3
"""`evh capture-restore`: a capture's records, and the item files of the datasets made from it, read again.

    python tests/test_capture_restore.py

In a throwaway project, offline: records/ and the dataset's items deleted (as in a fresh clone) come back
byte for byte, and the dataset materializes; the source moved is found with --query KEY=VALUE; a source
that changed is refused with nothing written; a scrubbed capture has its recorded scrubber run again; a
records/ that does not match is replaced only with --force; no partial folder is left behind.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-capture-restore-"))
env = dict(os.environ, EVAL_HOME=str(proj))
env.pop("EVAL_DATA_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def snapshot(rel: str) -> dict:
    return {p[len(rel) + 1 :]: _runstore.read_bytes(proj, p) for p in _runstore.files_under(proj, rel)}


rows: list[dict] = [
    {"id": "r1", "body": "first ticket", "kind": "x", "created_at": "2026-10-01T10:00:00Z"},
    {
        "id": "r2",
        "body": "second ticket, mail bob@example.com",
        "kind": "y",
        "created_at": "2026-10-02T10:00:00Z",
    },
    {
        "id": "r3",
        "body": {"signal": "s", "probes": {"p": 1}},
        "kind": "x",
        "created_at": "2026-10-03T10:00:00Z",
    },
]
SCRUB = """
import json, re, sys
from pathlib import Path
for f in Path(sys.argv[1]).glob("*.json"):
    rec = json.loads(f.read_text())
    if isinstance(rec.get("body"), str):
        rec["body"] = re.sub(r"\\S+@\\S+", "[email]", rec["body"])
    f.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\\n")
"""

try:
    (proj / "data").mkdir()
    (proj / "export").mkdir()
    (proj / "export" / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (proj / "scrub.py").write_text(SCRUB)
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "export/rows.jsonl"}),
        "--capture",
        "c1",
    )
    r = r if r.returncode else evh("dataset-from-capture", "c1", "--dataset-id", "c1_v1")
    check("setup: a capture and a dataset made from it", r.returncode == 0, out(r)[-400:])
    cap = proj / "data" / "captures" / "c1"
    cap_rel, src_rel = "captures/c1", "sources/c1_v1"
    want_recs, want_items = snapshot(f"{cap_rel}/records"), snapshot(src_rel)

    # As a fresh clone has it: capture.json and the dataset file, no records and no item files.
    _runstore.rmtree(proj, f"{cap_rel}/records")
    _runstore.rmtree(proj, src_rel)
    r = evh("capture-restore", "--capture", "c1")
    check(
        "restore: the records and the dataset's item files come back byte for byte, and it says what it wrote",
        r.returncode == 0
        and snapshot(f"{cap_rel}/records") == want_recs
        and snapshot(src_rel) == want_items
        and "3 records restored" in r.stdout
        and "hashes ok" in r.stdout
        and "c1_v1: 3 item file(s) to data/sources/c1_v1" in r.stdout,
        out(r),
    )
    r = evh("dataset-materialize", "--dataset-id", "c1_v1")
    check("restore: the dataset materializes from what it wrote", r.returncode == 0, out(r)[-300:])

    # The source somewhere else: the recorded query no longer reaches it; --query points at the new place.
    (proj / "moved").mkdir()
    shutil.move(proj / "export" / "rows.jsonl", proj / "moved" / "rows.jsonl")
    _runstore.rmtree(proj, f"{cap_rel}/records")
    r = evh("capture-restore", "--capture", "c1")
    check(
        "the recorded source gone: refused, the importer's failure named, nothing written",
        r.returncode != 0 and "importer" in r.stderr and not _runstore.exists(proj, f"{cap_rel}/records"),
        out(r),
    )
    r = evh("capture-restore", "--capture", "c1", "--query", "path=moved/rows.jsonl")
    check(
        "--query KEY=VALUE replaces that key of the recorded query: restored, hashes ok",
        r.returncode == 0 and snapshot(f"{cap_rel}/records") == want_recs,
        out(r),
    )
    r = evh("capture-restore", "--capture", "c1", "--query", "nokey")
    check("--query without KEY=VALUE: refused", r.returncode != 0 and "KEY=VALUE" in r.stderr, out(r))

    # A source whose content changed: the record's hash no longer matches.
    changed = [dict(rows[0], body="first ticket, edited"), *rows[1:]]
    (proj / "moved" / "rows.jsonl").write_text("".join(json.dumps(x) + "\n" for x in changed))
    _runstore.rmtree(proj, f"{cap_rel}/records")
    _runstore.rmtree(proj, src_rel)
    r = evh("capture-restore", "--capture", "c1", "--query", "path=moved/rows.jsonl")
    check(
        "a source record that changed: refused, the record named, no records/ and no item files written",
        r.returncode != 0
        and "1 record(s) differ from what the capture recorded, e.g. r1" in r.stderr
        and not _runstore.exists(proj, f"{cap_rel}/records")
        and not _runstore.exists(proj, src_rel),
        out(r),
    )
    names = _runstore.listdir(proj, cap_rel)
    check(
        "no partial folder is left beside records/ after a refusal",
        not [n for n in names if n.startswith(".records.partial-")],
        names,
    )
    # A records/ that does not match is replaced only with --force.
    (proj / "moved" / "rows.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    evh("capture-restore", "--capture", "c1", "--query", "path=moved/rows.jsonl")
    _runstore.write_text(proj, f"{cap_rel}/records/r1.json", '{"id": "r1", "body": "tampered"}\n')
    r = evh("capture-restore", "--capture", "c1", "--query", "path=moved/rows.jsonl")
    check(
        "a records/ that does not match: refused without --force, the file left as it is",
        r.returncode != 0
        and "--force" in r.stderr
        and "tampered" in _runstore.read_text(proj, f"{cap_rel}/records/r1.json"),
        out(r),
    )
    r = evh("capture-restore", "--capture", "c1", "--query", "path=moved/rows.jsonl", "--force")
    check(
        "with --force: replaced by the records read again",
        r.returncode == 0 and snapshot(f"{cap_rel}/records") == want_recs,
        out(r),
    )

    # A scrubbed capture: the records as kept are the scrubbed ones; the recorded scrubber runs again.
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "moved/rows.jsonl"}),
        "--capture",
        "s1",
    )
    r = (
        r
        if r.returncode
        else evh("capture-scrub", "s1", "--command", f"{sys.executable} scrub.py {{records}}")
    )
    r = r if r.returncode else evh("dataset-from-capture", "s1", "--dataset-id", "s1_v1")
    check("setup: a scrubbed capture and a dataset made after the scrub", r.returncode == 0, out(r)[-400:])
    scap, ssrc = proj / "data" / "captures" / "s1", proj / "data" / "sources" / "s1_v1"
    scap_rel, ssrc_rel = "captures/s1", "sources/s1_v1"
    want_s, want_si = snapshot(f"{scap_rel}/records"), snapshot(ssrc_rel)
    _runstore.rmtree(proj, f"{scap_rel}/records")
    _runstore.rmtree(proj, ssrc_rel)
    r = evh("capture-restore", "--capture", "s1")
    check(
        "scrubbed: read again, scrubbed again with the recorded command, the records and items match",
        r.returncode == 0
        and snapshot(f"{scap_rel}/records") == want_s
        and snapshot(ssrc_rel) == want_si
        and "scrubbed again" in r.stdout
        and b"[email]" in want_s["r2.json"],
        out(r),
    )
    r = evh("capture-restore", "--capture", "nope")
    check("an unknown capture: refused", r.returncode != 0 and "no capture" in r.stderr, out(r))

    # The same in a project whose data is in its database (RFC-025): the records are built in a folder on disk (the
    # scrubber runs on real files), then written into the database; nothing is left on disk under data/. The folder
    # used to be made under data/, which does not exist there (advisor review, 2026-11-06).
    (proj / "config.yaml").write_text("store: sqlite\n")
    env["EVAL_STORE"] = "sqlite"
    r = evh("data-migrate", "--to", "sqlite")
    check("setup: the project moved into its database", r.returncode == 0, out(r)[-300:])
    sys.path.insert(0, str(HERE.parent))
    os.environ.update(EVAL_HOME=str(proj), EVAL_STORE="sqlite")
    from evaluation_harness import _store

    def db_snapshot(d: Path) -> dict:
        return {
            p.relative_to(d).as_posix(): _store.read_bytes(p)
            for p in sorted(_store.rglob(d, "*"))
            if _store.is_file(p)
        }

    _store.rmtree(scap / "records")
    _store.close()
    r = evh("capture-restore", "--capture", "s1")
    check(
        "sqlite: a scrubbed capture read again into the database, scrubbed with its recorded command, the records match;"
        " nothing left on disk",
        r.returncode == 0
        and db_snapshot(scap / "records") == want_s
        and "scrubbed again" in r.stdout
        and not _store.stray_files()
        and not any((proj / ".build" / "staging").glob("*")),
        out(r)[-400:],
    )
    _store.close()
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
