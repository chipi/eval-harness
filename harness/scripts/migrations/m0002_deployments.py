"""Format 2, RFC-032 step 2: a model's deployments become records of their own, data/deployments/<model>/<id>.yaml,
each with the dated history of its checks: its onboarding becomes its first check, and each arm smoke the model record
kept (by config id) becomes a check of the deployment its config names. The model record keeps its own facts.

It reads the stored files as they are, not through the model: the configs are found as format 1 kept them (data/configs,
validate.json's `configs` globs, a study's trials). A smoke whose deployment is not a fact (its config names none and the
model has several) is refused, naming it: nothing is guessed."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

NUMBER = 2
ABOUT = "RFC-032 step 2: deployments apart from models, each with its checks (onboarding, arm smokes) as dated history"


def _yaml_rt() -> Any:
    from ruamel.yaml import YAML  # noqa: PLC0415

    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _configs() -> dict[str, dict[str, Any]]:
    """{config_id: config} as format 1 found the arms."""
    import json  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    data, root = _common.DATA, _common.ROOT
    found = set(_store.glob(data / "configs", "*.yaml")) if _store.is_dir(data / "configs") else set()
    studies = data / "studies"
    if _store.is_dir(studies):
        found |= {f for f in _store.glob(studies, "*/*/t*.yaml") if _store.is_file(f)}
        found |= {f for f in _store.glob(studies, "*/*/confirm/*.yaml") if _store.is_file(f)}
    policy = data / "validate.json"
    if _store.is_file(policy):
        for pattern in json.loads(_store.read_text(policy, encoding="utf-8")).get("configs") or []:
            found |= {f for f in _store.glob(root, pattern) if _store.is_file(f)}
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(found):
        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(doc, dict) and doc.get("config_id"):
            out.setdefault(str(doc["config_id"]), doc)
    return out


def _plan() -> tuple[list[tuple[Path, str, list[tuple[Path, dict[str, Any]]]]], list[str]]:
    """Each model record to rewrite (its new text) with its deployments' records, and the smokes that cannot be
    placed."""
    import yaml  # noqa: PLC0415

    base = _common.DATA / "models"
    if not _store.is_dir(base):
        return [], []
    configs = None
    plan, refused = [], []
    for f in sorted(_store.glob(base, "*.yaml")):
        text = _store.read_text(f, encoding="utf-8")
        plain = yaml.safe_load(text) or {}
        if not isinstance(plain, dict) or ("deployments" not in plain and "smokes" not in plain):
            continue
        mid = str(plain.get("model_id") or f.stem)
        deps = [d for d in plain.get("deployments") or [] if isinstance(d, dict) and d.get("id")]
        checks: dict[str, list[dict[str, Any]]] = {str(d["id"]): [] for d in deps}
        for d in deps:
            if isinstance(d.get("onboarding"), dict):
                checks[str(d["id"])].append({"kind": "onboarding", **d["onboarding"]})
        for cid, smoke in (plain.get("smokes") or {}).items():
            configs = configs if configs is not None else _configs()
            named = (configs.get(cid) or {}).get("deployment")
            dep = str(named) if named else (next(iter(checks)) if len(checks) == 1 else None)
            if dep not in checks:
                refused.append(
                    f"{f.name}: the smoke of {cid} names no deployment of {mid} "
                    f"({'its config names ' + repr(named) if named else 'its config names none, and the model has ' + str(len(checks))}): "
                    "set the config's `deployment:` and migrate again"
                )
                continue
            checks[dep].append({"kind": "smoke", "config": cid, **smoke})
        records = []
        for place, d in enumerate(deps):
            did = str(d["id"])
            rec = {"model_id": mid, "deployment_id": did, "order": place}
            rec.update({k: v for k, v in d.items() if k not in ("id", "onboarding")})
            rec["checks"] = sorted(checks[did], key=lambda c: str(c.get("at", "")))
            records.append((_common.DATA / "deployments" / mid / f"{did}.yaml", rec))
        y = _yaml_rt()
        doc = y.load(text)
        doc.pop("deployments", None)
        doc.pop("smokes", None)
        buf = io.StringIO()
        y.dump(doc, buf)
        plan.append((f, buf.getvalue(), records))
    return plan, refused


def run(dry_run: bool) -> None:
    """Move the deployments out, or say what it would move; refuse first, writing nothing, if a smoke has no place."""
    import yaml  # noqa: PLC0415

    plan, refused = _plan()
    if refused:
        _common.die("a smoke's deployment is not known:\n  " + "\n  ".join(refused), "invalid-file")
    n_dep = sum(len(r) for _f, _t, r in plan)
    n_chk = sum(len(rec["checks"]) for _f, _t, r in plan for _p, rec in r)
    if not plan:
        print("  0 changed: already in this format")
        return
    print(
        f"  {len(plan)} model record(s): {n_dep} deployment(s) to their own records, {n_chk} check(s) kept as their history"
    )
    if dry_run:
        return
    for f, text, records in plan:
        for path, rec in records:
            _store.mkdir(path.parent, parents=True, exist_ok=True)
            _common.write_text_atomic(
                path, yaml.safe_dump(rec, sort_keys=False, allow_unicode=True, width=110)
            )
        _common.write_text_atomic(f, text)
