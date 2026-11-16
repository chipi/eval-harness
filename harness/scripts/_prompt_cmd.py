"""The prompt operations' bodies (RFC-028; RFC-032 P3: they run as jobs, ops/study_jobs.py).

(`evh prompt-list`, `prompt-show` and `prompt-diff` read them: ops/prompts.py)
evh prompt-version NAME (--from-file F | --text T) [--parent ID] --note "..." [--by WHO]
evh prompt-export ID --to PATH              a version's bytes written out, for a person to commit
"""

from __future__ import annotations

from typing import Any

from evaluation_harness import _jsonout, _prompts, _store
from evaluation_harness._common import die
from evaluation_harness.ops import legacy


def _runs_of() -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(prompt name, sha256) -> the runs whose fingerprint names that version, with their primary score."""
    from evaluation_harness import _runs  # noqa: PLC0415

    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    full = {}  # a version id -> its sha256, for the versions runs name (RFC-032 step 4b)
    for _d, m in _runs.runs_on():
        used = dict((((m.get("fingerprint") or {}).get("settings") or {}).get("prompts")) or {})
        for name, vid in (m.get("prompt_versions") or {}).items():
            if vid not in full:
                full[vid] = next((v["sha256"] for v in _prompts.versions(name) if v["id"] == vid), vid)
            used.setdefault(name, full[vid])
        prim = m.get("primary_metric")
        score = (m.get("scores") or {}).get(prim) if prim else None
        for name, sha in used.items():
            out.setdefault((name, str(sha)), []).append(
                {
                    "run_id": m["run_id"],
                    "system_id": m.get("system_id"),
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
        die(f"no prompt version {vid!r} (evh prompt-list lists them)", "not-found")
    doc = next((v for v in _prompts.versions(name) if v["sha256"].startswith(sha16)), {})
    return doc, data


def version_body(**inputs: Any) -> int:
    """evh prompt-version: a version recorded from a file or text, with its parent and a note."""
    a = legacy.namespace(inputs, "prompt-version")
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


def export_body(**inputs: Any) -> int:
    """evh prompt-export: a version's bytes written to a path, for a person to commit."""
    a = legacy.namespace(inputs, "prompt-export")
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
