"""A toy filing stage: an alert becomes a new issue, or a comment on (or a reopen of) the issue its key already has.

The caller sets GH (reads and writes an issue tracker) and LEDGER (the file mapping each key to its issue), as the
triage fleet's own filing stage is wired. Version 3: an info-level alert files nothing, and a scheduled job's alert
waits for its third failure (a rule no alert in the history exercises: a replay's coverage names it).
"""

import json
import os
import re

GH = None
LEDGER = "filed.json"
REPO = "acme/service"


def key_of(signal):
    return re.sub(r"\d+", "N", signal["name"]).lower()


def _load():
    if not os.path.exists(LEDGER):
        return {}
    with open(LEDGER, encoding="utf-8") as fh:
        return json.load(fh)


def _save(ledger):
    with open(LEDGER, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, sort_keys=True)


def _cron_waits(signal):
    return int(signal.get("failures", 1)) < 3


def file(signal):
    if signal.get("level") == "info":
        return "none"
    if signal.get("source") == "cron" and _cron_waits(signal):
        return "none"
    ledger = _load()
    key = key_of(signal)
    n = ledger.get(key)
    if n is not None:
        if GH.state(REPO, n) == "closed":
            GH.reopen(REPO, n)
            GH.comment(REPO, n, f"reopening: {key} is back")
            return f"reopen:{n}"
        GH.comment(REPO, n, f"recurred: {key}")
        return f"comment:{n}"
    n = GH.create(REPO, signal["name"])
    ledger[key] = n
    _save(ledger)
    return f"create:{n}"
