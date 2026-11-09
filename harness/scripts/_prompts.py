"""Prompt versions (RFC-028): the prompt files a config declares, versioned by their content.

    data/prompts/<name>/<sha16>.txt     the bytes as read (sha16: the first 16 hex digits of their sha256)
    data/prompts/<name>/<sha16>.json    id, sha256, parent, note, actor, created_at, source, extension

A config declares `prompts: {name: {file: path}}` and/or `prompt_root: {name, path, include, vary}`. At each run
`resolve` hashes every declared file, records a version for bytes not seen before (written once: the name is the
content's hash, so two runs recording the same bytes write one record), and gives back what the fingerprint and the
adapter need. A root's varied files are given to the adapter in a per-run copy of the root, so no tracked file is
ever written.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

NAME = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")
#: Never part of a root's digest: caches and dotfiles differ between Python versions and machines.
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def prompts_dir() -> Path:
    """Where the versions live: data/prompts/ (in either store)."""
    return _common.DATA / "prompts"


def sha256(data: bytes) -> str:
    """The hex sha256 of a prompt's bytes."""
    return hashlib.sha256(data).hexdigest()


def _project_path(path: Any) -> Path:
    p = Path(str(path))
    return p if p.is_absolute() else _common.ROOT / p


def check_name(name: str, where: str) -> None:
    """A prompt name: path segments of letters, digits, `_`, `.`, `-`, joined by `/`."""
    if not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name.split("/"):
        _common.die(
            f"{where}: prompt name {name!r}: segments of letters, digits, '_', '.' or '-', joined by '/'",
            "invalid-file",
        )


def version_id(name: str, sha: str) -> str:
    """A version's id: `<name>/<sha16>`."""
    return f"{name}/{sha[:16]}"


def split_id(vid: str) -> tuple[str, str]:
    """`<name>/<sha16>` as (name, sha16); a ValueError when it is not one."""
    name, _, sha16 = str(vid).rpartition("/")
    if not name or not re.fullmatch(r"[0-9a-f]{16}", sha16):
        raise ValueError(f"not a prompt version id (<name>/<16 hex digits>): {vid!r}")
    return name, sha16


def record(
    name: str,
    data: bytes,
    *,
    source: dict[str, Any],
    note: str,
    parent: str | None = None,
    extension: str = "",
) -> tuple[dict[str, Any], bool]:
    """The version these bytes are, recorded when new: (its record, whether this call recorded it)."""
    from evaluation_harness import _actor  # noqa: PLC0415

    sha = sha256(data)
    d = prompts_dir() / name
    meta_path, text_path = d / f"{sha[:16]}.json", d / f"{sha[:16]}.txt"
    if _store.is_file(meta_path):
        return json.loads(_store.read_text(meta_path, encoding="utf-8")), False
    if parent is not None:
        split_id(parent)
        if not _store.is_file(prompts_dir() / split_id(parent)[0] / f"{split_id(parent)[1]}.json"):
            _common.die(f"--parent {parent}: no such prompt version", "not-found")
    doc = {
        "id": version_id(name, sha),
        "name": name,
        "sha256": sha,
        "parent": parent,
        "note": note,
        "actor": _actor.actor(),
        "created_at": _common.now(),
        "source": source,
        "extension": extension,
        "bytes": len(data),
    }
    _store.mkdir(d, parents=True, exist_ok=True)
    if not _store.is_file(text_path):
        try:
            _store.create_new(text_path, data)
        except FileExistsError:
            pass
    try:
        _store.create_new(meta_path, (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    except FileExistsError:  # another run recorded the same bytes a moment ago: the same version
        return json.loads(_store.read_text(meta_path, encoding="utf-8")), False
    return doc, True


def versions(name: str) -> list[dict[str, Any]]:
    """A name's versions, oldest first, each with its display number `n`."""
    d = prompts_dir() / name
    out = []
    for p in _store.glob(d, "*.json") if _store.is_dir(d) else []:
        try:
            out.append(json.loads(_store.read_text(p, encoding="utf-8")))
        except ValueError:
            continue
    out.sort(key=lambda v: (str(v.get("created_at")), str(v.get("id"))))
    for i, v in enumerate(out, 1):
        v["n"] = i
    return out


def names() -> list[str]:
    """Every prompt name that has a version, sorted."""
    root = prompts_dir()
    if not _store.is_dir(root):
        return []
    found = {str(p.parent.relative_to(root).as_posix()) for p in _store.rglob(root, "*.json")}
    return sorted(found)


def text_of(vid: str) -> bytes:
    """A version's bytes; FileNotFoundError when it is not recorded."""
    name, sha16 = split_id(vid)
    p = prompts_dir() / name / f"{sha16}.txt"
    if not _store.is_file(p):
        raise FileNotFoundError(vid)
    return _store.read_bytes(p)


def _git_commit(path: Path) -> str | None:
    import subprocess  # noqa: PLC0415  # nosec B404 - git, read-only

    try:
        r = subprocess.run(  # nosec B603 B607 - git, read-only, no shell
            ["git", "-C", str(path.parent), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def _root_files(root: Path, include: list[str]) -> list[str]:
    """The root's files its digest covers: those `include` matches, caches and dotfiles left out, sorted."""
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if any(x in SKIP_DIRS or x.startswith(".") for x in parts) or rel.endswith(SKIP_SUFFIXES):
            continue
        if include and not any(fnmatch.fnmatch(rel, g) for g in include):
            continue
        out.append(rel)
    return out


def root_digest(root: Path, include: list[str]) -> str:
    """One sha256 over a root's files: their sorted relative paths and each file's sha256."""
    body = [(rel, sha256((root / rel).read_bytes())) for rel in _root_files(root, include)]
    return hashlib.sha256(json.dumps(body).encode()).hexdigest()


def resolve(cfg: dict[str, Any], config_path: Any, run_label: str) -> dict[str, Any] | None:
    """The config's declared prompts at this run: every file hashed and its version found or recorded, and (for a
    root) a per-run copy made. None when the config declares none. Returns {"settings": what the fingerprint's
    settings take, "params": what the adapter is given, "copy": the per-run copy to remove after, or None}."""
    prompts = cfg.get("prompts") or {}
    root_spec = cfg.get("prompt_root")
    if not prompts and not root_spec:
        return None
    if not isinstance(prompts, dict):
        _common.die(f"{config_path}: prompts: a mapping of name to {{file: path}}", "invalid-file")
    given: dict[str, dict[str, Any]] = {}
    shas: dict[str, str] = {}

    def take(name: str, path: Path, shown: str) -> None:
        check_name(name, str(config_path))
        if not path.is_file():
            _common.die(f"{config_path}: prompt {name}: no file at {shown}", "not-found")
        data = path.read_bytes()
        doc, new = record(
            name,
            data,
            source={"path": shown, "commit": _git_commit(path)},
            note=f"recorded by a run of {run_label}",
            extension=path.suffix,
        )
        if new:
            print(f"  prompt {name}: new version {doc['id']}")
        shas[name] = doc["sha256"]
        given[name] = {
            "text": data.decode("utf-8", errors="replace"),
            "path": str(path),
            "version": doc["id"],
            "sha256": doc["sha256"],
        }

    for name, spec in prompts.items():
        if not isinstance(spec, dict) or not spec.get("file"):
            _common.die(f"{config_path}: prompts.{name}: {{file: <path>}}", "invalid-file")
        take(name, _project_path(spec["file"]), str(spec["file"]))
    settings: dict[str, Any] = {"prompts": shas} if shas else {}
    params: dict[str, Any] = {"prompts": given} if given else {}
    copy = None
    if root_spec:
        if not isinstance(root_spec, dict) or not root_spec.get("name") or not root_spec.get("path"):
            _common.die(f"{config_path}: prompt_root: {{name, path, vary, include}}", "invalid-file")
        root = _project_path(root_spec["path"])
        if not root.is_dir():
            _common.die(
                f"{config_path}: prompt_root.path {root_spec['path']}: no such directory", "not-found"
            )
        include = list(root_spec.get("include") or [])
        for rel in root_spec.get("vary") or []:
            if not (root / rel).is_file():
                _common.die(
                    f"{config_path}: prompt_root.vary {rel}: not in {root_spec['path']} (the copy never adds a file)",
                    "not-found",
                )
            take(f"{root_spec['name']}/{rel}", root / rel, f"{root_spec['path']}/{rel}")
        import secrets  # noqa: PLC0415

        copy = _common.ROOT / ".build" / "prompt-roots" / f"{run_label}-{secrets.token_hex(3)}"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        settings["prompt_root_sha256"] = root_digest(copy, include)
        params["prompt_root"] = str(copy)
        settings["prompts"] = shas
    return {"settings": settings, "params": params, "copy": copy}


def remove_copy(resolved: dict[str, Any] | None) -> None:
    """The per-run copy of a root, removed when the run ends."""
    if resolved and resolved.get("copy"):
        shutil.rmtree(resolved["copy"], ignore_errors=True)


def published() -> bool:
    """Whether the project publishes its prompts' text on the catalog's pages: `catalog: {publish: [prompts]}` in its
    config.yaml (RFC-028; owner, 2026-11-09). Off by default: prompts may be private and pages may be public."""
    import yaml  # noqa: PLC0415

    cfg = _common.ROOT / "config.yaml"
    try:
        doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {} if cfg.is_file() else {}
    except (OSError, yaml.YAMLError):
        return False
    pub = ((doc.get("catalog") or {}) if isinstance(doc, dict) else {}).get("publish") or []
    return isinstance(pub, list) and "prompts" in pub
