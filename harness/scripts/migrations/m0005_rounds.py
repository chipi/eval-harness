"""Format 5, RFC-032 step 5: a round stores its arms. Each arm is a system read under one label, the runs it is read
through, how and when it entered the round, and its retirement (owner, 2026-11-13, "I agree with all 5").

It reads the stored data as format 4 kept it, not through the model: data/rounds/<goal>/<r>.yaml with `carried` and
`retired`, and the runs and scores in data/runs (run.json, scores/<key>/score.json).

- The arms are the round's as format 4 read them: the systems whose plain runs name the round, and those `carried`,
  less a retirement naming every plain run of the system (or naming none). Each is read under the round's label: the
  re-score its `scoring` last wrote ("rescored 5f2c057c"), else the plain runs; its runs are the system's runs on the
  dataset with a score under that label. It entered by running in the round, or carried from the round before.
- A retirement of a system that is not among them becomes an arm of its own, retired: read under the round's label
  where its runs have a score there, else under their own (a re-timing's machine, "repeats", "pair"); entered by
  running in the round when its runs name it, else carried. Its retirement keeps when, why and who.
- `carried` and `retired` go. A baseline version a round promoted (its `conclusion.promoted_run`, of that goal and
  dataset) names the round and the arm.

Refused, writing nothing: a retirement that names some but not all of an in-play system's runs (format 4 kept the
system in play; which runs the arm is read through would be a guess), and a round file that is not YAML.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

NUMBER = 5
ABOUT = "RFC-032 step 5: a round stores its arms (system, label, runs, how it entered, its retirement)"

PURPOSE_LABEL = {"run": "", "repeat": "repeats", "pair": "pair"}


def _json(p: Path) -> Any:
    try:
        return json.loads(_store.read_text(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _runs() -> dict[str, dict[str, Any]]:
    """{run id: {"run": run.json, "labels": {label of each score}, "first": the first score's label}}."""
    out: dict[str, dict[str, Any]] = {}
    base = _common.DATA / "runs"
    if not _store.is_dir(base):
        return out
    for d in sorted(_store.iterdir(base)):
        r = _json(d / "run.json") if _store.is_dir(d) else None
        if not isinstance(r, dict):
            continue
        purpose = r.get("purpose") or "run"
        by_purpose = (r.get("machine") or "") if purpose == "retime" else PURPOSE_LABEL.get(purpose, purpose)
        labels, first = set(), None
        sdir = d / "scores"
        for s in sorted(_store.iterdir(sdir)) if _store.is_dir(sdir) else []:
            meta = _json(s / "score.json") or {}
            lbl = ", ".join(x for x in (str(meta.get("label") or ""), by_purpose) if x)
            labels.add(lbl)
            if meta.get("first"):
                first = lbl
        out[d.name] = {"run": r, "labels": labels, "first": first}
    return out


def _round_label(rnd: dict[str, Any]) -> str:
    """The label a round reads its arms under: the re-score its scoring last wrote, else the plain runs."""
    scoring = rnd.get("scoring") or []
    if not scoring:
        return ""
    written = [str(w) for w in scoring[-1].get("written") or []]
    return next((w for w in written if ", " not in w), "")


def arms_for(rnd: dict[str, Any], runs: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """The arms format 4's data says a round has: (arms, refusals)."""
    ds, rid, goal = rnd.get("dataset_id"), rnd.get("round_id"), rnd.get("goal")
    label = _round_label(rnd)
    on_ds = {k: v for k, v in runs.items() if v["run"].get("dataset_id") == ds}

    def plain(system: str) -> set[str]:
        return {k for k, v in on_ds.items() if v["run"].get("config_id") == system and "" in v["labels"]}

    def read_under(system: str, lbl: str) -> list[str]:
        return sorted(
            k for k, v in on_ds.items() if v["run"].get("config_id") == system and lbl in v["labels"]
        )

    ran = sorted(
        {
            v["run"]["config_id"]
            for v in on_ds.values()
            if v["run"].get("round") == rid and v["run"].get("goal") == goal and "" in v["labels"]
        }
    )
    carried = [str(c) for c in rnd.get("carried") or []]
    entered_at = rnd.get("opened_at")
    who = rnd.get("actor")

    def entered(how: str) -> dict[str, Any]:
        e: dict[str, Any] = {"how": how, "at": entered_at}
        if how == "carried" and rnd.get("from"):
            e["from"] = rnd["from"]
        if who:
            e["actor"] = dict(who) if isinstance(who, dict) else who
        return e

    arms: dict[str, dict[str, Any]] = {}
    for c in [*ran, *[c for c in carried if c not in ran]]:
        arm: dict[str, Any] = {"system": c}
        if label:
            arm["label"] = label
        arm["runs"] = read_under(c, label)
        arm["entered"] = entered("ran" if c in ran else "carried")
        arms[c] = arm
    refused: list[str] = []
    extra: list[dict[str, Any]] = []
    for r in rnd.get("retired") or []:
        c = str(r.get("config_id"))
        named = [str(x) for x in r.get("runs") or []]
        gone = {"at": r.get("at"), "reason": r.get("reason")}
        if r.get("actor"):
            gone["actor"] = dict(r["actor"]) if isinstance(r["actor"], dict) else r["actor"]
        if c in arms:
            if not named or plain(c) <= set(named):
                arms[c]["retired"] = gone
            else:
                refused.append(
                    f"{goal} {rid}: the retirement of {c} names {', '.join(named)}, not every run of it"
                )
            continue
        has_round_label = bool(named) and all(label in on_ds.get(x, {}).get("labels", set()) for x in named)
        lbl = label if has_round_label or not named else (on_ds.get(named[0], {}).get("first") or "")
        here = bool(named) and all(on_ds.get(x, {}).get("run", {}).get("round") == rid for x in named)
        arm = {"system": c}
        if lbl:
            arm["label"] = lbl
        arm["runs"] = sorted(named) if named else read_under(c, lbl)
        arm["entered"] = entered("ran" if here else "carried")
        arm["retired"] = gone
        extra.append(arm)
    return [*arms.values(), *extra], refused


def plan() -> dict[str, Any]:
    """{"rounds": [(round file, its record with arms)], "refused": [...]}; reads the stored rounds and runs only."""
    import yaml  # noqa: PLC0415

    runs = _runs()
    out: list[tuple[Path, dict[str, Any]]] = []
    refused: list[str] = []
    base = _common.DATA / "rounds"
    for f in sorted(_store.glob(base, "*/r*.yaml")) if _store.is_dir(base) else []:
        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8"))
        except yaml.YAMLError as exc:
            refused.append(f"{f}: not YAML ({exc})")
            continue
        if not isinstance(doc, dict) or "arms" in doc:
            continue
        arms, why = arms_for(doc, runs)
        refused += why
        out.append((f, {**doc, "arms": arms}))
    return {"rounds": out, "refused": refused}


def _round_text(doc: dict[str, Any]) -> str:
    """As a round is saved: its keys in order, `carried` and `retired` gone, `arms` after the baseline."""
    import yaml  # noqa: PLC0415

    order = ["round_id", "goal", "dataset_id", "from", "hypothesis", "changes", "baseline", "arms", "budget_usd",
             "harness", "scorer", "scoring", "study", "status", "opened_at", "closed_at", "actor", "conclusion"]  # fmt: skip
    body = {k: doc[k] for k in order if k in doc and doc[k] not in (None, [], "")}
    if "baseline" in doc and doc.get("baseline") is None:
        body["baseline"] = None
    rest = {k: v for k, v in doc.items() if k not in order and k not in ("carried", "retired")}
    return yaml.safe_dump({**body, **rest}, sort_keys=False, allow_unicode=True, width=100)


def _baselines(rounds: list[tuple[Path, dict[str, Any]]]) -> list[tuple[Path, str]]:
    """The baseline versions a round promoted, naming the round and the arm."""
    out = []
    for _f, doc in rounds:
        run_id = (doc.get("conclusion") or {}).get("promoted_run")
        if not run_id:
            continue
        d = _common.DATA / "baselines" / str(doc.get("goal")) / str(doc.get("dataset_id"))
        for v in sorted(_store.glob(d, "*.json")) if _store.is_dir(d) else []:
            b = _json(v)
            if isinstance(b, dict) and b.get("promoted_from") == run_id and "round" not in b:
                arm = next((a["system"] for a in doc["arms"] if run_id in a.get("runs") or []), None)
                b = {**b, "round": doc["round_id"], **({"arm": arm} if arm else {})}
                out.append((v, json.dumps(b, indent=2, ensure_ascii=False) + "\n"))
    return out


def run(dry_run: bool) -> None:
    """Write each round's arms, and link the baselines its rounds promoted; refuse first, writing nothing."""
    p = plan()
    if p["refused"]:
        _common.die("rounds whose arms cannot be written:\n  " + "\n  ".join(p["refused"]), "invalid-file")
    if not p["rounds"]:
        print("  0 changed: already in this format")
        return
    links = _baselines(p["rounds"])
    n_arms = sum(len(d["arms"]) for _f, d in p["rounds"])
    n_ret = sum(1 for _f, d in p["rounds"] for a in d["arms"] if a.get("retired"))
    print(
        f"  {len(p['rounds'])} round(s): {n_arms} arm(s), {n_ret} of them retired; "
        f"{len(links)} baseline version(s) linked to the round that promoted them"
    )
    for f, d in p["rounds"]:
        in_play = sum(1 for a in d["arms"] if not a.get("retired"))
        print(f"    {f.parent.name} {d['round_id']}: {in_play} in play, {len(d['arms']) - in_play} retired")
    if dry_run:
        return
    for f, d in p["rounds"]:
        _common.write_text_atomic(f, _round_text(d))
    for f, text in links:
        _common.write_text_atomic(f, text)
