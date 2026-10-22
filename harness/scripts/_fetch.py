"""Items fetched from a pinned URL (ADR-0003).

An item with `source_url` is frozen by its `source_sha256`, as a file item is: the URL is where
to get the bytes, the hash is what they must be. A download is kept in `.cache/items/<sha256>`
(gitignored), so a dataset is fetched once per machine, and bytes that hash to anything else are
refused and deleted, never cached.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from _common import ITEM_CACHE

TIMEOUT_S = 60
CHUNK = 1 << 20


class FetchError(Exception):
    """The URL could not be read, or its bytes are not the pinned ones."""


def _download(url: str) -> Path:
    """The URL's bytes in a temporary file inside the cache directory."""
    ITEM_CACHE.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "evaluation-harness"})
    fd, tmp = tempfile.mkstemp(dir=ITEM_CACHE, prefix=".part-")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp, os.fdopen(fd, "wb") as out:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as exc:  # noqa: BLE001 — every failure to read is the same refusal
        Path(tmp).unlink(missing_ok=True)
        raise FetchError(f"{url}: {exc}") from exc
    return Path(tmp)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, sha256: Optional[str]) -> tuple:
    """(path in the cache, sha256). With `sha256` given, a cached copy is reused and a download
    whose bytes hash differently raises FetchError. Without it the bytes are pinned now: the
    caller records the hash it gets back, and from then on that is what the item is."""
    if sha256:
        cached = ITEM_CACHE / sha256
        if cached.is_file() and _sha256(cached) == sha256:
            return cached, sha256
    tmp = _download(url)
    got = _sha256(tmp)
    if sha256 and got != sha256:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"{url}: the bytes hash to {got[:12]}, not the pinned {sha256[:12]}. "
                         "The file at that URL changed; that is a new dataset version, not this one.")
    dst = ITEM_CACHE / got
    os.replace(tmp, dst)
    return dst, got


def suffix_of(url: str) -> str:
    """The URL path's file extension ('.mp3'), or '' when it has none."""
    from urllib.parse import urlparse

    name = urlparse(url).path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[1] if "." in name and len(name.rsplit(".", 1)[1]) <= 8 else ""
