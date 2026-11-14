"""Format 4, RFC-032 step 4: runs and scores. Every pass of a system over a dataset is one run in data/runs/<run_id>/;
every score of it sits under it, in scores/<scorer>@<reference>/. What a folder meant becomes a field (owner,
2026-11-13, "I agree with six").

It reads the stored data as format 3 kept it, not through the model: runs in data/runs and the other data/runs-*
folders, each run a directory holding metrics.json and predictions.jsonl (outputs.jsonl for a pass).

- A pass (data/runs, runs-linux, runs-pair, runs-repeats) becomes runs/<id>/run.json, the record less what its score
  measured, with `purpose` (run, retime, pair, repeat) and `machine` (its runner's operating system); `of` names the
  one other run of its system on its dataset when there is exactly one. Its outputs.jsonl moves beside it; its
  record's score becomes its first score.
- A score of a pass (runs-silver, runs-adjudicated, runs-rescored/<scorer>/<folder>, runs-judged/<scorer>,
  runs-labels-*, any other runs-* folder whose records are derived) becomes a score of the run it names in
  `derived.from`, keeping what differs from that run, labelled as its folder read ("silver", "rescored cd35dc1f",
  "judged/judge-summ-v1"). A judge score's key names its judging set; its pass's summary.json moves to
  data/judge-summaries/<scorer>@<set>.json.
- `derived.from_dir` names the run's new directory. Rounds: a retirement names the runs it retires, not a folder;
  `scoring.written` names labels. validate.json names arms by label (`runs`, `linux`, `rescored-cd35dc1f`), not
  folders; `scorer_sources[].dir` becomes `arms`. data/renames.json records each arm whose id changed.
- In a SQLite project the outputs and rows the database keeps under a folder's key move to the run's and score's.

Refused, writing nothing: a pass in a folder whose purpose is unknown, a score whose run is missing, two different
scores of one run with one key, a label that would not read as its folder did.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

NUMBER = 4
ABOUT = "RFC-032 step 4: one runs/ collection, each score under its run; a folder's meaning a field (purpose, label)"

#: The folders of passes, and the purpose each meant.
MEASURED = {"runs": "run", "runs-linux": "retime", "runs-pair": "pair", "runs-repeats": "repeat"}
PURPOSE_LABEL = {"run": "", "repeat": "repeats", "pair": "pair"}
SCORE_KEYS = ("scores", "primary_metric", "metric_kinds", "metric_directions", "metric_descriptions",
              "reference_tier", "rescore_dropped_metrics", "derived", "source_created_at")  # fmt: skip
RUN_ONLY = ("purpose", "machine", "of")
#: Files of a run directory that are the run's; the rest are its score's (metrics.json, predictions.jsonl).
RUN_FILES = ("outputs.jsonl", "rows.partial.jsonl")


def _json(p: Path) -> Any:
    try:
        return json.loads(_store.read_text(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rel(p: Path) -> str:
    return p.relative_to(_common.DATA).as_posix()


def _folders() -> list[Path]:
    """Every folder of format 3 that holds runs: data/runs*, runs-judged/<scorer>, runs-rescored/<scorer>/<folder>."""
    out = []
    for top in sorted(_store.glob(_common.DATA, "runs*")):
        if not _store.is_dir(top):
            continue
        if top.name == "runs-judged":
            out += sorted(d for d in _store.iterdir(top) if _store.is_dir(d))
        elif top.name == "runs-rescored":
            out += sorted(
                d
                for h in _store.iterdir(top)
                if _store.is_dir(h)
                for d in _store.iterdir(h)
                if _store.is_dir(d)
            )
        else:
            out.append(top)
    return out


def _runs_in(folder: Path) -> list[Path]:
    return sorted(
        d for d in _store.iterdir(folder) if _store.is_dir(d) and _store.is_file(d / "metrics.json")
    )


def old_label(rel: str) -> str:
    """The label a format 3 folder gave its arms (the catalog's), from its path under data/."""
    if rel == "runs":
        return ""
    parts = rel.split("/")
    if parts[0] == "runs-rescored" and len(parts) == 3:
        src = old_label(parts[2])
        return f"rescored {parts[1][:8]}" + (f", {src}" if src else "")
    if parts[0] == "runs-judged" and len(parts) == 2:
        return f"judged/{parts[1]}"
    return rel.removeprefix("runs-")


def prefix(label: str) -> str:
    """An arm id's first part for a label: `runs` for none, else its slug."""
    return "runs" if not label else re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def _machine(rec: dict) -> str:
    plat = str((((rec.get("fingerprint") or {}).get("runner")) or {}).get("platform") or "")
    return plat.split("/", 1)[0].lower()


def _scorer(rec: dict, judged: bool) -> str:
    w = (rec.get("derived") or {}).get("with") or {}
    if judged:
        return str(w.get("scorer_id") or "")
    sha = w.get("sha256") or (
        (((rec.get("fingerprint") or {}).get("instrument") or {}).get("adapter")) or {}
    ).get("sha256")
    return str(sha or "")[:12]


def _reference(rec: dict, judged: bool) -> str | None:
    if judged:
        return str(((rec.get("derived") or {}).get("with") or {}).get("judging_set_id") or "") or None
    return (((rec.get("fingerprint") or {}).get("data")) or {}).get("reference_id")


def _key(scorer: str, reference: str | None) -> str:
    return f"{scorer}@{str(reference).replace('/', '.') if reference else 'none'}"


def _split(rec: dict, run_rec: dict) -> tuple[dict, list[str]]:
    base = {k: v for k, v in run_rec.items() if k not in RUN_ONLY}
    return {k: v for k, v in rec.items() if k not in base or base[k] != v}, sorted(
        k for k in base if k not in rec
    )


def plan() -> dict[str, Any]:
    """{"runs": {id: run.json}, "scores": [...], "moves": [(src, dst)], "refused": [...], counts}."""
    refused: list[str] = []
    runs: dict[str, dict] = {}
    run_src: dict[str, Path] = {}
    derived: list[tuple[Path, str, dict]] = []
    for folder in _folders():
        rel = _rel(folder)
        purpose = MEASURED.get(rel)
        for d in _runs_in(folder):
            rec = _json(d / "metrics.json")
            if not isinstance(rec, dict) or not rec.get("config_id"):
                refused.append(f"{_rel(d)}: no readable record with a config_id")
                continue
            frm = (rec.get("derived") or {}).get("from")
            if purpose is not None:
                if d.name in runs:
                    refused.append(f"{_rel(d)} and {_rel(run_src[d.name])}: two passes of one id")
                    continue
                r = {k: v for k, v in rec.items() if k not in SCORE_KEYS}
                r["purpose"] = purpose
                r["machine"] = _machine(rec)
                old = _json(d / "run.json")
                for k, v in (old or {}).items() if isinstance(old, dict) else ():
                    r.setdefault(k, v)
                runs[d.name] = r
                run_src[d.name] = d
                derived.append((d, rel, rec))
            elif frm:
                derived.append((d, rel, rec))
            else:
                refused.append(f"{_rel(d)}: a pass in {rel}, a folder whose purpose is not known (one of "
                               f"{', '.join(MEASURED)}): move it into one, or delete it, and migrate again")  # fmt: skip
    of_group: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rid, r in runs.items():
        of_group[(str(r.get("config_id")), str(r.get("dataset_id")))].append(rid)
    no_of = 0
    for rid, r in runs.items():
        if r["purpose"] == "run":
            continue
        others = [x for x in of_group[(str(r.get("config_id")), str(r.get("dataset_id")))] if x != rid]
        if len(others) == 1:
            r["of"] = others[0]
        else:
            no_of += 1
    scores: dict[tuple[str, str], dict] = {}
    duplicates = 0
    arms: dict[str, str] = {}
    for d, rel, rec in derived:
        judged = rel.startswith("runs-judged/")
        measured = rel in MEASURED
        rid = d.name if measured else str((rec.get("derived") or {}).get("from"))
        if rid not in runs:
            refused.append(f"{_rel(d)}: a score of {rid}, a run that is not in {', '.join(MEASURED)}")
            continue
        if not measured:
            own_outs = _outs(d)
            if own_outs is not None and own_outs != _outs(run_src[rid]):
                refused.append(
                    f"{_rel(d)}: a score of {rid} that keeps outputs of its own, not its run's: a score has none "
                    "(its outputs are its run's). Run it again as a run of its own (`evh run`), or delete it, and "
                    "migrate again"
                )
                continue
        new = dict(rec)
        if isinstance(new.get("derived"), dict) and new["derived"].get("from_dir"):
            new["derived"] = {**new["derived"], "from_dir": f"runs/{new['derived']['from']}"}
        scorer = _scorer(rec, judged)
        reference = _reference(rec, judged)
        if not scorer:
            refused.append(
                f"{_rel(d)}: records no scorer (no derived.with.sha256 and no instrument adapter sha256)"
            )
            continue
        # The score's own label; what its run's purpose adds (", repeats") is the run's.
        label = (
            ""
            if measured
            else old_label(
                "/".join(rel.split("/")[:2]) + "/runs" if rel.startswith("runs-rescored/") else rel
            )
        )
        purpose = runs[rid]["purpose"]
        by_purpose = runs[rid]["machine"] if purpose == "retime" else PURPOSE_LABEL[purpose]
        read_as = ", ".join(x for x in (label, by_purpose) if x)
        if read_as != old_label(rel):
            refused.append(f"{_rel(d)}: would read as {read_as!r}, its folder read {old_label(rel)!r}")
            continue
        own, unset = _split(new, runs[rid])
        k = _key(scorer, reference)
        s = {"run": rid, "key": k, "own": own, "unset": unset, "label": label, "first": measured, "src": d,
             "rel": rel, "summary": (d.parent / "summary.json") if judged else None}  # fmt: skip
        old_arm = f"{rel}/{rec.get('dataset_id')}/{rec.get('config_id')}"
        if (rid, k) in scores:
            # One scorer on one reference, the same rows: the same measurement made twice (a round adopting the
            # scorer a run already had). The run's own score is kept; the copy's arm is the run's (owner, 2026-11-13).
            prev = scores[(rid, k)]
            if _rows(prev["src"]) != _rows(d) or not (prev["first"] or measured):
                refused.append(f"{_rel(d)} and {_rel(prev['src'])}: two different scores of {rid} by {k}")
                continue
            if measured:
                scores[(rid, k)] = s
                prev, s = s, prev
            duplicates += 1
            kept_as = prefix(", ".join(x for x in ("", by_purpose) if x))
            arms[f"{s['rel']}/{rec.get('dataset_id')}/{rec.get('config_id')}"] = (
                f"{kept_as}/{rec.get('dataset_id')}/{rec.get('config_id')}"
            )
            continue
        scores[(rid, k)] = s
        new_arm = f"{prefix(read_as)}/{rec.get('dataset_id')}/{rec.get('config_id')}"
        if old_arm != new_arm:
            arms[old_arm] = new_arm
    return {"runs": runs, "run_src": run_src, "scores": scores, "refused": refused, "no_of": no_of,
            "duplicates": duplicates, "arms": arms}  # fmt: skip


def _rows(d: Path) -> bytes | None:
    """A format 3 run directory's rows, as stored (a file, or the database's lines)."""
    p = d / "predictions.jsonl"
    if not _store.sqlite():
        return _store.read_bytes(p) if _store.is_file(p) else None
    conn = _store.connect(create=False)
    if conn is None:
        return None
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "rows" not in have:
        return None
    lines = conn.execute(
        "SELECT row FROM rows WHERE run = ? AND partial = 0 AND n > 0 ORDER BY n", (_rel(d),)
    )
    return "".join(r[0] for r in lines).encode()


def _outs(d: Path) -> dict[str, str] | None:
    """A format 3 run directory's own outputs, {item_id: text}, or None when it keeps none."""
    if not _store.sqlite():
        f = d / "outputs.jsonl"
        if not _store.is_file(f):
            return None
        rows = [json.loads(x) for x in _store.read_text(f, encoding="utf-8").splitlines() if x.strip()]
        return {str(r.get("item_id")): str(r.get("text")) for r in rows if isinstance(r, dict)}
    conn = _store.connect(create=False)
    if conn is None or "outputs" not in {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }:
        return None
    got = dict(conn.execute("SELECT item_id, text FROM outputs WHERE run = ?", (_rel(d),)).fetchall())
    return got or None


def _move_files(src: Path, dst: Path, names: tuple[str, ...]) -> None:
    for n in names:
        if _store.is_file(src / n):
            _store.mkdir(dst, parents=True, exist_ok=True)
            _store.replace(src / n, dst / n)


def _move_keys(table: str, old: str, new: str, partial: int | None = None) -> None:
    conn = _store.connect(create=False)
    if conn is None:
        return
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if table not in have or old == new:
        return
    where = " AND partial = ?" if partial is not None else ""
    with conn:
        conn.execute(
            f"UPDATE {table} SET run = ? WHERE run = ?{where}",  # noqa: S608 - a fixed table name  # nosec B608
            (new, old, *([partial] if partial is not None else [])),
        )


def _rounds(runs: dict[str, dict], run_src: dict[str, Path]) -> list[tuple[Path, str]]:
    """The rounds whose retirements or scoring name folders, rewritten: (file, its new text)."""
    import yaml  # noqa: PLC0415

    folder_of = {rid: _rel(src.parent) for rid, src in run_src.items()}
    out = []
    for f in sorted(_store.glob(_common.DATA / "rounds", "*/*.yaml")):
        text = _store.read_text(f, encoding="utf-8")
        doc = yaml.safe_load(text)
        if not isinstance(doc, dict):
            continue
        changed = False
        ds = doc.get("dataset_id")
        for r in doc.get("retired") or []:
            if "runs" in r:
                continue
            where = r.get("runs_dir") or "runs"
            ids = sorted(
                rid for rid, rec in runs.items()
                if folder_of[rid] == where and rec.get("config_id") == r.get("config_id") and rec.get("dataset_id") == ds
            )  # fmt: skip
            if "runs_dir" in r:
                del r["runs_dir"]
            r["runs"] = ids
            changed = True
        for sc in doc.get("scoring") or []:
            w = sc.get("written")
            if w and any(str(x).startswith("runs") for x in w):
                sc["written"] = [old_label(str(x)) if str(x).startswith("runs") else x for x in w]
                changed = True
        if changed:
            # As a round is saved (`evh round-*`): the same dump, so only what changed differs.
            out.append((f, yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)))
    return out


def _validate_policy(text: str, folders: list[str]) -> str:
    """validate.json's folders as arm labels' prefixes, `scorer_sources[].dir` as `arms`; edited as text, so the
    file's layout and comment stay."""
    for rel in sorted(folders, key=len, reverse=True):
        text = text.replace(json.dumps(rel), json.dumps(prefix(old_label(rel))))
    return re.sub(r'"dir"(\s*:)', r'"arms"\1', text)


def run(dry_run: bool) -> None:
    """Move every run and score into data/runs; refuse first, writing nothing."""
    p = plan()
    if p["refused"]:
        _common.die("runs that cannot move:\n  " + "\n  ".join(p["refused"]), "invalid-file")
    folders = _folders()
    if not p["runs"] and not p["scores"] and all(_rel(f) == "runs" for f in folders):
        print("  0 changed: already in this format")
        return
    by_label: dict[str, int] = defaultdict(int)
    for s in p["scores"].values():
        by_label[old_label(s["rel"]) or "runs"] += 1
    rounds = _rounds(p["runs"], p["run_src"])
    print(
        f"  {len(p['runs'])} run(s) into data/runs; {len(p['scores'])} score(s) under them"
        f" ({p['duplicates']} identical copy(ies) kept once); {len(p['arms'])} arm id(s) renamed;"
        f" {len(rounds)} round(s) rewritten; {p['no_of']} re-run(s) with no single run they re-do"
    )
    for lbl, n in sorted(by_label.items()):
        print(f"    {n:>4}  {lbl}")
    if dry_run:
        return
    sqlite = _store.sqlite()
    runs_root = _common.DATA / "runs"
    for rid, rec in p["runs"].items():
        src = p["run_src"][rid]
        dst = runs_root / rid
        _store.mkdir(dst, parents=True, exist_ok=True)
        if src != dst:
            if sqlite:
                _move_keys("outputs", _rel(src), _rel(dst))
                _move_keys("rows", _rel(src), _rel(dst), partial=1)
            else:
                _move_files(src, dst, RUN_FILES)
        _common.write_text_atomic(dst / "run.json", json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    summaries: set[tuple[Path, str]] = set()
    for (rid, k), s in p["scores"].items():
        sd = runs_root / rid / "scores" / k
        _store.mkdir(sd, parents=True, exist_ok=True)
        meta: dict[str, Any] = {
            "scorer": k.split("@", 1)[0],
            "reference": k.split("@", 1)[1],
            "label": s["label"],
        }
        if s["first"]:
            meta["first"] = True
        if s["unset"]:
            meta["unset"] = s["unset"]
        _common.write_text_atomic(sd / "score.json", json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        _common.write_text_atomic(
            sd / "metrics.json", json.dumps(s["own"], indent=2, ensure_ascii=False) + "\n"
        )
        if sqlite:
            _move_keys("rows", _rel(s["src"]), _rel(sd), partial=0)
        else:
            _move_files(s["src"], sd, ("predictions.jsonl",))
        if s["summary"] is not None and _store.is_file(s["summary"]):
            summaries.add((s["summary"], k))
    for f, k in summaries:
        dst = _common.DATA / "judge-summaries" / f"{k}.json"
        _store.mkdir(dst.parent, parents=True, exist_ok=True)
        _common.write_text_atomic(dst, _store.read_text(f, encoding="utf-8"))
    for f, text in rounds:
        _common.write_text_atomic(f, text)
    policy = _common.DATA / "validate.json"
    if _store.is_file(policy):
        before = _store.read_text(policy, encoding="utf-8")
        after = _validate_policy(before, [_rel(f) for f in folders])
        if after != before:
            _common.write_text_atomic(policy, after)
    # What is left of the old folders: each run's record and rows have moved; a folder's own notes (a README) are
    # kept as data/runs/<folder>.<name>, the rest removed with the folder.
    for (rid, _k), s in p["scores"].items():
        d = s["src"]
        if d == runs_root / rid:
            for name in ("metrics.json", "predictions.jsonl"):
                if _store.is_file(d / name):
                    _store.unlink(d / name)
    for top in sorted(
        {f if _rel(f).count("/") == 0 else _common.DATA / _rel(f).split("/")[0] for f in folders}
    ):
        if top == runs_root or not _store.is_dir(top):
            continue
        for f in sorted(_store.rglob(top, "*")):
            if not _store.is_file(f) or f.name in ("metrics.json", "predictions.jsonl", "summary.json"):
                continue
            if f.parent == top:
                _common.write_text_atomic(
                    runs_root / f"{top.name}.{f.name}", _store.read_text(f, encoding="utf-8")
                )
        _store.rmtree(top)
    if p["arms"]:
        f = _common.DATA / "renames.json"
        doc = json.loads(_store.read_text(f, encoding="utf-8")) if _store.is_file(f) else {}
        doc.setdefault("arms", {}).update(p["arms"])
        _common.write_text_atomic(f, json.dumps(doc, indent=2, sort_keys=True) + "\n")
