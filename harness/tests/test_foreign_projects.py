#!/usr/bin/env python3
"""Three look-alike projects, written the way the beta projects' data is shaped, read by every command (RFC-041, PLAN
0.8.1 R2).

    EVAL_STORE=files python tests/test_foreign_projects.py
    EVAL_STORE=sqlite python tests/test_foreign_projects.py

Why: the suite checked the harness against data the harness made itself. The beta projects' data is not made that way
(imports with no goal and prose measures, a repeat set with a lost pass, zero-price local models), and found three bugs
in a day. `_foreign.py` builds the three shapes with invented names, numbers and text (none of the projects' data is
here) through the harness's own commands, in the store EVAL_STORE names.

Two kinds of check, told apart by their names:

  - `now:`        hold today: no traceback; exit 0, or a refusal that names its kind (`ERROR (<kind>)`); the V-lines
                  validate gives; nothing printed as nan or inf. These must pass.
  - `RFC-041 Fn:` the facts RFC-041 makes true, asserted by hand on these projects. They FAIL on a branch before the
                  fix of that fact merges, and that is intended: each is the failing test of its fix (the repro-first
                  rule). One that passes today says so in its name only by passing.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _foreign  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

PROJECTS: list[Path] = []
SPENT: dict[str, float] = {}
TRACEBACK = "Traceback"
#: nan or inf printed as a value (`nanx`, `-inf`), not inside a word (`info`, `finance`)
NOT_A_NUMBER = re.compile(r"(?<![A-Za-z_./-])-?(?:nan|inf)x?(?![A-Za-z_])")
REFUSAL = re.compile(r"^ERROR \(([a-z-]+)\)", re.M)
LIMITS = ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF")


class Project:
    def __init__(self, name: str, build, build_ref: str | None = None) -> None:
        self.name = name
        self.proj = Path(tempfile.mkdtemp(prefix=f"evh-foreign-{name}-"))
        PROJECTS.append(self.proj)
        self.env = dict(os.environ, EVAL_HOME=str(self.proj), EVH_ACTOR="person:fixture")
        for k in LIMITS:
            self.env.pop(k, None)
        t = time.time()
        self.facts = build(self.proj, dict(self.env))
        SPENT[name] = time.time() - t
        if build_ref:
            self.env["EVAL_BUILD_REF"] = build_ref
        self.outputs: list[tuple[str, str]] = []

    def evh(self, *args, cap: str | None = None, **kw):
        env = dict(self.env)
        if cap is not None:
            env["EVAL_MAX_COST_USD"] = cap
        r = _cli.run(self.proj, env, *args, **kw)
        self.outputs.append((" ".join(map(str, args)), r.stdout + r.stderr))
        return r

    def read(self, label: str, *args, refusal_ok: bool = False, cap: str | None = None):
        """A command that reads: no traceback, and exit 0 (or, where it may, a refusal that names its kind)."""
        r = self.evh(*args, cap=cap)
        refused = REFUSAL.search(r.stderr)
        ok = TRACEBACK not in r.stdout + r.stderr and (
            r.returncode == 0 or (refusal_ok and refused is not None and r.returncode != 0)
        )
        how = (
            "exit 0"
            if r.returncode == 0
            else f"refused ({refused.group(1)})"
            if refused
            else f"exit {r.returncode}"
        )
        check(
            f"now: {self.name}: {label}: no traceback, {'exit 0 or a named refusal' if refusal_ok else 'exit 0'}",
            ok,
            (r.stdout + r.stderr)[-500:],
        )
        if r.returncode != 0 and refused:
            print(f"         {label}: {how}: {r.stderr.strip().splitlines()[0][:150]}")
        return r

    def json_of(self, r) -> dict:
        try:
            return json.loads(r.stdout).get("result", {}) if r.returncode == 0 else {}
        except json.JSONDecodeError:
            return {}


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).strip()


def table_row(html: str, key: str) -> list[str]:
    """The cells' text of the table row whose data-key is `key`."""
    m = re.search(rf'<tr data-key="{re.escape(key)}".*?</tr>', html, re.S)
    return [text_of(c) for c in re.findall(r"<td.*?</td>", m.group(0), re.S)] if m else []


def common_reads(p: Project, datasets: list[str], compare: tuple[str, str] | None) -> None:
    """Every read command, on every project."""
    p.read("runs-list", "runs-list")
    p.read("runs-list --json", "runs-list", "--json")
    listed = p.json_of(p.read("metric-list --json", "metric-list", "--json"))
    for m in [x["metric"] for x in listed.get("metrics", [])]:
        p.read(f"metric-show {m}", "metric-show", m)
    for ds in datasets:
        p.read(f"leaderboard {ds}", "leaderboard", ds, refusal_ok=True)
        p.read(f"cost-report --dataset-id {ds}", "cost-report", "--dataset-id", ds)
    p.read("cost-report", "cost-report")
    p.read("goal-list", "goal-list")
    p.read("arm-list", "arm-list")
    p.read("arm-list --systems 1", "arm-list", "--systems", "1")
    p.read("overview-show", "overview-show")
    p.read("env-check", "env-check", refusal_ok=True)
    if compare:
        p.read(
            "run-compare", "run-compare", "--baseline", compare[0], "--candidate", compare[1], refusal_ok=True
        )


def validate(p: Project, goals: list[str]) -> list[str]:
    r = p.evh("validate")
    lines = r.stdout.splitlines()
    fails = [ln for ln in lines if ln.startswith("  FAIL")]
    warns = [ln for ln in lines if re.match(r"\s+(WARN|warn)", ln)]
    notes = [ln.strip() for ln in lines if ln.strip().startswith("note:")]
    print(
        f"      {p.name}: validate exit {r.returncode}: {len(fails)} FAIL, {len(warns)} warning, {len(notes)} note"
    )
    for ln in [*fails, *warns, *notes]:
        print(f"        {ln.strip()[:170]}")
    check(
        f"now: {p.name}: validate: no traceback, exit 0",
        TRACEBACK not in r.stdout + r.stderr and r.returncode == 0,
        r.stdout[-600:],
    )
    check(f"now: {p.name}: validate: no FAIL line and no warning", not fails and not warns, fails + warns)
    margin = {
        m.group(1) for n in notes if (m := re.match(r"note: V14 goal (\w+): contenders are decided on", n))
    }
    # RFC-041 F1's notes: a goal measure no run records, a direction that is a decision rule (asserted below).
    measured = [n for n in notes if re.match(r"note: V14 goal \w+: primary (measure|direction) ", n)]
    check(
        f"now: {p.name}: validate: the only notes are V14's margin note, one per goal, and its direction notes",
        margin == set(goals) and len(notes) == len(goals) + len(measured),
        notes,
    )
    return lines


def migrate_check(p: Project) -> None:
    r = p.read("migrate --check", "migrate", "--check", refusal_ok=True)
    print(
        f"      {p.name}: migrate --check exit {r.returncode}: {(r.stdout + r.stderr).strip().splitlines()[-1][:140] if (r.stdout + r.stderr).strip() else ''}"
    )


def catalog(p: Project) -> Path:
    out = p.proj / "catalog-out"
    r = p.evh("catalog", "--out", out)
    check(
        f"now: {p.name}: catalog --out: no traceback, exit 0",
        TRACEBACK not in r.stdout + r.stderr and r.returncode == 0,
        (r.stdout + r.stderr)[-500:],
    )
    return out


def no_nan(p: Project) -> None:
    hits = [(c, m.group(0)) for c, o in p.outputs for m in [NOT_A_NUMBER.search(o)] if m]
    check(f"now: {p.name}: no command printed nan or inf as a value", not hits, hits[:4])


# ── the imported project (the podcast eval-data's shape) ─────────────────────────────────────────────────────────
def imported() -> None:
    print("\nimported project (no goal on a run, free-text builds, dirty null, prose goal measures, 64 arms)")
    p = Project("imported", _foreign.imported)
    runs = p.facts["runs"]
    big = runs[_foreign.IMPORTED_BIG]
    lines = validate(p, p.facts["goals"])
    migrate_check(p)
    common_reads(p, p.facts["datasets"], (big[0], big[1]))
    for ds in p.facts["datasets"]:
        a, b = (runs[ds][0], runs[ds][1])
        sa, sb = (re.sub(r"_2026\d{4}T\d{6}Z$", "", x) for x in (a, b))
        p.read(
            f"pair-test {ds}",
            "pair-test",
            ds,
            "--a",
            sa,
            "--b",
            sb,
            "--metric",
            "wer",
            "--json",
            refusal_ok=True,
        )
    out = catalog(p)
    no_nan(p)

    # `wer` has no declared direction on two datasets and a declaration (--asc) on the third.
    print("   RFC-041 F1 (direction): one answer for `wer` on every dataset")
    for ds in p.facts["datasets"]:
        # the arm with the lower wer first: its delta to the other is negative, and it is the better one
        first = min(runs[ds], key=lambda rid: _mean_wer(p, rid))
        second = max(runs[ds], key=lambda rid: _mean_wer(p, rid))
        sa, sb = (re.sub(r"_2026\d{4}T\d{6}Z$", "", x) for x in (first, second))
        v = p.json_of(p.evh("pair-test", ds, "--a", sa, "--b", sb, "--metric", "wer", "--json")).get(
            "values", {}
        )
        check(
            f"RFC-041 F1: pair-test on {ds}: wer is lower-is-better (the arm with the lower wer wins)",
            v.get("direction") == "lower",
            {k: v.get(k) for k in ("direction", "delta")},
        )
        shown = p.json_of(p.evh("metric-show", "wer", "--dataset", ds, "--json"))
        arms = [x["mean"] for d in shown.get("datasets", []) for x in d["arms"]]
        check(
            f"RFC-041 F1: metric-show wer on {ds}: lower, best first",
            str(shown.get("better", "")).startswith("lower") and arms == sorted(arms) and len(arms) > 1,
            (shown.get("better"), arms[:3]),
        )
        cmp_ = p.json_of(p.evh("run-compare", "--baseline", first, "--candidate", second, "--json"))
        verdict = next(
            (
                x["verdict"]
                for b in cmp_.get("blocks", [])
                for x in b.get("rows", [])
                if x.get("metric") == "wer"
            ),
            None,
        )
        check(
            f"RFC-041 F1: run-compare on {ds}: a higher wer than the baseline's is worse",
            verdict == "worse",
            verdict,
        )
    listed = p.json_of(p.evh("metric-list", "--json"))
    check(
        "RFC-041 F1: metric-list: wer is lower",
        next((m["better"] for m in listed.get("metrics", []) if m["metric"] == "wer"), "") == "lower",
        None,
    )
    page = (out / "metrics.html").read_text() if (out / "metrics.html").exists() else ""
    row = page[page.find('id="m-wer"') :][:3000]
    row = row[: row.find("</tr>")]
    check(
        "RFC-041 F1: the catalog's metrics page: wer's row says lower",
        ">lower<" in row and ">higher<" not in row,
        text_of(row)[:200],
    )
    v14 = [
        ln
        for ln in lines
        if "V14 goal" in ln and "contenders are decided on" not in ln and not ln.startswith("  ok")
    ]
    for gid, word in (
        ("english_transcription", "is recorded by no run"),
        ("speaker_attribution", "is recorded by no run"),
        ("regression_detection", "non_inferior"),
    ):
        check(
            f"RFC-041 F1: validate V14 warns about goal {gid} ({word})",
            any(gid in ln and word in ln for ln in v14),
            v14[:3],
        )

    # `dirty: null` on every run an import wrote: marked as unknown, never read as clean
    print("   RFC-041 F3 (unknown, none and zero)")
    r = p.json_of(p.evh("runs-list", "--json"))
    rows = r.get("runs", [])
    check(
        "RFC-041 F3: an import's run records dirty null, and runs-list --json says null (not false)",
        rows and all(x.get("dirty") is None for x in rows),
        [x.get("dirty") for x in rows[:3]],
    )


_MEANS: dict[tuple[str, str], float] = {}


def _mean_wer(p: Project, run_id: str) -> float:
    key = (str(p.proj), run_id)
    if key not in _MEANS:
        import _runstore  # noqa: PLC0415

        _MEANS[key] = _runstore.record_of(p.proj, run_id)["scores"]["wer"]
    return _MEANS[key]


# ── the fleet-shaped project ─────────────────────────────────────────────────────────────────────────────────────
def fleet() -> None:
    print(
        "\nfleet-shaped project (a --repeat 3 set with a lost pass and a joined repeat, a repeat on a changed setting)"
    )
    p = Project("fleet", _foreign.fleet)
    f = p.facts
    check(
        "setup: fleet: the repeat with `of` on a changed setting was accepted (the writer's rule is F7's)",
        f["changed_ok"],
        f["changed_out"],
    )
    validate(p, f["goals"])
    migrate_check(p)
    ds, x, y = f["dataset"], f["arm_lost"], f["arm_changed"]
    common_reads(p, [ds], (f["set"][0], f["no_goal"]))
    p.read(
        "pair-test",
        "pair-test",
        ds,
        "--a",
        x,
        "--b",
        "arm_z_v1",
        "--metric",
        "overlap_f1",
        "--json",
        refusal_ok=True,
    )
    p.read("leaderboard --goal", "leaderboard", ds, "--goal", "triage_a")
    p.read("goal-status", "goal-status", "triage_a")
    p.read("round-evidence", "round-evidence", "triage_a", f["round"], refusal_ok=True)
    p.read("baselines", "baselines")
    out = catalog(p)
    no_nan(p)

    print("   RFC-041 F2 (arm membership)")
    mine = sorted([*f["set"], f["joined"]])
    v = p.json_of(
        p.evh("pair-test", ds, "--a", x, "--b", "arm_z_v1", "--metric", "overlap_f1", "--json")
    ).get("values", {})
    check(
        f"RFC-041 F2: pair-test: {x} is its 3 runs (two of the set, and the repeat joined to it)",
        sorted(v.get("run_ids_a", [])) == mine,
        v.get("run_ids_a"),
    )
    board = p.json_of(p.evh("leaderboard", ds, "--goal", "triage_a", "--json"))
    rows = {
        r["system_id"]: r.get("n_runs")
        for b in board.get("blocks", [])
        for r in b.get("rows", [])
        if "system_id" in r
    }
    check(
        f"RFC-041 F2: leaderboard: {x} has 3 runs and there is no `{x} · repeats` row",
        rows.get(x) == 3 and f"{x} · repeats" not in rows,
        rows,
    )
    listed = p.json_of(p.evh("runs-list", "--json")).get("runs", [])
    of_x = sorted(r["run_id"] for r in listed if r["system_id"] == x)
    check(f"RFC-041 F2: runs-list: {x}'s 3 runs, the joined repeat among them", of_x == mine, of_x)
    arm = out / "a" / f"runs-{ds}-{x}.html"
    txt = text_of(arm.read_text()) if arm.exists() else ""
    check(
        f"RFC-041 F2: catalog: the arm page of {x} says 3 runs and no repeats page exists for it",
        " runs 3 " in txt and not (out / "a" / f"repeats-{ds}-{x}.html").exists(),
        re.findall(r" runs \d+ ", txt),
    )

    print("   RFC-041 F2: a repeat made on a changed setting stays apart")
    v = p.json_of(
        p.evh("pair-test", ds, "--a", y, "--b", "arm_z_v1", "--metric", "overlap_f1", "--json")
    ).get("values", {})
    check(
        f"RFC-041 F2: pair-test: {y} is its first run only; the changed-setting repeat is not in it",
        v.get("run_ids_a") == [f["first_y"]],
        v.get("run_ids_a"),
    )
    check(
        f"RFC-041 F2: catalog: the changed-setting repeat of {y} is read under `repeats`",
        (out / "a" / f"repeats-{ds}-{y}.html").exists(),
        None,
    )
    of_y = [r["run_id"] for r in listed if r["system_id"] == y]
    check(
        f"RFC-041 F2: runs-list: {y} lists its first run, not the changed-setting repeat",
        of_y == [f["first_y"]],
        of_y,
    )

    print("   RFC-041 F6 (the baseline per goal)")
    page = (out / "datasets.html").read_text() if (out / "datasets.html").exists() else ""
    heads = [text_of(h) for h in re.findall(r"<th>(.*?)</th>", page[page.find("<thead>") :][:2000], re.S)]
    cells = table_row(page, ds)
    cell = cells[heads.index("baseline")] if "baseline" in heads and len(cells) == len(heads) else ""
    base_a, base_b = (re.sub(r"_2026\d{4}T\d{6}Z(_r\d)?$", "", f["baselines"][g]) for g in f["goals"])
    check(
        "RFC-041 F6: the datasets page's baseline cell names each goal's baseline arm (triage_a's and triage_b's), not only the latest promoted",
        base_a != base_b and base_a in cell.replace(" ", "") and base_b in cell.replace(" ", ""),
        cell,
    )


# ── the bake-off-shaped project ──────────────────────────────────────────────────────────────────────────────────
def bakeoff() -> None:
    print(
        "\nbake-off-shaped project (zero-price systems, a custom adapter with kinds and no directions, 3 and 22 items)"
    )
    p = Project("bakeoff", _foreign.bakeoff, build_ref="bakeoff-fixture-1")
    f = p.facts
    validate(p, f["goals"])
    migrate_check(p)
    common_reads(p, f["datasets"], (f["runs"][0], f["runs"][1]))
    p.read("goal-status", "goal-status", "bakeoff_small")
    for cap in (None, "0", "1"):
        p.read(
            f"run --dry-run, EVAL_MAX_COST_USD={cap}",
            "run",
            "--system",
            "local_gamma",
            "--dataset",
            f["datasets"][1],
            "--dry-run",
            cap=cap,
        )
    out = catalog(p)
    no_nan(p)

    print("   RFC-041 F3 (unknown, none and zero)")
    sys_ = "local_alpha"
    page = (out / "arms.html").read_text() if (out / "arms.html").exists() else ""
    cells = table_row(page, f"c:{sys_}")
    spend = cells[4] if len(cells) > 4 else ""
    check(
        f'RFC-041 F3: the catalog\'s systems table: {sys_} (priced 0, cost 0.0 recorded) spends $0.00, not "—"',
        re.fullmatch(r"\$0(\.00)?", spend) is not None,
        cells,
    )
    runs_page = out / "a" / f"runs-{f['datasets'][0]}-{sys_}.html"
    row = (
        re.search(rf"{f['runs'][0]} \S+ \S+ \d+ (\S+)", text_of(runs_page.read_text()))
        if runs_page.exists()
        else None
    )
    check(
        "RFC-041 F3: the arm page's runs table: the zero-cost run's cost cell is $0.00, not \"—\"",
        row is not None and re.fullmatch(r"\$0(\.00)?", row.group(1)) is not None,
        row and row.group(1),
    )
    shown = {}
    for cap in (None, "0", "1"):
        r = p.evh("run", "--system", "local_gamma", "--dataset", f["datasets"][1], "--dry-run", cap=cap)
        shown[cap] = next(
            (ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip().startswith("cap ")), ""
        )
    check(
        "RFC-041 F3: the dry run with a cap of 0 shows $0.00 that spends nothing, not NONE",
        "$0.00" in shown["0"] and "spend nothing" in shown["0"] and "NONE" not in shown["0"],
        shown["0"],
    )
    check(
        "RFC-041 F3: the dry run with no cap says NONE, and with a cap of 1 shows $1.00",
        "NONE" in shown[None] and "$1.00" in shown["1"],
        shown,
    )
    r = p.evh("env-check", cap="0")
    line = next((ln for ln in r.stdout.splitlines() if "EVAL_MAX_COST_USD" in ln), "")
    check(
        "RFC-041 F3: env-check with a cap of 0 shows $0.00 that spends nothing",
        "$0.00" in line and "NONE" not in line,
        line,
    )


try:
    t0 = time.time()
    imported()
    fleet()
    bakeoff()
    print(
        "\nbuilt: "
        + ", ".join(f"{k} {v:.1f}s" for k, v in SPENT.items())
        + f"; whole test {time.time() - t0:.1f}s"
    )
finally:
    for d in PROJECTS:
        shutil.rmtree(d, ignore_errors=True)

sys.exit(summary())
