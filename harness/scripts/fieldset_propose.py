#!/usr/bin/env python3
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

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import re
from typing import Any

import yaml
from evaluation_harness import _fields, _sources
from evaluation_harness._common import FIELDS, die, evh_prog, write_text_atomic

#: A source's feature types (schema.org's, Hugging Face's and Python's spellings) as the field set's types.
TYPES = {
    "sc:text": "text", "text": "text", "string": "text", "str": "text", "large_string": "text",
    "sc:integer": "integer", "integer": "integer", "int": "integer", "int32": "integer", "int64": "integer",
    "sc:float": "number", "float": "number", "float32": "number", "float64": "number", "number": "number",
    "sc:boolean": "boolean", "boolean": "boolean", "bool": "boolean",
    "sc:date": "date", "sc:datetime": "date", "date": "date", "datetime": "date", "timestamp": "date",
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
        if kind == "text" and seen and len(values) <= max_choices and len(values) < len(seen):
            field.update(type="choice", values=values)
        field["description"] = f"from the source's {raw} ({t})" + (
            f", {len(values)} values in {len(seen)} sampled" if field["type"] == "choice" else ""
        )
        out.append(field)
    return out


def main() -> int:
    """Print (or write) a field set proposed from a source's features."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="a dataset source, as dataset-create --source names one")
    ap.add_argument("--query", default="{}", help="what to read, as JSON")
    ap.add_argument("--fieldset-id", required=True, help="the field set's id (data/fields/<id>.yaml)")
    ap.add_argument("--sample", type=int, default=200, help="items read to find the choices (default 200)")
    ap.add_argument(
        "--max-choices", type=int, default=20, help="at most this many values make a choice (default 20)"
    )
    ap.add_argument(
        "--write", action="store_true", help="write data/fields/<id>.yaml; refused when it exists"
    )
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", args.fieldset_id):
        die("--fieldset-id: lowercase letters, digits and _", "bad-argument")
    try:
        query = json.loads(args.query)
    except ValueError as e:
        die(f"--query is not JSON: {e}", "bad-argument")
    # The text is the item and the id its identity: neither is a field of it.
    skip = {query.get("text"), query.get("id")} - {None}
    cls, _path = _sources.resolve(args.source)
    src = cls({})
    try:
        features = (src.describe(query) or {}).get("features") or {}
        samples = []
        if features:
            names = {NAME.sub("_", str(k).rsplit("/", 1)[-1].lower()).strip("_") for k in features}
            keep = sorted(names - skip)
            for n, it in enumerate(src.items({**query, "fields": keep})):
                if n >= args.sample:
                    break
                samples.append(it.get("fields") or {})
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
    if not args.write:
        print(text, end="")
        print(
            f"# {len(fields)} field(s). Read it; to accept: the same command with --write", file=_sys.stderr
        )
        return 0
    out = FIELDS / f"{args.fieldset_id}.yaml"
    if out.exists():
        die(f"{out} exists: a field set is not overwritten (name another --fieldset-id)", "would-overwrite")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(out, text)
    print(f"wrote {out}: {len(fields)} field(s); use it: dataset-create … --fieldset {args.fieldset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
