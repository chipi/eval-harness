"""How the catalog's and the inspector's answers are said in the terminal: the text of `evh overview-show`, `arm-list`,
`arm-show`, `metric-list`, `metric-show`, `activity-show` and `comparison-show` (their operations compute, ops/views, and
these print what they computed), and the inspector's per-item views, which print as they compute (`item_view`, `_crosstab`,
`_items_out`, `sheet_view`: the answer of `comparison-item`, `comparison-crosstab`, `comparison-items` and `sheet-show`).

They read the project through the same adapter as the pages (config.yaml's catalog.adapter, else the harness's layout) and
compute with the same functions as the pages and the inspector server, so a number here is the number there. The pages are
a comfort; everything they show is a command."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import contextlib
import io
import json
import re
import statistics
import textwrap

from evaluation_harness import _jsonout, _outputs, _sheet, _visibility
from evaluation_harness import catalog_arms as ca
from evaluation_harness import catalog_build as cb
from evaluation_harness import catalog_models as cm
from evaluation_harness import catalog_periods as cp
from evaluation_harness import catalog_serve as cs
from evaluation_harness._common import die
from evaluation_harness.model import arm_views as av
from evaluation_harness.model import metric_views as mviews
from evaluation_harness.model.entity import Problem
from evaluation_harness.stats import fmt_p

KINDS = av.KINDS


def _table(heads: list, rows: list) -> None:
    if _jsonout.table(heads, rows):  # under --json: kept as data, not printed
        return
    cells = [[str(c) for c in r] for r in rows]
    w = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(heads)]
    print("  " + "  ".join(h.ljust(w[i]) for i, h in enumerate(heads)).rstrip())
    print("  " + "  ".join("-" * x for x in w))
    for r in cells:
        print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip())


def _condition_value(v) -> str:
    """A field's value in the conditions table: whole, except a digest, whose first 16 characters tell it apart."""
    text = str(v)
    return text[:16] if re.fullmatch(r"[0-9a-f]{24,}", text) else text


def _fmt(v) -> str:
    return "—" if v is None else cb.fmt(v)


_scored = av.scored
_kind = av.kind


def _refused(fn, *args):
    """What a view's data function gives, its refusal the command's: a thing that is not there, or an input that is
    wrong (`die` names its kind as a literal)."""
    try:
        return fn(*args)
    except Problem as exc:
        if exc.kind == "not-found":
            die(str(exc), "not-found")
        die(str(exc), "bad-argument")


def say(printer, data) -> str:
    """What a command prints for a view's data, as text (the operation's answer)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        printer(data)
    return buf.getvalue().rstrip("\n")


def _pcells(p: dict, flows: tuple) -> list:
    """A row's period cells: new, then each flow with its trend (usd as money, tokens with commas)."""
    fmts = {
        "usd": lambda v: cb.fmt_amount(v, "usd") if v else "—",
        "tokens": lambda v: f"{round(v):,}" if v else "—",
    }
    return ["new" if p["new"] else ""] + [cp.cell(p[f], p[f"{f}_prev"], fmts.get(f, str)) for f in flows]


PERIOD_HEADS = {
    "runs": "runs in period",
    "arms": "arms in period",
    "usd": "spend in period",
    "tokens": "tokens in period",
    "events": "changes in period",
}


def print_goals(d: dict) -> None:
    """Every goal, one row each: what it decides on, its datasets, how many systems were filed, the arm it recommends;
    with a period, each one's runs, spend and changes beside the period before, and what happened in it."""
    per = d.get("period")
    flows = ("runs", "usd", "events")
    if per and per["line"]:
        print(per["line"])
    _table(
        ["goal", "decides", "datasets", "systems filed", "recommended", "title"]
        + (["", *(PERIOD_HEADS[f] for f in flows)] if per else []),
        [
            [
                g["goal"],
                (g["measure"] or {}).get("measure", ""),
                ", ".join(g["datasets"]),
                g["systems_filed"],
                "; ".join(
                    x["label"]
                    + (f" ({' · '.join(x['vs_baseline'])} vs baseline)" if x["vs_baseline"] else "")
                    for x in g["recommended"]
                )
                or "none yet",
                g.get("title") or "",
                *(_pcells(g["period"], flows) if per else []),
            ]
            for g in d["goals"]
        ],
    )
    if per:
        print("\nwhat happened in the period:")
        if per["happened"]:
            _table(["when", "goal", "what"], [[x["when"], x["goal"], x["what"]] for x in per["happened"]])
        else:
            print("  nothing")


def print_goal(r: dict) -> None:
    """One goal in full: what it is for, its decision rule, its studies, the answer so far on each dataset (the baseline
    promoted, and per reference scored against each arm's row: its mean, the paired test against the leader, the
    contender test, its cost and speed, its flags and whether it leads), the recommended arm and why, and its rounds."""
    from evaluation_harness import _goal_view  # noqa: PLC0415
    from evaluation_harness.axes import axis_title, cell_text  # noqa: PLC0415

    print(f"{r['title']}\n")
    print(textwrap.fill(r["statement"], width=96))
    print(f"\n  decision   {r['decision']}\n  decides    {r['measure']}, {r['direction']} is better")
    print(f"  strategy   {r['strategy']}: {r['strategy_about']}")
    print(f"  tie-break  {', '.join(r['tie_break'])}")
    for gr in r["guardrails"]:
        src = f" ({gr['source']})" if gr.get("source") else ""
        print(
            textwrap.fill(
                f"guardrail  {gr['name']}: {gr['rule']}{src}",
                width=96,
                initial_indent="  ",
                subsequent_indent="             ",
            )
        )
    for x in r["links"]:
        print(f"  link       {x['note'] + ': ' if x.get('note') else ''}{x['url']}")
    for s in r["studies"]:
        print(
            f"\nstudy {s['study']}: {s['status']}, from {s['baseline']}, ${s['spent_usd']:.4f} spent"
            + (f"; ended: {s['end']}" if s["end"] else "")
        )
        for t in s["rows"]:
            print(f"  t{t['k']}  {t['outcome']!s:<9} {t['change'] or t['hypothesis']}  — {t['reason']}")
        for c in s["confirms"]:
            print(
                f"  confirmed on {c.get('test')}: {c.get('outcome')} (look {(c.get('look') or {}).get('number')})"
            )
    print("\nthe answer so far:")
    for a in r["answer"]:
        b = a["baseline"]
        if b:
            print(
                f"  {a['dataset']}: baseline {b.get('arm') or b['run']} (promoted {(b['promoted_at'] or '')[:10]})"
            )
            print(textwrap.fill(b["reason"], width=92, initial_indent="    ", subsequent_indent="    "))
        else:
            print(f'  {a["dataset"]}: no decision yet (evh run-promote --run <run_id> --reason "...")')
    for d in r["datasets"]:
        print(
            f"\n{d['dataset']}"
            + (f" · {d['role']}" if d["role"] else "")
            + ("" if d["decides"] else " (does not decide)")
        )
        if d["notes"]:
            print(textwrap.fill(d["notes"], width=96, initial_indent="  ", subsequent_indent="  "))
        for line in (d["looks"], d["exposure"]):
            if line:
                print(f"  {line}")
        if not d["groups"]:
            print(f"  no arm records {r['measure']}")
        for g in d["groups"]:
            what = g["scored_against"]
            print(f"\n  {'scored by ' + what if what.startswith('judge ') else 'scored against ' + what}")
            axes, hyps, arms = (
                g["axes_shown"],
                {a["arm"]: a["hypothesis"] for a in g["arms"] if a["hypothesis"]},
                g["arms"],
            )
            with_kind = any(g["row_kinds"].get(a["arm"]) for a in arms)
            _table(
                [
                    "arm",
                    f"mean {g['measure']}",
                    f"{r['item_word']}s",
                    "vs leader (paired test)",
                    "contender test (within the margin)",
                    *(axis_title(ax) for ax in axes),
                    *(["row"] if with_kind else []),
                    "flags",
                    "decision",
                    *(["hypothesis"] if hyps else []),
                ],
                [
                    [
                        a["label"]
                        + (" [baseline]" if a["baseline"] else "")
                        + (" [recommended]" if a["recommended"] else "")
                        + (f" [retired in {a['retired_in']}]" if a["retired_in"] else ""),
                        _fmt(a["mean"]),
                        a["n"],
                        _goal_view.vs_text(a["vs_leader"]),
                        _goal_view.ni_text(a["noninferior"]),
                        *(cell_text(ax, a["axes"][ax["name"]]) for ax in axes),
                        *([g["row_kinds"].get(a["arm"], "")] if with_kind else []),
                        "; ".join(a["flags"]) or "—",
                        "leader" if a["leader"] else "",
                        *([_goal_view.hypothesis_text(hyps.get(a["arm"]))] if hyps else []),
                    ]
                    for a in arms
                ],
            )
            if g["arms_left_out"]:
                f = g["filter"]
                print(
                    f"  {g['arms_shown']} of {g['arms_total']} arms shown, {g['arms_left_out']} left out by "
                    + " ".join(
                        [f"--arms {p}" for p in f["arms"]]
                        + ([f"--top {f['top']}"] if f["top"] is not None else [])
                    )
                    + " (the baseline, the leader and the recommended arm are always shown)"
                )
            rec = next((a["label"] for a in arms if a["recommended"]), None)
            print(
                f"\n  recommended: {rec}"
                if rec
                else "\n  shown, not recommended"
                if g["shown_only"]
                else "\n  no single arm recommended" + (" yet" if g["leader"] else ": no arm is eligible")
            )
            for w in [*g["why"], g["baseline_gap_text"]]:
                if w:
                    print(textwrap.fill(w, width=96, initial_indent="    - ", subsequent_indent="      "))
            t = g["leader_vs_baseline"]
            if t:
                fam = (
                    f", Bonferroni over {t['family']} arms: {fmt_p(t['p_adjusted'])}"
                    if t["family"] > 1
                    else ""
                )
                print(
                    f"    leader against the baseline: {t['verdict']}, delta {t['delta']:+.4f}, p {fmt_p(t['p'])}{fam}"
                )
    if r["rounds"]:
        print("\nrounds (evh round-list " + r["goal"] + " for the evidence):")
        for x in r["rounds"]:
            print(
                f"  {x['round']:4} {x['status']:7} {x['arms']} arm(s), {x['retired']} retired  {x['conclusion'][:70]}"
            )


def print_dataset_catalog(c: dict) -> None:
    """What the catalog adds to a dataset's record: its arms, its tags and origin, the baselines promoted on it and its
    item fields (the values of public fields only)."""
    print(
        f"{c['arms']} arm(s) from {c['systems']} system(s) (a system rescored against silver or by a judge is an arm of its own)"
    )
    if c["tags"]:
        print("tags: " + ", ".join(f"{k}={t}" for k, t in sorted(c["tags"].items())))
    if c["origin"]:
        print(f"made from {c['origin']}")
    for b in c["baselines"]:
        of = f"{b['goal']}'s baseline" if b.get("goal") else "the dataset's own baseline"
        print(
            f"{of}, version {b.get('version')}: {b.get('arm') or b['run']} (promoted {(b['promoted_at'] or '')[:10]})"
        )
        print(textwrap.fill(b["reason"], width=92, initial_indent="  ", subsequent_indent="  "))
    fs = c["fields"]
    if not fs:
        return
    rows = []
    for x in fs["fields"]:
        if not x["public"]:
            vals = "not public"
        elif "counts" in x:
            vals = " · ".join(f"{k} {n}" for k, n in sorted(x["counts"].items(), key=lambda kv: -kv[1]))
        elif "median" in x:
            vals = f"{x['min']} – {x['max']}, median {x['median']}"
        elif "min" in x:
            vals = f"{x['min']} – {x['max']}"
        elif "distinct" in x:
            vals = f"{x['distinct']} distinct"
        else:
            vals = "—"
        rows.append(
            [
                x["name"],
                x["type"] + (f" ({x['unit']})" if x.get("unit") else ""),
                f"{x['filled']} of {x['of']}",
                vals,
            ]
        )
    print(f"\nfields (field set {fs['fieldset']}; values of public fields only):")
    _table(["field", "type", "filled", "values"], rows)


def _onboarding(r: dict) -> str:
    """A model's onboarding in a word and a day; code under test is replayed, not onboarded: its versions."""
    if r["kind"] == "code":
        v = r["versions"] or {"n": 0, "checked": 0}
        return f"{v['n']} version(s), {v['checked']} checked for faithfulness"
    if r["status"] == "none":
        return "none"
    return f"{ {'vetted': 'pass', 'onboarded': 'probed'}.get(r['status'], 'check') } {r['onboarded'] or ''}"


def print_models(d: dict) -> None:
    """Every model record, one row each (the `models` page in the terminal)."""
    rows = d["models"]
    if not rows:
        print("no model matches" if d["records"] else "no model records: data/models/<model_id>.yaml")
        return
    _table(
        [
            "model",
            "kind",
            "where",
            "weights",
            "build",
            "deployments",
            "settings",
            "onboarding",
            "arms",
            "goals",
            "best result",
        ],
        [
            [
                r["model"],
                r["kind"],
                r["hosting"] or "—",
                r["weights"] or "—",
                ", ".join(r["build"]) + (" (differs)" if r["differs"] else "") if r["build"] else "—",
                ", ".join(r["deployment_ids"]) or "—",
                r["settings"],
                _onboarding(r),
                r["arms"],
                ", ".join(r["goals"]) or "—",
                "; ".join(f"{b['goal']} #{b['rank']} of {b['of']}" for b in r["best"]) or "—",
            ]
            for r in rows
        ],
    )


def print_model(d: dict) -> None:
    """One model record in full: its facts, deployments with what differs, each one's onboarding, its settings history and
    its arms with their smoke (the model's page in the terminal)."""
    rec, c = d["record"], d["catalog"]
    code = rec.get("kind") == "code"
    print(f"{rec.get('name') or d['model']}  [{rec.get('kind') or ''}]")
    onboarding = _onboarding(
        {
            "kind": rec.get("kind"),
            "status": c["status"],
            "onboarded": c["onboarded"],
            "versions": c["versions"],
        }
    )
    for k, x in (
        ()
        if code
        else (
            ("weights", rec.get("weights") or "—"),
            ("licence", rec.get("licence") or "—"),
            ("aliases", ", ".join(rec.get("aliases") or [])),
            ("where", c["hosting"] or "—"),
            ("onboarding", onboarding),
        )
    ):
        print(f"  {k:15} {x}")
    why = rec.get("settings_why") or {}
    for k, x in (rec.get("settings") or {}).items():
        print(f"  setting {k:12} {x}" + (f"  ({why[k]})" if why.get(k) else ""))
    if code:  # code under test (the fleet's feedback 27): its versions, not deployments
        print(f"  {'repository':15} {rec.get('repo') or '—'}")
        print("\nversions:")
        vrows = c["version_rows"]
        if vrows:
            _table(["version", "in production", "what changed", "faithfulness"], vrows)
        else:
            print("  none recorded: list its commits under `versions`")
        return
    deps = c["deployment_rows"]
    print("\ndeployments:")
    if deps:
        _table(
            [
                "deployment",
                "where",
                "server or device",
                "build",
                "matches the record",
                "checked",
                "onboarding",
            ],
            [
                [
                    b["id"],
                    b["where"] + (f" ({b['backend']})" if b.get("backend") else ""),
                    b.get("server") or b.get("device") or b.get("backend") or "—",
                    cm.build_text(b),
                    f"differs: {c['diffs'][b['id']]}" if c["diffs"].get(b["id"]) else "yes",
                    cm.day(b.get("checked_at")) or "—",
                    f"{o['status']} {cm.day(o.get('at'))}" if (o := b.get("onboarding") or {}) else "none",
                ]
                for b in deps
            ],
        )
    else:
        print("  none recorded")
    print("\nonboarding:")
    if deps:
        for dep in deps:
            onb = dep.get("onboarding") or {}
            if not onb:
                print(
                    f"  {dep['id']}: not onboarded: evh model-onboard {d['model']} --deployment {dep['id']}"
                )
                continue
            print(
                f"  {dep['id']}: {onb.get('status')} {cm.day(onb.get('at'))}"
                + (f" on {onb['where']}" if onb.get("where") else "")
            )
            for k, v in (onb.get("report") or {}).items():
                print(f"    {k.replace('_', ' '):16} {cm.kv(v) if isinstance(v, dict) else v}")
            for f in onb.get("flags") or []:
                print(f"    flag: {f}")
    else:
        print(f"  not onboarded: evh model-onboard {d['model']}")
    print("\nsettings history:")
    if c["history"]:
        _table(
            ["when", "what changed", "why"],
            [
                [
                    cm.day(h.get("at")),
                    f"{h.get('what')}: {h.get('from', '—')} → {h.get('to', '—')}"
                    if "from" in h or "to" in h
                    else h.get("what"),
                    h.get("why") or "—",
                ]
                for h in c["history"]
            ],
        )
    else:
        print("  none recorded")
    print("\narms:")
    if c["arm_rows"]:
        _table(
            ["arm id", "goal", "its settings", "arm smoke", "result"],
            [
                [
                    a["arm"],
                    a["goal"] or "—",
                    ", ".join(a["settings"]) or "—",
                    a["smoke"],
                    f"{a['measure']} {_fmt(a['value'])}" if a["measure"] else "—",
                ]
                for a in c["arm_rows"]
            ],
        )
    else:
        print("  none")


def print_datasets(d: dict) -> None:
    """Every dataset, one row each: its version and items, the arms and systems read on it, its reference sets, where it
    came from, its tags, its parts; with a period, each one's runs and spend beside the period before."""
    rows, per = d["datasets"], d.get("period")
    if per and per["line"]:
        print(per["line"])
    flows = ("runs", "usd")
    heads = [
        "dataset",
        "version",
        f"{d['item_word']}s",
        "arms",
        "systems",
        "reference sets",
        "made from",
        "tags",
        "here",
    ]
    cells = []
    for r in rows:
        here = " ".join(k for k, v in r["parts"].items() if v) or "none"
        cells.append(
            [
                r["dataset"],
                f"v{r['version']}" if r["recorded"] else "no record here",
                r["items"] if r["recorded"] else "",
                "" if r["arms"] is None else r["arms"],
                "" if r["systems"] is None else r["systems"],
                ", ".join(r["references"]) or "—",
                r["parent"] or r["origin"] or "",
                " ".join(f"{k}={t}" for k, t in sorted(r["tags"].items())),
                ("sealed; " if r["sealed"] else "") + f"{here}; {len(r['label_sets'])} label set(s)",
                *(_pcells(r["period"], flows) if per else []),
            ]
        )
    _table(heads + (["", *(PERIOD_HEADS[f] for f in flows)] if per else []), cells)


def print_metrics(d: dict) -> None:
    """What each metric measures, one after another (the `metrics` view's data)."""
    if d["period"]:
        print(d["period"] + "\n")
    for m in d["metrics"]:
        print(
            f"{m['metric']}  ({m['better']} is better)"
            if m["better"] != "neutral"
            else f"{m['metric']}  (neutral: a description)"
        )
        print(
            textwrap.fill(
                m["description"] or mviews.NOT_DESCRIBED,
                width=96,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )
        print("    recorded on: " + ", ".join(f"{ds} ({n} arms)" for ds, n in sorted(m["datasets"].items())))
        if m["decides"]:
            print("    decides: " + ", ".join(m["decides"]))
        if m["weighs"]:
            print("    weighed by: " + ", ".join(m["weighs"]))
        if m["period"]:
            p = m["period"]
            print(
                f"    in the period: {cp.cell(p['arms'], p['arms_prev'])} arms recording it"
                + ("  [new]" if p["new"] else "")
            )


def print_metric(d: dict) -> None:
    """One metric, as its page shows it (the `metric` view's data)."""
    print(d["metric"])
    for text in (d["description"] or mviews.NOT_DESCRIBED, d["details"]):
        if text:
            print(textwrap.fill(text, width=96, initial_indent="  ", subsequent_indent="  ") + "\n")
    print(f"  better       {d['better']}")
    print(f"  kind         {d['kind']}")
    print("  decides      " + (", ".join(d["decides"]) or "no goal"))
    print("  weighed by   " + (", ".join(d["weighs"]) or "no goal"))
    for ds in d["datasets"]:
        print(f"\non {ds['dataset']}:")
        _table(
            ["arm", f"mean {d['metric']}", f"{d['item_word']}s", "scored against", "row"],
            [[a["arm"], a["shown"], a["n"], a["scored_against"], a["row"]] for a in ds["arms"]],
        )


def print_overview(d: dict) -> None:
    """The catalog's home page, as `evh overview-show` prints it (the `overview` view's data)."""
    p = d["period"]
    since, until, against = p["since"], p["until"], p["against"]
    span = f"{p['label']}, {since} to {until}"
    print(f"{span}" + (f"; trends against {against}, {p['prev'][0]} to {p['prev'][1]}" if p["prev"] else ""))
    for t in d["tiles"]:
        if t["kind"] == "stock":
            line = f"+{t['new']} new" if t["new"] else "none new"
            value = str(t["value"])
        else:
            line = t["trend"]["text"] + (f" vs {against}" if t["trend"]["pct"] is not None else "")
            value = cb.fmt_amount(t["value"], "usd") if t["what"] == "billed" else f"{round(t['value']):,}"
        print(f"  {cb.TILE_LABEL.get(t['what'], t['what']):15} {value:>16}  {line}".rstrip())
    print(
        "\ngoals at a glance (the leader of the gold group against the baseline, Bonferroni over the arms it was chosen from, threshold 0.05):"
    )
    rows = d["goals"]
    if rows:
        _table(
            ["goal", "dataset", "decides", "baseline", "leader", "leader vs baseline", "recommended"],
            [
                [
                    r["goal"],
                    r["dataset"],
                    r["measure"]
                    + (" (lower)" if r["lower"] else "")
                    + (f" [no gold: {r['group']}]" if r["group"] and not r["gold"] else ""),
                    f"{r['baseline_label']} {_fmt(r['baseline_mean'])}" if r["baseline"] else "none promoted",
                    f"{r['leader_label']} {_fmt(r['leader_mean'])}" if r["leader"] else "—",
                    r["verdict"],
                    (
                        r["recommended_label"]
                        + (f" ({' · '.join(r['vs_baseline'])} vs baseline)" if r["vs_baseline"] else "")
                    )
                    if r["recommended"]
                    else "none yet",
                ]
                for r in rows
            ],
        )
        print(
            "  recommended: what each goal's strategy picks once its limits and the tie-break (cost, then"
            " speed, by default) are applied; evh goal-leaderboard G says why."
        )
    else:
        print("  no goals yet")
    if d["first"]:
        print(f"\nactivity, {span}: measured runs per day")
        counts = d["activity"]
        days = sorted({day for c in counts.values() for day in c})
        if days:
            _table(
                ["day", *sorted(counts), "total"],
                [
                    [
                        day,
                        *(counts[x].get(day, 0) for x in sorted(counts)),
                        sum(counts[x].get(day, 0) for x in counts),
                    ]
                    for day in days
                ],
            )
        else:
            print("  none")
        for unit, per in d["spend"].items():
            print(f"\nspend in {'USD' if unit == 'usd' else 'tokens'}, {span}:")
            if not per:
                print("  none recorded")
                continue
            for name, days_ in per.items():
                print(f"  {name:20} {cb.fmt_amount(sum(days_.values()), unit)}")
    else:
        print("\nactivity and spend: nothing is recorded with a date yet")
    print("\ncoverage:")
    _table(
        [
            "dataset",
            f"{d['item_word']}s",
            "arms scored against",
            "reference sets",
            "metrics",
            "goals",
            "last run",
        ],
        [
            [
                c["dataset"] + (f" (from {c['parent']})" if c["parent"] else ""),
                c["items"],
                " · ".join(f"{k} {n}" for k, n in c["scored"].items()) or "—",
                ", ".join(c["references"]) or "—",
                len(c["metrics"]),
                ", ".join(c["goals"]) or "—",
                c["last"][:10] or "—",
            ]
            for c in d["coverage"]
        ],
    )
    if since:
        ev = d["events"]
        print(f"\nrecorded, {span}: {len(ev)}")
        _table(["when", "what", "kind"], [[x["at"][:16].replace("T", " "), x["what"], x["kind"]] for x in ev])


def print_arms(d: dict, by: str = "dataset", every: bool = False) -> None:
    """Every arm that fits, grouped as the arms page groups them, or one row a system (the `arms` view's data)."""
    ca_groups = dict(ca.GROUPS)
    f, rows = d["filters"], d["arms"]
    if not rows:
        why = []
        if f["weights"]:
            why.append(
                "an arm's weights come from the model records (data/models/, the adapter's model_facts)"
            )
        if f["quality"]:
            why.append("only arms a goal's decision weighs have a place against its quality leader")
        print("no arm matches" + (f": {'; '.join(why)}" if why else ""))
        return
    per, line = d["period"]["rows"], d["period"]["line"]
    flows = ("runs", "usd")
    if line:
        print(line)
    heads_p = ["", *(PERIOD_HEADS[x] for x in flows)] if per else []
    if f["systems"]:
        _table(
            ["system", "model", "provider", "datasets", "arms", "spend", "rank on each goal", *heads_p],
            [
                [
                    c["system"],
                    c["model"] or "—",
                    c["provider"] or "—",
                    ", ".join(c["datasets"]),
                    c["arms"],
                    cb.fmt_amount(c["usd"], "usd") if c["usd"] else "—",
                    "; ".join(f"{r['goal']} #{r['rank']} of {r['of']}" for r in c["ranks"]) or "—",
                    *(_pcells(per[f"c:{c['system']}"], flows) if per else []),
                ]
                for c in d["systems"]
            ],
        )
        return
    # "dataset" groups by what can be ranked together, as the page does: a dataset, scored one way, on one measure.
    key = "" if by == "none" else "set" if by == "dataset" else by
    # One dataset asked for is that group opened; otherwise a group shows its first three, as the page does.
    fold = 0 if every or f["dataset"] or not key else 3
    groups: dict = {}
    for r in sorted(rows, key=ca._reading_order):
        groups.setdefault((ca.set_key(r) if key == "set" else r[key]) if key else "", []).append(r)
    for name in sorted(groups):
        if key:
            print(
                f"\n{ca_groups[key]} {name or '—'} ({len(groups[name])} arm{'' if len(groups[name]) == 1 else 's'})"
            )
        _table(
            [
                "arm id",
                "how measured",
                "dataset",
                "model",
                "provider",
                *(["model record"] if d["has_record"] else []),
                "role",
                "deciding measure",
                "cost / item",
                "latency",
                *heads_p,
            ],
            [
                [
                    r["arm"],
                    r["how"]
                    + (" (wrote its own reference)" if r["kind"] == "t-author" else "")
                    + (f" ({r['moved']:+.3f} vs measured)" if r["moved"] is not None else "")
                    + ("; the goals read its re-score" if r["superseded_by"] else ""),
                    r["dataset"],
                    r["model"] or "—",
                    (r["provider"] or "—") + (" (local)" if r["local"] else ""),
                    *(
                        [
                            f"{r['record']}{'@' + r['deployment'] if r['deployment'] else ''} ({cm.SMOKE_WORDS[r['smoke']]})"
                            if r["record"]
                            else "—"
                        ]
                        if d["has_record"]
                        else []
                    ),
                    ", ".join(dict.fromkeys(r["roles"])) or "—",
                    f"{r['measure']} {_fmt(r['value'])} {'↓' if r['lower'] else '↑'}"
                    if r["measure"]
                    else "—",
                    "—" if r["cost"] is None else "$0" if r["cost"] == 0 else f"${r['cost']:.4f}",
                    "—"
                    if not r["latency"]
                    else f"{r['latency'] / 1000:.1f} s"
                    if r["latency"] >= 1000
                    else f"{r['latency']:.0f} ms",
                    *(_pcells(per[r["arm"]], flows) if per else []),
                ]
                for r in (groups[name][:fold] if fold else groups[name])
            ],
        )
        if fold and len(groups[name]) > fold:
            ds = groups[name][0]["dataset"]
            more = (
                f"evh dataset-arm-list {ds} lists them, with the dataset's other groups "
                f"({sum(r['dataset'] == ds for r in rows)} arms)"
                if key == "set"
                else "evh arm-list --all"
            )
            print(f"  … and {len(groups[name]) - fold} more: {more}")
    if any(r["roles"] for r in rows):
        print(
            "\nroles: leader, first on the goal's deciding measure among the arms its decision weighs (not "
            "significantly ahead of N: N it cannot be told apart from); recommended, what the goal's rule picks; "
            "baseline, the arm the goal promoted. ×N after an arm: N runs of it, averaged per item."
        )


def print_arm(d: dict) -> None:
    """One arm in full, as its page shows it (the `arm` view's data)."""
    print(d["label"] + ("  [baseline]" if d["baseline"] else ""))
    for k, x in (
        ("dataset", d["dataset"]),
        ("scored against", d["scored_against"]),
        ("goal", d["goal"] or "—"),
        ("runs", d["runs"]),
        ("headline", f"{d['headline']['metric']} {_fmt(d['headline']['mean'])}"),
        ("last run", d["last"][:16].replace("T", " ") or "—"),
    ):
        print(f"  {k:15} {x}")
    if d["wrote"]:
        print(
            "  note            wrote the reference it is scored against: its row measures agreement with itself"
        )
    if d["superseded_by"]:
        print(f"  re-scored       the goals read its re-score, {d['superseded_by']}")
    if d["cost_speed"]:
        print("\ncost and speed, per " + d["item_word"] + ":")
        for c in d["cost_speed"]:
            print(f"  {c['axis']:16} {c['text']}")
    print("\nmetrics:")
    _table(
        ["metric", "mean", f"{d['item_word']}s", "better"],
        [[m["metric"], m["shown"], m["n"], m["better"]] for m in d["metrics"]],
    )
    if d["run_list"]:
        print("\nruns:")
        _table(
            ["run", "made", f"{d['item_word']}s", "cost", "how"],
            [
                [
                    r["run"],
                    r["made"][:16].replace("T", " "),
                    r["items"] if r["items"] is not None else "—",
                    f"${r['cost_usd']:.6f}" if r["cost_usd"] is not None else "—",
                    r["how"],
                ]
                for r in d["run_list"]
            ],
        )
    cfg = d["config"]
    if cfg:
        print(
            f"\nsystem {cfg.get('system_id') or ''} (adapter {cfg.get('adapter') or '—'}"
            + (f"; deployment {cfg['deployment']}" if cfg.get("deployment") else "")
            + "; credentials are never shown):"
        )
        for k, x in sorted(cfg["params"].items()):
            print(f"  {k:20} {x}")
    if d["conditions"]:
        print("\nconditions:")
        for k, x in sorted(d["conditions"].items()):
            print(f"  {k:28} {x}")
    if d["siblings"]:
        print("\nthe same system, scored other ways:")
        _table(
            ["arm id", "scored against", "headline", "mean", "row"],
            [[x["arm"], x["scored_against"], x["metric"], _fmt(x["mean"]), x["row"]] for x in d["siblings"]],
        )
    for r in d["rounds"]:
        print(f"round {r['round']} of {r['goal']}: {'retired' if r['retired'] else 'in play'}, {r['status']}")
    for note in d["notes"]:
        print(f"note: {note}")


def _arm_ids(A, tokens: list, label: str) -> list:
    """Arm ids from what the user typed: a full arm id, or a system id looked up among the arms read under `label`."""
    return _refused(av.arm_ids, A, tokens, label)


def print_comparison(
    d: dict, label: dict, item_word: str, what: str = "", by: str = "", analysis: bool = False, xmetric=None
) -> None:
    """A comparison's verdicts, the arms with only an average, the conditions that differ and, with `by`, its breakdown
    (the comparison's data); `label` names each arm, `what` says the baseline is a round's leader."""
    vals = list((d.get("series") or {}).get(d["baseline"], {}).values())
    base_mean = statistics.fmean(vals) if vals else d.get("baseline_mean")
    better = "higher" if d.get("higher_is_better") else "lower"
    print(
        f"{d['metric']} ({better} is better) · baseline {label.get(d['baseline'], d['baseline'])}{what}: mean {_fmt(base_mean)} · Holm across {d['family_size']}\n"
    )
    _table(
        ["run vs baseline", "verdict", "n", "mean", "Δ", "95% CI of Δ", "wins–losses", "p", "Holm threshold"],
        [
            [
                label.get(r["arm"], r["arm"]),
                r["verdict"],
                r["n"],
                _fmt(r["mean"]),
                _fmt(r["delta"]),
                "—" if not r.get("ci") else f"{r['ci'][0]:+.3f} to {r['ci'][1]:+.3f}",
                f"{r['wins']}–{r['losses']}" + (f" ({r['ties']} ties)" if r.get("ties") else ""),
                "—" if r.get("p") is None else fmt_p(r["p"]),
                "—" if not r.get("threshold") else f"{r['threshold']:.4f}",
            ]
            for r in sorted(d["rows"], key=lambda r: r.get("p") if r.get("p") is not None else 9)
        ],
    )
    avgs = d.get("averages") or {}
    if avgs:
        print(f"\nAverage only · {len(avgs)}: no per-{item_word} scores, so no test")
        _table(
            ["run", "recorded average", "vs the baseline's mean"],
            [
                [label.get(a, a), _fmt(v), "—" if base_mean is None else f"{v - base_mean:+.3f}"]
                for a, v in sorted(
                    avgs.items(), key=lambda kv: -kv[1] if d.get("higher_is_better") else kv[1]
                )
            ],
        )
    c = d.get("conditions")
    if c and c.get("fields"):
        if not c["differ"]:
            print(
                f"\nSame conditions: all {c['fields']} recorded fields match (machine, libraries, harness, scorer, items, reference bytes)."
            )
        else:
            print(f"\nConditions: {len(c['differ'])} of {c['fields']} fields differ")
            for w in c["warnings"]:
                print(f"  NOTE: {w}")
            order = list(
                d.get("series") or d.get("labels") or [d["baseline"], *(r["arm"] for r in d["rows"])]
            )
            _table(
                ["field", *[label.get(a, a) for a in order]],
                [
                    [f["name"], *[_condition_value(f["values"].get(a, "—")) for a in order]]
                    for f in c["differ"]
                ],
            )
    if analysis:
        _analysis(d, label, xmetric)
    br = d.get("breakdown")
    if br:
        print(f"\nby {by} (Holm across {br['family_size']}):")
        _table(
            [by, "run vs baseline", "verdict", "n", "Δ", "p"],
            [
                [
                    g["group"],
                    label.get(r["arm"], r["arm"]),
                    r["verdict"],
                    r["n"],
                    _fmt(r["delta"]),
                    "—" if r.get("p") is None else fmt_p(r["p"]),
                ]
                for g in br["groups"]
                for r in g["rows"]
            ],
        )


def item_view(A, args) -> None:
    """One item of the arms compared: each arm's output beside the reference, the item itself, its fields and labels
    (`args`: runs, baseline, label, item)."""
    arms = _arm_ids(A, [t.strip() for t in args.runs.split(",") if t.strip()], args.label)
    base = _arm_ids(A, [args.baseline], args.label)[0] if args.baseline else arms[0]
    label = {a: A.describe(a)["label"] for a in arms}
    ref = A.describe(base).get("reference", "")
    got = cs.item({"arms": [",".join(arms)], "item": [args.item], "ref": [ref] if ref else [""]})
    if got.get("error"):
        die(got["error"], "bad-argument")
    _jsonout.value("item", got)
    for f in got.get("fields") or []:
        print(f"  {f.get('label') or f['name']}: {f['value']}")
    src = got.get("source") or {}
    if src.get("kind") == "text":
        print(f"\n== {args.item} (the {A.item_word} itself)\n{src['text'].rstrip()}")
    elif src.get("note"):
        print(f"\n({src['note']})")
    if got.get("reference"):
        print(f"\n== {ref} (reference)\n{(got['reference']['view'] or {}).get('text', '(none)')}")
    for a, view in got["views"].items():
        # What the page prints above an output: which run it is, and for a repeated arm that
        # it is one repeat beside the mean of all of them.
        info = " · ".join(f"{k} {v}" for k, v in (view.get("info") or {}).items())
        print(
            f"\n== {label[a]}{'  (baseline)' if a == base else ''}"
            + (f"\n({info})" if info else "")
            + f"\n{view.get('text') or view.get('note', '(none)')}"
        )


def _show(heads: list, rows: list) -> None:
    """A table of the sheet: under --json its values as they are, in the terminal numbers rounded and gaps a dash."""
    if _jsonout.table(heads, rows):
        return
    _table(heads, [["—" if v is None else _fmt(v) if isinstance(v, float) else v for v in r] for r in rows])


def sheet_view(A, args) -> int:
    """The dataset's items down, a column per run, printed (RFC-023, _sheet); `args`: dataset_id, runs, metric, label, where,
    by, disagree, split, wrong_against, new_vs, unlabelled, scores_only."""
    from evaluation_harness import _picks  # noqa: PLC0415

    if _visibility.public_env():
        die("--sheet shows the items' outputs and labels: not served publicly", "not-public")
    if not args.dataset_id:
        die("--sheet: name the dataset with --dataset-id", "bad-argument")
    runs = [t.strip() for t in (args.runs or "").split(",") if t.strip()]
    for flag, n, on in (
        ("--disagree", 2, args.disagree),
        ("--split", 3, args.split),
        ("--wrong-against", 1, args.wrong_against),
    ):
        if on and len(runs) < n:
            die(f"{flag} needs {n} run(s) or more in --runs (the first is production's)", "bad-argument")
    model = _sheet.build(
        args.dataset_id,
        runs,
        cs._fields_of,
        metric=args.metric,
        label=args.label,
        wrong_against=args.wrong_against,
        new_vs=args.new_vs,
    )
    found = _sheet.by_where(model, args.where)
    if args.by and args.by not in model["decl"]:
        die(f"--by {args.by}: no field {args.by!r} on {args.dataset_id}", "not-found")
    wanted = [
        s
        for s, on in (
            ("wrong", args.wrong_against),
            ("disagree", args.disagree),
            ("split", args.split),
            ("new", args.new_vs),
            ("unlabelled", args.unlabelled),
        )
        if on
    ]
    shown = _sheet.by_signals(found, wanted)
    from evaluation_harness import _exposure  # noqa: PLC0415

    _exposure.read_by_harness(args.dataset_id, [r["item"] for r in shown], "sheet-show")
    counts = _sheet.counts(found)
    way = (
        f"{model['metric']} ({'lower' if model['lower'] else 'higher'} is better)" if model["metric"] else ""
    )
    print(
        f"{args.dataset_id}: {len(shown)} of {len(found)} {A.item_word}(s)"
        + (f" ({', '.join(wanted)})" if wanted else "")
        + "".join(f" · {s} {n}" for s, n in counts.items() if n)
        + (f" · read on {way}" if way else "")
        + "\n"
    )
    state = _picks.state()

    def picked(item: str) -> str:
        p = state.get((args.dataset_id, item)) or {}
        if p.get("action") != "pick":
            return ""
        return f"for {', '.join(p['for'])}" if p.get("for") else "no target yet"

    head, body, _ = _sheet.flat(model, shown, scores_only=args.scores_only, short=True, picked=picked)
    _show(head, body)
    if runs and model["metric"]:
        fhead, flines = _sheet.footer_table(model, _sheet.footer(model, shown))
        print(f"\nper run, over the {len(shown)} row(s) shown:")
        _show(fhead, flines)
    if args.by:
        groups: dict[str, list] = {}
        for r in shown:
            groups.setdefault(str(r["fields"].get(args.by, "—")), []).append(r)
        print(f"\nby {args.by}:")
        _table(
            [args.by, "rows", *_sheet.SIGNALS],
            [[g, len(rs), *_sheet.counts(rs).values()] for g, rs in groups.items()],
        )
    if shown:
        items = " ".join(f"--item {r['item']}" for r in shown)
        print(
            f'\npick them:  evh pick --dataset-id {args.dataset_id} {items} [--for V] [--tag k=v] [--note "…"]'
        )
        print(
            f"label them: evh label-sheet --dataset-id {args.dataset_id} {items} --out sheet.csv"
            + (f" --runs {','.join(runs)}" if runs else "")
        )
    return 0


def _run_of(A, arm: str):
    """(dataset id, the run folder) of an arm id."""
    from evaluation_harness.label_sheet import run_dir  # noqa: PLC0415

    ds = A.describe(arm).get("dataset", "")
    return ds, run_dir(arm, ds)


def _is_score(v) -> bool:
    """A per-item score's value: a number, true/false, or none (an item it was not scored on)."""
    return v is None or isinstance(v, (bool, int, float))


def _label(v) -> str:
    """A value as a table names it: whole numbers without the .0, a gap `none`."""
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)


def _path(row: dict, dotted: str):
    """The value at a dotted path in a prediction row (`_meta.gates`), None when any step is missing."""
    cur = row
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _order(vals) -> list:
    """Labels in the order a table reads: numbers ascending, then text, `none` last."""

    def key(v: str):
        try:
            return (1 if v == "none" else 0, 0, float(v), "")
        except ValueError:
            return (1 if v == "none" else 0, 1, 0.0, v)

    return sorted(set(vals), key=key)


def _crosstab(A, args) -> None:
    """evh comparison-crosstab --runs R --crosstab A,B [--group FIELD [--group-match REGEX]] [--where F:V]: per group, the items
    counted by their value of score A (down) and score B (across); the items off the diagonal are named."""
    from evaluation_harness._runs import item_rows  # noqa: PLC0415

    names = [m.strip() for m in args.crosstab.split(",") if m.strip()]
    if len(names) != 2:
        die(
            "--crosstab A,B: two per-item scores, comma-separated (e.g. model_false_dismiss,false_dismiss)",
            "bad-argument",
        )
    ma, mb = names
    rx = None
    if args.group_match:
        try:
            rx = re.compile(args.group_match)
        except re.error as exc:
            die(f"--group-match {args.group_match!r}: {exc}", "bad-argument")
    arms = _arm_ids(A, [t.strip() for t in args.runs.split(",") if t.strip()], args.label)
    out = []
    for arm in arms:
        ds, d = _run_of(A, arm)
        rows = list(item_rows(d, strict=False))
        if not rows:
            die(f"{arm}: no predictions.jsonl rows to cross", "not-enough")
        for m in (ma, mb, *([args.group.split(".")[0]] if args.group else [])):
            if not any(m in r for r in rows):
                have = sorted({k for r in rows for k in r if k != "item_id"})
                die(f"{arm}: no per-item {m!r} on record (recorded: {', '.join(have)})", "not-enough")
        # Two per-item SCORES: numbers, true/false or nothing. A `_`-field or one holding text or a record (`_meta`
        # holds the arm's output) would label rows with that content and name each item: the outputs, readable,
        # on a public server too. Such a field is a --group (refused publicly), never a score.
        scores = sorted({k for r in rows for k, v in r.items() if not k.startswith("_") and _is_score(v)})
        for m in (ma, mb):
            if m.startswith("_") or not all(_is_score(r.get(m)) for r in rows):
                die(
                    f"--crosstab {m}: not a per-item score (numbers or true/false); "
                    f"a recorded field belongs in --group. Scores on record: {', '.join(scores)}",
                    "bad-argument",
                )
        keep = None
        if args.where:
            decl, values = cs._fields_of(ds)
            kept, err = cs._filter({"_": {r["item_id"]: 1 for r in rows}}, decl, values, args.where)
            if err:
                die(err, "bad-argument")
            keep = set(kept["_"])
        groups: dict[str, list] = {}
        for r in rows:
            if keep is not None and r["item_id"] not in keep:
                continue
            g = "all"
            if args.group:
                raw = _path(r, args.group)
                text = None if raw is None else _label(raw)
                if rx is not None and text is not None:
                    m = rx.search(text)
                    text = None if not m else (m.group(1) if rx.groups else m.group(0))
                g = _label(text)
            groups.setdefault(g, []).append((r["item_id"], _label(r.get(ma)), _label(r.get(mb))))
        out.append((arm, groups))
    cells_json = []
    for arm, groups in out:
        for g in _order(groups):
            items = groups[g]
            ra, cb_ = _order(a for _, a, _b in items), _order(b for _, _a, b in items)
            n: dict[tuple[str, str], list[str]] = {(a, b): [] for a in ra for b in cb_}
            for i, a, b in items:
                n[(a, b)].append(i)
            head = (f"{A.describe(arm)['label']}: " if len(arms) > 1 else "") + (
                f"{args.group} = {g}" if args.group else "all items"
            )
            print(f"\n{head} · {len(items)} {A.item_word}(s)")
            _table(
                [f"{ma} \\ {mb}", *cb_, "total"],
                [[a, *[len(n[(a, b)]) for b in cb_], sum(len(n[(a, b)]) for b in cb_)] for a in ra]
                + [["total", *[sum(len(n[(a, b)]) for a in ra) for b in cb_], len(items)]],
            )
            off = [(a, b) for a in ra for b in cb_ if a != b and n[(a, b)]]
            for a, b in off:
                ids = n[(a, b)]
                more = len(ids) - args.max_ids
                shown = ids if args.max_ids < 0 else ids[: args.max_ids]
                print(
                    f"  {ma}={a}, {mb}={b}: {len(ids)}  "
                    + ", ".join(shown)
                    + (f" … and {more} more" if more > 0 else "")
                )
            cells_json.append(
                {
                    "arm": arm,
                    "group": g if args.group else None,
                    "items": len(items),
                    "rows": ra,
                    "columns": cb_,
                    "counts": [[len(n[(a, b)]) for b in cb_] for a in ra],
                    "cells": [
                        {"a": a, "b": b, "n": len(n[(a, b)]), "diagonal": a == b, "item_ids": n[(a, b)]}
                        for a in ra
                        for b in cb_
                        if n[(a, b)]
                    ],
                }
            )
    _jsonout.values(
        {
            "crosstab": {
                "a": ma,
                "b": mb,
                "group": args.group,
                "group_match": args.group_match,
                "groups": cells_json,
            }
        }
    )


def _items_out(A, args) -> None:
    """evh comparison-items --runs A,B --items-out [--disagree] [--where F:V]: each item's output of every run, its scores, the
    recorded facts, beside the reference and the labels (the sheet's model, read as records, the texts whole)."""

    tokens = [t.strip() for t in args.runs.split(",") if t.strip()]
    if args.disagree and len(tokens) < 2:
        die(
            "--disagree needs two runs or more in --runs (the first is the one the others are compared to)",
            "bad-argument",
        )
    arms = _arm_ids(A, tokens, args.label)
    if args.baseline:
        base = _arm_ids(A, [args.baseline], args.label)[0]
        if base not in arms:
            die(f"--baseline {args.baseline}: not among --runs", "bad-argument")
        tokens.insert(0, tokens.pop(arms.index(base)))
    dss = {A.describe(a).get("dataset", "") for a in arms}
    if len(dss) != 1:
        die(
            f"--items-out: the runs are on {len(dss)} datasets ({', '.join(sorted(dss))}); one dataset at a time",
            "bad-argument",
        )
    ds = dss.pop()
    model = _sheet.build(ds, tokens, cs._fields_of, metric=args.metric, label=args.label)
    found = _sheet.by_where(model, args.where)
    shown = _sheet.by_signals(found, ["disagree"] if args.disagree else [])
    # Only the shown items' rows: one query per item in the sqlite store, each run's rows indexed once in files.
    tok_of = {d: a["token"] for a, (d, _m) in zip(model["arms"], model["_runs"], strict=True)}
    meta: dict[str, dict[str, object]] = {a["token"]: {} for a in model["arms"]}
    for r in shown:
        for d, row in _outputs.item_across(list(tok_of), r["item"]).items():
            meta[tok_of[d]][r["item"]] = row.get("_meta")
    records = []
    for r in shown:
        records.append(
            {
                "item_id": r["item"],
                "item": r["text"],
                "fields": r["fields"],
                "signals": r["signals"],
                "arms": {
                    a["token"]: {
                        "run": a["run"],
                        "decision": r["shown"].get(a["token"]),
                        "output": r["decisions"].get(a["token"]),
                        "scores": r["scores"].get(a["token"], {}),
                        "meta": meta[a["token"]].get(r["item"]),
                    }
                    for a in model["arms"]
                },
                "references": r["references"],
                "labels": r["label_text"],
            }
        )
    _jsonout.values(
        {"items_out": {"dataset_id": ds, "runs": [a["run"] for a in model["arms"]], "items": records}}
    )
    from evaluation_harness import _exposure  # noqa: PLC0415

    _exposure.read_by_harness(ds, [r["item_id"] for r in records], "inspect --items-out")
    print(f"{ds}: {len(shown)} of {len(found)} {A.item_word}(s)" + (" (disagree)" if args.disagree else ""))
    cut = args.max_chars
    for rec in records:
        print(f"\n== {rec['item_id']}" + (f"  {rec['item']}" if rec["item"] else ""))
        for k, v in rec["references"].items():
            print(f"  reference {k}: {_clip(v, cut)}")
        for k, v in rec["labels"].items():
            print(f"  label {k}: {v}")
        for t, x in rec["arms"].items():
            sc = " ".join(f"{k}={_label(v)}" for k, v in x["scores"].items())
            print(
                f"  [{t}] {_clip(x['decision'], 80) if x['decision'] is not None else '(none)'}  {sc}".rstrip()
            )
            if x["meta"]:
                print(f"    meta: {_clip(json.dumps(x['meta'], ensure_ascii=False), cut)}")
            if x["output"] is not None:
                print(f"    output: {_clip(_readable(x['output']), cut)}")


def _readable(output: str) -> str:
    """An output that is a JSON object, as the terminal reads it: without the `_`-keys (a trace of the run's probes),
    which --json keeps; any other output as it is."""
    try:
        got = json.loads(output)
    except ValueError:
        return output
    if not isinstance(got, dict):
        return output
    kept = {k: v for k, v in got.items() if not k.startswith("_")}
    left = len(got) - len(kept)
    return json.dumps(kept, ensure_ascii=False) + (f" (+ {left} `_` key(s): --json)" if left else "")


def _clip(text, n: int) -> str:
    """One line of a text, cut at n characters with how long it was (n 0: whole)."""
    one = " ".join(str(text or "").split())
    return one if not n or len(one) <= n else one[: n - 1] + f"… ({len(one)} chars)"


def _quantiles(vals: list) -> str:
    v = sorted(vals)
    q = statistics.quantiles(v, n=4, method="inclusive") if len(v) > 1 else [v[0]] * 3
    return f"min {_fmt(v[0])}  p25 {_fmt(q[0])}  median {_fmt(q[1])}  p75 {_fmt(q[2])}  max {_fmt(v[-1])}"


def _analysis(d: dict, label: dict, xmetric: str | None) -> None:
    """The inspector's analysis charts as numbers: each arm's spread over the items, each arm's
    per-item difference from the baseline, and (with --x) each arm's mean on a second metric."""
    print(f"\nspread per run ({d['metric']}, one line per arm):")
    _table(
        ["arm", "mean", "spread over the items"],
        [
            [label.get(a, a), _fmt(statistics.fmean(s.values())), _quantiles(list(s.values()))]
            for a, s in d["series"].items()
            if s
        ],
    )
    base = d["series"].get(d["baseline"], {})
    rows = []
    for a, s in d["series"].items():
        if a == d["baseline"]:
            continue
        diffs = [s[i] - base[i] for i in s if i in base]
        if diffs:
            rows.append([label.get(a, a), _fmt(statistics.fmean(diffs)), _quantiles(diffs)])
    if rows:
        print(f"\ndifference from the baseline ({label.get(d['baseline'], d['baseline'])}), per item:")
        _table(["arm", "mean Δ", "spread of Δ over the items"], rows)
    shape = d.get("shape") or {}
    xm = xmetric or next(iter(shape), None)
    if xmetric and xmetric not in shape:
        print(
            f"\n(--x {xmetric}: not recorded per item on these arms; recorded: {', '.join(shape) or 'none'})"
        )
    elif xm:
        # The scatter's crosses: each arm's mean over the items that have both numbers.
        rows = []
        for a, ys in d["series"].items():
            pts = [(shape[xm].get(a, {})[i], y) for i, y in ys.items() if i in shape[xm].get(a, {})]
            if pts:
                rows.append(
                    [
                        label.get(a, a),
                        _fmt(statistics.fmean(y for _, y in pts)),
                        _fmt(statistics.fmean(x for x, _ in pts)),
                        len(pts),
                    ]
                )
        if rows:
            print(f"\n{d['metric']} against {xm}, each arm's mean (the scatter's crosses):")
            _table(["arm", d["metric"], xm, "items"], rows)


def print_activity(d: dict) -> None:
    """The activity page: the period, then by dataset, by arm and by kind (the `activity` view's data)."""
    print(d["period"])
    flows = ("runs", "usd", "tokens")
    print("\nby dataset:")
    _table(
        ["dataset", "", *(PERIOD_HEADS[f] for f in flows)],
        [[r["dataset"], *_pcells(r, flows)] for r in d["by_dataset"]],
    )
    arms = d["by_arm"]
    print(f"\nby arm ({arms['active']} active in the period; the {len(arms['rows'])} that moved most):")
    if arms["active"]:
        _table(
            ["arm", "", *(PERIOD_HEADS[f] for f in flows)],
            [[r["arm"], *_pcells(r, flows)] for r in arms["rows"]],
        )
    else:
        print("  none")
    print("\nby kind:")
    _table(
        ["what was billed", "", *(PERIOD_HEADS[f] for f in ("usd", "tokens"))],
        [[r["name"], *_pcells(r, ("usd", "tokens"))] for r in d["by_kind"]],
    )
