"""Where a dataset's items came from: the `source` block every source fills the same way (PLAN_0.8.0 E1).

    "source": {"provider": "huggingface", "ref": "fancyzhx/ag_news", "url": "https://…", "revision": null,
               "config": "default", "split": "test", "gated": null, "description_sha256": null,
               "item_url": "https://…/viewer/default/test?row={row}"}

No key belongs to one host: `provider` names the source (huggingface, kaggle, openml, croissant, url, folder, or a
project's own), `ref` is its name for the dataset, `revision` its own version of it (a commit, a release; never the
dataset's `version`), `config` and `split` the part read, `gated` whether reading it needs an agreement,
`description_sha256` the hash of its description as read (so a changed card shows). `item_url` is a template for one
item's page, with `{row}` (the item's `source_row`) or `{item_id}`. A value nobody recorded is null, never a guess.

A fetcher writes `data/sources/<dataset_id>.rows.json` beside the items (`{"source": {…}, "item_url", "rows":
{item_id: {"row", "sha256"}}}`); `dataset-create` reads it into the record, taking a row only for an item whose bytes
are the ones the fetcher wrote.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

KEYS = ("provider", "ref", "url", "revision", "config", "split", "gated", "description_sha256", "item_url")


def web(url: Any) -> bool:
    """An http(s) URL: the only kind a page links to (a `javascript:` one would run on click)."""
    return isinstance(url, str) and url.lower().startswith(("https://", "http://"))


def block(given: dict[str, Any]) -> dict[str, Any]:
    """A source block with every key, in order: what was given, null for the rest. An older fetcher's `name` is its
    `ref`; a provider not given is the URL's host (huggingface.co is `huggingface`)."""
    src = {k: given.get(k) for k in KEYS}
    if src["ref"] is None and given.get("name"):
        src["ref"] = given["name"]
    if src["provider"] is None and web(src["url"]):
        host = urlparse(src["url"]).hostname or ""
        src["provider"] = "huggingface" if host in ("huggingface.co", "hf.co") else host or None
    return src


def problems(src: Any) -> list[str]:
    """What is wrong with a source block, [] when nothing is."""
    if not isinstance(src, dict):
        return ["source is not an object"]
    out = [f"source.{k} is not a key of the block ({', '.join(KEYS)})" for k in src if k not in KEYS]
    if not src.get("provider"):
        out.append("source.provider is missing")
    for k in ("url",):
        if src.get(k) is not None and not web(src[k]):
            out.append(f"source.{k} {src[k]!r} is not an http(s) address")
    t = src.get("item_url")
    if t is not None and not (web(t) and ("{row}" in t or "{item_id}" in t)):
        out.append("source.item_url is not an http(s) template with {row} or {item_id}")
    if src.get("gated") is not None and not isinstance(src["gated"], bool):
        out.append("source.gated is not true, false or null")
    d = src.get("description_sha256")
    if d is not None and not (isinstance(d, str) and re.fullmatch(r"[0-9a-f]{64}", d)):
        out.append("source.description_sha256 is not a sha256")
    return out


def item_link(src: dict[str, Any] | None, item: dict[str, Any]) -> str | None:
    """One item's page at its source: its own source_url, else the source's item_url filled with its row or id."""
    if web(item.get("source_url")):
        return item["source_url"]
    t = str((src or {}).get("item_url") or "")
    if not web(t):
        return None
    if "{row}" in t:
        row = item.get("source_row")
        return t.replace("{row}", str(row)) if row is not None else None
    return t.replace("{item_id}", str(item["item_id"]))


def from_rows_file(path: Path, items: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(source block, {item_id: row}) from a fetcher's rows file: a row counts only when its sha256 is the item's
    (an id alone may recur in another dataset). (None, {}) when there is no file or no row matches."""
    from evaluation_harness._common import read_json  # noqa: PLC0415

    if not path.is_file():
        return None, {}
    doc = read_json(path)
    sha = {it["item_id"]: it.get("source_sha256") for it in items}
    rows = {
        k: v["row"]
        for k, v in (doc.get("rows") or {}).items()
        if isinstance(v, dict) and sha.get(k) and v.get("sha256") == sha[k]
    }
    if not rows:
        return None, {}
    given = dict(doc.get("source") or {})
    given.setdefault("item_url", doc.get("item_url"))
    return block(given), rows


ROW_IN_URL = re.compile(r"([?&]row=)(\d+)")


def from_profile(profile: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, int]]:
    """(source block, {item_id: row}) recovered from a committed profile made before 0.8.0, whose per-item
    `source_url` is the source's page for the row (`…?row=N`). Only when every linked item's URL is the same template;
    else (None, {}): nothing is guessed."""
    src = profile.get("source") or {}
    urls = {r["item_id"]: r["source_url"] for r in profile.get("rows") or [] if web(r.get("source_url"))}
    if not src or not urls:
        return None, {}
    templates = {ROW_IN_URL.sub(r"\g<1>{row}", u) for u in urls.values()}
    if len(templates) != 1 or "{row}" not in next(iter(templates)):
        return None, {}
    rows = {i: int(m.group(2)) for i, u in urls.items() if (m := ROW_IN_URL.search(u))}
    return block({**src, "item_url": templates.pop()}), rows
