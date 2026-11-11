"""The study commands (RFC-029).

    evh study-run STUDY [--spec FILE] [--resume] [--dry-run]     open it and run the loop (grid, command); agent: open
    evh study-ask STUDY                                          the state for the agent sampler, with an ask id
    evh study-tell STUDY --ask ID --proposal FILE               the agent's proposal run as the next trial
    evh study-stop STUDY                                         the loop stops after its trial; the study ends
    evh studies [--goal G]  ·  evh studies --study STUDY         what the logs say
    evh study-confirm STUDY --test D --rule superiority|noninferiority [--trial K] [--dry-run]
    evh study-import FILE --goal G --study ID                   Karpathy's results.tsv as a closed study

STUDY is <goal>/<study_id>, or the id when one goal has it.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from evaluation_harness import _jsonout, _store, _study
from evaluation_harness._common import die, evh_prog


def _ap(desc: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=evh_prog(), description=desc)


def _json_flag(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--json", action="store_true", help="one JSON object on stdout when done (text to stderr)"
    )


def run_study(argv: list[str]) -> int:
    """evh study-run: open a study and run its loop (the agent sampler: open it and return)."""
    ap = _ap("open a study and run it (RFC-029): research on validation items, never evidence")
    ap.add_argument("study", help="<goal>/<study_id>")
    ap.add_argument(
        "--spec", type=Path, help="the spec, written into data/studies/<goal>/<study_id>.yaml first"
    )
    ap.add_argument("--resume", action="store_true", help="continue a study after its last finished trial")
    ap.add_argument("--dry-run", action="store_true", help="check the spec and print the plan; call nothing")
    _json_flag(ap)
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("study-run", a.json, live=sys.stderr):
        if "/" not in a.study:
            die("study-run names <goal>/<study_id>", "bad-argument")
        goal, sid = a.study.split("/", 1)
        if a.spec is not None:
            if not _store.is_file(a.spec):
                die(f"--spec {a.spec}: no such file", "not-found")
            if _store.is_file(_study.spec_path(goal, sid)):
                die(
                    f"{_study.spec_path(goal, sid)} exists: a study's spec is written once", "would-overwrite"
                )
            _store.mkdir(_study.spec_path(goal, sid).parent, parents=True, exist_ok=True)
            _store.write_text(_study.spec_path(goal, sid), _store.read_text(a.spec, encoding="utf-8"))
        if not _store.is_file(_study.spec_path(goal, sid)):
            die(f"no spec at {_study.spec_path(goal, sid)} (--spec FILE writes it)", "not-found")
        s = _study.spec(goal, sid)
        found = _study.problems(goal, sid, s)
        if found:
            die(f"study {goal}/{sid}: " + "; ".join(found), "invalid-file")
        st = _study.state(goal, sid)
        sampler = s["sampler"] if isinstance(s["sampler"], str) else "command"
        if a.dry_run:
            stop = s.get("stop") or {}
            print(f"study {goal}/{sid}: {sampler} sampler on {s['dataset']}, from {s['baseline']['config']}, decided on "
                  f"{s['measure']}; at most {stop.get('trials', 'until stopped')} trial(s), "
                  f"${stop.get('usd', 'EVAL_MAX_COST_USD')} in all. Nothing was called.")  # fmt: skip
            _jsonout.values({"study": f"{goal}/{sid}", "sampler": sampler, "dry_run": True})
            return 0
        if st["status"] == "ended":
            die(
                f"study {goal}/{sid} has ended ({st['end'].get('reason')}): a new study continues it",
                "not-allowed",
            )
        if st["status"] in ("running", "stopping") and not a.resume:
            die(f"study {goal}/{sid} was started: --resume continues it after its last trial", "not-allowed")
        if a.resume:
            lost = _study.mark_interrupted(goal, sid)
            if lost:
                print(
                    f"  trial(s) {', '.join(map(str, lost))} stopped mid-way: recorded as interrupted; going on after them"
                )
        if st["status"] == "not started":
            ev = _study.open_study(goal, sid)
            print(f"study {goal}/{sid}: round {ev['round']} opened, from {ev['baseline']}")
        if sampler == "agent":
            print(
                f"  the agent sampler: evh study-ask {goal}/{sid}, then evh study-tell {goal}/{sid} --ask <id> --proposal FILE"
            )
            _jsonout.values({"study": f"{goal}/{sid}", "status": "waiting for the agent"})
            return 0
        smp: Any = "grid" if sampler == "grid" else _study.CommandSampler(str(s["sampler"]["command"]))
        try:
            with _study.loop_lock(goal, sid):
                why = _study.run_loop(goal, sid, smp)
        finally:
            if smp != "grid":
                smp.close()
        end = _study.close_study(goal, sid, why)
        print(f"study {goal}/{sid} ended: {why}. {end['summary']}")
        _jsonout.values(
            {"study": f"{goal}/{sid}", "end": end, "trials": len(_study.state(goal, sid)["trials"])}
        )
    return 0


def ask(argv: list[str]) -> int:
    """evh study-ask: the state the agent sampler proposes from, and an ask id (one open at a time)."""
    ap = _ap("the state of a study for the agent sampler, with an ask id (RFC-029)")
    ap.add_argument("study")
    _json_flag(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("study-ask", a.json, live=sys.stderr):
        goal, sid = _study.resolve(a.study)
        s, st = _study.spec(goal, sid), _study.state(goal, sid)
        if st["status"] != "running":
            die(f"study {goal}/{sid} is {st['status']}: nothing to ask", "not-allowed")
        timeout = float((s.get("stop") or {}).get("ask_timeout_h") or 2) * 3600
        why = _study.stop_reason(goal, sid, _started(st), _start_hash(goal, sid))
        if why:
            end = _study.close_study(goal, sid, why)
            die(f"study {goal}/{sid} ended: {why}. {end['summary']}", "not-allowed")
        open_ask = st["open_ask"]
        state = _study.sampler_state(goal, sid)
        shown = [{"item_id": x["item_id"], "sha256": x.get("sha256")} for x in state["weakest_items"]]
        if open_ask and _age(open_ask) < timeout:
            ask_id = open_ask["ask_id"]
        else:
            ask_id = _study.new_ask_id()
            _study.append(goal, sid, {"event": "ask", "ask_id": ask_id, "shown": shown})
        print(json.dumps({"ask_id": ask_id, **state}, indent=2, default=str))
        _jsonout.values({"ask_id": ask_id, "state": state})
    return 0


def _started(st: dict[str, Any]) -> float:
    import datetime  # noqa: PLC0415

    try:
        return datetime.datetime.fromisoformat(str(st["started_at"]).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return time.time()


def _age(ev: dict[str, Any]) -> float:
    return time.time() - _started({"started_at": ev.get("at")})


def _start_hash(goal: str, sid: str) -> str:
    return next(e for e in _study.events(goal, sid) if e.get("event") == "start")["spec_sha256"]


def tell(argv: list[str]) -> int:
    """evh study-tell: the agent's proposal for the open ask, run as the next trial."""
    ap = _ap("run the agent's proposal as a study's next trial (RFC-029)")
    ap.add_argument("study")
    ap.add_argument("--ask", required=True, help="the ask id study-ask gave")
    given = ap.add_mutually_exclusive_group(required=True)
    given.add_argument(
        "--proposal",
        type=Path,
        help='a JSON file: {"params": {"a.b": v}, "prompts": {name: text}, "hypothesis": "...", "rationale": "..."}',
    )
    given.add_argument("--proposal-json", help="the same proposal as JSON text (an MCP tool call sends this)")
    _json_flag(ap)
    from evaluation_harness._actor import add_by, require_named  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("study-tell", a.json, live=sys.stderr):
        require_named("study-tell")
        goal, sid = _study.resolve(a.study)
        s, st = _study.spec(goal, sid), _study.state(goal, sid)
        timeout = float((s.get("stop") or {}).get("ask_timeout_h") or 2) * 3600
        o = st["open_ask"]
        if not o or o["ask_id"] != a.ask:
            die(
                f"ask {a.ask} is not the study's open ask (used, or never asked): study-ask again",
                "not-allowed",
            )
        if _age(o) >= timeout:
            die(f"ask {a.ask} lapsed (older than {timeout / 3600:g} h): study-ask again", "not-allowed")
        if a.proposal is not None and not _store.is_file(a.proposal):
            die(f"--proposal {a.proposal}: no such file", "not-found")
        text = _store.read_text(a.proposal, encoding="utf-8") if a.proposal is not None else a.proposal_json
        try:
            proposal = json.loads(text)
        except ValueError as exc:
            die(f"the proposal is not JSON ({exc})", "invalid-file")
        if not isinstance(proposal, dict) or not (proposal.get("params") or proposal.get("prompts")):
            die("--proposal: an object with params and/or prompts (and a hypothesis)", "bad-argument")
        allowed = set(((s.get("space") or {}).get("prompts")) or [])
        for name in proposal.get("prompts") or {}:
            if allowed and name not in allowed:
                die(
                    f"prompt {name} is not in the study's space (space.prompts: {', '.join(sorted(allowed))})",
                    "not-allowed",
                )
        with _study.loop_lock(goal, sid):
            if _study.state(goal, sid)["open_ask"] != o:
                die(f"ask {a.ask} was told while this call waited: study-ask again", "not-allowed")
            line = _study.trial(
                goal, sid, len(st["trials"]) + 1, proposal, ask_id=a.ask, shown=o.get("shown")
            )
        print(f"trial {line['k']}: {line['outcome']}: {line.get('reason')}")
        _jsonout.values({"trial": line})
    return 0


def stop(argv: list[str]) -> int:
    """evh study-stop: the loop stops after its current trial (an agent study ends at once)."""
    ap = _ap("stop a study (RFC-029)")
    ap.add_argument("study")
    _json_flag(ap)
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("study-stop", a.json, live=sys.stderr):
        goal, sid = _study.resolve(a.study)
        st = _study.state(goal, sid)
        if st["status"] == "ended":
            die(f"study {goal}/{sid} has already ended", "not-allowed")
        s = _study.spec(goal, sid)
        if s.get("sampler") == "agent" or st["status"] == "not started":
            end = (
                _study.close_study(goal, sid, "stopped (study-stop)")
                if st["status"] != "not started"
                else None
            )
            print(f"study {goal}/{sid} ended" + (f": {end['summary']}" if end else " before it started"))
        else:
            _study.append(goal, sid, {"event": "stop"})
            print(f"study {goal}/{sid}: the loop stops after its current trial")
        _jsonout.values({"study": f"{goal}/{sid}"})
    return 0


def _one(study: str) -> None:
    """`evh studies --study`: one study, as its log says."""
    goal, sid = _study.resolve(study)
    st = _study.state(goal, sid)
    print(
        f"study {goal}/{sid}: {st['status']}, round {st['round']}, from {st['baseline']}, ${st['spent_usd']:.4f} spent"
    )
    for t in st["trials"]:
        print(
            f"  t{t['k']}  {t.get('outcome'):<9} {t.get('hypothesis') or t.get('change')}  — {t.get('reason')}"
        )
    best = st["best"]
    print(f"  best so far: {best['config_id'] if best else st['baseline'] + ' (the baseline)'}")
    for c in st["confirms"]:
        print(
            f"  confirm on {c.get('test')}: {c.get('outcome', 'started')} (look {(c.get('look') or {}).get('number')})"
        )
    if st["end"]:
        print(f"  ended: {st['end'].get('reason')}. {st['end'].get('summary')}")
    _jsonout.value("study", st)


def studies(argv: list[str]) -> int:
    """evh studies: every study, by goal; or one, as its log says."""
    ap = _ap("every study, by goal; or one with --study, as its log says (RFC-029)")
    ap.add_argument("--goal")
    ap.add_argument("--study", help="one study (GOAL/ID): each trial, the best so far, its confirmations")
    _json_flag(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("studies", a.json):
        if a.study:
            _one(a.study)
            return 0
        out = []
        root = _study.root()
        for p in sorted(_store.glob(root, "*/*.yaml")) if _store.is_dir(root) else []:
            goal, sid = p.parent.name, p.stem
            if a.goal and goal != a.goal:
                continue
            st = _study.state(goal, sid)
            kept = sum(1 for t in st["trials"] if t.get("outcome") == "kept")
            out.append({"goal": goal, "study": sid, "status": st["status"], "trials": len(st["trials"]), "kept": kept,
                        "spent_usd": st["spent_usd"], "confirms": len(st["confirms"])})  # fmt: skip
            print(
                f"{goal}/{sid}: {st['status']}, {len(st['trials'])} trial(s), {kept} kept, ${st['spent_usd']:.4f}"
            )
        if not out:
            print("no studies: write a spec and run evh study-run <goal>/<id> --spec FILE")
        _jsonout.value("studies", out)
    return 0


def confirm(argv: list[str]) -> int:
    """evh study-confirm: the best trial against the baseline on a test set, once, as one look (RFC-029)."""
    ap = _ap("confirm a study's best trial on a test set: one look, one-sided at its level (RFC-029)")
    ap.add_argument("study")
    ap.add_argument(
        "--test", required=True, help="the test set (a goal's role: test dataset, or a sealed side)"
    )
    ap.add_argument(
        "--rule",
        required=True,
        choices=("superiority", "noninferiority"),
        help="given before any test item is read",
    )
    ap.add_argument("--trial", type=int, help="this trial instead of the best kept one")
    ap.add_argument(
        "--margin", type=float, help="noninferiority: the margin (default: the study's accept.margin)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="the items, the look and whether it can succeed; run nothing"
    )
    ap.add_argument(
        "--confirm-extra-look", action="store_true", help="past the set's limit: the person's consent"
    )
    ap.add_argument(
        "--override-no-evidence",
        action="store_true",
        help="items that cannot show it: run anyway, inconclusive",
    )
    _json_flag(ap)
    from evaluation_harness._actor import add_by, require_named  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("study-confirm", a.json, live=sys.stderr):
        return _confirm(a, require_named)


def _confirm(a: argparse.Namespace, require_named: Any) -> int:
    from evaluation_harness import _looks, stats  # noqa: PLC0415
    from evaluation_harness._common import load_dataset  # noqa: PLC0415

    who = require_named("study-confirm")
    goal, sid = _study.resolve(a.study)
    s, st = _study.spec(goal, sid), _study.state(goal, sid)
    if not _looks.is_test_set(a.test):
        die(
            f"{a.test} is not a test set (a goal's role: test dataset, or a split's sealed side)",
            "not-allowed",
        )
    t = next((x for x in st["trials"] if x.get("k") == a.trial), None) if a.trial else st["best"]
    if t is None:
        die("no trial to confirm: none was kept (--trial K names one)", "not-found")
    if t.get("outcome") == "failed":
        die(f"trial {t['k']} failed: nothing to confirm", "not-allowed")
    metric = str(s["measure"])
    lower = _study.lower_is_better(goal, metric) or s.get("direction") == "lower"
    margin = (
        a.margin
        if a.margin is not None
        else ((s.get("accept") or {}).get("margin") if isinstance(s.get("accept"), dict) else None)
    )
    if a.rule == "noninferiority" and margin is None:
        die("--rule noninferiority needs a margin (--margin, or accept.margin in the spec)", "bad-argument")
    test = load_dataset(a.test)
    val = load_dataset(s["dataset"])
    seen = {it["item_id"] for it in val.get("items") or []} | {
        it.get("source_sha256") for it in val.get("items") or [] if it.get("source_sha256")
    }
    # Every item shown to a sampler in any study of the goal, by id and by content (a test item with a shown item's
    # bytes is the same text).
    shown: set = set()
    for p in _store.glob(_study.root() / goal, "*.events.jsonl"):
        for ev in _study.events(goal, p.name[: -len(".events.jsonl")]):
            for x in ev.get("shown") or []:
                shown |= {x.get("item_id"), x.get("sha256")} - {None}
    items = [it["item_id"] for it in test.get("items") or []
             if not {it["item_id"], it.get("source_sha256")} & (seen | shown)]  # fmt: skip
    excluded = len(test.get("items") or []) - len(items)
    if not items:
        die(
            f"every item of {a.test} is in the validation set or was shown to a sampler: none left",
            "not-enough",
        )
    trial_cid, base_cid = t["config_id"], st["baseline"]
    on = f"-on-{a.test}"
    k = _looks.key(a.test, trial_cid + on, base_cid + on, metric, a.rule)
    reach = stats.min_attainable_p_one_sided(n=len(items), rule=a.rule, margin=margin or 0.0)
    number, reused = _looks.next_number(a.test, k)
    level = _looks.level(number)
    can = reach is not None and reach <= level
    print(
        f"study-confirm {goal}/{sid}: trial {t['k']} ({trial_cid}) against {base_cid} on {a.test}, {a.rule}"
    )
    print(f"  {len(items)} test item(s) ({excluded} left out: in the validation set or shown to a sampler)")
    print(f"  look {number}{' (the same question: reused)' if reused else ''}, one-sided at {level:.4%}; these items "
          + (f"reach p {reach:.4g} at best" if reach is not None else "are too few for the test (under 100)")
          + ("" if can else ": they cannot show it"))  # fmt: skip
    if a.dry_run:
        _jsonout.values(
            {"items": len(items), "look": number, "level": level, "can_reach": can, "dry_run": True}
        )
        return 0
    if not can and not a.override_no_evidence:
        die(
            "the test items could never show it: fresh items, or --override-no-evidence (the person; inconclusive)",
            "not-enough",
        )
    conf = _study.folder(goal, sid) / "confirm"
    ids_file = conf / f"t{t['k']}{on}.items"
    with _looks.taking(a.test, k, consent=a.confirm_extra_look) as look:
        # The rule and the items, written before any test item is run: the naming in advance.
        _study.append(goal, sid, {"event": "confirm", "phase": "named", "trial": t["k"], "test": a.test, "rule": a.rule,
                                  "margin": margin, "items": len(items), "excluded": excluded, "actor": who,
                                  "look": {x: v for x, v in look.items() if x != "reused"}})  # fmt: skip
        for cid in (trial_cid, base_cid):
            _p, cfg = _study.config_of(cid)
            cfg = {**cfg, "config_id": cid + on, "dataset_id": a.test}
            cfg.pop("round", None)
            cfg.pop("hypothesis", None)
            path = conf / f"{cid}{on}.yaml"
            if not _store.is_file(path):
                _store.mkdir(conf, parents=True, exist_ok=True)
                _store.create_new(path, yaml.safe_dump(cfg, sort_keys=False).encode("utf-8"))
        if not _store.is_file(ids_file):
            _store.create_new(ids_file, ("\n".join(items) + "\n").encode("utf-8"))
        _open_sealed(
            a.test, [trial_cid + on, base_cid + on], look, who, f"study-confirm {goal}/{sid} trial {t['k']}"
        )
    runs: dict[str, list[str]] = {}
    for cid in (trial_cid + on, base_cid + on):
        code, _paid, rids = _study.run_config(cid, int(s.get("repeats") or 1), items=ids_file)
        if code != 0 or not rids:
            die(
                f"the confirmation's run of {cid} ended with exit {code}: the look stands, unanswered",
                "failed",
            )
        runs[cid] = rids
    argv = ["pair-test", "--dataset-id", a.test, "--a", trial_cid + on, "--b", base_cid + on, "--metric", metric,
            "--look-level", repr(level), "--json", "--asc" if lower else "--desc"]  # fmt: skip
    argv += ["--margin", repr(margin)] if margin is not None else []
    r = _study._evh(argv)
    if r.returncode != 0:
        die(f"pair-test refused: {(r.stderr.strip().splitlines() or ['?'])[-1]}", "failed")
    v = (json.loads(r.stdout).get("result") or {}).get("values") or {}
    lv = v.get("look") or {}
    if not can:
        outcome = "inconclusive"
    elif a.rule == "superiority":
        outcome = "better" if lv.get("verdict") == "SIGNIFICANT" else "not shown"
    else:
        outcome = (
            "non-inferior" if (lv.get("noninferior") or {}).get("verdict") == "non-inferior" else "not shown"
        )
    vs = next(x for x in st["trials"] if x.get("k") == t["k"]).get("vs_baseline") or {}
    line = _study.append(goal, sid, {
        "event": "confirm", "phase": "verdict", "trial": t["k"], "test": a.test, "rule": a.rule, "outcome": outcome,
        "delta": v.get("delta"), "p_one_sided": lv.get("p_one_sided"), "n": v.get("n"), "runs": runs,
        "validation_delta": vs.get("delta"), "look": {x: val for x, val in look.items() if x != "reused"},
    })  # fmt: skip
    print(f"  outcome: {outcome} (delta {v.get('delta'):+.4g} on the test items; {vs.get('delta')} on validation, "
          "where it was chosen: the optimizer's curse makes that one larger)")  # fmt: skip
    if outcome in ("better", "non-inferior"):
        print(f"  suggested (never run): evh run-promote --run {runs[trial_cid + on][-1]} --goal {goal} "
              f"--reason \"confirmed by {goal}/{sid} on {a.test}\"")  # fmt: skip
    _jsonout.values({"confirm": line})
    return 0


def _open_sealed(test: str, cids: list[str], look: dict[str, Any], who: dict[str, Any], why: str) -> None:
    """A sealed set opened to exactly the confirmation's two configs, as this look (its entries carry the look)."""
    from evaluation_harness import _seal  # noqa: PLC0415
    from evaluation_harness._common import DATASETS, load_dataset, now, write_json  # noqa: PLC0415

    doc = load_dataset(test)
    if not doc.get("sealed"):
        return
    opened = _seal.opened_for(doc)
    for cid in cids:
        if cid in opened:
            continue
        doc["unsealed"] = [*(doc.get("unsealed") or []), {
            "config_id": cid, "at": now(), "reason": why,
            "hypothesis": {"against": cids[1], "named": "the study's confirm line, written before any test item ran"},
            "commit": "not determinable", "actor": who, "look": {x: v for x, v in look.items() if x != "reused"},
        }]  # fmt: skip
    write_json(DATASETS / f"{test}.json", doc)


def import_tsv(argv: list[str]) -> int:
    """evh study-import: Karpathy's results.tsv (commit, val_bpb, memory_gb, status, description) as a closed
    study, marked imported; its trials carry one number each and cannot be confirmed."""
    ap = _ap("import a past loop's results.tsv as a closed study (RFC-029)")
    ap.add_argument("file", type=Path)
    ap.add_argument("--goal", required=True)
    ap.add_argument("--study", required=True, help="the study id to give it")
    _json_flag(ap)
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    a = ap.parse_args(argv)
    with _jsonout.collect("study-import", a.json, live=sys.stderr):
        from evaluation_harness._common import load_goals  # noqa: PLC0415

        if a.goal not in load_goals():
            die(f"no goal {a.goal!r}", "not-found")
        if not _study.STUDY_ID.fullmatch(a.study):
            die(f"--study {a.study!r}: lower-case letters, digits, '_' or '-'", "bad-argument")
        if _store.is_file(_study.spec_path(a.goal, a.study)):
            die(f"study {a.goal}/{a.study} exists", "would-overwrite")
        if not _store.is_file(a.file):
            die(f"{a.file}: no such file", "not-found")
        rows = list(csv.DictReader(io.StringIO(_store.read_text(a.file, encoding="utf-8")), delimiter="\t"))
        need = {"commit", "val_bpb", "status", "description"}
        if not rows or not need <= set(rows[0]):
            die(
                f"{a.file}: a results.tsv with columns {', '.join(sorted(need))} (memory_gb optional)",
                "invalid-file",
            )
        spec = {"imported": True, "source": str(a.file), "measure": "val_bpb", "direction": "lower",
                "note": "imported from a results.tsv: one number per trial, not confirmable"}  # fmt: skip
        _store.mkdir(_study.spec_path(a.goal, a.study).parent, parents=True, exist_ok=True)
        _store.write_text(_study.spec_path(a.goal, a.study), yaml.safe_dump(spec, sort_keys=False))
        _study.append(
            a.goal,
            a.study,
            {"event": "start", "imported": True, "round": None, "baseline": None, "spec_sha256": None},
        )
        status_map = {"keep": "kept", "discard": "dropped", "crash": "failed"}
        for k, row in enumerate(rows, 1):
            try:
                val = float(row["val_bpb"])
            except (TypeError, ValueError):
                val = None
            _study.append(a.goal, a.study, {
                "event": "trial", "k": k, "imported": True, "config_id": None, "commit": row.get("commit"),
                "val_bpb": val, "memory_gb": row.get("memory_gb"), "outcome": status_map.get(str(row.get("status")).strip(), "dropped"),
                "hypothesis": row.get("description"), "reason": f"imported: {row.get('status')}", "cost_usd": 0,
            })  # fmt: skip
        _study.append(
            a.goal,
            a.study,
            {"event": "end", "reason": "imported", "summary": f"{len(rows)} trial(s) imported from {a.file}"},
        )
        print(f"study {a.goal}/{a.study}: {len(rows)} trial(s) imported (closed; not confirmable)")
        _jsonout.values({"study": f"{a.goal}/{a.study}", "trials": len(rows)})
    return 0


def run(sub: str) -> int:
    """One of the study commands, by name."""
    return {
        "run": run_study, "ask": ask, "tell": tell, "stop": stop, "studies": studies,
        "confirm": confirm, "import": import_tsv,
    }[sub](sys.argv[1:])  # fmt: skip
