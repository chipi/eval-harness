"""The mutations test_data_mutations.py applies to a copy of a project: real-looking data the readers must survive (RFC-041,
PLAN 0.8.1 R5).

    python tests/_mutations.py NAME DIR      apply mutation NAME to the project in DIR (EVAL_HOME, EVAL_STORE as in the environment)
    python tests/_mutations.py oracle DIR    print what the project's files say, as JSON

Each mutation edits what a hand, an older release or another tool would leave in a project's files, through the store the
project is in (`_runstore`): a run's record, a score's rows, a goal's file, or a command of the harness where the harness
itself writes the thing (a unicode system's run, a promoted baseline). It runs in a process of its own: `_runstore`
aims the store at one project per process.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import _foreign  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

#: The day boundary the time-zone mutations straddle: a run stamped a half minute before it, one a half minute after.
BEFORE_MIDNIGHT = "2026-11-30T23:59:30Z"
AFTER_MIDNIGHT = "2026-12-01T00:00:30Z"
UNICODE_SYSTEM = "sÿstème_日本語_v1"
UNICODE_DATASET = "données_日本語_v1"
UNICODE_ITEMS = ("élément_1", "項目_2", "пункт_3")
NO_SUCH_MEASURE = "measure_no_run_records"
GHOST_REFERENCE = "gold/ghost_v1"
#: Metrics a perturbation leaves alone: a count of failures, a cost and a time are not what a second pass changes.
STEADY = ("cost", "failed", "resumed", "latency")


def put_json(proj: Path, rel: str, doc: Any) -> None:
    """A JSON document written into the project's data/ through its store."""
    _runstore.write_text(proj, rel, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def run_ids(proj: Path) -> list[str]:
    """The ids of the project's runs that have a record."""
    return [r for r in _runstore.listdir(proj, "runs") if _runstore.is_file(proj, f"runs/{r}/run.json")]


def ordered(proj: Path) -> list[tuple[str, dict[str, Any]]]:
    """Every run as (id, record), the oldest first by (created_at, run id): the order the harness reads a latest run in."""
    recs = [(r, _runstore.read_json(proj, f"runs/{r}/run.json")) for r in run_ids(proj)]
    return sorted(recs, key=lambda x: (x[1].get("created_at") or "", x[0]))


def save(proj: Path, run_id: str, rec: dict[str, Any]) -> None:
    """A run's record written back."""
    put_json(proj, f"runs/{run_id}/run.json", rec)


def by_dataset(proj: Path) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """The runs per dataset, the oldest first."""
    out: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for rid, rec in ordered(proj):
        out.setdefault(rec["dataset_id"], []).append((rid, rec))
    return out


def goals(proj: Path) -> dict[str, dict[str, Any]]:
    """Every goal's document, by id."""
    return {
        n[: -len(".yaml")]: yaml.safe_load(_runstore.read_text(proj, f"goals/{n}")) or {}
        for n in _runstore.listdir(proj, "goals")
        if n.endswith(".yaml")
    }


def put_goal(proj: Path, goal_id: str, doc: dict[str, Any]) -> None:
    """A goal's document written back."""
    _runstore.write_text(
        proj, f"goals/{goal_id}.yaml", yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    )


def edit_scores(
    proj: Path, run_id: str, change: Callable[[list[dict[str, Any]], dict[str, Any], dict[str, Any]], None]
) -> None:
    """For each score of a run, `change(rows, metrics, score)` edits the per-item rows, metrics.json and score.json in
    place and they are written back."""
    with _runstore._InProject(proj) as data:
        for sd in model_runs.scores_of(data / "runs" / run_id):
            rows = _runstore.rows(sd)
            metrics = json.loads(_store.read_text(sd / model_runs.METRICS))
            score = json.loads(_store.read_text(sd / model_runs.SCORE))
            change(rows, metrics, score)
            _runstore.put_rows(sd, rows)
            _store.write_text(sd / model_runs.METRICS, json.dumps(metrics, indent=2) + "\n")
            _store.write_text(sd / model_runs.SCORE, json.dumps(score, indent=2) + "\n")


def commit_runs(proj: Path) -> None:
    """The project's runs committed to git (the files store; the sqlite store's database is what it commits): validate's
    V8 checks the arms git tracks, so a duplicate in an untracked project is not looked for."""
    if _runstore.sqlite():
        return
    git = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]
    for args in (["init", "-q"], ["add", "-f", "data/runs"], ["commit", "-q", "--allow-empty", "-m", "runs"]):
        subprocess.run([*git, *args], cwd=proj, check=True, capture_output=True, stdin=subprocess.DEVNULL)  # nosec B603 B607


def build(proj: Path) -> _foreign.Build:
    """The harness's own commands in the project, for what the harness itself writes."""
    env = dict(os.environ, EVAL_HOME=str(proj), EVH_ACTOR="person:fixture", EVAL_BUILD_REF="mutation-fixture")
    for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR", "EVH_PUBLIC"):
        env.pop(k, None)
    return _foreign.Build(proj, env)


# ── the mutations ────────────────────────────────────────────────────────────────────────────────────────────────────
def no_goal(proj: Path) -> None:
    """Runs that name no goal among runs that do: every second run (oldest first) drops its `goal`, the others name the
    first goal that lists their dataset."""
    cover: dict[str, str] = {}
    for gid, doc in sorted(goals(proj).items()):
        for d in doc.get("datasets") or []:
            cover.setdefault(d["dataset_id"], gid)
    for i, (rid, rec) in enumerate(ordered(proj)):
        if i % 2:
            rec.pop("goal", None)
        elif rec["dataset_id"] in cover:
            rec["goal"] = cover[rec["dataset_id"]]
        save(proj, rid, rec)


def cost_zero_and_missing(proj: Path) -> None:
    """On each dataset the oldest run records a cost of 0 and the next one records none (no `cost_usd` in its rows and
    scores): a free model and a model nobody priced, side by side."""

    def zero(rows: list, metrics: dict, _score: dict) -> None:
        for r in rows:
            r["cost_usd"] = 0.0
        metrics.setdefault("scores", {}).update(cost_usd=0.0, total_cost_usd=0.0)

    def missing(rows: list, metrics: dict, _score: dict) -> None:
        for r in rows:
            r.pop("cost_usd", None)
        for k in ("cost_usd", "total_cost_usd"):
            metrics.get("scores", {}).pop(k, None)

    for runs in by_dataset(proj).values():
        edit_scores(proj, runs[0][0], zero)
        if len(runs) > 1:
            edit_scores(proj, runs[1][0], missing)


def dirty_null(proj: Path) -> None:
    """Every run's `build.dirty` is null (git could not say) and so is its fingerprint's harness `dirty`."""
    for rid, rec in ordered(proj):
        rec.setdefault("build", {})["dirty"] = None
        harness = ((rec.get("fingerprint") or {}).get("instrument") or {}).get("harness")
        if isinstance(harness, dict):
            harness["dirty"] = None
        save(proj, rid, rec)


def clone_run(
    proj: Path, run_id: str, new_id: str, change: Callable[[dict[str, Any]], None], reference: bool = True
) -> None:
    """A run copied under another id, its record changed by `change`; with `reference` False its score is read against no
    reference. It is written as the model writes a run (`_runstore.make_run`), in whichever store the project is."""
    from evaluation_harness import _outputs  # noqa: PLC0415

    rec = copy.deepcopy(_runstore.read_json(proj, f"runs/{run_id}/run.json"))
    rec.pop("run_id", None)
    change(rec)
    with _runstore._InProject(proj) as data:
        src = data / "runs" / run_id
        texts = {o["item_id"]: o["text"] for o in _outputs.store().lines(src)}
        scores = []
        for sd in model_runs.scores_of(src):
            meta = json.loads(_store.read_text(sd / model_runs.SCORE))
            metrics = json.loads(_store.read_text(sd / model_runs.METRICS))
            if not reference:
                meta["reference"] = None
                metrics.pop("reference_tier", None)
            scores.append({**meta, "metrics": metrics, "rows": _runstore.rows(sd)})
        _runstore.make_run(data / "runs", new_id, rec, outputs=texts, scores=scores)


def unicode_ids(proj: Path) -> None:
    """A system and a dataset whose ids are in other scripts, as a hand-edited or imported project holds them (the
    harness's writers refuse such an id, so these are written as files): runs of the new system on an existing dataset, of
    an existing system on the new dataset, and of both."""
    first_id, first = ordered(proj)[0]
    ds, system = first["dataset_id"], first["system_id"]
    _runstore.write_text(
        proj,
        f"systems/{UNICODE_SYSTEM}.yaml",
        f"system_id: {UNICODE_SYSTEM}\nparams:\n  provider: echo\n  sentences: 1\n",
    )
    record = _runstore.read_json(proj, f"datasets/{ds}.json")
    put_json(proj, f"datasets/{UNICODE_DATASET}.json", {**record, "dataset_id": UNICODE_DATASET})
    with _runstore._InProject(proj) as data:
        if _store.is_dir(data / "materialized" / ds):
            _store.copy_tree(data / "materialized" / ds, data / "materialized" / UNICODE_DATASET)

    def named(system_id: str, dataset_id: str) -> Callable[[dict[str, Any]], None]:
        """A change that makes a record the run of `system_id` on `dataset_id`, read against no reference on the new one."""

        def change(rec: dict[str, Any]) -> None:
            rec.update(system_id=system_id, dataset_id=dataset_id, created_at="2026-12-01T10:00:00Z")
            rec.pop("goal", None)
            fp = rec.get("fingerprint") or {}
            if isinstance(fp.get("data"), dict):
                fp["data"]["dataset_id"] = dataset_id
                if dataset_id != ds:
                    fp["data"].update(reference_id=None, reference_tier=None)
            if isinstance(fp.get("arm"), dict):
                fp["arm"]["config_id"] = system_id

        return change

    for i, (sid, dsid) in enumerate(
        ((UNICODE_SYSTEM, ds), (system, UNICODE_DATASET), (UNICODE_SYSTEM, UNICODE_DATASET))
    ):
        clone_run(proj, first_id, f"{sid}_20261201T1{i}0000Z", named(sid, dsid), reference=dsid == ds)


def underscore_r_not_a_set(proj: Path) -> None:
    """Two runs of the newest run's arm named `<id>_r1` and `<id>_r2` by hand, with no `repeat_index`: not a repeat set. Their
    scores differ a little from the original's, as two passes of a model do."""
    rid, rec = ordered(proj)[-1]
    for n, factor in ((1, 0.97), (2, 0.94)):
        new = f"{rid}_r{n}"
        with _runstore._InProject(proj) as data:
            _runstore.copy_run(data / "runs" / rid, data / "runs" / new)
        copy_rec = copy.deepcopy(rec)
        copy_rec["run_id"] = new
        copy_rec.pop("repeat_index", None)
        copy_rec["created_at"] = f"2026-12-02T10:0{n}:00Z"
        save(proj, new, copy_rec)

        def shift(rows: list, metrics: dict, _score: dict, f: float = factor) -> None:
            for r in rows:
                for k, v in list(r.items()):
                    if isinstance(v, float) and not any(s in k for s in STEADY):
                        r[k] = round(v * f, 6)
            for k, v in list(metrics.get("scores", {}).items()):
                if isinstance(v, float) and not any(s in k for s in STEADY):
                    metrics["scores"][k] = round(v * f, 6)

        edit_scores(proj, new, shift)
    commit_runs(proj)


def missing_optional_fields(proj: Path) -> None:
    """Every second run lacks the fields the run schema does not require: purpose, actor, machine, started_at,
    providers_seen, adapter."""
    for i, (rid, rec) in enumerate(ordered(proj)):
        if i % 2:
            for k in ("purpose", "actor", "machine", "started_at", "providers_seen", "adapter"):
                rec.pop(k, None)
            save(proj, rid, rec)


def n_items_missing(proj: Path) -> None:
    """Every second run lacks `n_items`, which the run schema requires: a record written by hand or by an older tool."""
    for i, (rid, rec) in enumerate(ordered(proj)):
        if i % 2:
            rec.pop("n_items", None)
            save(proj, rid, rec)


def extra_unknown_fields(proj: Path) -> None:
    """Every run carries fields no release defines: at the top, in `build` and in the fingerprint."""
    for rid, rec in ordered(proj):
        rec["x_ticket"] = "OPS-12 ünï"
        rec["tags"] = ["nightly", "日本語"]
        rec["future"] = {"nested": [1, {"a": None}], "ratio": 0.5}
        rec.setdefault("build", {})["builder"] = "ci-7"
        if isinstance(rec.get("fingerprint"), dict):
            rec["fingerprint"]["future_part"] = {"id": "x"}
        save(proj, rid, rec)


def _measure_of(proj: Path, run_id: str) -> str | None:
    """The primary metric a run's first score records."""
    with _runstore._InProject(proj) as data:
        sd = model_runs.first_score(data / "runs" / run_id)
        return (
            (json.loads(_store.read_text(sd / model_runs.METRICS)) or {}).get("primary_metric")
            if sd
            else None
        )


def two_goals_two_baselines(proj: Path) -> None:
    """Two goals on one dataset (the one with the most systems), each promoting another system's latest run as its
    baseline, made by the harness's own commands."""
    from evaluation_harness import _common  # noqa: PLC0415

    per = by_dataset(proj)
    ds = max(per, key=lambda d: len({r["system_id"] for _i, r in per[d]}))
    latest: dict[str, str] = {}
    for rid, rec in per[ds]:
        latest[rec["system_id"]] = rid
    systems = sorted(latest)
    measure = _measure_of(proj, latest[systems[0]]) or "overlap_f1"
    direction = "lower" if _common.lower_is_better(measure) else "higher"
    b = build(proj)
    for gid, system in zip(("mutation_goal_a", "mutation_goal_b"), systems[:2], strict=False):
        b.must(
            "goal-new", gid, "--set", f"title=Goal {gid}", "--set", "statement=An invented goal for a mutation.",
            "--set", "decision=An invented decision.", "--set", f"success_criteria.primary.measure={measure}",
            "--set", f"success_criteria.primary.direction={direction}", "--set", f"datasets.0.dataset_id={ds}",
            "--set", "datasets.0.role=test",
        )  # fmt: skip
        b.must(
            "run-promote", "--run", latest[system], "--goal", gid, "--reason", "An invented promotion.",
            "--allow-dirty", "--by", "ana",
        )  # fmt: skip


def utc_day_boundary(proj: Path) -> None:
    """On each dataset the newest run is stamped half a minute before a UTC midnight and the one before it half a minute
    after: the same instant is one day in UTC and another in a zone far from it."""
    for runs in by_dataset(proj).values():
        for (rid, rec), stamp in zip(reversed(runs), (BEFORE_MIDNIGHT, AFTER_MIDNIGHT), strict=False):
            rec["created_at"] = stamp
            rec["started_at"] = stamp
            save(proj, rid, rec)


def reference_gone(proj: Path) -> None:
    """The reference the first dataset's runs were scored against is gone. Where the project has none (an import), the
    newest run of each dataset names one that was never made."""
    refs = [
        (t, n)
        for t in _runstore.listdir(proj, "references")
        for n in _runstore.listdir(proj, f"references/{t}")
    ]
    if refs:
        tier, name = refs[0]
        _runstore.rmtree(proj, f"references/{tier}/{name}")
        return

    def ghost(_rows: list, metrics: dict, score: dict) -> None:
        score["reference"] = GHOST_REFERENCE
        metrics["reference_tier"] = "gold"

    for runs in by_dataset(proj).values():
        rid, rec = runs[-1]
        edit_scores(proj, rid, ghost)
        rec.setdefault("fingerprint", {}).setdefault("data", {})["reference_id"] = GHOST_REFERENCE
        save(proj, rid, rec)


def goal_measure_unrecorded(proj: Path) -> None:
    """Every goal's primary measure is one no run records."""
    for gid, doc in goals(proj).items():
        doc.setdefault("success_criteria", {}).setdefault("primary", {})["measure"] = NO_SUCH_MEASURE
        put_goal(proj, gid, doc)


def no_fingerprint(proj: Path) -> None:
    """Every second run has no fingerprint, as a run of an older release has none."""
    for i, (rid, rec) in enumerate(ordered(proj)):
        if i % 2 == 0:
            rec.pop("fingerprint", None)
            save(proj, rid, rec)


def hide_a_dataset(proj: Path) -> None:
    """A project with a dataset whose text is hidden (`text: hidden`), so a public environment has something to withhold:
    the first dataset with runs, when none is hidden yet."""
    names = sorted(n[: -len(".json")] for n in _runstore.listdir(proj, "datasets") if n.endswith(".json"))
    docs = {n: _runstore.read_json(proj, f"datasets/{n}.json") for n in names}
    if any(d.get("text") == "hidden" for d in docs.values()):
        return
    ds = next(iter(by_dataset(proj)))
    put_json(proj, f"datasets/{ds}.json", {**docs[ds], "text": "hidden"})


def oracle(proj: Path) -> dict[str, Any]:
    """What the files say, read apart from every reader: each run's dataset, system, UTC stamp, recorded cost (None when
    its first score records none) and `build.dirty`; each dataset's first item id; each hidden dataset's item ids with a stretch of each item's text."""
    runs: dict[str, Any] = {}
    with _runstore._InProject(proj) as data:
        for rid, rec in ordered(proj):
            sd = model_runs.first_score(data / "runs" / rid)
            scores = (json.loads(_store.read_text(sd / model_runs.METRICS)).get("scores") or {}) if sd else {}
            runs[rid] = {
                "dataset": rec["dataset_id"],
                "system": rec["system_id"],
                "created_at": rec.get("created_at"),
                "cost": scores.get("cost_usd"),
                "dirty": (rec.get("build") or {}).get("dirty", "absent"),
                "named_goal": rec.get("goal"),
            }
        hidden: dict[str, dict[str, str]] = {}
        first_items: dict[str, str] = {}
        for n in _runstore.listdir(proj, "datasets"):
            doc = _runstore.read_json(proj, f"datasets/{n}") if n.endswith(".json") else {}
            ds = n[: -len(".json")]
            if doc.get("items"):
                first_items[ds] = doc["items"][0]["item_id"]
            if doc.get("text") != "hidden":
                continue
            items = {}
            for it in doc.get("items") or []:
                f = data / "materialized" / ds / f"{it['item_id']}.txt"
                if _store.is_file(f):
                    items[it["item_id"]] = _store.read_text(f, encoding="utf-8").strip()[:48]
            hidden[ds] = items
    return {"runs": runs, "hidden": hidden, "first_items": first_items}


#: name -> the function; the time-zone variants change the environment the readers run in, not the data
MUTATIONS: dict[str, Callable[[Path], None]] = {
    "no_goal": no_goal,
    "cost_zero_and_missing": cost_zero_and_missing,
    "dirty_null": dirty_null,
    "unicode_ids": unicode_ids,
    "underscore_r_not_a_set": underscore_r_not_a_set,
    "missing_optional_fields": missing_optional_fields,
    "n_items_missing": n_items_missing,
    "extra_unknown_fields": extra_unknown_fields,
    "two_goals_two_baselines": two_goals_two_baselines,
    "utc_day_boundary": utc_day_boundary,
    "reference_gone": reference_gone,
    "goal_measure_unrecorded": goal_measure_unrecorded,
    "no_fingerprint": no_fingerprint,
    "hide_a_dataset": hide_a_dataset,
}


def main(argv: list[str]) -> int:
    """Apply mutation `argv[0]` to the project in `argv[1]`, or with `oracle` print what its files say as JSON; return 0, or
    2 with the usage."""
    if len(argv) != 2 or (argv[0] not in MUTATIONS and argv[0] != "oracle"):
        print(__doc__)
        return 2
    proj = Path(argv[1]).resolve()
    os.environ["EVAL_HOME"] = str(proj)
    if argv[0] == "oracle":
        print(json.dumps(oracle(proj)))
    else:
        MUTATIONS[argv[0]](proj)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
