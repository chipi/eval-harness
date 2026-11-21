"""A toy filing stage: an alert becomes a new issue, or a comment on (or a reopen of) the issue its key already has.

The caller sets GH (reads and writes an issue tracker) and LEDGER (the file mapping each key to its issue), as the
triage fleet's own filing stage is wired. Version 2: the key ignores case and numbers, so "Disk 91% on db2" and
"disk 97% on DB3" are one issue.
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


def file(signal):
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
