"""Format 3, RFC-032 step 3: configs become systems. A system is what is evaluated, with no dataset, goal or round
(a run names those); the configs that differ only in their dataset become one system. Every live reference to a
config id that changes is renamed with it; frozen evidence keeps the ids it was made under (owner, 2026-11-13).

It reads the stored files as format 2 kept them, not through the model: the configs are data/configs, a study's trials
and confirmations, the globs validate.json's `configs` names and the folders config.yaml's `configs:` lists.

- Each config becomes `<folder>/<system_id>.yaml` (a folder named `configs` becomes `systems`), `config_id` its
  `system_id`, its `dataset_id`, `goal` and `round` gone, its comments kept.
- A group of configs in one folder whose ids differ only by a dataset token (`_n200`, `_n100`, `_dm200`) and a version,
  on different datasets and alike in every other key, becomes one system: its id the group's without the token, with
  the highest version. A group on different datasets that differs in another key is refused, naming the key.
- Renamed: runs' `config_id` and fingerprint arm, a hypothesis's `against`, `expect_identical_to`, rounds' carried
  and retired arms, deployments' smoke checks (their `config` field becomes `system`), a sealed dataset's unseals, study
  specs (`baseline.config` becomes `baseline.system`) and logs, faithfulness records, validate.json (`configs` becomes
  `systems`), and a data README's mention. Kept: judging sets and their verdicts, reference manifests and looks, which
  are content-addressed (a set's id and a run's reference hash are made of them).
- data/renames.json records each renamed id, for the catalog's redirects and for a person reading old notes.
"""

from __future__ import annotations

import io
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

NUMBER = 3
ABOUT = "RFC-032 step 3: configs become systems (no dataset, goal or round), merged by dataset; live references renamed"

TOKEN = re.compile(r"_(?:n|dm)\d+(?=_|$)")
VERSION = re.compile(r"^(.*)_v(\d+)$")
MOVED = ("config_id", "dataset_id", "goal", "round")
#: Folders under data/ whose records are content-addressed, or are copies of the world (never renamed).
KEPT = ("judging-sets", "judge-verdicts", "references", "labels", "materialized", "sources", "captures", "corpora",
        "profiles", "datasets-cache", "history")  # fmt: skip


def _yaml_rt() -> Any:
    from ruamel.yaml import YAML  # noqa: PLC0415

    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _config_dirs() -> list[Path]:
    """config.yaml's `configs:` folders, inside the project."""
    import yaml  # noqa: PLC0415

    cfg = _common.ROOT / "config.yaml"
    if not _store.is_file(cfg):
        return []
    try:
        listed = (yaml.safe_load(_store.read_text(cfg, encoding="utf-8")) or {}).get("configs")
    except (yaml.YAMLError, AttributeError):
        return []
    root = _common.ROOT.resolve()
    return [
        p for d in listed or [] if (p := (root / str(d)).resolve()).is_relative_to(root) and _store.is_dir(p)
    ]


def _found() -> list[Path]:
    """Every config as format 2 found them."""
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
    for d in _config_dirs():
        found |= {f for f in _store.glob(d, "*.yaml") if _store.is_file(f)}
    return sorted(found)


def _dest(src: Path, system_id: str) -> Path:
    """Where a system is written: the config's folder, a folder named `configs` becoming `systems`."""
    parts = list(src.parent.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "configs":
            parts[i] = "systems"
            break
    return Path(*parts) / f"{system_id}.yaml"


def _system_text(text: str, system_id: str) -> str:
    """The config's text as a system: `config_id` renamed `system_id` in its place, the run's keys taken out, every
    comment kept."""
    y = _yaml_rt()
    doc = y.load(text)
    keys = list(doc.keys())
    at = keys.index("config_id")
    doc.insert(at, "system_id", system_id)
    for k in MOVED:
        if k in doc:
            del doc[k]
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def plan() -> dict[str, Any]:
    """What the step does: {"write": [(src, dest, text)], "remove": [paths], "renamed": {old: new}, "refused": [...]}."""
    import yaml  # noqa: PLC0415

    configs: list[tuple[Path, dict[str, Any], str]] = []
    refused: list[str] = []
    for f in _found():
        text = _store.read_text(f, encoding="utf-8")
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            refused.append(f"{f}: not YAML ({exc})")
            continue
        if not isinstance(doc, dict) or not doc.get("config_id"):
            refused.append(f"{f}: no config_id")
            continue
        configs.append((f, doc, text))
    groups: dict[tuple[str, str], list[tuple[Path, dict[str, Any], str, int | None]]] = defaultdict(list)
    for f, doc, text in configs:
        m = VERSION.match(str(doc["config_id"]))
        base, ver = (m.group(1), int(m.group(2))) if m else (str(doc["config_id"]), None)
        groups[(str(f.parent), TOKEN.sub("", base))].append((f, doc, text, ver))
    renamed: dict[str, str] = {}
    write: list[tuple[Path, Path, str]] = []
    for (_folder, base), members in sorted(groups.items()):
        datasets = [d.get("dataset_id") for _f, d, _t, _v in members]
        merge = len(members) > 1 and len(set(datasets)) == len(datasets)
        if merge:
            shapes = {
                json.dumps({k: v for k, v in d.items() if k not in MOVED}, sort_keys=True)
                for _f, d, _t, _v in members
            }
            if len(shapes) > 1:
                keys = sorted(
                    {
                        k
                        for _f, d, _t, _v in members
                        for k in set(d) | set(members[0][1])
                        if k not in MOVED and d.get(k) != members[0][1].get(k)
                    }
                )
                refused.append(
                    f"{', '.join(str(d['config_id']) for _f, d, _t, _v in members)}: on different datasets and "
                    f"different in {', '.join(keys)}: name them apart (their ids) or make them alike, and migrate again"
                )
                continue
            vers = [v for *_x, v in members if v is not None]
            sid = f"{base}_v{max(vers)}" if vers else base
            # The member without a dataset token describes the system itself (its comments say so); a token's member
            # says what differs on its dataset.
            keep = max(
                members,
                key=lambda m: (m[3] or 0, not TOKEN.search(str(m[1]["config_id"])), -len(str(m[0]))),
            )
            for _f, d, _t, _v in members:
                if d["config_id"] != sid:
                    renamed[str(d["config_id"])] = sid
            write.append((keep[0], _dest(keep[0], sid), _system_text(keep[2], sid)))
        else:
            for f, d, text, _v in members:
                sid = str(d["config_id"])
                write.append((f, _dest(f, sid), _system_text(text, sid)))
    dests: dict[Path, Path] = {}
    for src, dest, _t in write:
        if dest in dests:
            refused.append(
                f"{src} and {dests[dest]} would both be {dest}: two systems of one id in one folder"
            )
        dests[dest] = src
    return {
        "write": write,
        "remove": [f for f, _d, _t in configs],
        "renamed": renamed,
        "refused": refused,
    }


def _token_re(renamed: dict[str, str]) -> re.Pattern[str]:
    ids = sorted(renamed, key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z0-9_.-])(" + "|".join(map(re.escape, ids)) + r")(?![A-Za-z0-9_-])")


def _rename_json_text(text: str, renamed: dict[str, str]) -> str:
    """Each JSON string that IS an old id, renamed; anything else as it was (a run id beginning with one included)."""
    if not renamed:
        return text
    pat = re.compile(r'"(' + "|".join(map(re.escape, sorted(renamed, key=len, reverse=True))) + r')"')
    return pat.sub(lambda m: f'"{renamed[m.group(1)]}"', text)


def _rename_tokens(text: str, renamed: dict[str, str]) -> str:
    """Each id written as a token (YAML, prose), renamed."""
    if not renamed:
        return text
    return _token_re(renamed).sub(lambda m: renamed[m.group(1)], text)


def _reference_files(skip: set[Path]) -> list[tuple[Path, str]]:
    """The data files that refer to systems by id: (file, how it is renamed: json, tokens). A run's folder is read for
    its metrics.json only (its outputs hold no id); `skip`: the configs themselves, which become systems."""
    data = _common.DATA
    out: list[tuple[Path, str]] = []
    for top in sorted(_store.iterdir(data)) if _store.is_dir(data) else []:
        if not _store.is_dir(top) or top.name in KEPT or top.name in ("configs", "systems"):
            continue
        files = _store.rglob(top, "metrics.json") if top.name.startswith("runs") else _store.rglob(top, "*")
        for f in sorted(files):
            if not _store.is_file(f) or f in skip:
                continue
            if f.suffix in (".json", ".jsonl"):
                out.append((f, "json"))
            elif f.suffix in (".yaml", ".yml", ".md"):
                out.append((f, "tokens"))
    for name in ("validate.json",):
        if _store.is_file(data / name):
            out.append((data / name, "json"))
    return out


def _smoke_field(text: str) -> str:
    """A deployment's smoke check names its system (`system:`), not its config."""
    return re.sub(r"(?m)^(\s*)config: ", r"\1system: ", text)


def _validate_policy(text: str) -> str:
    """validate.json's `configs` globs as `systems` globs, its comment's words with them, and config.yaml's folders
    added: edited as text, so only those lines move."""
    out = re.sub(r'"configs"(\s*:)', r'"systems"\1', text, count=1)
    m = re.search(r'"systems"\s*:\s*\[[^\]]*\]', out)
    if m:
        out = out[: m.start()] + m.group(0).replace("/configs/", "/systems/") + out[m.end() :]
    for old, new in (
        ("  configs         V18: globs, relative to this project's root, of arm configs kept outside",
         "  systems         V18: globs, relative to this project's root, of systems kept outside"),
        ("data/configs (the examples' arms), so their model_record notes are seen",
         "data/systems (the examples'), so their model_record notes are seen"),
        ("V8 (no duplicate config_id)", "V8 (no duplicate system on a dataset)"),
        ("(dataset_id, config_id) pairs allowed to repeat", "(dataset_id, system) pairs allowed to repeat"),
    ):  # fmt: skip
        out = out.replace(old, new)
    dirs = _config_dirs()
    if dirs:
        doc = json.loads(out)
        root = _common.ROOT.resolve()
        globs = list(doc.get("systems") or [])
        for d in dirs:
            rel = "/".join(
                "systems" if x == "configs" else x for x in d.relative_to(root).as_posix().split("/")
            )
            globs.append(f"{rel}/*.yaml")
        doc["systems"] = globs
        out = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    return out


def _study_spec(text: str) -> str:
    """A study spec's `baseline: {config: X}` as `baseline: {system: X}`."""
    return re.sub(r"(?m)^(\s+)config:(\s)", r"\1system:\2", text)


def run(dry_run: bool) -> None:
    """Write the systems, rename the references, record the renames; refuse first, writing nothing."""
    p = plan()
    if p["refused"]:
        _common.die("configs that cannot become systems:\n  " + "\n  ".join(p["refused"]), "invalid-file")
    renamed = p["renamed"]
    if not p["remove"]:
        print("  0 changed: already in this format")
        return
    changes: list[tuple[Path, str, str]] = []
    for f, how in _reference_files(set(p["remove"])):
        before = _store.read_text(f, encoding="utf-8")
        after = before
        if f.name == "validate.json" and f.parent == _common.DATA:
            after = _validate_policy(_rename_json_text(before, renamed))
        elif how == "json":
            after = _rename_json_text(before, renamed)
        else:
            after = _rename_tokens(before, renamed)
            if f.parent.parent.name == "deployments" and f.suffix == ".yaml":
                after = _smoke_field(after)
            if f.parent.parent.name == "studies" and f.suffix == ".yaml":
                after = _study_spec(after)
        if after != before:
            changes.append((f, before, after))
    n_sys = len(p["write"])
    print(
        f"  {len(p['remove'])} config(s) into {n_sys} system(s); {len(renamed)} id(s) renamed; "
        f"{len(changes)} file(s) that refer to them updated"
    )
    for old, new in sorted(renamed.items())[:8]:
        print(f"    {old} -> {new}")
    if len(renamed) > 8:
        print(f"    ... and {len(renamed) - 8} more (data/renames.json)")
    if dry_run:
        return
    for _src, dest, text in p["write"]:
        _store.mkdir(dest.parent, parents=True, exist_ok=True)
        _common.write_text_atomic(dest, text)
    written = {dest for _s, dest, _t in p["write"]}
    for f in p["remove"]:
        if f not in written and _store.is_file(f):
            _store.unlink(f)
    for f, _b, after in changes:
        _common.write_text_atomic(f, after)
    cfg = _common.ROOT / "config.yaml"
    if _config_dirs() and _store.is_file(cfg):
        y = _yaml_rt()
        doc = y.load(_store.read_text(cfg, encoding="utf-8"))
        doc.pop("configs", None)
        buf = io.StringIO()
        y.dump(doc, buf)
        _common.write_text_atomic(cfg, buf.getvalue())
    for d in {f.parent for f in p["remove"]}:
        if d.name == "configs" and _store.is_dir(d) and not any(True for _ in _store.iterdir(d)):
            _store.rmtree(d)
    if renamed:
        f = _common.DATA / "renames.json"
        doc = json.loads(_store.read_text(f, encoding="utf-8")) if _store.is_file(f) else {}
        doc.setdefault("systems", {}).update(renamed)
        _common.write_text_atomic(f, json.dumps(doc, indent=2, sort_keys=True) + "\n")
