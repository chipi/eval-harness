"""The prompt versions' operations (RFC-028, RFC-032 step 3): `evh prompt-list`, `evh prompt-show`, and the resources
under /api/v1/prompts. A version is recorded by a run, `evh prompt-version` or a study; these read them."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_P = "evaluation_harness.ops.prompts"

OPS = (
    Op("prompt-list", "read", "every prompt name: how many versions, the latest, and how many runs used one", "GET",
       "/prompts", f"{_P}:list_prompts", f"{_P}:say_list"),
    Op("prompt-show", "read", "one prompt's versions, oldest first: each one's parent, note, who made it and the runs "
       "that used it", "GET", "/prompts/versions", f"{_P}:show_prompt", f"{_P}:say_prompt",
       inputs={
           "name": {"type": "string", "description": "the prompt's name (segments joined by /)"},
           "text": {"type": "boolean", "description": "each version's text too"},
       },
       required=("name",)),
    Op("prompt-diff", "read", "two prompt versions compared: their text as a unified diff, and the runs of each (RFC-028)",
       "GET", "/prompts/diff", f"{_P}:diff_prompts", f"{_P}:say_diff",
       inputs={
           "a": {"type": "string", "description": "a version id, <name>/<sha16>"},
           "b": {"type": "string", "description": "the other version id"},
       }, required=("a", "b"), positional=("a", "b")),
)  # fmt: skip


def list_prompts() -> dict[str, Any]:
    """Every prompt name with its versions' count, the latest and the runs that used any."""
    from evaluation_harness import _format, _prompt_cmd, _prompts  # noqa: PLC0415

    _format.require()
    used = _prompt_cmd._runs_of()
    rows = []
    for name in _prompts.names():
        vs = _prompts.versions(name)
        rows.append(
            {
                "name": name,
                "versions": len(vs),
                "latest": vs[-1]["id"] if vs else None,
                "runs": sum(len(used.get((name, v["sha256"]), [])) for v in vs),
            }
        )
    return {"prompts": rows}


def show_prompt(name: str, text: bool = False) -> dict[str, Any]:
    """One prompt's versions, each with the runs that used it; with `text`, each version's text."""
    from evaluation_harness import _format, _prompt_cmd, _prompts  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    _format.require()
    vs = _prompts.versions(name)
    if not vs:
        have = _prompts.names()
        raise Problem(
            f"no prompt {name!r}"
            + (f": one of {', '.join(have)}" if have else ": there are no prompt versions"),
            "not-found",
        )
    used = _prompt_cmd._runs_of()
    out = [{**v, "runs": used.get((name, v["sha256"]), [])} for v in vs]
    if text:
        for v in out:
            v["text"] = _prompts.text_of(v["id"]).decode("utf-8", "replace")
    return {"name": name, "versions": out}


def say_list(r: dict[str, Any]) -> str:
    """prompt-list's answer as text: one name a line."""
    rows = r["prompts"]
    if not rows:
        return "no prompt versions yet: a run of a system that declares `prompts:` records them"
    w = max(len(x["name"]) for x in rows)
    return "\n".join(
        f"{x['name']:<{w}}  {x['versions']:>3} version(s)  {x['runs']:>4} run(s)  latest {x['latest']}"
        for x in rows
    )


def say_prompt(r: dict[str, Any]) -> str:
    """prompt-show's answer as text: each version, its note and its runs."""
    lines = []
    for v in r["versions"]:
        who = (v.get("actor") or {}).get("name") or "?"
        lines.append(
            f"v{v['n']}  {v['id']}  {v.get('created_at')}  by {who}  parent {v.get('parent') or '-'}"
        )
        lines.append(f"     {v.get('note') or ''}")
        if "text" in v:
            lines.extend(f"     | {x}" for x in str(v["text"]).splitlines())
        lines.extend(f"     run {x['run_id']}  {x['metric']}={x['score']}" for x in v["runs"])
    return "\n".join(lines)


def diff_prompts(a: str, b: str) -> dict[str, Any]:
    """Two versions' text as a unified diff, and the runs that used each."""
    import difflib  # noqa: PLC0415

    from evaluation_harness import _format, _prompt_cmd, _prompts  # noqa: PLC0415
    from evaluation_harness.ops.legacy import refusing  # noqa: PLC0415

    _format.require()
    with refusing():
        da, ta = _prompt_cmd._version_or_die(a)
        db, tb = _prompt_cmd._version_or_die(b)
    lines = list(
        difflib.unified_diff(
            ta.decode("utf-8", "replace").splitlines(keepends=True),
            tb.decode("utf-8", "replace").splitlines(keepends=True),
            fromfile=a,
            tofile=b,
        )
    )
    used = _prompt_cmd._runs_of()
    return {
        "a": a,
        "b": b,
        "diff": "".join(lines),
        "runs": {
            vid: used.get((_prompts.split_id(vid)[0], d.get("sha256", "")), [])
            for vid, d in ((a, da), (b, db))
        },
    }


def say_diff(r: dict[str, Any]) -> str:
    """prompt-diff's answer as text: the diff, then each version's runs."""
    out = [r["diff"].rstrip("\n") if r["diff"] else "the two versions are the same text"]
    for vid, runs in r["runs"].items():
        out.append(
            f"\n{vid}: {len(runs)} run(s)"
            + "".join(f"\n  {x['run_id']}  {x['metric']}={x['score']}" for x in runs)
        )
    return "\n".join(out)
