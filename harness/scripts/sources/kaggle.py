"""The kaggle source: a table file of a Kaggle dataset, at a version (PLAN_0.8.0 P3).

    evh dataset-create --dataset-id D --source kaggle \\
        --query '{"ref": "uciml/iris", "version": 2, "file": "Iris.csv", "text": "Species", "fields": ["SepalLengthCm"]}'

Kaggle's own API (v1) answers a public dataset without kagglehub and without credentials (checked 2026-11-05):
`datasets/view/<ref>` gives its title, licence and current version, `datasets/download/<ref>?datasetVersionNumber=N`
its files as a zip. Query: `ref` (owner/slug); `version` (default the current one, recorded either way); `file` (the
zip member; may be left out when there is one readable file); `text`, `id`, `fields`, `offset`, `limit` as the
other table sources. Kaggle lists no checksum, so the bytes are not checked against the source; each item is frozen
by its own sha256. It records the source block (provider kaggle, the ref, the version as `revision`, its page, the
sha256 of its description), the licence when Kaggle's name for it is one we can map, and the title. A private or
gated dataset needs credentials: `EVAL_FETCH_HEADERS` `{"www.kaggle.com": {"Authorization": "Basic …"}}`.
`KAGGLE_ENDPOINT` names another server.
"""

from __future__ import annotations

import hashlib
import io
import os
import zipfile
from collections.abc import Iterator
from typing import Any

from evaluation_harness.sources import _tables

#: Kaggle's licence names (its picker's), as SPDX ids; a name not here is not mapped.
LICENCES = {
    "CC0: Public Domain": "CC0-1.0",
    "CC BY 4.0": "CC-BY-4.0",
    "Attribution 4.0 International (CC BY 4.0)": "CC-BY-4.0",
    "CC BY-SA 4.0": "CC-BY-SA-4.0",
    "Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)": "CC-BY-SA-4.0",
    "CC BY-SA 3.0": "CC-BY-SA-3.0",
    "CC BY-NC-SA 4.0": "CC-BY-NC-SA-4.0",
    "Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)": "CC-BY-NC-SA-4.0",
    "CC BY-NC 4.0": "CC-BY-NC-4.0",
    "CC BY-ND 4.0": "CC-BY-ND-4.0",
    "ODC Public Domain Dedication and Licence (PDDL)": "PDDL-1.0",
    "ODC Attribution License (ODC-By)": "ODC-By-1.0",
    "Open Database License (ODbL)": "ODbL-1.0",
    "Apache 2.0": "Apache-2.0",
    "MIT": "MIT",
    "Unknown": "unknown",
}


def _endpoint() -> str:
    return os.environ.get("KAGGLE_ENDPOINT", "https://www.kaggle.com").rstrip("/")


class Source:
    """Items from one table file of a Kaggle dataset, at one version."""

    def __init__(self, options: dict) -> None:
        self.options = options

    @staticmethod
    def _view(query: dict) -> dict:
        ref = str(query.get("ref") or "")
        if ref.count("/") != 1:
            raise ValueError('the kaggle source needs a ref, "owner/slug", in its query')
        return _tables.get_json(f"{_endpoint()}/api/v1/datasets/view/{ref}")

    def _version(self, query: dict, view: dict | None = None) -> int:
        if query.get("version"):
            return int(query["version"])
        got = (view or self._view(query)).get("currentVersionNumber")
        if not got:
            raise ValueError(f'Kaggle gives no version for {query["ref"]}: name one with "version"')
        return int(got)

    def describe(self, query: dict) -> dict:
        """Kaggle's words for the dataset: the source block at its version, licence, title."""
        v = self._view(query)
        desc = str(v.get("description") or "")
        out: dict[str, Any] = {
            "source": {
                "provider": "kaggle",
                "ref": query["ref"],
                "url": f"{_endpoint()}/datasets/{query['ref']}",
                "revision": str(self._version(query, v)),
                "description_sha256": hashlib.sha256(desc.encode("utf-8")).hexdigest() if desc else None,
            },
            "description": v.get("title") or None,
        }
        lic = LICENCES.get(str(v.get("licenseName") or ""))
        if lic:
            out["licence"] = lic
        return out

    def items(self, query: dict) -> Iterator[dict]:
        """The rows of one file of the version's zip: text, id, row and kept fields."""
        if not query.get("text"):
            raise ValueError('name the column that is an item\'s text: "text" in the query')
        version = self._version(query)
        data = _tables.fetched(
            f"{_endpoint()}/api/v1/datasets/download/{query['ref']}?datasetVersionNumber={version}"
        )
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise ValueError(f"{query['ref']} version {version}: not a zip ({e})") from e
        names = [n for n in zf.namelist() if _tables.kind_of(n)]
        name = query.get("file") or (names[0] if len(names) == 1 else None)
        if not name or name not in zf.namelist():
            raise ValueError(
                f'{query["ref"]} version {version} has {", ".join(zf.namelist())}: name the table with "file"'
            )
        kind = _tables.kind_of(name)
        if not kind:
            raise ValueError(f"{name}: only parquet, CSV, JSON and JSON lines files are read")
        cols = [query["text"], *([query["id"]] if query.get("id") else []), *(query.get("fields") or [])]
        yield from _tables.items(_tables.rows(zf.read(name), kind, cols), query)
