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
SYSTEM = """You label a triage agent's past decisions on production error signals.

The agent receives an error signal from a web app (Orrery) and decides one of:
- file: a real problem in the app's code or configuration that someone should fix: open an issue;
- escalate: needs a person's judgement now (the agent cannot tell, or it is urgent);
- dismiss: not worth anyone's time: noise, a browser extension, a bot, an old build, a transient;
- cleanup: a deliberate test or probe error that should be removed, not fixed.

The label is the decision a careful triager should have made AT THE TIME, from what the agent could see:
`seen_at_decision` (the signal and the answers to its probes). Three rules:
1. Judge from `seen_at_decision`. If the right call needed something the agent could not see, say so in
   the reason.
2. Use `afterwards` ONLY to establish what the signal really was: a later fix shows it was a real defect; a
   close comment that explains it (an extension, a staging mirror, a stale build) shows what it was. A claim
   such as "it came from an old build" counts as knowable at the time only if `seen_at_decision` shows it.
3. Ignore whether a GitHub issue for the same error already existed or was filed later. Finding duplicates
   is a later stage's job, not this agent's: a real defect is `file` (or `escalate`) even when an issue for
   it is open.
Answer with JSON only: {"label": "file|dismiss|escalate|cleanup", "reason": "<one sentence>",
"knowable_at_decision": "yes|partly|no", "confidence": "high|medium|low"}."""


def _clip(s: object, n: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, sort_keys=True)
    return s if len(s) <= n else s[:n] + f"… [{len(s) - n} more characters]"


def prompt_for(row: dict) -> str:
    """What the labeller reads for one decision."""
    fd, out = row.get("fleet_decision") or {}, row.get("outcome") or {}
    # What the issues say about the signal (a fix, an explanation), not whether they were open: rule 3.
    issues = [
        {"title": li.get("title"), "close_comments": [_clip(c, 600) for c in close_comments(li)]}
        for li in out.get("linked_issues") or []
        if close_comments(li)
    ]
    later = [
        {k: x.get(k) for k in ("ts", "disposition", "reason")}
        for x in out.get("later_decisions_same_fingerprint") or []
    ]
    parts = {
        "seen_at_decision": {
            "signal": row.get("signal"),
            "probe_answers": {k: _clip(v, 4000) for k, v in (row.get("probes") or {}).items()},
        },
        "production_decided": {k: fd.get(k) for k in ("disposition", "certainty", "reason", "ts")},
        "afterwards": {"what_the_issues_say": issues, "later_decisions_same_fingerprint": later[:20]},
    }
    return json.dumps(parts, indent=1, ensure_ascii=False)


def ask(url: str, key: str, model: str, user: str) -> tuple[dict, dict]:
    """(the parsed answer, the response's usage and model)."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "max_tokens": 1500,
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
    text = (resp["choices"][0]["message"]["content"] or "").strip()
    return parse(text), {
        "usage": resp.get("usage") or {},
        "model": resp.get("model"),
        "finish": resp["choices"][0].get("finish_reason"),
        "text": text,
    }


def parse(text: str) -> dict:
    """The answer's JSON (bare, fenced or inside prose); an unreadable answer is recorded, not fatal."""
    start, end = text.find("{"), text.rfind("}")
    try:
        ans = json.loads(text[start : end + 1]) if start >= 0 else {}
    except json.JSONDecodeError:
        ans = {}
    if not isinstance(ans, dict) or ans.get("label") not in LABELS:
        return {"label": "", "reason": f"unparsed: {text[:300]}", "confidence": ""}
    return ans


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
    # Every answer is kept as it arrives (a paid call): a rerun reuses the ones already answered.
    raw_path = args.sheet / f"items_model.raw.{args.model}.jsonl"
    done = {}
    if raw_path.is_file():
        for x in raw_path.read_text(encoding="utf-8").splitlines():
            d = json.loads(x)
            done[d["id"]] = d
    out, tin, tout = [], 0, 0
    for i, s in enumerate(sheet, 1):
        if s["id"] in done and done[s["id"]]["prompt_sha"] == prompt_sha:
            info = done[s["id"]]
        else:
            _, info = ask(url, key, args.model, prompt_for(rows[s["id"]]))
            info = {"id": s["id"], "prompt_sha": prompt_sha, **info}
            with raw_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(info, ensure_ascii=False) + "\n")
        ans = parse(info["text"])
        tin += info["usage"].get("prompt_tokens") or 0
        tout += info["usage"].get("completion_tokens") or 0
        prod = s["production_decided"].split(" ")[0]
        out.append(
            {
                **s,
                "model_label": ans["label"],
                "model_reason": ans.get("reason", ""),
                "model_confidence": ans.get("confidence", ""),
                "knowable_at_decision": ans.get("knowable_at_decision", ""),
                "agrees_with_production": "yes" if ans["label"] == prod else "no",
                "labeller": f"{args.model} ({info['model']}), prompt {prompt_sha}",
            }
        )
        print(
            f"{i}/{len(sheet)} {s['id'][:50]}: production {prod}, model {ans['label'] or 'UNPARSED'}"
            f" (finish {info.get('finish')})",
            flush=True,
        )
    with (args.sheet / "items_model.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    off = [r for r in out if r["agrees_with_production"] == "no"]
    md = (
        f"# Part B: where {args.model} disagrees with production ({len(off)} of {len(out)})\n\n"
        "Answer in `items_model.csv`, column `answer`: the label you choose (file, dismiss, escalate, "
        "cleanup). Rows where the model agrees with production are not listed.\n\n"
        "| id | alert | production | model | knowable then | confidence | model's reason |\n"
        "|---|---|---|---|---|---|---|\n"
        + "".join(
            f"| {r['id']} | {r['alert']} | {r['production_decided']} | {r['model_label']} | "
            f"{r['knowable_at_decision']} | {r['model_confidence']} | {r['model_reason'].replace('|', '/')} |\n"
            for r in off
        )
    )
    (args.sheet / "items_model.md").write_text(md, encoding="utf-8")
    print(json.dumps({"rows": len(out), "disagree": len(off), "tokens_in": tin, "tokens_out": tout}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
