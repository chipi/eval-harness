"""Judge scorers (RFC-032 step 7): the scorer's record, the scores it made and the people's checks of its judges, with one
table of where each lives. A scorer is data/scorers/<scorer_id>.yaml; the scores it made are under their runs
(`runs/<run>/scores/<scorer>@<judging set>/`, label `judged/<scorer>`); its verdicts, summaries and judging sets are
`judge-verdicts/<scorer>/<set>/`, `judge-summaries/<scorer>@<set>.json` and `judging-sets/<set>.json` (written by
`evh judge-score`); and its judges' validation against people is a part of it:

    data/judge-validation/<scorer>/<source>/report.json          one source's numbers, per judge
    data/judge-validation/<scorer>/<source>/<judge>/<record>.json  the judge's reply to each article of the source

A scorer that has made judged scores is not changed: a new version is a new scorer (a new id, `supersedes`), because
every judged score records the hash of the scorer it was made with and every verdict the fingerprint of its judge.
A judge is written with `params`, or names `system: <system_id>` and is read as that system's settings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._codeid import content_sha256
from evaluation_harness.model import runs as _runs
from evaluation_harness.model.entity import Entity, Problem
from evaluation_harness.model.systems import SYSTEM

#: Where the people's checks of a scorer's judges are, under data/.
VALIDATION_FOLDER = "judge-validation"
#: What a judged score's label starts with: `judged/<scorer>`.
JUDGED = "judged/"


def _links(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The scorer a scorer supersedes and the systems its judges name exist."""
    out: list[dict[str, Any]] = []
    old = record.get("supersedes")
    if old and not _store.is_file(SCORER.path(str(old))):
        out.append({"path": ["supersedes"], "message": f"no scorer {old!r} in this project"})
    for i, j in enumerate(record.get("judges") or []):
        sid = j.get("system") if isinstance(j, dict) else None
        if sid and not _store.is_file(SYSTEM.path(str(sid))):
            out.append({"path": ["judges", i, "system"], "message": f"no system {sid!r} in this project"})
    return out


def frozen(scorer_id: str) -> str:
    """Why the scorer is not changed, "" when it may be: it has made judged scores."""
    n = len(judged_scores(scorer_id))
    if not n:
        return ""
    return (
        f"it made {n} judged score(s), each recording the scorer as it was: a changed rubric, prompt or judge is a new "
        f"scorer (a new id, with `supersedes: {scorer_id}` and `why`)"
    )


SCORER = Entity(
    name="scorer",
    plural="scorers",
    folder="scorers",
    id_field="scorer_id",
    schema="scorer.schema.json",
    links=_links,
    frozen=frozen,
)


def content_hash(doc: Any) -> str:
    """A scorer's hash: the content of its parsed YAML (a comment changes nothing), as every judged score records it."""
    return content_sha256(doc)


def current_sha256(scorer_id: str, data: Path | None = None) -> str | None:
    """The hash of the scorer's file as it is now; None when there is none (or it does not parse)."""
    import yaml  # noqa: PLC0415

    f = SCORER.under(data).path(scorer_id)
    if not _store.is_file(f):
        return None
    try:
        return content_hash(yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {})
    except yaml.YAMLError:
        return None


def judge_system_params(system_id: str) -> dict[str, Any]:
    """What a judge naming `system: <id>` is called with: the system's params under the record of the model it names,
    as a run reads them."""
    from evaluation_harness import _models  # noqa: PLC0415

    rec = SYSTEM.get(system_id)
    try:
        return dict(_models.resolve(rec, _common.DATA).get("params") or {})
    except ValueError as exc:
        raise Problem(f"system {system_id!r}: {exc}", "invalid-file") from None


def resolve_judges(sc: dict[str, Any]) -> None:
    """Give each judge that names a system the params it is called with (in place); one that names a system that does
    not exist, or both a system and params, is refused as a Problem naming the judge. The scorer's hash is of the file
    as written, so it is taken before this."""
    for j in sc.get("judges") or []:
        if not isinstance(j, dict) or "system" not in j:
            continue
        if "params" in j:
            raise Problem(f"judge {j.get('id')!r}: names a system and params; name one", "invalid-file")
        try:
            j["params"] = judge_system_params(str(j["system"]))
        except Problem as exc:
            raise Problem(f"judge {j.get('id')!r}: {exc}", exc.kind) from None


def judged_scores(scorer_id: str | None = None) -> list[dict[str, Any]]:
    """Every judged score (of one scorer, or of all): {scorer, run, system, set, dir, sha256}, `sha256` the hash of the
    scorer the score records it was made with (None when it records none)."""
    out = []
    for rid in _runs.run_ids():
        for sd in _runs.scores_of(rid):
            m = _runs.meta(sd)
            if not str(m.get("label") or "").startswith(JUDGED) or scorer_id not in (None, m.get("scorer")):
                continue
            rec = _runs.record(sd) or {}
            out.append(
                {
                    "scorer": m.get("scorer"),
                    "run": rid,
                    "system": rec.get("config_id"),
                    "set": m.get("reference"),
                    "dir": sd,
                    "sha256": ((rec.get("derived") or {}).get("with") or {}).get("scorer_sha256"),
                }
            )
    return out


def _data(data: Path | None) -> Path:
    return _common.DATA if data is None else Path(data)


def validation_dir(scorer_id: str, data: Path | None = None) -> Path:
    """Where the people's checks of the scorer's judges are."""
    return _data(data) / VALIDATION_FOLDER / scorer_id


def verdicts_dir(scorer_id: str, data: Path | None = None) -> Path:
    """The scorer's verdicts: a folder per judging set, in it a folder per judge."""
    return _data(data) / "judge-verdicts" / scorer_id


def summary_file(scorer_id: str, set_id: str, data: Path | None = None) -> Path:
    """What the scorer's pass over a judging set summarised."""
    return _data(data) / "judge-summaries" / f"{scorer_id}@{set_id}.json"


def judging_set_file(set_id: str, data: Path | None = None) -> Path:
    """A frozen judging set: which arms' outputs, in which blocks, on which items."""
    return _data(data) / "judging-sets" / f"{set_id}.json"


def judging_sets_of(scorer_id: str, data: Path | None = None) -> list[str]:
    """The ids of the judging sets the scorer has verdicts or a summary for, sorted."""
    vroot = verdicts_dir(scorer_id, data)
    ids = {p.name for p in _store.iterdir(vroot) if _store.is_dir(p)} if _store.is_dir(vroot) else set()
    sroot = _data(data) / "judge-summaries"
    if _store.is_dir(sroot):
        ids |= {p.stem.partition("@")[2] for p in _store.glob(sroot, f"{scorer_id}@*.json")}
    return sorted(ids)


def _json(path: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def checks_of(scorer_id: str, data: Path | None = None) -> list[dict[str, Any]]:
    """The people's checks of the scorer's judges, one per source of human ratings: its report, and for each judge the
    records of its replies counted, with the cost and the unparsed replies the report states. Never the records."""
    base = validation_dir(scorer_id, data)
    if not _store.is_dir(base):
        return []
    now = current_sha256(scorer_id, data)
    out: list[dict[str, Any]] = []
    for src in sorted(_store.iterdir(base)):
        if not _store.is_dir(src):
            continue
        report = _json(src / "report.json")
        said = (report or {}).get("judges") or {}
        judges: list[dict[str, Any]] = []
        for jd in sorted(_store.iterdir(src)):
            if _store.is_dir(jd):
                st = said.get(jd.name)
                st = st if isinstance(st, dict) else {}
                judges.append(
                    {
                        "judge": jd.name,
                        "records": sum(1 for _ in _store.glob(jd, "*.json")),
                        "billed_usd": st.get("billed_usd"),
                        "unparsed": st.get("unparsed"),
                    }
                )
        stamped = ((report or {}).get("inputs") or {}).get("scorer_sha256")
        out.append(
            {
                "source": src.name,
                "citation": (report or {}).get("source"),
                "articles": (report or {}).get("articles"),
                "report": report is not None,
                "scorer_sha256": stamped,
                "current": bool(stamped) and stamped == now,
                "judges": judges,
                "records": sum(j["records"] for j in judges),
            }
        )
    return out
