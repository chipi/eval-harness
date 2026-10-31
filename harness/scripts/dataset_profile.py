#!/usr/bin/env python3
"""What is inside a dataset, without its text: `evh dataset-profile` writes it, `evh dataset-items` reads it.

    evh dataset-profile --dataset-id ag_news_200          # data/profiles/ag_news_200.json
    evh dataset-items --dataset-id ag_news_200            # its shape, then one row per item
    evh dataset-items --dataset-id ag_news_200 --item 00ea08cd9ddbc99f   # one item (its text when it is here)

A dataset's text often cannot be redistributed (docs/DATA.md), so the published catalog never
had it, and a reader could not see what an item looks like. A profile is what can be published:
the number of items and how long they are, the shape of the gold reference (the labels and how
many of each, the entries per item, or how long a reference is), and per item its id, length,
reference, and where it can be read at its source. It is computed where the items are
materialized and committed, so a catalog built anywhere shows it.

Where an item can be read comes from the dataset itself, never guessed: an item fetched from a
`source_url` links there; otherwise a fetcher may write `data/sources/<dataset_id>.rows.json`
(`{"source": {"name", "url"}, "item_url": "...{row}...", "rows": {item_id: {"row", "sha256"}}}`),
as this repository's Hugging Face fetchers do; an entry counts only when its sha256 is the item's.
Only an http(s) address is a link. Without either, an item has no link.

`--with-text` adds each item's text, and refuses unless every item's source file is tracked by
git: it publishes only what the repository already does (a project's own synthetic data).
"""

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from evaluation_harness import _common, _visibility
from evaluation_harness._common import die, read_json, write_json
from evaluation_harness._fingerprint import items_digest
from evaluation_harness._version import __version__
from evaluation_harness.catalog_adapter import HarnessAdapter

#: A gold reference reads as labels when it takes at most this many distinct values, each short.
MAX_LABELS = 30
MAX_LABEL_WORDS = 5
#: Text kept per item with --with-text; the page folds it.
MAX_TEXT = 2000
BINS = 10


def words_of(text: str) -> int:
    """Words in an item: whitespace-separated, and for a JSON item those of its string values."""
    try:
        doc = json.loads(text)
    except ValueError:
        return len(text.split())
    if isinstance(doc, (dict, list)):
        n, stack = 0, [doc]
        while stack:
            x = stack.pop()
            if isinstance(x, str):
                n += len(x.split())
            elif isinstance(x, dict):
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
        return n
    return len(text.split())


def stats(xs: list[int]) -> dict:
    """min, quartiles, max; and a histogram of equal-width bins as [low, high, count]."""
    if not xs:
        return {}
    s = sorted(xs)
    q = lambda f: s[min(len(s) - 1, int(f * (len(s) - 1) + 0.5))]  # noqa: E731
    lo, hi = s[0], s[-1]
    width = max(1, -(-(hi - lo + 1) // BINS))
    hist = [[lo + k * width, lo + (k + 1) * width - 1, 0] for k in range(-(-(hi - lo + 1) // width))]
    for x in s:
        hist[(x - lo) // width][2] += 1
    return {"min": lo, "p25": q(0.25), "median": q(0.5), "p75": q(0.75), "max": hi, "histogram": hist}


def reference_shape(texts: dict[str, str]) -> tuple[dict, dict[str, str]]:
    """The shape of a reference over its items, and a short description per item."""
    parsed: dict = {}
    for item, t in texts.items():
        try:
            parsed[item] = json.loads(t)
        except ValueError:
            parsed[item] = t
    kinds = {type(v).__name__ for v in parsed.values()}
    if kinds == {"list"}:
        n = {k: len(v) for k, v in parsed.items()}
        return {"shape": "lists", "entries": stats(list(n.values()))}, {
            k: f"{v} entries" for k, v in n.items()
        }
    if kinds == {"dict"}:
        keys = sorted({k for v in parsed.values() for k in v})
        return {"shape": "record", "keys": keys}, {k: f"{len(v)} fields" for k, v in parsed.items()}
    plain = {k: (v if isinstance(v, str) else t) for (k, v), t in zip(parsed.items(), texts.values())}
    values = Counter(v.strip() for v in plain.values())
    # Labels are few short values that repeat (a class per item); a short answer per item that
    # rarely recurs is the item's gold, and is summarised as text, never listed.
    if (
        len(values) <= MAX_LABELS
        and len(values) <= len(plain) / 2
        and all(len(v.split()) <= MAX_LABEL_WORDS for v in values)
    ):
        return {"shape": "labels", "labels": dict(sorted(values.items()))}, {
            k: v.strip() for k, v in plain.items()
        }
    n = {k: len(v.split()) for k, v in plain.items()}
    return {"shape": "text", "words": stats(list(n.values()))}, {k: f"{v} words" for k, v in n.items()}


def gold_references(dataset_id: str) -> list[tuple[str, Path]]:
    """(reference id, directory) for each gold reference of the dataset that is on this machine."""

    out = []
    for r in HarnessAdapter(data_dir=_common.DATA).references():
        if r.get("dataset") == dataset_id and r.get("tier") == "gold":
            out.append((r["id"], r["dir"]))
    return out


def source_links(dataset: dict) -> tuple[dict | None, dict[str, str]]:
    """The dataset's source and a URL per item: an item's own source_url, else a rows map entry
    whose sha256 is the item's frozen one (an id alone may recur in another dataset)."""
    items = dataset.get("items") or []
    urls = {it["item_id"]: it["source_url"] for it in items if web(it.get("source_url"))}
    sha = {it["item_id"]: it.get("source_sha256") for it in items}
    source, best = None, 0
    for f in sorted(_common.SOURCES.glob("*.rows.json")):
        doc = read_json(f)
        rows = {
            k: v["row"]
            for k, v in (doc.get("rows") or {}).items()
            if isinstance(v, dict) and sha.get(k) and v.get("sha256") == sha[k]
        }
        if not rows:
            continue
        for item, row in rows.items():
            url = str(doc.get("item_url") or "").replace("{row}", str(row))
            if web(url):
                urls.setdefault(item, url)
        if len(rows) > best:
            best, source = len(rows), doc.get("source")
    if source and not web(source.get("url")):
        source = {k: v for k, v in source.items() if k != "url"}
    return source, urls


def web(url) -> bool:
    """An http(s) URL: the only kind a page links to (a `javascript:` one would run on click)."""
    return isinstance(url, str) and url.lower().startswith(("https://", "http://"))


def tracked(paths: list[Path]) -> list[Path]:
    """The paths git has not committed (all of them when this is not a git checkout): a file only
    staged is not yet in the history anyone can read."""
    root = _common.ROOT
    try:
        out = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "-z",
                "--name-only",
                "HEAD",
                "--",
                *[str(p.relative_to(root)) for p in paths],
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError, ValueError):
        return paths
    known = set(filter(None, out.split("\0")))
    return [p for p in paths if str(p.relative_to(root)) not in known]


def profile(dataset_id: str, with_text: bool) -> dict:
    """The profile of a materialized dataset (refuses when it is not materialized here)."""
    ds = _common.load_dataset(dataset_id)
    items = ds.get("items") or []
    mat = _common.MATERIALIZED / dataset_id
    texts: dict[str, str] = {}
    for it in items:
        p = mat / (it.get("source_path") or it["item_id"])
        if not p.is_file():
            die(
                f"{dataset_id} is not materialized here ({p} is missing): a profile is computed from the items. "
                f"Fetch and materialize it first (`evh dataset-materialize --dataset-id {dataset_id}`, or in "
                "this repository `make data EXP=<experiment>`)."
            )
        texts[it["item_id"]] = p.read_text(encoding="utf-8", errors="replace")
    if with_text and ds.get("text") == "hidden":
        die(f"{dataset_id} is `text: hidden`: its profile carries no text (RFC-019)")
    if with_text:
        src_dir = _common.ROOT / ds.get("source_dir", "data/sources")
        files = [src_dir / (it.get("source_path") or it["item_id"]) for it in items]
        missing = tracked(files)
        if missing:
            die(
                f"--with-text publishes item text, and {len(missing)} of {dataset_id}'s source files are not "
                f"tracked by git (e.g. {missing[0]}): only text the repository already holds may be published."
            )
    words = {k: words_of(t) for k, t in texts.items()}
    refs: list[dict] = []
    per_item: dict[str, dict[str, str]] = {}
    for ref_id, d in gold_references(dataset_id):
        got = {k: (d / f"{k}.txt").read_text(encoding="utf-8") for k in texts if (d / f"{k}.txt").is_file()}
        if not got:
            refs.append(
                {
                    "id": ref_id,
                    "shape": "absent",
                    "note": "not profiled: its texts were not on the machine that wrote this profile",
                }
            )
            continue
        shape, desc = reference_shape(got)
        refs.append({"id": ref_id, "items": len(got), **shape})
        per_item[ref_id] = desc
    source, urls = source_links(ds)
    kind = "json" if all(t.lstrip()[:1] in "{[" for t in texts.values()) else "text"
    rows = []
    for it in items:
        k = it["item_id"]
        row = {"item_id": k, "words": words[k], "reference": {r: d[k] for r, d in per_item.items() if k in d}}
        if k in urls:
            row["source_url"] = urls[k]
        if with_text:
            row["text"] = texts[k][:MAX_TEXT]
        rows.append(row)
    return {
        "dataset_id": dataset_id,
        "items_sha256": items_digest(ds),
        "made_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "harness": __version__,
        "source": source,
        "items": {"n": len(items), "kind": kind, "words": stats(list(words.values()))},
        "references": refs,
        "rows": rows,
    }


def _shape_line(r: dict) -> str:
    if r["shape"] == "labels":
        return ", ".join(f"{k} {v}" for k, v in sorted(r["labels"].items(), key=lambda kv: (-kv[1], kv[0])))
    if r["shape"] == "lists":
        e = r["entries"]
        return f"lists: {e['min']}–{e['max']} entries per item, median {e['median']}"
    if r["shape"] == "record":
        return "a record per item: " + ", ".join(r["keys"])
    if r["shape"] == "text":
        w = r["words"]
        return f"text: {w['min']}–{w['max']} words, median {w['median']}"
    return r.get("note", r["shape"])


def render(p: dict, item: str | None) -> str:
    """The profile as `evh dataset-items` prints it; with `item`, that item and its text when here."""
    w = p["items"]["words"]
    out = [
        (
            f"{p['dataset_id']}: {p['items']['n']} items ({p['items']['kind']}), "
            f"{w.get('min', 0)}–{w.get('max', 0)} words, median {w.get('median', 0)}"
        )
    ]
    if p.get("source"):
        out.append(f"source: {p['source']['name']}  {p['source']['url']}")
    for r in p["references"]:
        out.append(f"gold {r['id']}: {_shape_line(r)}")
    rows = [r for r in p["rows"] if not item or r["item_id"].startswith(item)]
    if item and not rows:
        die(f"no item {item!r} in {p['dataset_id']}")
    out.append("")
    for r in rows:
        ref = "; ".join(f"{v}" for v in r["reference"].values())
        out.append(f"{r['item_id'][:16]}  {r['words']:>6} words  {ref}  {r.get('source_url', '')}".rstrip())
        if item:
            local = _common.item_path(p["dataset_id"], r["item_id"])
            text = local.read_text(encoding="utf-8", errors="replace") if local else r.get("text")
            out.append("")
            out.append(
                text if text else "(its text is not on this machine, and the profile does not carry it)"
            )
    return "\n".join(out)


def load_profile(dataset_id: str) -> dict:
    """data/profiles/<dataset_id>.json, or a refusal saying how to write it."""
    f = _common.DATA / "profiles" / f"{_common.dataset_id_ok(dataset_id)}.json"
    if not f.is_file():
        die(
            f"no profile for {dataset_id} ({f}): write one with `evh dataset-profile --dataset-id {dataset_id}` "
            "where the dataset is materialized."
        )
    return read_json(f)


def main_profile(argv: list[str] | None = None) -> int:
    """evh dataset-profile."""
    ap = argparse.ArgumentParser(prog="evh dataset-profile", description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument(
        "--with-text",
        action="store_true",
        help="add each item's text (only when git has committed every item's file)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help='the profile written, as JSON: {"command", "version", "result": <the profile>}',
    )
    args = ap.parse_args(argv)
    p = profile(args.dataset_id, args.with_text)
    out = _common.DATA / "profiles" / f"{_common.dataset_id_ok(args.dataset_id)}.json"
    write_json(out, p)
    if args.json:
        print(json.dumps({"command": "dataset-profile", "version": __version__, "result": p}, indent=1))
    else:
        print(f"wrote {out}\n" + render(p, None).split("\n\n")[0])
    return 0


def main_items(argv: list[str] | None = None) -> int:
    """evh dataset-items."""
    ap = argparse.ArgumentParser(prog="evh dataset-items", description=__doc__.split("\n\n")[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--item", help="one item: its id, or the start of it; its text when it is here")
    ap.add_argument(
        "--json",
        action="store_true",
        help='the profile as JSON: {"command", "version", "result": <the profile>}',
    )
    args = ap.parse_args(argv)
    p = load_profile(args.dataset_id)
    hide = _visibility.public_env() and _visibility.hidden(args.dataset_id)
    if hide:  # a public server's command, on a `text: hidden` dataset: ids and lengths only
        if args.item:
            die(f"{args.dataset_id} is `text: hidden`: no item is shown here")
        p = _visibility.public_profile(p)
    if args.json:
        if args.item:
            rows = [dict(r) for r in p["rows"] if r["item_id"].startswith(args.item)]
            if not rows:
                die(f"no item {args.item!r} in {p['dataset_id']}")
            for r in rows:  # its text when it is here, as the printed form shows it
                local = _common.item_path(p["dataset_id"], r["item_id"])
                if local:
                    r["text"] = local.read_text(encoding="utf-8", errors="replace")
            p = dict(p, rows=rows)
        print(json.dumps({"command": "dataset-items", "version": __version__, "result": p}, indent=1))
    else:
        print(render(p, args.item))
    return 0


if __name__ == "__main__":
    sys.exit(main_profile())
