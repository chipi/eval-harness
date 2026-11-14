"""The code a replay runs (RFC-030): a model record of `kind: code` (the fleet's feedback 27), read for a replay.

`data/models/<id>.yaml` with `kind: code` names the system's repository (`repo`) and its `versions`, each a `commit`,
when it was `deployed` in production (`[{from, to}]`, `to` absent while it runs). How faithfully a replay reproduced
a version is in the faithfulness records (model/faithfulness), not here. A replay reads each version from a local git
checkout: `checkout:` when `repo` is a URL, else `repo` itself. It runs each item at the commit deployed when the item
happened, from a copy of that commit unpacked with `git archive` under `.build/code/<id>/<commit>/`: nothing is
written into the checkout, and a copy is clean by construction.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _fields, _store


def copies_dir(model_id: str) -> Path:
    """.build/code/<id>/: one unpacked copy per commit, kept for the next run."""
    return _common.ROOT / ".build" / "code" / model_id


def periods(rec: dict[str, Any]) -> tuple[list[tuple[Any, Any, str]], list[str]]:
    """([(from, to or None, commit)] sorted by from, problems): the record's deployed periods as moments. A period
    whose times are not date-times with an offset, that ends before it starts, or that overlaps another is a
    problem: a replay could not say which commit ran then."""
    out, bad = [], []
    for v in rec.get("versions") or []:
        for p in v.get("deployed") or []:
            start = _fields.moment(str(p.get("from", "")))
            end = _fields.moment(str(p["to"])) if p.get("to") else None
            if start is None or (p.get("to") and end is None):
                bad.append(f"version {v.get('commit')}: deployed {p} is not a date-time with an offset")
                continue
            if end is not None and end <= start:
                bad.append(f"version {v.get('commit')}: deployed to {p['to']} is not after from {p['from']}")
                continue
            out.append((start, end, str(v["commit"])))
    out.sort(key=lambda x: x[0])
    for (_s1, e1, c1), (s2, _e2, c2) in zip(out, out[1:]):
        if e1 is None or s2 < e1:
            bad.append(f"versions {c1[:12]} and {c2[:12]} were both deployed at {s2.isoformat()}")
    return out, bad


def load(model_id: str) -> dict[str, Any]:
    """The code record a replay names (`model_record:`), its periods checked; dies naming what is wrong."""
    from evaluation_harness import _models  # noqa: PLC0415

    rec = _models.find(_common.DATA, model_id)
    if rec is None:
        _common.die(
            f"no model record {model_id!r} ({_models.records_dir(_common.DATA) / (model_id + '.yaml')})",
            "not-found",
        )
    if rec.get("kind") != "code":
        _common.die(
            f"model record {model_id} is not kind: code, so a replay has no commits to run", "invalid-file"
        )
    if not rec.get("versions"):
        _common.die(f"code record {model_id} lists no versions", "invalid-file")
    # A key in the wrong place was read as absent (the fleet's beta: `dated_by` on a version, not on its deployment,
    # dated nothing and said nothing): the record is held to its schema before anything reads it.
    try:
        import jsonschema  # noqa: PLC0415

        schema = json.loads(_store.read_text(_common.SCHEMAS / "model.schema.json", encoding="utf-8"))
        errs = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '(top)'}: {e.message[:120]}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(rec)
        ]
    except ImportError:  # pragma: no cover - V1 says jsonschema is missing
        errs = []
    if errs:
        hint = (
            " (dated_by goes on a deployment: versions[].deployed[].dated_by)"
            if any("dated_by" in e for e in errs)
            else ""
        )
        _common.die(f"code record {model_id}: " + "; ".join(errs[:5]) + hint, "invalid-file")
    _p, bad = periods(rec)
    if bad:
        _common.die(f"code record {model_id}: " + "; ".join(bad), "invalid-file")
    return rec


def versions_sha256(rec: dict[str, Any]) -> str:
    """One hash over what says which commit ran when (each version's commit and deployed periods): an edit to a
    period or a commit moves it."""
    part = [
        {"commit": v.get("commit"), "deployed": v.get("deployed") or []} for v in rec.get("versions") or []
    ]
    return hashlib.sha256(json.dumps(part, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def checkout(rec: dict[str, Any]) -> Path:
    """The local git checkout versions are read from: `checkout`, else `repo` when it is a path (relative to the
    project root)."""
    raw = str(rec.get("checkout") or rec.get("repo") or "")
    if re.match(r"^[a-z+]+://|^[^/]+@[^/]+:", raw):
        _common.die(
            f"code record {rec.get('model_id')}: repo {raw} is not a local checkout; add checkout: <a clone's path>",
            "not-configured",
        )
    p = Path(raw)
    return p if p.is_absolute() else _common.ROOT / p


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=120, check=False)


def full_commit(rec: dict[str, Any], commit: str) -> str:
    """`commit` (a sha, short or full, or a ref) as the full sha in the record's checkout; dies when it has none."""
    where = checkout(rec)
    r = _git(where, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    sha = r.stdout.decode().strip() if r.returncode == 0 else ""
    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        _common.die(
            f"code record {rec['model_id']}: {where} has no commit {commit!r}"
            + ("" if (where / ".git").exists() else " (it is not a git checkout)"),
            "not-found",
        )
    return sha


def commit_at(rec: dict[str, Any], moment: Any) -> str | None:
    """The commit deployed at `moment` (an aware datetime), or None when no period covers it."""
    for start, end, commit in periods(rec)[0]:
        if start <= moment and (end is None or moment < end):
            return commit
    return None


def copy_of(rec: dict[str, Any], commit: str) -> Path:
    """The unpacked copy of `commit` (a full sha), made once under the `code:<id>` lock: two jobs never unpack the same
    commit at once, and a copy that exists is complete (it is unpacked beside and renamed into place)."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    dest = copies_dir(rec["model_id"]) / commit
    if (dest / ".evh-commit").is_file():
        return dest
    key = f"code:{rec['model_id']}"
    held = key in (os.environ.get("EVH_LOCKS") or "").split(",")
    who = os.environ.get("EVH_JOB") or f"pid {os.getpid()}"
    if held:
        _unpack(rec, commit, dest)
        return dest
    with _jobs.holding(
        [(key, True)], who, lambda k, h: print(f"  waiting for {k} (held by {h or 'another job'})")
    ):
        if not (dest / ".evh-commit").is_file():
            _unpack(rec, commit, dest)
    return dest


def _unpack(rec: dict[str, Any], commit: str, dest: Path) -> None:
    import shutil  # noqa: PLC0415

    r = _git(checkout(rec), "archive", "--format=tar", commit)
    if r.returncode != 0:
        _common.die(
            f"code record {rec['model_id']}: git archive {commit[:12]} failed: {r.stderr.decode()[:300]}",
            "failed",
        )
    tmp = dest.parent / f".{commit}.partial-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        # git archive of the record's own checkout; still, no member may land outside the copy: no absolute path, no
        # `..`, no link, and Python's data filter where it has one (3.10.12+, 3.11.4+).
        safe = [
            m
            for m in tar.getmembers()
            if not (m.name.startswith("/") or ".." in Path(m.name).parts or m.issym() or m.islnk())
        ]
        if hasattr(tarfile, "data_filter"):
            tar.extractall(tmp, members=safe, filter="data")  # nosec B202 - members checked above
        else:  # pragma: no cover - a Python before 3.10.12
            tar.extractall(tmp, members=safe)  # noqa: S202  # nosec B202 - members checked above
    (tmp / ".evh-commit").write_text(commit + "\n")
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)


def runs_of(model_id: str) -> list[dict[str, Any]]:
    """The runs whose fingerprint names this record (`deployment.code.record`): run_id, config_id, commits."""
    from evaluation_harness.model import runs as _model_runs  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    for rid in _model_runs.run_ids():
        rec = _model_runs.run(rid)
        if rec is None:
            continue
        code = ((rec.get("fingerprint") or {}).get("deployment") or {}).get("code") or {}
        if code.get("record") == model_id:
            out.append(
                {
                    "run_id": rec.get("run_id"),
                    "config_id": rec.get("config_id"),
                    "commits": code.get("commits"),
                    "faithfulness": rec.get("faithfulness"),
                }
            )
    return out
