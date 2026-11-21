"""A field set proposed from a dataset source's features, for a person to read and accept (PLAN_0.8.0 E8).

    evh fieldset-propose --source croissant --query '{"path": "croissant.json", "text": "text"}' --fieldset-id notes
    evh fieldset-propose … --write          write data/fields/<id>.yaml (never over one that exists)

Each feature the source describes (`describe(query)["features"]`, {name: type}) becomes a field: its type mapped to
the field set's (schema.org's sc:Integer is integer, sc:Text text, …); a text feature whose sampled values are few
(at most --max-choices distinct among --sample items) is proposed as a choice, its values listed. The fields that are
the items' text and id are left out (the item and its identity, not fields of it). Nothing is written without --write; the proposal is
checked as `dataset-create` checks a field set, so an accepted one can be used as it is.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import yaml
from evaluation_harness import _fields, _jsonout, _sources, _store
from evaluation_harness._common import FIELDS, die, write_text_atomic
from evaluation_harness.ops import legacy

#: A source's feature types (schema.org's, Hugging Face's and Python's spellings) as the field set's types.
TYPES = {
    "sc:text": "text", "text": "text", "string": "text", "str": "text", "large_string": "text",
    "sc:integer": "integer", "integer": "integer", "int": "integer", "int32": "integer", "int64": "integer",
    "sc:float": "number", "float": "number", "float32": "number", "float64": "number", "number": "number",
    "sc:boolean": "boolean", "boolean": "boolean", "bool": "boolean",
    "sc:date": "date", "date": "date", "sc:datetime": "datetime", "datetime": "datetime", "timestamp": "datetime",
    "sc:url": "url", "url": "url",
}  # fmt: skip
NAME = re.compile(r"[^a-z0-9_]+")


def propose(
    features: dict[str, str], samples: list[dict[str, Any]], skip: set, max_choices: int
) -> list[dict]:
    """The proposed fields, in the source's order."""
    out = []
    for raw, t in features.items():
        name = NAME.sub("_", str(raw).rsplit("/", 1)[-1].lower()).strip("_")
        if not name or name in skip:
            continue
        kind = TYPES.get(str(t).lower(), "text")
        field: dict[str, Any] = {"name": name, "type": kind}
        seen = [s[name] for s in samples if s.get(name) not in (None, "")]
        values = sorted({str(v) for v in seen})
        if kind in ("date", "datetime") and seen:
            # A source's date type says nothing of its values' shape (a timestamp with no offset is no `datetime`): the
            # type is kept only when every sampled value reads as it, else text, and the description says why.
            from evaluation_harness import _fields  # noqa: PLC0415

            try:
                for v in seen:
                    _fields.parse({"type": kind}, v)
            except (ValueError, TypeError):
                field["type"] = kind = "text"
                t = f"{t}, whose sampled values do not read as a {TYPES.get(str(t).lower())}"
        if kind == "text" and seen and len(values) <= max_choices and len(values) < len(seen):
            field.update(type="choice", values=values)
        field["description"] = f"from the source's {raw} ({t})" + (
            f", {len(values)} values in {len(seen)} sampled" if field["type"] == "choice" else ""
        )
        out.append(field)
    return out


def body(**inputs: Any) -> int:
    """Print (or write) a field set proposed from a source's features."""
    args = legacy.namespace(inputs, "fieldset-propose")
    if not re.fullmatch(r"[a-z0-9_]+", args.fieldset_id):
        die("--fieldset-id: lowercase letters, digits and _", "bad-argument")
    try:
        query = json.loads(args.query)
    except ValueError as e:
        die(f"--query is not JSON: {e}", "bad-argument")
    # The text is the item, the id its identity and the answer its reference (dataset-create's label set): none is a
    # field of it.
    skip = {query.get("text"), query.get("id"), query.get("answer")} - {None}
    cls, _path = _sources.resolve(args.source)
    src = cls({})
    try:
        features = (src.describe(query) or {}).get("features") or {}
        samples = []
        if features:
            names = {NAME.sub("_", str(k).rsplit("/", 1)[-1].lower()).strip("_") for k in features}
            keep = sorted(names - skip)
            items = src.items({**query, "fields": keep})
            try:
                for n, it in enumerate(items):
                    if n >= args.sample:
                        break
                    samples.append(it.get("fields") or {})
            finally:
                # read in part: closed now, not at the interpreter's exit (source_preview says why)
                close = getattr(items, "close", None)
                if close:
                    close()
    except (ValueError, OSError) as e:
        die(f"--source {args.source}: {e}", "invalid-file")
    if not features:
        die(f"--source {args.source}: it describes no features to propose fields from", "not-enough")
    fields = propose(features, samples, skip, args.max_choices)
    doc = {
        "fieldset_id": args.fieldset_id,
        "description": f"proposed from source {args.source}; read before accepting",
        "fields": fields,
    }
    problems = _fields.fieldset_problems(args.fieldset_id, doc)
    if problems:
        die("the proposal is not a valid field set: " + "; ".join(problems[:5]), "invalid-file")
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    _jsonout.values({"fieldset": doc, "written": bool(args.write)})
    if not args.write:
        print(text, end="")
        print(
            f"# {len(fields)} field(s). Read it; to accept: the same command with --write",
            file=sys.stderr,
        )
        return 0
    out = FIELDS / f"{args.fieldset_id}.yaml"
    if _store.exists(out):
        die(
            f"{out} exists: a field set is not overwritten (name another --fieldset-id)",
            "would-overwrite",
        )
    _store.mkdir(out.parent, parents=True, exist_ok=True)
    write_text_atomic(out, text)
    print(f"wrote {out}: {len(fields)} field(s); use it: dataset-create … --fieldset {args.fieldset_id}")
    return 0
