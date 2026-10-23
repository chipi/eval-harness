"""Items fetched from a pinned URL (ADR-0003).

An item with `source_url` is frozen by its `source_sha256`, as a file item is: the URL is where
to get the bytes, the hash is what they must be. A download is kept in `.cache/items/<sha256>`
(gitignored), so a dataset is fetched once per machine, and bytes that hash to anything else are
refused and deleted, never cached.
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from _common import ITEM_CACHE
from _common import sha256 as _sha256  # `sha256` is fetch()'s parameter name
from _retry import call_with_retries

TIMEOUT_S = 60
CHUNK = 1 << 20


class FetchError(Exception):
    """The URL could not be read, or its bytes are not the pinned ones."""


def _headers_for(url: str) -> dict:
    """The project's own headers for this URL's host, from EVAL_FETCH_HEADERS (environment or
    .env): a JSON object {"host": {"Header": "value"}}. Only the exact host gets them, and
    they are attached so that a redirect to another host does not carry them. They are never
    printed or written into a dataset."""
    raw = os.environ.get("EVAL_FETCH_HEADERS", "").strip()
    if not raw:
        return {}
    try:
        table = json.loads(raw)
    except ValueError as exc:
        raise FetchError('EVAL_FETCH_HEADERS is not JSON: {"host": {"Header": "value"}}') from exc
    got = table.get(urlparse(url).hostname or "") if isinstance(table, dict) else None
    return {str(k): str(v) for k, v in got.items()} if isinstance(got, dict) else {}


def _download_once(url: str) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "evaluation-harness"})  # noqa: S310 — fetch() refuses any scheme but http(s)
    for k, v in _headers_for(url).items():
        req.add_unredirected_header(k, v)
    fd, tmp = tempfile.mkstemp(dir=ITEM_CACHE, prefix=".part-")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp, os.fdopen(fd, "wb") as out:  # noqa: S310 — fetch() refuses any scheme but http(s)  # nosec B310
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return Path(tmp)


def _download(url: str) -> Path:
    """The URL's bytes in a temporary file inside the cache directory. A transient failure
    (429, 5xx, a timeout, a dropped connection) is retried as the harness retries a provider
    (_retry.py: EVAL_MAX_RETRIES, EVAL_RETRY_MAX_DELAY); a 404 or 403 is not."""
    ITEM_CACHE.mkdir(parents=True, exist_ok=True)
    try:
        return call_with_retries(_download_once, (url,), label=urlparse(url).hostname or url)
    except FetchError:
        raise
    except Exception as exc:  # every failure to read is the same refusal
        raise FetchError(f"{url}: {exc}") from exc


def fetch(url: str, sha256: str | None) -> tuple:
    """(path in the cache, sha256). With `sha256` given, a cached copy is reused and a download
    whose bytes hash differently raises FetchError. Without it the bytes are pinned now: the
    caller records the hash it gets back, and from then on that is what the item is."""
    if urlparse(url).scheme not in ("http", "https"):
        # urlopen would also read file:// and ftp://; a dataset's schema allows only these two.
        raise FetchError(f"{url}: only http:// and https:// URLs can be items")
    if sha256:
        cached = ITEM_CACHE / sha256
        if cached.is_file() and _sha256(cached) == sha256:
            return cached, sha256
    tmp = _download(url)
    got = _sha256(tmp)
    if sha256 and got != sha256:
        tmp.unlink(missing_ok=True)
        raise FetchError(
            f"{url}: the bytes hash to {got[:12]}, not the pinned {sha256[:12]}. "
            "The file at that URL changed; that is a new dataset version, not this one."
        )
    dst = ITEM_CACHE / got
    os.replace(tmp, dst)
    return dst, got


def suffix_of(url: str) -> str:
    """The URL path's file extension ('.mp3'), or '' when it has none."""
    name = urlparse(url).path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[1] if "." in name and len(name.rsplit(".", 1)[1]) <= 8 else ""
