"""Model records for a test, written as the project keeps them (RFC-032 step 2): a test says a model the way a person
reads it (its deployments inside it, each with its latest onboarding, its arms' smokes by config id), and gets the
files of today's layout: data/models/<id>.yaml, data/deployments/<id>/<deployment>.yaml with its order and its checks,
and the project's format.

    for rel, text in files_of(doc).items(): _runstore.write_text(project, rel, text)
    write(data_dir, doc)                    # a data folder on disk
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _format


def files_of(doc: dict[str, Any], smoke_deployment: dict[str, str] | None = None) -> dict[str, str]:
    """{path under data/: text}: the model's record, each deployment's, and the format. A smoke goes to the
    deployment `smoke_deployment` names for its config, else the model's first."""
    mid = doc["model_id"]
    deps = [d for d in doc.get("deployments") or [] if isinstance(d, dict)]
    out = {
        f"models/{mid}.yaml": yaml.safe_dump(
            {k: v for k, v in doc.items() if k not in ("deployments", "smokes")}, sort_keys=False
        )
    }
    checks: dict[str, list[dict[str, Any]]] = {str(d["id"]): [] for d in deps}
    for d in deps:
        if isinstance(d.get("onboarding"), dict):
            checks[str(d["id"])].append({"kind": "onboarding", **d["onboarding"]})
    for cid, smoke in (doc.get("smokes") or {}).items():
        dep = (smoke_deployment or {}).get(cid) or (str(deps[0]["id"]) if deps else None)
        if dep is None:
            raise ValueError(f"{mid}: a smoke ({cid}) needs a deployment to be a check of")
        checks[dep].append({"kind": "smoke", "config": cid, **smoke})
    for place, d in enumerate(deps):
        did = str(d["id"])
        rec = {"model_id": mid, "deployment_id": did, "order": place}
        rec.update({k: v for k, v in d.items() if k not in ("id", "onboarding")})
        rec["checks"] = sorted(checks[did], key=lambda c: str(c.get("at", "")))
        out[f"deployments/{mid}/{did}.yaml"] = yaml.safe_dump(rec, sort_keys=False)
    out[_format.NAME] = f"format: {_format.FORMAT}\n"
    return out


def write(data: Path, doc: dict[str, Any], smoke_deployment: dict[str, str] | None = None) -> None:
    """The model's files under a data folder on disk, replacing its deployments as they were."""
    shutil.rmtree(data / "deployments" / doc["model_id"], ignore_errors=True)
    for rel, text in files_of(doc, smoke_deployment).items():
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_text(text)


def stamp(data: Path) -> None:
    """The data folder's format, as `evh init` writes it."""
    data.mkdir(parents=True, exist_ok=True)
    (data / _format.NAME).write_text(f"format: {_format.FORMAT}\n")


def put(proj: Path | str, doc: dict[str, Any], smoke_deployment: dict[str, str] | None = None) -> None:
    """The model's files written into a test project's data/, in its store (files or SQLite), its deployments as
    they were replaced."""
    import _runstore  # noqa: PLC0415

    gone = f"deployments/{doc['model_id']}"
    for name in _runstore.listdir(proj, gone):
        _runstore.unlink(proj, f"{gone}/{name}")
    for rel, text in files_of(doc, smoke_deployment).items():
        _runstore.write_text(proj, rel, text)


def view(proj: Path | str, model_id: str) -> dict[str, Any]:
    """The model as the project reads it: its record with its deployments (each with its latest onboarding) and
    its arms' latest smokes."""
    import _runstore  # noqa: PLC0415
    from evaluation_harness import _models  # noqa: PLC0415

    with _runstore._InProject(proj) as data:
        return _models.find(data, model_id) or {}


def deployment(proj: Path | str, model_id: str, deployment_id: str) -> dict[str, Any]:
    """A deployment's own record as stored, its checks included."""
    import _runstore  # noqa: PLC0415

    return yaml.safe_load(_runstore.read_text(proj, f"deployments/{model_id}/{deployment_id}.yaml")) or {}
