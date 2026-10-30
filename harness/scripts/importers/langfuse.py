"""The langfuse importer: traces from a Langfuse project, through its public API.

The host and keys come from the environment (LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY; options `host_env`, `public_key_env`, `secret_key_env` name others), never
from the query, which the capture records. Query keys, all optional:
  name, environment, user_id, session_id, tags   filters, as the API takes them
  since/until                                    ISO times on the trace, [since, until)
  observations                                   true: each trace's generations and spans, and
                                                 its scores, in the record (one more call each)

A record: id = the trace id, body = {input, output[, observations]}, fields = {name, environment,
tags, latency, total_cost, session_id, release, metadata}, created_at, source = {system: langfuse,
url: the trace's path on the host, without the host}, outcome = its scores, when observations were
read.

evh capture --importer langfuse --query '{"name": "triage", "since": "2026-10-01"}' --capture c1
"""

from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Iterator

PAGE = 50
OBSERVATION_KEYS = (
    "id",
    "type",
    "name",
    "startTime",
    "endTime",
    "model",
    "input",
    "output",
    "usageDetails",
    "costDetails",
    "calculatedTotalCost",
    "parentObservationId",
)


class Importer:
    """Traces of one Langfuse project."""

    def __init__(self, options: dict) -> None:
        env = os.environ
        self.host = (env.get(options.get("host_env", "LANGFUSE_HOST")) or "").rstrip("/")
        pub = env.get(options.get("public_key_env", "LANGFUSE_PUBLIC_KEY")) or ""
        sec = env.get(options.get("secret_key_env", "LANGFUSE_SECRET_KEY")) or ""
        if not (self.host and pub and sec):
            raise ValueError(
                "the langfuse importer needs LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY "
                "in the environment (or .env)"
            )
        if urllib.parse.urlparse(self.host).scheme not in ("http", "https"):
            raise ValueError(f"LANGFUSE_HOST {self.host!r}: an http(s) URL")
        self.auth = "Basic " + base64.b64encode(f"{pub}:{sec}".encode()).decode()
        self.project: str | None = None

    def _get(self, path: str, params: dict | None = None) -> dict:
        q = urllib.parse.urlencode(
            {k: v for k, v in (params or {}).items() if v not in (None, "")}, doseq=True
        )
        url = f"{self.host}{path}" + (f"?{q}" if q else "")
        req = urllib.request.Request(url, headers={"Authorization": self.auth})  # noqa: S310 — scheme checked in __init__  # nosec B310
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — scheme checked in __init__  # nosec B310
            return json.load(r)

    def _path(self, trace_id: str) -> str:
        if self.project is None:
            data = self._get("/api/public/projects").get("data") or [{}]
            self.project = data[0].get("id", "")
        return f"/project/{self.project}/traces/{trace_id}"

    def records(self, query: dict) -> Iterator[dict]:
        """The project's traces within the query's filters and window, newest pages first as the API gives them."""
        params = {
            "name": query.get("name"),
            "environment": query.get("environment"),
            "userId": query.get("user_id"),
            "sessionId": query.get("session_id"),
            "tags": query.get("tags"),
            "fromTimestamp": query.get("since"),
            "toTimestamp": query.get("until"),
            "limit": PAGE,
        }
        page = 1
        while True:
            d = self._get("/api/public/traces", {**params, "page": page})
            for t in d.get("data") or []:
                body = {"input": t.get("input"), "output": t.get("output")}
                outcome = None
                if query.get("observations"):
                    full = self._get(f"/api/public/traces/{urllib.parse.quote(t['id'])}")
                    obs = sorted(full.get("observations") or [], key=lambda o: o.get("startTime") or "")
                    body["observations"] = [{k: o.get(k) for k in OBSERVATION_KEYS} for o in obs]
                    outcome = {"scores": full.get("scores") or []}
                yield {
                    "id": t["id"],
                    "body": body,
                    "fields": {
                        "name": t.get("name"),
                        "environment": t.get("environment"),
                        "tags": t.get("tags") or [],
                        "latency": t.get("latency"),
                        "total_cost": t.get("totalCost"),
                        "session_id": t.get("sessionId"),
                        "release": t.get("release"),
                        "metadata": t.get("metadata"),
                    },
                    "created_at": t.get("timestamp"),
                    "source": {"system": "langfuse", "url": self._path(t["id"])},
                    "outcome": outcome,
                }
            if page >= ((d.get("meta") or {}).get("totalPages") or 1):
                return
            page += 1
