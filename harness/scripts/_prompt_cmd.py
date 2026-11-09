"""The prompt commands (RFC-028): versions read, compared, recorded and exported.

evh prompts [NAME] [--json]                 names; or a name's versions, lineage and the runs that used each
evh prompt-diff A B [--json]                two versions' text as a unified diff, and the runs of each
evh prompt-version NAME (--from-file F | --text T) [--parent ID] --note "..." [--by WHO]
evh prompt-export ID --to PATH              a version's bytes written out, for a person to commit
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _prompts, _store
from evaluation_harness._common import die, evh_prog


def _runs_of() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(prompt name, sha256) -> the runs whose fingerprint names that version, with their primary score."""
    from evaluation_harness import _runs  # noqa: PLC0415

    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for d, m in _runs.runs_on():
        used = (((m.get("fingerprint") or {}).get("settings") or {}).get("prompts")) or {}
        if not isinstance(used, dict):
            continue
        prim = m.get("primary_metric")
        score = (m.get("scores") or {}).get(prim) if prim else None
        for name, sha in used.items():
            out.setdefault((name, str(sha)), []).append(
                {
                    "run_id": d.name,
                    "config_id": m.get("config_id"),
                    "dataset_id": m.get("dataset_id"),
                    "metric": prim,
                    "score": score,
                }
            )
    return out


def _version_or_die(vid: str) -> tuple[dict[str, Any], bytes]:
    try:
        name, sha16 = _prompts.split_id(vid)
        data = _prompts.text_of(vid)
    except (ValueError, FileNotFoundError):
        die(f"no prompt version {vid!r} (evh prompts lists them)", "not-found")
    doc = next((v for v in _prompts.versions(name) if v["sha256"].startswith(sha16)), {})
    return doc, data


def prompts(argv: list[str]) -> int:
    """evh prompts: every name, or one name's versions with their lineage and runs."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="prompt versions (RFC-028)")
    ap.add_argument("name", nargs="?", help="one prompt name (default: every name)")
    ap.add_argument("--json", action="store_true", help="the same as one JSON object")
    a = ap.parse_args(argv)
    with _jsonout.collect("prompts", a.json):
        used = _runs_of()
        if not a.name:
            rows = []
            for name in _prompts.names():
                vs = _prompts.versions(name)
                rows.append({"name": name, "versions": len(vs), "latest": vs[-1]["id"] if vs else None,
                             "runs": sum(len(used.get((name, v["sha256"]), [])) for v in vs)})  # fmt: skip
            for r in rows:
                print(
                    f"{r['name']:<48} {r['versions']:>3} version(s)  {r['runs']:>4} run(s)  latest {r['latest']}"
                )
            if not rows:
                print("no prompt versions yet: declare `prompts:` in a config, and its next run records them")
            _jsonout.value("prompts", rows)
            return 0
        vs = _prompts.versions(a.name)
        if not vs:
            die(f"no prompt named {a.name!r} (evh prompts lists the names)", "not-found")
        out = []
        for v in vs:
            runs = used.get((a.name, v["sha256"]), [])
            who = (v.get("actor") or {}).get("name") or "?"
            print(f"v{v['n']}  {v['id']}  {v.get('created_at')}  by {who}  parent {v.get('parent') or '-'}")
            print(f"     {v.get('note') or ''}")
            for r in runs:
                print(f"     run {r['run_id']}  {r['metric']}={r['score']}")
            out.append({**v, "runs": runs})
        _jsonout.value("versions", out)
    return 0


def diff(argv: list[str]) -> int:
    """evh prompt-diff: two versions' text as a unified diff, and the runs of each."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="two prompt versions compared (RFC-028)")
    ap.add_argument("a", help="a version id, <name>/<sha16>")
    ap.add_argument("b", help="the other")
    ap.add_argument("--json", action="store_true", help="the same as one JSON object")
    a = ap.parse_args(argv)
    with _jsonout.collect("prompt-diff", a.json):
        da, ta = _version_or_die(a.a)
        db, tb = _version_or_die(a.b)
        lines = list(
            difflib.unified_diff(
                ta.decode("utf-8", "replace").splitlines(keepends=True),
                tb.decode("utf-8", "replace").splitlines(keepends=True),
                fromfile=a.a,
                tofile=a.b,
            )
        )
        sys.stdout.write("".join(lines) if lines else "the two versions are the same text\n")
        used = _runs_of()
        for vid, d in ((a.a, da), (a.b, db)):
            runs = used.get((_prompts.split_id(vid)[0], d.get("sha256", "")), [])
            print(
                f"\n{vid}: {len(runs)} run(s)"
                + "".join(f"\n  {r['run_id']}  {r['metric']}={r['score']}" for r in runs)
            )
        _jsonout.values({"a": a.a, "b": a.b, "diff": "".join(lines)})
    return 0


def version(argv: list[str]) -> int:
    """evh prompt-version: a version recorded from a file or text, with its parent and a note."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="record a prompt version (RFC-028)")
    ap.add_argument("name", help="the prompt's name, as configs declare it")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-file", type=Path, help="the version's bytes, from this file")
    src.add_argument("--text", help="the version's text")
    ap.add_argument("--parent", help="the version it was made from (<name>/<sha16>)")
    ap.add_argument("--note", required=True, help="what changed and why")
    ap.add_argument("--json", action="store_true", help="the version's record as JSON")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("prompt-version", a.json, live=sys.stderr):
        _prompts.check_name(a.name, "prompt-version")
        if a.from_file is not None:
            if not _store.is_file(a.from_file):
                die(f"--from-file {a.from_file}: no such file", "not-found")
            data, ext, where = _store.read_bytes(a.from_file), a.from_file.suffix, str(a.from_file)
        else:
            data, ext, where = a.text.encode("utf-8"), "", "--text"
        doc, new = _prompts.record(
            a.name, data, source={"path": where}, note=a.note, parent=a.parent, extension=ext
        )
        if not new:
            print(f"{doc['id']} is already recorded ({doc.get('created_at')}): these bytes are that version")
        else:
            print(f"{doc['id']}  recorded" + (f", from {a.parent}" if a.parent else ""))
        _jsonout.values({"version": doc, "new": new})
    return 0


def export(argv: list[str]) -> int:
    """evh prompt-export: a version's bytes written to a path, for a person to commit."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description="write a prompt version out (RFC-028)")
    ap.add_argument("id", help="the version, <name>/<sha16>")
    ap.add_argument("--to", type=Path, required=True, help="where to write it")
    ap.add_argument("--json", action="store_true", help="what was written, as JSON")
    a = ap.parse_args(argv)
    with _jsonout.collect("prompt-export", a.json, live=sys.stderr):
        _doc, data = _version_or_die(a.id)
        target = a.to.resolve()
        if any(part in ("site-packages", "dist-packages") for part in target.parts):
            die(
                f"--to {a.to}: inside an installed package; export into a checkout and commit it there",
                "not-allowed",
            )
        import subprocess  # noqa: PLC0415  # nosec B404 - git, read-only

        if _store.exists(target):
            r = subprocess.run(  # nosec B603 B607 - git, read-only, no shell
                ["git", "-C", str(target.parent), "status", "--porcelain", "--", target.name],
                capture_output=True, text=True, check=False,
            )  # fmt: skip
            if r.returncode == 0 and r.stdout.strip():
                die(f"--to {a.to}: has uncommitted changes; commit or discard them first", "would-overwrite")
        _store.write_bytes(target, data)
        print(f"{a.id} -> {a.to} ({len(data)} bytes)")
        _jsonout.values({"id": a.id, "to": str(a.to), "bytes": len(data)})
    return 0


def run(sub: str) -> int:
    """One of the prompt commands, by name."""
    return {"prompts": prompts, "diff": diff, "version": version, "export": export}[sub](sys.argv[1:])
