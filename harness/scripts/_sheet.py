"""The sheet (RFC-023, PRD-014 FR8): one view of everything a dataset's items and arms have.

    evh inspect --sheet --dataset-id prod_2026_11 --runs production_2026_11,triage_lead_v1 \\
        --wrong-against owner_2026_11 --new-vs triage_v1

The items down, a column per arm across: what each wrote, every score it has on that item (its run's metrics, the
primary first, and the judge's, where a judging pass under data/runs-judged/<scorer>/ covered that run), a column
per label set or reference set, the winner per row, the signals, and a footer per arm. The inspector's page, the
terminal and the CSV are this model, flattened three ways.

Winner: per judging scorer with a `judge_won` metric (pick, pairwise) the arm(s) with the most; and on the chosen
metric (`--metric`, else the goal's primary, else the runs' primary) the best arm in the metric's direction. Every
arm tied for the best is named. On a pick or pairwise verdict only an arm the judge preferred (`judge_won` above 0)
wins: a row the judge gave to an arm not shown has no winner. Footer, per arm: its mean on the chosen metric, its
win rate (the share of the rows shown that it wins, a shared win split; on a pick or pairwise verdict, of the rows
judged, so a row nobody shown won counts against every arm), and the verdict: the goal's decision (axes.decide) when
a goal names the dataset, else the paired test against the leader.

The signals, each a filter (given together, an item needs all of them) and the sort (most signals first):

- wrong: the first run's decision (production's, by convention) is wrong against the label, in --wrong-against SET:
  the adapter's own score of the output against the label says so (`correct` 0), else it is not the label's
  decision by `same(a, b)`;
- disagree: another run decided differently from the first;
- split: the other runs (the candidates) decided differently among themselves;
- new: a field value the dataset in --new-vs has never had: its choice and yes/no fields, and its text fields with at
  most NEW_MAX values there (an alert name, a source), never a date or a number (each new day would read new);
- unlabelled: no label in any set yet.

"Decided the same" is the first run's adapter's `same(a, b)` (the same text when it has none). Nothing is written:
the view ends with the `evh pick` and `evh label-sheet` commands for the rows it shows.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import random
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _outputs, _store
from evaluation_harness._common import (
    BOOKKEEPING_PREFIXES,
    LABELS_PREFIX,
    classify_metrics,
    die,
    load_dataset,
    load_goals,
    read_json,
    scored_against_dir,
)
from evaluation_harness._label_sets import answers, label_line, labels_for, sets, source_line
from evaluation_harness._runs import item_rows, lower_is_better_on, read_metrics, runs_on
from evaluation_harness._sheets import ALSO, NOTE, label_header
from evaluation_harness.label_sheet import run_dir, view

SIGNALS = ("wrong", "disagree", "split", "new", "unlabelled")
#: --new-vs compares a field only when the governed dataset has at most this many values for it (a choice, an
#: alert name, a source), not a free text where every value is new.
NEW_MAX = 30
#: The longest title(item) the sheet shows as an item's start (the item's own start is label_sheet.VIEW).
VIEW_TITLE = 160
#: A judged run's per-item metric that says who won the row (pick, pairwise), and the one that grades it. An
#: unvalidated judging pass names them with a `_unvalidated` ending (judge_score.write_scored_runs).
WON = ("judge_won", "judge_won_unvalidated")
GRADE = ("judge_score", "judge_score_unvalidated")
FILLS = ("label", "pick", "scores", "tags")
#: The marker of a row that is not an item (the rubric, a footer): sheet-import leaves out every item_id starting so.
NOT_AN_ITEM = "#"
KEY_SUFFIX = ".key.json"
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _set_named(name: str, dataset_id: str) -> None:
    """Refuse a label set no dataset has, and a bare name that two datasets' sets on this dataset's items share
    (labels follow an item by its bytes into every dataset holding it): which one the row read was a guess."""
    if not any(name in (d["set"], f"{d['dataset_id']}/{d['set']}") for d in sets()):
        die(f"--wrong-against {name}: no such label set (evh labels lists them)", "not-found")
    if "/" not in name:
        same = sorted(
            {
                f"{r['dataset_id']}/{r['set']}"
                for rows in labels_for(dataset_id).values()
                for r in rows
                if r["set"] == name
            }
        )
        if len(same) > 1:
            die(
                f"--wrong-against {name}: {len(same)} label sets are named so ({', '.join(same)}); name one as DATASET/SET",
                "bad-argument",
            )


def _new_values(fields_of, dataset_id: str, new_vs: str) -> dict[str, list[str]]:
    """{item: ["field=value", ...]}: the values of this dataset's items that `new_vs` has never had."""
    decl, values = fields_of(dataset_id)
    vdecl, vvalues = fields_of(new_vs)
    seen: dict[str, set[str]] = {}
    for name in decl:
        if name in vdecl:
            have = {str(v) for vs in vvalues.values() if (v := vs.get(name)) is not None}
            kind = (vdecl[name] or {}).get("type")
            if kind in ("choice", "boolean") or (kind in ("text", "url") and len(have) <= NEW_MAX):
                seen[name] = have
    out: dict[str, list[str]] = {}
    for item, vs in values.items():
        new = [f"{n}={vs[n]}" for n, have in seen.items() if vs.get(n) is not None and str(vs[n]) not in have]
        if new:
            out[item] = new
    return out


def _short(text: Any, n: int = 48) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= n else one[: n - 1] + "…"


# ── the arms ─────────────────────────────────────────────────────────────────────────────────────


def _numbers(row: dict) -> dict[str, float]:
    """A prediction row's metrics: its numbers (a boolean is not one), bookkeeping and `_` fields left out."""
    return {
        k: float(v)
        for k, v in row.items()
        if k != "item_id"
        and not k.startswith(("_", *BOOKKEEPING_PREFIXES))
        and isinstance(v, (int, float))
        and not isinstance(v, bool)
    }


def _arm_dir(token: str, dataset_id: str, from_dir: str) -> Path:
    """A run by its id, or a config's latest run on the dataset, under `from_dir` (runs, runs-silver,
    runs-judged/<scorer>); `runs` is also where label_sheet.run_dir looks (and in the label sets' runs)."""
    if from_dir and from_dir != "runs":
        if ".." in Path(from_dir).parts:
            die(f"--from {from_dir}: a folder under data/", "bad-argument")
        base = _common.DATA / from_dir
        d = base / token
        m = read_metrics(d) if _store.is_dir(d) else None
        if m is not None:
            if m.get("dataset_id") != dataset_id:
                die(f"--runs {token}: that run is not on {dataset_id}", "mismatch")
            return d
        found = runs_on(dataset_id, runs_dir=base, config_id=token)
        if found:
            return found[-1][0]
        die(f"--runs {token}: no run of that config on {dataset_id} under {from_dir}", "not-found")
    return run_dir(token, dataset_id)


def _judged(d: Path, dataset_id: str) -> list[dict[str, Any]]:
    """The judging passes that covered run `d`: data/runs-judged/<scorer>/<same run folder>, each {scorer, dir,
    metrics, per_item {item: {metric: value}}, names (the judge's metrics a cell shows)}."""
    root = _common.DATA / "runs-judged"
    out = []
    for sd in sorted(_store.iterdir(root)) if _store.is_dir(root) else []:
        jd = sd / d.name
        if not _store.is_dir(sd) or sd == d.parent or not _store.is_dir(jd):
            continue
        jm = read_metrics(jd)
        if (
            jm is None
            or jm.get("dataset_id") != dataset_id
            or (jm.get("derived") or {}).get("kind") != "judge"
        ):
            continue
        per = {r["item_id"]: _numbers(r) for r in item_rows(jd, strict=False)}
        have = {k for r in per.values() for k in r}
        names = [n for n in dict.fromkeys([jm.get("primary_metric"), *WON, *GRADE]) if n and n in have]
        if names:
            out.append({"scorer": sd.name, "dir": jd, "metrics": jm, "per_item": per, "names": names})
    return out


def _under_data(d: Path) -> str:
    """A run folder as a path under data/ (where the key finds it again), else as it is."""
    try:
        return d.resolve().relative_to(_common.DATA.resolve()).as_posix()
    except ValueError:
        return str(d)


def _arm(token: str, dataset_id: str, from_dir: str) -> dict[str, Any]:
    d = _arm_dir(token, dataset_id, from_dir)
    return {
        "token": token,
        "dir": d,
        "metrics": read_metrics(d) or {},
        "per_item": {r["item_id"]: _numbers(r) for r in item_rows(d, strict=False)},
        "judged": _judged(d, dataset_id),
    }


def _series(a: dict[str, Any], ref: str) -> dict[str, float]:
    """{item: value} of one metric of an arm: `metric` (its run's) or `scorer/metric` (a judging pass's)."""
    scorer, _, name = ref.rpartition("/")
    if scorer:
        j = next((j for j in a["judged"] if j["scorer"] == scorer), None)
        src = j["per_item"] if j else {}
    else:
        src = a["per_item"]
    return {i: r[name] for i, r in src.items() if name in r}


def _runs_of(arms: list[dict[str, Any]], ref: str) -> list[tuple[Path, dict]]:
    """The run records a metric ref is read from (for its direction)."""
    scorer = ref.rpartition("/")[0]
    if scorer:
        return [(j["dir"], j["metrics"]) for a in arms for j in a["judged"] if j["scorer"] == scorer]
    return [(a["dir"], a["metrics"]) for a in arms]


def _goal_for(dataset_id: str, arms: list[dict[str, Any]]) -> tuple[str, dict] | None:
    """The goal the runs name, else a goal whose datasets list this one (the first by id): (id, goal)."""
    goals = load_goals()
    named = [m for a in arms if (m := a["metrics"].get("goal")) in goals]
    if named:
        return named[0], goals[named[0]]
    for gid in sorted(goals):
        if dataset_id in [d.get("dataset_id") for d in goals[gid].get("datasets") or []]:
            return gid, goals[gid]
    return None


def _resolve_metric(arms: list[dict[str, Any]], spec: str | None, goal: dict | None) -> str | None:
    """The metric ref the sheet is read on: `--metric` (a run's metric, or SCORER/metric), else the goal's primary
    measure when an arm records it, else the first arm's primary metric."""
    own = {k for a in arms for r in a["per_item"].values() for k in r}
    judged: dict[str, set[str]] = {}
    for a in arms:
        for j in a["judged"]:
            for k in {k for r in j["per_item"].values() for k in r}:
                judged.setdefault(k, set()).add(j["scorer"])

    def find(name: str) -> str | None:
        if "/" in name:
            scorer, _, metric = name.rpartition("/")
            return name if scorer in judged.get(metric, set()) else None
        if name in own:
            return name
        if len(judged.get(name, ())) == 1:
            return f"{next(iter(judged[name]))}/{name}"
        return None

    if spec:
        got = find(spec)
        if got:
            return got
        if len(judged.get(spec, ())) > 1:
            die(
                f"--metric {spec}: judged by {', '.join(sorted(judged[spec]))}; name one (SCORER/{spec})",
                "bad-argument",
            )
        known = sorted(own | {f"{s}/{k}" for k, ss in judged.items() for s in ss})
        die(
            f"--metric {spec}: no run in --runs records it (recorded: {', '.join(known) or 'none'})",
            "not-found",
        )
    measure = ((goal or {}).get("success_criteria") or {}).get("primary", {}).get("measure")
    if measure and find(measure):
        return find(measure)
    for a in arms:
        p = a["metrics"].get("primary_metric")
        if p and p in own:
            return str(p)
    if arms and own:
        return sorted(own)[0]
    if arms:
        die("no run in --runs records a per-item metric: nothing to read the sheet on", "not-enough")
    return None


def _shown_names(a: dict[str, Any], chosen: str | None) -> list[str]:
    """The run's metrics a cell shows, the primary first: quality metrics, the primary, and the chosen one."""
    keys = {k for r in a["per_item"].values() for k in r}
    kinds = classify_metrics(a["metrics"].get("metric_kinds"))
    primary = a["metrics"].get("primary_metric")
    keep = [k for k in sorted(keys) if kinds.get(k, "quality") == "quality" or k in (primary, chosen)]
    return sorted(keep, key=lambda k: (k != primary, k))


def _best(values: dict[str, float], lower: bool) -> list[str]:
    """The arms tied for the best value (to 1e-9), in the order given."""
    if not values:
        return []
    top = (min if lower else max)(values.values())
    return [t for t, v in values.items() if abs(v - top) <= 1e-9]


# ── the model ────────────────────────────────────────────────────────────────────────────────────


def build(
    dataset_id: str,
    tokens: list[str],
    fields_of,
    *,
    metric: str | None = None,
    from_dir: str = "runs",
    wrong_against: str | None = None,
    new_vs: str | None = None,
    items: list[str] | None = None,
) -> dict[str, Any]:
    """The sheet of a dataset over runs (ids, or config ids: their latest run on the dataset; the first stands for
    production): {dataset_id, arms [{token, run, path, config_id, scores [ref]}], metric (a ref), lower, goal, decl,
    label_cols, ref_cols, winner_cols, metrics (every ref one can be read on), rows}, one row per item of the dataset (or `items`) in its order, each
    {item, text, fields, decisions {token: output}, shown {token: what a view shows}, scores {token: {ref: value}},
    labels [{set, dataset_id, source, text}], label_text {key: line}, references {id: text}, winners {key: [token]},
    signals {name: detail}}. `fields_of(dataset)` gives ({name: field}, {item: {name: value}}) (the inspector's
    `_fields_of`). Filtering, the footer and the flat forms are the functions below."""
    from evaluation_harness._adapter import adapter_module, decision_of, same_of, shown, title_of  # noqa: PLC0415

    ds = load_dataset(dataset_id)
    if len(set(tokens)) != len(tokens):
        die("--runs names an arm twice", "bad-argument")
    arms = [_arm(t, dataset_id, from_dir) for t in tokens]
    found_goal = _goal_for(dataset_id, arms)
    ref = _resolve_metric(arms, metric, found_goal[1] if found_goal else None)
    lower = bool(ref) and lower_is_better_on(_runs_of(arms, str(ref)), str(ref).rpartition("/")[2])

    spec = arms[0]["metrics"].get("adapter") if arms else None
    deciders = {a["token"]: decision_of(a["metrics"].get("adapter")) for a in arms}
    same = same_of(spec) if arms else None
    score = getattr(adapter_module(spec), "score", None) if arms else None
    titled = title_of(spec) if arms else None

    def start(i: str) -> str:
        """The item's start: the first arm's adapter's title(item) when it gives one, else the item's own start."""
        if titled is not None:
            whole = view(dataset_id, i, None)
            try:
                got = titled(whole) if whole else None
            except Exception:  # noqa: BLE001 - an item the adapter cannot read shows its own start
                got = None
            if got:
                return _short(got, VIEW_TITLE)
        return view(dataset_id, i)

    def is_wrong(label: str, out: str) -> bool:
        """The adapter's verdict on an output against a label (`correct` 0), else none of the label's answers."""
        if callable(score):
            try:
                got = score(out, label)
            except Exception:  # noqa: BLE001 - an adapter that cannot score this pair falls back to same()
                got = None
            if isinstance(got, dict) and "correct" in got:
                return bool(got["correct"] == 0)
        return same is not None and not any(same(x, out) for x in answers(label))

    if wrong_against:
        _set_named(wrong_against, dataset_id)
    if new_vs:
        load_dataset(new_vs)
    new = _new_values(fields_of, dataset_id, new_vs) if new_vs else {}
    decl, values = fields_of(dataset_id)
    labels = labels_for(dataset_id)

    label_cols: dict[str, dict[str, Any]] = {}
    for found in labels.values():
        for x in found:
            key = f"{x['dataset_id']}/{x['set']}"
            name = x["set"] if x["dataset_id"] == dataset_id else key
            label_cols.setdefault(
                key,
                {
                    "key": key,
                    "name": name,
                    "kind": x["source"].get("kind", ""),
                    "by": source_line(x["source"]),
                    "header": f"label: {name} ({source_line(x['source'])})",
                },
            )
    refs: dict[str, Path] = {}
    for a in arms:
        rid = ((a["metrics"].get("fingerprint") or {}).get("data") or {}).get("reference_id") or a[
            "metrics"
        ].get("reference_id")
        d = scored_against_dir(rid) if rid and not str(rid).startswith(LABELS_PREFIX) else None
        if rid and d is not None and _store.is_dir(d):
            refs.setdefault(str(rid), d)
    ref_cols = [{"key": rid, "header": f"reference: {rid}"} for rid in refs]

    series: dict[str, dict[str, dict[str, float]]] = {}
    for a in arms:
        own = {k for r in a["per_item"].values() for k in r}
        s = {k: _series(a, k) for k in own}
        for j in a["judged"]:
            for k in {k for r in j["per_item"].values() for k in r}:
                s[f"{j['scorer']}/{k}"] = _series(a, f"{j['scorer']}/{k}")
        series[a["token"]] = s
    score_refs: dict[str, list[str]] = {}
    for a in arms:
        t = a["token"]
        shown_ = [k for k in _shown_names(a, ref if ref and "/" not in ref else None) if series[t].get(k)]
        if ref and ref not in shown_ and series[t].get(ref):
            shown_.append(ref)
        for j in a["judged"]:
            shown_ += [f"{j['scorer']}/{n}" for n in j["names"] if series[t].get(f"{j['scorer']}/{n}")]
        score_refs[t] = list(dict.fromkeys(shown_))

    won_scorers = sorted(
        {j["scorer"] for a in arms for j in a["judged"] if any(n in WON for n in j["names"])}
    )
    winner_cols: list[dict[str, Any]] = [
        {"key": f"winner: {s}", "header": f"winner: {s}", "judge": s} for s in won_scorers
    ]
    chosen_is_won = (
        bool(ref) and str(ref).rpartition("/")[0] in won_scorers and str(ref).rpartition("/")[2] in WON
    )
    if ref and not chosen_is_won:
        winner_cols.append({"key": f"winner: {ref}", "header": f"winner: {ref}", "metric": ref})

    from evaluation_harness import _tags  # noqa: PLC0415

    tagged = _tags.by_run(dataset_id)
    tag_arms = [a["token"] for a in arms if a["dir"].name in tagged]
    wanted = set(items) if items is not None else None
    out = []
    # Each arm's outputs read once, not once an item: 50 arms on 10,000 items were 500,000 lookups, each finding the
    # run's source again (in the SQLite store, 4 path resolutions a lookup: 121 of a 146 s sheet, PLAN_0.8.0 S3).
    texts = {a["token"]: _outputs.outputs(a["dir"]) for a in arms}
    for it in ds.get("items") or []:
        i = it["item_id"]
        if wanted is not None and i not in wanted:
            continue
        dec = {t: (txt.strip() if (txt := texts[t].get(i)) is not None else None) for t in texts}
        mine = labels.get(i, [])
        sig: dict[str, str] = {}
        outs = [(n, o) for n, o in dec.items() if o is not None]
        first = dec.get(tokens[0]) if tokens else None
        if wrong_against and first is not None and same is not None:
            lab = next(
                (r["text"] for r in mine if wrong_against in (r["set"], f"{r['dataset_id']}/{r['set']}")),
                None,
            )
            if lab is not None and is_wrong(lab, first):
                sig["wrong"] = wrong_against
        if first is not None and same is not None:
            off = [n for n, o in outs if n != tokens[0] and not same(first, o)]
            if off:
                sig["disagree"] = ", ".join(off)
        cands = [o for n, o in outs if n != tokens[0]]
        if same is not None and len(cands) > 1 and any(not same(cands[0], o) for o in cands[1:]):
            sig["split"] = f"{len(cands)} candidates"
        if i in new:
            sig["new"] = ", ".join(new[i])
        if not mine:
            sig["unlabelled"] = ""
        winners: dict[str, list[str]] = {}
        # {pick or pairwise column: {arm: its judge_won on this row}}: the win rate credits each arm its own share.
        judged_on: dict[str, dict[str, float]] = {}
        # {metric column: the arms with a value on this row}: an arm's win rate is over the rows it was scored on.
        scored_on: dict[str, list[str]] = {}
        for w in winner_cols:
            if "judge" in w:
                vals = {
                    a["token"]: v
                    for a in arms
                    for j in a["judged"]
                    if j["scorer"] == w["judge"]
                    for n in WON
                    if (v := j["per_item"].get(i, {}).get(n)) is not None
                }
            else:
                vals = {t: s[w["metric"]][i] for t, s in series.items() if i in s.get(w["metric"], {})}
            if "judge" in w or w["metric"] in WON:
                # A pick or pairwise verdict: only an arm the judge preferred wins the row. When the judge picked an
                # arm not shown, every shown arm has 0, and the row is nobody's win (it still counts in the rate).
                if vals:
                    judged_on[w["key"]] = vals
                winners[w["key"]] = _best({t: v for t, v in vals.items() if v > 0}, False)
            else:
                scored_on[w["key"]] = sorted(vals)
                winners[w["key"]] = _best(vals, lower)
        out.append(
            {
                "item": i,
                "text": start(i),
                "fields": values.get(i, {}),
                "decisions": dec,
                "shown": {n: shown(deciders.get(n), o) for n, o in dec.items()},
                "scores": {
                    t: {k: series[t][k][i] for k in score_refs[t] if i in series[t][k]} for t in series
                },
                "labels": mine,
                "label_text": {f"{x['dataset_id']}/{x['set']}": label_line(x["text"]) for x in mine},
                "references": {
                    rid: txt
                    for rid, d in refs.items()
                    if _store.is_file(f := d / f"{i}.txt")
                    and (txt := _store.read_text(f, encoding="utf-8").strip())
                },
                "winners": winners,
                "judged_on": judged_on,
                "scored_on": scored_on,
                "signals": sig,
                # The failure modes tagged on each arm's output (PLAN_0.8.0 D1): [] read and fine; absent not read.
                "tags": {
                    a["token"]: tagged[a["dir"].name][i] for a in arms if i in tagged.get(a["dir"].name, {})
                },
            }
        )
    return {
        "dataset_id": dataset_id,
        "tag_arms": tag_arms,
        "arms": [
            {
                "token": a["token"],
                "run": a["dir"].name,
                "path": _under_data(a["dir"]),
                "config_id": a["metrics"].get("config_id", ""),
                "scores": score_refs[a["token"]],
            }
            for a in arms
        ],
        "metric": ref,
        "lower": lower,
        "goal": found_goal[0] if found_goal else None,
        "decl": decl,
        "label_cols": sorted(label_cols.values(), key=lambda c: c["key"]),
        "ref_cols": ref_cols,
        "winner_cols": winner_cols,
        "metrics": sorted({k for s_ in series.values() for k in s_}),
        "rows": out,
        "_series": series,
        "_goal": found_goal[1] if found_goal else None,
        "_runs": [(a["dir"], a["metrics"]) for a in arms],
    }


def by_where(model: dict[str, Any], where: list[str]) -> list[dict[str, Any]]:
    """The rows whose fields match every `--where FIELD:VALUE` (FIELD:LO..HI); refused for a field the dataset lacks."""
    from evaluation_harness import _fields  # noqa: PLC0415

    found: list[dict[str, Any]] = model["rows"]
    for w in where:
        name, _, want = w.partition(":")
        if name not in model["decl"]:
            die(f"--where {w}: no field {name!r} on {model['dataset_id']}", "not-found")
        try:
            found = [r for r in found if _fields.matches(model["decl"][name], r["fields"].get(name), want)]
        except ValueError as exc:
            die(f"--where {w}: {exc}", "bad-argument")
    return found


def by_signals(rows: list[dict[str, Any]], wanted: list[str]) -> list[dict[str, Any]]:
    """The rows carrying every signal asked for, the ones with most signals first (the dataset's order within)."""
    return sorted(
        (r for r in rows if all(s in r["signals"] for s in wanted)), key=lambda r: -len(r["signals"])
    )


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """How many of the rows carry each signal."""
    return {s: sum(s in r["signals"] for r in rows) for s in SIGNALS}


# ── the footer ───────────────────────────────────────────────────────────────────────────────────


def _verdicts(model: dict[str, Any], sub: dict[str, dict[str, float]]) -> tuple[dict[str, str], str]:
    """({arm: verdict}, how it was decided). With a goal naming the dataset: axes.decide over the rows shown, on the
    chosen metric (leader, contender, out and why, else the paired test against the leader). Without: the paired
    test of every arm against the one with the best mean."""
    from evaluation_harness import axes, stats  # noqa: PLC0415

    toks = [t for t, s in sub.items() if s]
    if not toks:
        return dict.fromkeys(sub, ""), ""
    ref, lower = model["metric"], model["lower"]
    # An arm with no score on the metric was not measured on it: no verdict, and it takes no part in the decision
    # (a goal's decision over one scored arm crowned it "leader, recommended" for the other's want of a score).
    unscored = {t: f"no {ref} in this run" for t, s in sub.items() if not s}
    if len(toks) < 2:
        return {**dict.fromkeys(toks, f"the only arm shown with {ref}: nothing to compare"), **unscored}, ""
    sub = {t: sub[t] for t in toks}
    goal = model["_goal"]
    if goal is not None:
        crit = goal.get("success_criteria") or {}
        if ref != (crit.get("primary") or {}).get("measure"):
            own = {k: v for k, v in (crit.get("axes") or {}).items() if k != "quality"}
            goal = {
                **goal,
                "success_criteria": {
                    **crit,
                    "primary": {"measure": ref, "direction": "lower" if lower else "higher"},
                    "axes": own,
                },
            }
        keep = {i for s in sub.values() for i in s}
        arms_ = {
            t: {
                "label": t,
                "flags": [],
                "scores": {
                    k: {"values": {i: v for i, v in vs.items() if i in keep}}
                    for k, vs in model["_series"][t].items()
                },
            }
            for t in sub
        }
        field = _common.goal_cluster(goal, model["dataset_id"])
        dec = axes.decide(
            goal,
            arms_,
            lambda m: "lower" if lower_is_better_on(model["_runs"], m) else None,
            clusters=_common.item_clusters(model["dataset_id"], field) if field else None,
            cluster_by=field,
        )
        if dec["leader"] is not None:
            out = {}
            for t in sub:
                q = dec["rows"][t]["quality"].get("vs_leader") or {}
                test = q.get("verdict", "") + (
                    f" (p {stats.fmt_p(q['p'])})" if q.get("p") is not None else ""
                )
                if t in dec["out"]:
                    out[t] = "out: " + "; ".join(dec["out"][t])
                elif t == dec["leader"]:
                    out[t] = "leader, recommended" if dec["recommended"] == t else "leader"
                elif t in dec["contenders"]:
                    out[t] = "contender"
                else:
                    out[t] = f"not a contender: {test}" if test else "not a contender"
            return {**out, **unscored}, f"the goal {model['goal']}'s decision"
    means = {t: statistics.fmean(sub[t].values()) for t in toks}
    leader = _best(means, lower)[0]
    cmp = stats.compare({t: sub[t] for t in toks}, leader, higher_is_better=not lower)
    out = dict.fromkeys(sub, "")
    out[leader] = "leader"
    for r in cmp["rows"]:
        out[r["arm"]] = r["verdict"] + (f" (p {stats.fmt_p(r['p'])})" if r.get("p") is not None else "")
    return {**out, **unscored}, "the paired test against the leader"


def footer(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per arm, over the rows given: {metric, mean {arm}, n {arm}, win_rate {winner column: {arm}}, verdict {arm},
    decided}. A win rate is the share of the rows with a winner that the arm wins, a shared win split; on a pick or
    pairwise verdict, the arm's share of what the judge gave over the rows it judged (its judge_won, the judging
    pass's own win rate when every arm is shown), a row the judge gave to an arm not shown being nobody's."""
    toks = [a["token"] for a in model["arms"]]
    ref = model["metric"]
    items = {r["item"] for r in rows}
    sub = {t: {i: v for i, v in (model["_series"][t].get(ref) or {}).items() if i in items} for t in toks}
    rates: dict[str, dict[str, float | None]] = {}
    for w in model["winner_cols"]:
        judged = [r["judged_on"][w["key"]] for r in rows if w["key"] in r["judged_on"]]
        if judged:
            rates[w["key"]] = {t: sum(v.get(t, 0.0) for v in judged) / len(judged) for t in toks}
            continue
        # Over the rows each arm was scored on: an arm with no value on a row was not compared there, and one scored on
        # none has no win rate (not 0, which would read as always beaten).
        won = [
            (r["winners"][w["key"]], r["scored_on"].get(w["key"], []))
            for r in rows
            if r["winners"].get(w["key"])
        ]
        rates[w["key"]] = {}
        for t in toks:
            mine = [x for x, scored in won if t in scored]
            rates[w["key"]][t] = sum(1 / len(x) for x in mine if t in x) / len(mine) if mine else None
    verdict, decided = _verdicts(model, sub) if ref and toks else (dict.fromkeys(toks, ""), "")
    return {
        "metric": ref,
        "mean": {t: (statistics.fmean(s.values()) if s else None) for t, s in sub.items()},
        "n": {t: len(s) for t, s in sub.items()},
        "win_rate": rates,
        "verdict": verdict,
        "decided": decided,
    }


def footer_table(model: dict[str, Any], f: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    """The footer as a table of its own: a column per arm, a line per row (the terminal's, the JSON's)."""
    toks = [a["token"] for a in model["arms"]]
    way = "lower" if model["lower"] else "higher"
    lines: list[list[Any]] = [
        [f"mean {f['metric']} ({way} is better)", *[f["mean"][t] for t in toks]],
        ["rows scored", *[f["n"][t] for t in toks]],
    ]
    for w in model["winner_cols"]:
        lines.append([f"win rate · {w['header']}", *[f["win_rate"][w["key"]][t] for t in toks]])
    lines.append(
        [f"verdict ({f['decided']})" if f["decided"] else "verdict", *[f["verdict"][t] for t in toks]]
    )
    return ["per arm", *toks], lines


# ── flat forms: the terminal, the CSV ────────────────────────────────────────────────────────────


def flat(
    model: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    scores_only: bool = False,
    short: bool = False,
    picked: Callable[[str], str] | None = None,
    split_fields: bool = False,
) -> tuple[list[str], list[list[Any]], dict[str, dict[str, int | None]]]:
    """(header, rows, anchors): the sheet as a table. `short` shortens the texts for a terminal; `picked` adds the
    column of what is picked; `split_fields` gives each field a column (the CSV), else one `fields` column. The
    anchors say, per arm, where its columns start and which one holds the chosen metric (where a footer goes)."""

    def cut(s: Any, n: int) -> str:
        return _short(s, n) if short else str(s or "")

    def shown_of(t: str) -> Callable[[dict], Any]:
        return lambda r: cut(r["shown"].get(t), 48)

    def score_of(t: str, k: str) -> Callable[[dict], Any]:
        return lambda r: r["scores"][t].get(k)

    def label_of(key: str) -> Callable[[dict], Any]:
        return lambda r: cut(r["label_text"].get(key, ""), 32)

    def reference_of(key: str) -> Callable[[dict], Any]:
        return lambda r: cut(r["references"].get(key, ""), 32)

    def winner_of(key: str) -> Callable[[dict], Any]:
        return lambda r: " = ".join(r["winners"].get(key) or [])

    def tags_of(t: str) -> Callable[[dict], Any]:
        return lambda r: "" if t not in r.get("tags", {}) else "|".join(r["tags"][t]) or "ok"

    def field_of(name: str) -> Callable[[dict], Any]:
        return lambda r: _blank(r["fields"].get(name))

    cols: list[tuple[str, Callable[[dict], Any]]] = [
        ("item_id", lambda r: r["item"]),
        ("item", lambda r: cut(r["text"], 40)),
        ("signals", lambda r: ", ".join(f"{s} ({d})" if d else s for s, d in r["signals"].items())),
    ]
    anchors: dict[str, dict[str, int | None]] = {}
    for a in model["arms"]:
        t = a["token"]
        first, at = len(cols), None
        if not scores_only:
            cols.append((t, shown_of(t)))
        for k in a["scores"]:
            if k == model["metric"]:
                at = len(cols)
            cols.append((f"{t}: {k}", score_of(t, k)))
        if t in model.get("tag_arms", []):
            cols.append((f"{t}: failure modes", tags_of(t)))
        if len(cols) > first:
            anchors[t] = {"first": first, "metric": at}
    cols += [(c["header"], label_of(c["key"])) for c in model["label_cols"]]
    cols += [(c["header"], reference_of(c["key"])) for c in model["ref_cols"]]
    cols += [(w["header"], winner_of(w["key"])) for w in model["winner_cols"]]
    if picked is not None:
        cols.append(("picked", lambda r: picked(r["item"])))
    if split_fields:
        cols += [(f"field: {name}", field_of(name)) for name in model["decl"]]
    else:
        cols.append(("fields", lambda r: cut(", ".join(f"{k}={v}" for k, v in r["fields"].items()), 60)))
    return [h for h, _ in cols], [[g(r) for _, g in cols] for r in rows], anchors


def _blank(v: Any) -> Any:
    return "" if v is None else v


def csv_sheet(
    model: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    scores_only: bool = False,
    fill: str | None = None,
    choices: list[str] | None = None,
) -> tuple[list[str], list[list[Any]]]:
    """The CSV of the sheet (header, rows): the flat form with a column per field, and after the rows the footer
    (each line an `item_id` starting `#`, which sheet-import leaves out). `fill="label"` adds the empty columns a
    person labels in: `label` (the allowed `choices` in its header), `also right` and `note`, and no footer."""
    head, body, anchors = flat(model, rows, scores_only=scores_only, split_fields=True)
    if fill == "label":
        return [*head, label_header(choices), ALSO, NOTE], [[*r, "", "", ""] for r in body]
    f = footer(model, rows)

    def line(name: str, per_arm: dict[str, Any], on_metric: bool = False) -> list[Any]:
        row: list[Any] = [""] * len(head)
        row[0] = f"{NOT_AN_ITEM}{name}"
        for t, v in per_arm.items():
            a = anchors.get(t)
            if a is not None and v is not None:
                row[a["metric"] if on_metric and a["metric"] is not None else a["first"]] = v  # type: ignore[index]
        return row

    foot = [line(f"mean {f['metric']}", f["mean"], on_metric=True)]
    for w in model["winner_cols"]:
        foot.append(line(f"win rate · {w['header']}", f["win_rate"][w["key"]]))
    foot.append(line("verdict", f["verdict"]))
    return head, [*body, *foot]


# ── a sheet filled elsewhere: blind columns and the key ──────────────────────────────────────────


def text_sha256(text: str) -> str:
    """sha256 of a text with its whitespace collapsed: a spreadsheet may re-wrap a cell, never change its words."""
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def rubric_text(fill: str, scale: tuple[int, int], given: str | None) -> str:
    """What the filler is asked: the rubric a person wrote (--rubric FILE), else the default for the fill."""
    if given and given.strip():
        return given.strip()
    if fill == "pick":
        return (
            "Pick the best output for each item: write its letter in the `pick` column (`A|B` when two are equally "
            "best). Leave a row empty to skip it."
        )
    return (
        f"Score each output for each item from {scale[0]} to {scale[1]} (higher is better) in its `score` column. "
        "Leave a cell empty to skip it."
    )


def blind(
    model: dict[str, Any],
    rows: list[dict[str, Any]],
    fill: str,
    *,
    seed: int = 0,
    rubric: str,
    scale: tuple[int, int] = (1, 5),
) -> tuple[list[str], list[list[Any]], dict[str, Any], int]:
    """A sheet to judge in: (header, rows, key, rows left out). The arms' outputs are columns A, B, C… in an order
    shuffled per row by the seed, and the sheet names no arm; the key says which letter was which arm on each row,
    the rubric and its sha256, and each cell's text hash (so a sheet that is not the key's is refused). The first
    row is the rubric, its `item_id` `#rubric`. `pick` needs two outputs on a row, `scores` one. The `item` column
    holds the whole item (a judge reads what the outputs were written from)."""
    if fill not in ("pick", "scores"):
        raise ValueError(fill)
    n = len(model["arms"])
    if n > len(LETTERS):
        die(f"--fill {fill}: at most {len(LETTERS)} arms", "bad-argument")
    if fill == "pick" and n < 2:
        die("--fill pick needs two runs or more in --runs", "bad-argument")
    letters = list(LETTERS[:n])
    head = [
        "item_id",
        "item",
        *letters,
        *(["pick"] if fill == "pick" else [f"score: {x}" for x in letters]),
        NOTE,
    ]
    body: list[list[Any]] = [[f"{NOT_AN_ITEM}rubric", rubric, *[""] * (len(head) - 2)]]
    key_rows: dict[str, dict[str, Any]] = {}
    left_out = 0
    for r in rows:
        outs = [
            (k, o)
            for k, a in enumerate(model["arms"])
            if (o := (r["decisions"].get(a["token"]) or "").strip())
        ]
        if len(outs) < (2 if fill == "pick" else 1):
            left_out += 1
            continue
        random.Random(f"{seed}:{r['item']}").shuffle(outs)
        cells = {letters[p]: o for p, (_, o) in enumerate(outs)}
        key_rows[r["item"]] = {
            letters[p]: {"arm": k, "text_sha256": text_sha256(o)} for p, (k, o) in enumerate(outs)
        }
        body.append(
            [
                r["item"],
                view(model["dataset_id"], r["item"], None),
                *[cells.get(x, "") for x in letters],
                *[""] * (len(head) - 2 - n),
            ]
        )
    key = {
        "kind": "sheet-key",
        "dataset_id": model["dataset_id"],
        "fill": fill,
        "seed": seed,
        "arms": [
            {"arm": a["token"], "run": a["run"], "path": a["path"], "config_id": a["config_id"]}
            for a in model["arms"]
        ],
        "letters": letters,
        "rubric": rubric,
        "rubric_sha256": hashlib.sha256(rubric.encode("utf-8")).hexdigest(),
        "scale": list(scale) if fill == "scores" else None,
        "rows": key_rows,
    }
    return head, body, key, left_out


def key_path(sheet: Path) -> Path:
    """Where a sheet's key is kept: beside it, `sheet.csv` -> `sheet.key.json`."""
    return sheet.with_name(sheet.stem + KEY_SUFFIX)


def read_key(path: Path) -> dict[str, Any]:
    """A sheet's key; refused when missing or not a key."""
    if not _store.is_file(path):
        die(f"no key at {path}: `--fill` writes it beside the sheet (name another with --key)", "not-found")
    try:
        key = read_json(path)
    except ValueError:
        die(f"{path}: not JSON", "invalid-file")
    if not isinstance(key, dict) or key.get("kind") != "sheet-key" or not key.get("rows"):
        die(f"{path}: not a sheet key", "invalid-file")
    return key
