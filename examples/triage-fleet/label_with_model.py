#!/usr/bin/env python3
"""Part B of the labelling sheet, proposed by a model: one label per exact decision, with a reason.

    EVH_GATEWAY_URL=http://<gateway>/v1 EVH_GATEWAY_KEY_FILE=~/.config/evh/eval-key \\
        python examples/triage-fleet/label_with_model.py decisions.jsonl \\
        --sheet sheet/ --model eval-claude-fable-51

Reads sheet/items.csv (written by label_sheet.py) and, for each row, sends the model everything a
person labelling it would see: the signal, the probe answers, what production decided and why, and
what happened afterwards (the linked issues with the comments beside their closes, later decisions
on the same fingerprint). It asks what the right decision was, with hindsight. Writes
sheet/items_model.csv: the rows with `model_label`, `model_reason`, `agrees_with_production`, and
sheet/items_model.md, the rows where it disagrees, for the owner to decide.

A model's label is a proposal. The owner's answer is the label: rows where the model agrees with
production are taken as production's decision only because the owner said so (2026-10-30), and the
arms of the labeller's own family are marked as such wherever results are shown.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importer import close_comments  # the same reading of the close comments as the capture

LABELS = ("file", "dismiss", "escalate", "cleanup")
SYSTEM = """You label a triage agent's past decisions on production error signals, with hindsight.

The agent receives an error signal from a web app (Orrery) and decides one of:
- file: a real problem in the app's code or configuration that someone should fix: open an issue;
- escalate: needs a person's judgement now (the agent cannot tell, or it is urgent);
- dismiss: not worth anyone's time: noise, a browser extension, a bot, an old build, already handled;
- cleanup: a deliberate test or probe error that should be removed, not fixed.

You see what the agent saw (the signal and the probe answers) and what happened afterwards. Decide what
the right decision was at the time, using what happened afterwards as evidence of what the signal was.
Answer with JSON only: {"label": "file|dismiss|escalate|cleanup", "reason": "<one sentence>",
"confidence": "high|medium|low"}."""


def _clip(s: object, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, sort_keys=True)
    return s if len(s) <= n else s[:n] + f"… [{len(s) - n} more characters]"


def prompt_for(row: dict) -> str:
    """What the labeller reads for one decision."""
    fd, out = row.get("fleet_decision") or {}, row.get("outcome") or {}
    issues = [
        {
            "number": li.get("number"),
            "title": li.get("title"),
            "relation_to_this_decision": li.get("relation"),
            "matched_by": li.get("matched_by"),
            "state": li.get("state"),
            "close_comments": [_clip(c, 600) for c in close_comments(li)],
        }
        for li in out.get("linked_issues") or []
    ]
    later = [
        {k: x.get(k) for k in ("ts", "disposition", "reason")}
        for x in out.get("later_decisions_same_fingerprint") or []
    ]
    parts = {
        "signal": row.get("signal"),
        "probe_answers": {k: _clip(v, 4000) for k, v in (row.get("probes") or {}).items()},
        "production_decided": {k: fd.get(k) for k in ("disposition", "certainty", "reason", "ts")},
        "afterwards": {"linked_issues": issues, "later_decisions_same_fingerprint": later[:20]},
    }
    return json.dumps(parts, indent=1, ensure_ascii=False)


def ask(url: str, key: str, model: str, user: str) -> tuple[dict, dict]:
    """(the parsed answer, the response's usage and model)."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "max_tokens": 400,
        "temperature": 0,
        "metadata": {"tags": ["evh-eval", "evh-label"]},
    }
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"EVH_GATEWAY_URL must be http(s): {url!r}")
    req = urllib.request.Request(  # noqa: S310  # nosec B310 (scheme checked above)
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310  # nosec B310 (scheme checked above)
        resp = json.load(r)
    text = resp["choices"][0]["message"]["content"].strip()
    start, end = text.find("{"), text.rfind("}")
    ans = json.loads(text[start : end + 1]) if start >= 0 else {}
    if ans.get("label") not in LABELS:
        ans = {"label": "", "reason": f"unparsed: {text[:200]}", "confidence": ""}
    return ans, {"usage": resp.get("usage") or {}, "model": resp.get("model")}


def main() -> int:
    """Label the sheet's part B with a model."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("items", type=Path, help="the decisions file (JSONL)")
    ap.add_argument("--sheet", type=Path, required=True, help="the directory label_sheet.py wrote")
    ap.add_argument("--model", required=True, help="the gateway alias of the labeller")
    args = ap.parse_args()
    url = os.environ.get("EVH_GATEWAY_URL", "")
    key_file = os.environ.get("EVH_GATEWAY_KEY_FILE", "")
    if not url or not key_file:
        raise SystemExit("set EVH_GATEWAY_URL and EVH_GATEWAY_KEY_FILE (a file holding the key)")
    key = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
    rows = {
        r["id"]: r
        for r in (json.loads(x) for x in args.items.read_text(encoding="utf-8").splitlines() if x.strip())
    }
    sheet = list(csv.DictReader((args.sheet / "items.csv").open(encoding="utf-8")))
    prompt_sha = hashlib.sha256(SYSTEM.encode()).hexdigest()[:12]
    out, tin, tout = [], 0, 0
    for i, s in enumerate(sheet, 1):
        ans, info = ask(url, key, args.model, prompt_for(rows[s["id"]]))
        tin += info["usage"].get("prompt_tokens") or 0
        tout += info["usage"].get("completion_tokens") or 0
        prod = s["production_decided"].split(" ")[0]
        out.append(
            {
                **s,
                "model_label": ans["label"],
                "model_reason": ans.get("reason", ""),
                "model_confidence": ans.get("confidence", ""),
                "agrees_with_production": "yes" if ans["label"] == prod else "no",
                "labeller": f"{args.model} ({info['model']}), prompt {prompt_sha}",
            }
        )
        print(f"{i}/{len(sheet)} {s['id'][:50]}: production {prod}, model {ans['label']}", flush=True)
    with (args.sheet / "items_model.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    off = [r for r in out if r["agrees_with_production"] == "no"]
    md = (
        f"# Part B: where {args.model} disagrees with production ({len(off)} of {len(out)})\n\n"
        "Answer in `items_model.csv`, column `answer`: the label you choose (file, dismiss, escalate, "
        "cleanup). Rows where the model agrees with production are not listed.\n\n"
        "| id | alert | production | model | confidence | model's reason |\n|---|---|---|---|---|---|\n"
        + "".join(
            f"| {r['id']} | {r['alert']} | {r['production_decided']} | {r['model_label']} | "
            f"{r['model_confidence']} | {r['model_reason'].replace('|', '/')} |\n"
            for r in off
        )
    )
    (args.sheet / "items_model.md").write_text(md, encoding="utf-8")
    print(json.dumps({"rows": len(out), "disagree": len(off), "tokens_in": tin, "tokens_out": tout}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
