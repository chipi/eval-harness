"""Replay runs (RFC-030 R1): the system's real code run over recorded items in order, each at the commit it came from.

A config replays when it has `replay:`; it names the code it runs as any arm names its record, `model_record:` a
record of `kind: code` (the fleet's feedback 27), whose versions say which commit ran in production when:

    model_record: signal_fleet
    replay:
      order: [ts, kind]                       # item fields the items run in (later ones break ties; then item_id)
      time_field: cycle_start                 # a datetime field: the version deployed then runs the item
      version_field: deployed_commit          # optional: production's own record of its commit wins
      support: [replay_world.py]              # the adapter's own modules, beside it, hashed with it
      commit: <sha>                           # a candidate: every item at this one commit
      hide: {kinds: [stale-label]}            # production's own writes of these kinds, made inside the replayed
                                              # window, hidden from the replay (RFC-031 P1)

Each call is made once (a retry would repeat side effects), and `--resume`, `--items` and `--repeat` above 1 are
refused: state the skipped or replayed items wrote would be missing, or a second pass would inherit the first's. The
adapter gets `params["item"]` ({item_id, fields}) and `params["code"]` ({record, commit, path, changed}); `changed` is
true on the first item at a new commit, where it imports that version (`_codeload.use`) and re-applies its patches.
With `hide`, it also gets `params["hide"]` ({kinds, since: the first replayed item's time}): its world stand-in hides
production's own writes of those kinds made since then (the stale check's confound: a later variant saw production's
own labels and nudged nothing), and leaves everything else as recorded. The setting is part of the adapter's identity,
so only a faithfulness record made with it lets such a replay be scored. The adapter reports per item, in
`Result.extra["history_confound"]` (1 or 0), whether the variant met a human reaction recorded after an action
production took and it did not: the run counts them over all its items (an item the adapter leaves unmarked is 0),
and every score on it says so, counted over the items that score reads.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evaluation_harness import _coderec, _common, _fields, _store

KEYS = ("order", "time_field", "version_field", "support", "commit", "hide")


@dataclass
class Plan:
    """A replay's items in the order they run, and the commit each runs at."""

    record: dict[str, Any]
    items: list[dict[str, Any]]
    commit_of: dict[str, str]
    candidate: str | None
    settings: dict[str, Any]
    support: dict[str, Path] = field(default_factory=dict)

    @property
    def model_id(self) -> str:
        return str(self.record["model_id"])

    def commits(self) -> dict[str, int]:
        """{commit: how many items run at it}, in the order the commits are first used."""
        out: dict[str, int] = {}
        for it in self.items:
            c = self.commit_of[it["item_id"]]
            out[c] = out.get(c, 0) + 1
        return out


def is_replay(cfg: dict[str, Any]) -> bool:
    """Whether a config replays code (it has `replay:`)."""
    return isinstance(cfg.get("replay"), dict)


def _sort_key(order: list[str], item: dict[str, Any]) -> tuple:
    out: list[tuple] = []
    fields = item.get("fields") or {}
    for name in order:
        v = fields.get(name)
        if v is None:
            out.append((2, 0.0, ""))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append((0, float(v), ""))
        elif isinstance(v, str) and _fields.moment(v) is not None and "T" in v:
            out.append((0, _fields.moment(v).timestamp(), ""))
        else:
            out.append((1, 0.0, str(v)))
    return (*out, item["item_id"])


def prepare(
    cfg: dict[str, Any], config_path: Path, ds: dict[str, Any], adapter_path: Path | None
) -> Plan | None:
    """The plan for a replay config, or None for any other. Dies on a malformed spec, an unknown field, an item no
    deployment covers, or a commit the checkout does not have."""
    spec = cfg.get("replay")
    if spec is None:
        return None
    if not isinstance(spec, dict) or set(spec) - set(KEYS):
        _common.die(f"{config_path}: replay takes {', '.join(KEYS)}", "invalid-file")
    if not cfg.get("model_record"):
        _common.die(
            f"{config_path}: a replay names the code it runs, `model_record: <a kind: code record>` (RFC-030)",
            "invalid-file",
        )
    if cfg.get("code"):
        _common.die(
            f"{config_path}: a replay's code is its record's versions; `code:` (one checkout) is for other arms",
            "invalid-file",
        )
    order = spec.get("order")
    if not (isinstance(order, list) and order and all(isinstance(x, str) for x in order)):
        _common.die(
            f"{config_path}: replay.order is a list of the item fields the items run in", "invalid-file"
        )
    tf, vf, cand = spec.get("time_field"), spec.get("version_field"), spec.get("commit")
    if not tf and not vf and not cand:
        _common.die(
            f"{config_path}: replay needs time_field (the record's deployments pick the commit) or version_field",
            "invalid-file",
        )
    rec = _coderec.load(str(cfg["model_record"]))
    items = list(ds.get("items") or [])
    known: set[str] = set()
    for it in items:
        known.update((it.get("fields") or {}).keys())
    for name in [*order, *(x for x in (tf, vf) if x)]:
        if name not in known:
            _common.die(
                f"{config_path}: replay names the field {name!r}, which no item of {ds['dataset_id']} carries",
                "invalid-file",
            )
    support: dict[str, Path] = {}
    base = adapter_path.parent if adapter_path else _common.ROOT
    for name in spec.get("support") or []:
        p = base / str(name)
        if not _store.is_file(p):
            _common.die(f"{config_path}: replay.support {name!r}: no file {p}", "not-found")
        support[str(name)] = p
    ordered = sorted(items, key=lambda it: _sort_key(order, it))
    candidate = _coderec.full_commit(rec, str(cand)) if cand else None
    resolved: dict[str, str] = {}

    def full(c: str) -> str:
        if c not in resolved:
            resolved[c] = _coderec.full_commit(rec, c)
        return resolved[c]

    commit_of: dict[str, str] = {}
    uncovered = []
    for it in ordered:
        if candidate:
            commit_of[it["item_id"]] = candidate
            continue
        f = it.get("fields") or {}
        if vf and f.get(vf):
            commit_of[it["item_id"]] = full(str(f[vf]))
            continue
        t = _fields.moment(f[tf]) if tf and isinstance(f.get(tf), str) else None
        c = _coderec.commit_at(rec, t) if t is not None else None
        if c is None:
            uncovered.append(f"{it['item_id']} ({tf}={f.get(tf)!r})")
            continue
        commit_of[it["item_id"]] = full(c)
    if uncovered:
        _common.die(
            f"code record {rec['model_id']}: no deployed version covers {len(uncovered)} item(s): "
            + ", ".join(uncovered[:6]),
            "not-found",
        )
    settings = {"order": order, "time_field": tf, "version_field": vf, "support": sorted(support)}
    hide = spec.get("hide")
    if hide is not None:
        kinds = hide.get("kinds") if isinstance(hide, dict) else None
        if not (
            isinstance(hide, dict)
            and set(hide) <= {"kinds", "window"}
            and isinstance(kinds, list)
            and kinds
            and all(isinstance(k, str) and k.strip() for k in kinds)
            and hide.get("window", "replayed") == "replayed"
        ):
            _common.die(
                f"{config_path}: replay.hide is {{kinds: [the kinds of production's own writes to hide]}}, hidden "
                "when made inside the replayed window (window: replayed, the one window)",
                "invalid-file",
            )
        first = ordered[0] if ordered else {}
        since = (first.get("fields") or {}).get(tf) if tf else None
        settings["hide"] = {"kinds": sorted(kinds), "window": "replayed", "since": since}
    return Plan(rec, ordered, commit_of, candidate, settings, support)


def item_params(plan: Plan) -> Any:
    """`f(item) -> {item, code}`, the per-item params a replay adds; each commit's copy is made when first used."""
    last: list[str] = []

    def per_item(item: dict[str, Any]) -> dict[str, Any]:
        c = plan.commit_of[item["item_id"]]
        changed = not last or last[-1] != c
        path = _coderec.copy_of(plan.record, c)
        if changed:
            last.append(c)
        out = {
            "item": {"item_id": item["item_id"], "fields": dict(item.get("fields") or {})},
            "code": {"record": plan.model_id, "commit": c, "path": str(path), "changed": changed},
        }
        if plan.settings.get("hide"):
            out["hide"] = {"kinds": plan.settings["hide"]["kinds"], "since": plan.settings["hide"]["since"]}
        return out

    return per_item


def adapter_identity(adapter_id: str, adapter_path: Path | None, plan: Plan) -> dict[str, Any]:
    """The instrument's adapter for a replay: the adapter's hash and each support module's, and one hash over them."""
    from evaluation_harness._codeid import file_sha256  # noqa: PLC0415

    support = {n: file_sha256(p) for n, p in sorted(plan.support.items())}
    own = file_sha256(adapter_path) if adapter_path else None
    # What the replay hides is part of the instrument: a faithfulness record made without it does not cover it.
    hide = plan.settings.get("hide")
    joint = hashlib.sha256(
        json.dumps(
            {"adapter": own, "support": support, **({"hide": hide["kinds"]} if hide else {})}, sort_keys=True
        ).encode()
    ).hexdigest()
    return {"id": adapter_id, "sha256": joint, "adapter_sha256": own, "support": support or None}


def code_part(plan: Plan) -> dict[str, Any]:
    """`deployment.code` for a replay: the record, its repository and deployments' hash, each commit and its items."""
    return {
        "record": plan.model_id,
        "repo": plan.record.get("repo"),
        "versions_sha256": _coderec.versions_sha256(plan.record),
        "commits": plan.commits(),
        "candidate": plan.candidate,
    }


def refuse_flags(args: Any) -> None:
    """A replay run's refusals: what would make its state wrong."""
    for flag, bad in (
        ("--resume", getattr(args, "resume", None)),
        ("--items", getattr(args, "items", None) is not None),
        ("--repeat above 1", (getattr(args, "repeat", 1) or 1) > 1),
    ):
        if bad:
            _common.die(
                f"a replay run refuses {flag}: the state skipped or repeated items write would be missing or "
                "doubled (RFC-030). Run the whole replay once.",
                "bad-argument",
            )


def environment() -> None:
    """A replay process says so (EVH_REPLAY=1), so a system can refuse real calls under it."""
    os.environ["EVH_REPLAY"] = "1"
