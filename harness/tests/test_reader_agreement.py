#!/usr/bin/env python3
"""Every reader says the same of a fact: the CLI, the API, the MCP reads, the catalog export, the inspector (RFC-041, PLAN
0.8.1 R3).

    EVAL_STORE=files  python tests/test_reader_agreement.py
    EVAL_STORE=sqlite python tests/test_reader_agreement.py

Why: each reader was tested alone, so a fact that two of them work out apart (the direction of a measure, the runs of an
arm, the baseline of a goal) was right in each test and wrong between them (SLIP_ANALYSIS_0.8.1 section 3, six of the ten
bugs). Here five projects (the tutorial's, R2's three look-alikes of the beta projects, and a 0.7 repeat set that was re-scored)
are built in the store EVAL_STORE names, and each reader is asked for the facts it states:

  - the value, the items behind it, the direction word, for every (arm, metric);
  - for every arm: its run ids, their number, its latest run, the reference it is read against, its cost state (unknown,
    zero or an amount);
  - for every goal on a dataset: the baseline (the run and the arm); for a dataset: whether its text is shown publicly;
  - for every arm `arm-list` lists: that `arm-show` shows it. A refusal is a disagreement, not "unavailable": an arm
    a reader lists and refuses is no arm (the 0.8.0 dump named arms by their label, `rescored 3d3a6afd, repeats`, where
    the id is its slug, `rescored-3d3a6afd-repeats`).

The readers: `evh <command> --json` (tools/facts_dump.py, the dumper the beta projects run), the same commands through
the API of `evh catalog-serve` (local, and `--public` for the public flag), through the MCP server's read operations
in a process of its own, the catalog export's pages (their `data-v` and `data-key` attributes, and the words a page
says where it has no attribute: a metric's `better`, an arm's `scored against`, a dataset's baseline sentence) and the
inspector's /api/compare. A fact is compared among the readers that give it; a matrix says which reader gives which.

Then it must bite: a reader made to work a fact out itself (`_reader_stubs.py`: the catalog's direction from the name
table; the runs of an arm with the other references' runs averaged in) is run in its place, and the check must fail,
naming that reader and that fact.

`KNOWN` lists a disagreement found here and not yet fixed, with where it is (an entry that no longer reproduces fails: remove it).
"""

import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _serve  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

_spec = importlib.util.spec_from_file_location("facts_dump", HARNESS / "tools" / "facts_dump.py")
assert _spec and _spec.loader
FD = importlib.util.module_from_spec(_spec)
sys.modules["facts_dump"] = FD
_spec.loader.exec_module(FD)

PROC = HERE / "_reader_proc.py"
CLI = HARNESS / "scripts" / "cli.py"
STORE = os.environ.get("EVAL_STORE", "").strip() or "files"
LIMITS = ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF", "EVAL_GOALS_DIR", "EVH_PUBLIC")
KINDS = list(FD.KINDS)
BUILDERS = ("tutorial", "imported", "fleet", "bakeoff", "rescored")
PROJECTS: list[Path] = []
SPENT: dict[str, dict[str, float]] = {}
FactMap = dict[tuple, Any]

#: Disagreements this test found that are not fixed yet: (project, fact, key, the readers that differ) -> where it is.
#: The check reproduces each one and fails when it no longer does.
KNOWN: dict[tuple[str, str, tuple, frozenset], str] = {}


class Project:
    """A project built by `_reader_proc.py build` in a process of its own."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.proj = Path(tempfile.mkdtemp(prefix=f"evh-agree-{name}-"))
        PROJECTS.append(self.proj)
        self.env = dict(os.environ, EVAL_HOME=str(self.proj), EVH_ACTOR="person:fixture")
        for k in LIMITS:
            self.env.pop(k, None)
        t = time.time()
        r = subprocess.run(  # nosec B603 - this interpreter and the test's own helper
            [sys.executable, str(PROC), "build", name, str(self.proj)],
            cwd=self.proj, env=self.env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=1800, check=False,
        )  # fmt: skip
        if r.returncode != 0:
            raise RuntimeError(f"building {name} failed: {(r.stdout + r.stderr)[-800:]}")
        SPENT[name] = {"build": time.time() - t}

    @property
    def evh(self) -> str:
        return f"{sys.executable} {CLI}"


# ── readers: results as facts ────────────────────────────────────────────────────────────────────────────────────────
def prefixed(prefix: str, c: Any) -> tuple[dict[str, FactMap], dict[str, list[str]]]:
    return (
        {f"{prefix}:{r}": d for r, d in c.facts.items()},
        {f"{prefix}:{r}": w for r, w in c.why.items()},
    )


def cli_reader(p: Project, evh: str | None = None, only: set[str] | None = None) -> Any:
    return FD.collect(FD.Cli(evh or p.evh, str(p.proj), p.env).read, jobs=6, only=only)


class Http:
    """GET <route> of an op, as the API serves it: a local server with its token, or a public one by its host name."""

    def __init__(self, port: int, token: str | None, host: str) -> None:
        self.port, self.token, self.host = port, token, host

    def get(self, path: str) -> tuple[int, Any]:
        h = {"Host": self.host, **({"Authorization": f"Bearer {self.token}"} if self.token else {})}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=h)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - this test's own server  # nosec B310
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {"error": body[:200]}

    def read(self, op: str, public: bool = False, **params: Any) -> dict[str, Any]:
        from evaluation_harness.ops import OPS  # noqa: PLC0415

        spec = OPS[op]
        parts = spec.path_params()
        route = spec.route
        for k in parts:
            route = route.replace("{" + k + "}", urllib.parse.quote(str(params[k]), safe=""))
        query = urllib.parse.urlencode({k: v for k, v in params.items() if k not in parts})
        status, body = self.get(f"/api/v1{route}" + (f"?{query}" if query else ""))
        if status != 200:
            raise FD.Unavailable(f"{op}: HTTP {status}: {str(body.get('error'))[:160]}")
        return dict(body["result"])


def api_reader(p: Project) -> Any:
    """The commands through a local `evh catalog-serve`, the public flag through one started `--public`."""
    srv, port, _out = _serve.start(p.proj, p.env)
    srv2, port2, _out2 = _serve.start(p.proj, p.env, "--public", "a.example", "--rate", "1000000")
    try:
        tok_file = p.proj / ".build" / "api-token"
        local = Http(port, tok_file.read_text().strip() if tok_file.exists() else None, f"127.0.0.1:{port}")
        shown = Http(port2, None, "a.example")

        def read(op: str, public: bool = False, **params: Any) -> dict[str, Any]:
            return (shown if public else local).read(op, **params)

        return FD.collect(read, jobs=1)
    finally:
        for s in (srv, srv2):
            s.terminate()
        for s in (srv, srv2):
            try:
                s.wait(15)
            except subprocess.TimeoutExpired:
                s.kill()


def api_inspector(p: Project, cli_facts: FactMap) -> tuple[dict[str, FactMap], dict[str, list[str]]]:
    """`GET /api/compare` of up to four arms of each dataset, one call per metric: the inspector's own derivation."""
    srv, port, _out = _serve.start(p.proj, p.env)
    try:
        tok_file = p.proj / ".build" / "api-token"
        api = Http(port, tok_file.read_text().strip() if tok_file.exists() else None, f"127.0.0.1:{port}")
        arms: dict[str, list[str]] = {}
        for (kind, key), v in sorted(cli_facts.items()):
            if kind == "arms":
                arms.setdefault(key[0], []).extend(v)
        out: dict[str, FactMap] = {}
        why: list[str] = []
        for ds, ids in sorted(arms.items()):
            pick = sorted(set(ids))[:4]
            names: list[str] = []
            first = True
            while first or names:
                metric = names.pop(0) if names else ""
                status, body = api.get(
                    "/api/compare?"
                    + urllib.parse.urlencode(
                        {"runs": ",".join(pick), **({"metric": metric} if metric else {})}
                    )
                )
                if status != 200 or "metrics" not in body:
                    why.append(f"/api/compare {ds}: HTTP {status}: {str(body.get('error'))[:120]}")
                    break
                d = out.setdefault("inspector:compare", {})
                if first:
                    names = [m["name"] for m in body["metrics"]]
                    first = False
                    for m in body["metrics"]:
                        w = (
                            "neutral"
                            if m.get("neutral")
                            else "lower"
                            if m.get("lower_is_better")
                            else "higher"
                        )
                        d[("direction", (ds, m["name"]))] = w
                    for a in body.get("arms") or []:
                        d[("reference", (a["id"],))] = FD.ref(a.get("reference"))
                        d[("n_runs", (a["id"],))] = a.get("runs")
                    continue
                m = body.get("metric") or metric
                base = body.get("baseline")
                for r in body.get("rows") or []:
                    d[("value", (r["arm"], m))] = r["mean"]
                    d[("n_items", (r["arm"], m))] = r["n"]
                    if base and r.get("baseline_mean") is not None:
                        d[("value", (base, m))] = r["baseline_mean"]
        return out, ({"inspector:compare": why} if why else {})
    finally:
        srv.terminate()
        try:
            srv.wait(15)
        except subprocess.TimeoutExpired:
            srv.kill()


def mcp_reader(p: Project, stub: str | None = None) -> Any:
    out = p.proj / "mcp-facts.json"
    r = subprocess.run(  # nosec B603 - this interpreter and the test's own helper
        [sys.executable, str(PROC), "mcp", str(out), *(["--stub", stub] if stub else [])],
        cwd=p.proj, env=p.env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900, check=False,
    )  # fmt: skip
    if r.returncode != 0:
        raise RuntimeError(f"the MCP reader failed: {(r.stdout + r.stderr)[-600:]}")
    doc = json.loads(out.read_text())
    return (
        {f"mcp:{rd}": {(k, tuple(key)): v for k, key, v in facts} for rd, facts in doc["facts"].items()},
        {f"mcp:{rd}": w for rd, w in doc["why"].items()},
    )


# ── the catalog's pages ──────────────────────────────────────────────────────────────────────────────────────────────
def text(s: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", s.replace("<wbr>", ""))).strip())


def dv(cell: str) -> float | str | None:
    m = re.search(r'data-v="([^"]*)"', cell)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return int(v) if v.is_integer() and "." not in m.group(1) else v
    except ValueError:
        return m.group(1)


def cost_cell(cell: str) -> str:
    """A cost cell's state as the page shows it: `$0` is a zero, `$x` an amount; a cell with no dollar in it (`—`, or the
    tokens alone, `63 tok`, which is what a page shows of a run whose cost was not recorded) is unknown."""
    m = re.search(r"\$\s*([0-9][0-9.,]*)", text(cell))
    if not m:
        return "unknown"
    return "zero" if float(m.group(1).replace(",", "")) == 0 else "amount"


def tables(h: str) -> list[tuple[str, int, list[str], list[tuple[str, list[str]]]]]:
    """(id, where it starts, its headers, its rows as (the tr's attributes, the cells' html)) of every table with an id."""
    out = []
    for m in re.finditer(r'<table id="([^"]+)"[^>]*>(.*?)</table>', h, re.S):
        body = m.group(2)
        heads = [text(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
        rows = [
            (attrs, re.findall(r"<td[^>]*>(.*?)</td>", inner, re.S))
            for attrs, inner in re.findall(r"<tr([^>]*)>(.*?)</tr>", body, re.S)
            if "<td" in inner
        ]
        out.append((m.group(1), m.start(), heads, rows))
    return out


def attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'{name}="([^"]*)"', attrs)
    return html.unescape(m.group(1)) if m else None


def kv(h: str) -> dict[str, str]:
    return {text(k): v for k, v in re.findall(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", h, re.S)}


def catalog_facts(out: Path) -> tuple[dict[str, FactMap], dict[str, list[str]]]:
    """What the export's pages state, from their attributes (`data-key`, `data-v`, `data-g`, `data-better`, the
    arm page's `inspect.html?runs=` link) and, where a page has none, the words it says: an arm's `scored against` and `last
    run`, a metric's `better`, a dataset's `<goal>'s baseline, version N` sentence. A goal's baseline is the row a goal
    page tags `baseline`."""
    got: dict[str, FactMap] = {}
    why: dict[str, list[str]] = {}

    def put(reader: str, kind: str, key: tuple, value: Any) -> None:
        if value is None:
            return
        d = got.setdefault(f"catalog:{reader}", {})
        d[(kind, key)] = sorted({*d.get((kind, key), ()), *value}) if kind == "arms" else value

    by_file: dict[str, str] = {}
    arm_pages = sorted((out / "a").glob("*.html")) if (out / "a").is_dir() else []
    pages = {p: p.read_text(encoding="utf-8") for p in arm_pages}
    for p, h in pages.items():
        m = re.search(r'inspect\.html\?runs=([^"&,]+)', h)
        if m:
            by_file[p.stem] = urllib.parse.unquote(html.unescape(m.group(1)))
    if not arm_pages:
        why.setdefault("catalog:arm page", []).append("the export has no arm pages")
    for p, h in pages.items():
        arm = by_file.get(p.stem)
        if not arm:
            why.setdefault("catalog:arm page", []).append(f"{p.name}: no inspect link to name its arm")
            continue
        facts = kv(h)
        ds = text(facts.get("dataset", ""))
        put("arm page", "arms", (ds,), [arm])
        sa = facts.get("scored against", "")
        link = re.search(r'<a class="cell-link" href="\.\./r/[^"]*">(.*?)</a>', sa, re.S)
        said = text(sa)
        put(
            "arm page",
            "reference",
            (arm,),
            FD.ref(text(link.group(1))) if link else FD.ref(None if said.startswith("nothing") else said),
        )
        if "runs" in facts:
            put("arm page", "n_runs", (arm,), int(text(facts["runs"])))
        if "last run" in facts:
            put("arm page", "latest_day", (arm,), text(facts["last run"])[:10])
        if "cost per item" in facts:
            put("arm page", "cost_state", (arm,), cost_cell(facts["cost per item"]))
        for tid, _at, _heads, rows in tables(h):
            if tid == "armmetrics":
                for _a, cells in rows:
                    name = text(cells[0])
                    put("arm metrics", "value", (arm, name), dv(cells[1]))
                    put("arm metrics", "n_items", (arm, name), dv(cells[2]))
                    put("arm metrics", "direction", (ds, name), FD.word(text(cells[3])))
                    if name == "cost_usd":
                        put("arm metrics", "cost_state", (arm,), cost_cell(cells[1]))
            if tid == "armruns":
                made = [(dv(c[1]) or "", text(c[0])) for _a, c in rows]
                put("arm page", "runs", (arm,), sorted(r for _m, r in made))
                put("arm page", "latest", (arm,), max(made)[1] if made else None)

    idx = out / "arms.html"
    if idx.exists():
        h = idx.read_text(encoding="utf-8")
        for tid, _at, heads, rows in tables(h):
            if tid != "arms":
                continue
            col = {name: i for i, name in enumerate(heads)}
            for a, cells in rows:
                row_arm, row_ds = attr(a, "data-key"), attr(a, "data-dataset")
                if row_arm is None or row_ds is None:
                    continue
                put("arms index", "arms", (row_ds,), [row_arm])
                against = re.search(r" against (.+?) · ", attr(a, "data-set") or "")
                put("arms index", "reference", (row_arm,), FD.ref(against.group(1)) if against else None)
                cell = cells[col["deciding measure"]]
                v = re.search(r'<span data-v="([^"]*)"[^>]*data-better="([^"]*)"', cell)
                label = re.search(r'<a class="cell-link"[^>]*>(.*?)</a>', cell, re.S)
                if v and label:
                    put("arms index", "value", (row_arm, text(label.group(1))), float(v.group(1)))
                    put("arms index", "direction", (row_ds, text(label.group(1))), v.group(2))
                put("arms index", "n_runs", (row_arm,), dv(cells[col["repeats"]]))
                put("arms index", "cost_state", (row_arm,), cost_cell(cells[col["cost / item"]]))

    for page in sorted((out / "m").glob("*.html")) if (out / "m").is_dir() else []:
        h = page.read_text(encoding="utf-8")
        name = text(re.search(r"<h1>(.*?)</h1>", h, re.S).group(1))  # type: ignore[union-attr]
        better = FD.word(text(kv(h).get("better", "")))
        marks = [
            (m.start(), text(m.group(1)))
            for m in re.finditer(r'<span class="num">\d+</span>on ([^<]+)</h2>', h)
        ]
        for tid, at, _heads, rows in tables(h):
            if not re.match(r"on\d+$", tid):
                continue
            ds = [d for s, d in marks if s < at][-1]
            if better in ("lower", "higher", "neutral"):
                put("metric page", "direction", (ds, name), better)
            for _a, cells in rows:
                href = re.search(r'href="\.\./a/([^"]+)\.html"', cells[0])
                arm = by_file.get(href.group(1)) if href else None
                if not arm:
                    continue
                put("metric page", "value", (arm, name), dv(cells[1]))
                put("metric page", "n_items", (arm, name), dv(cells[2]))
                ref_link = re.search(r'<a class="cell-link"[^>]*>(.*?)</a>', cells[3], re.S)
                put("metric page", "reference", (arm,), FD.ref(text(ref_link.group(1))) if ref_link else None)

    for page in sorted((out / "d").glob("*.html")) if (out / "d").is_dir() else []:
        h = page.read_text(encoding="utf-8")
        ds = text(re.search(r"<h1>(.*?)</h1>", h, re.S).group(1))  # type: ignore[union-attr]
        for goal, href in re.findall(
            r"([\w.-]+)&#x27;s baseline, version \d+, promoted [^<]*</p>\s*<p class=\"lead\">\s*<b>\s*<a [^>]*href=\"\.\./a/([^\"]+)\.html\"",
            h,
        ):
            put("dataset page", "baseline_arm", (ds, goal), by_file.get(href))

    for page in sorted((out / "g").glob("*.html")) if (out / "g").is_dir() else []:
        h = page.read_text(encoding="utf-8")
        goal = page.stem
        dsm = [(m.start(), m.group(1)) for m in re.finditer(r'href="\.\./d/([^"]+)\.html"', h)]
        for tid, at, heads, rows in tables(h):
            if not tid.startswith("ans"):
                continue
            ds = [d for s, d in dsm if s < at][-1]
            measure = next((x[5:] for x in heads if x.startswith("mean ")), None)
            for _a, cells in rows:
                href = re.search(r'href="\.\./a/([^"]+)\.html"', cells[0])
                arm = by_file.get(href.group(1)) if href else None
                if not arm:
                    continue
                if 'class="tag-base"' in cells[0]:  # two arms tagged is two baselines: say so, as `x + y`
                    tagged = got.get("catalog:goal page", {}).get(("baseline_arm", (ds, goal)))
                    put(
                        "goal page",
                        "baseline_arm",
                        (ds, goal),
                        " + ".join(sorted({*(tagged or "").split(" + "), arm} - {""})),
                    )
                if measure:
                    put("goal page", "value", (arm, measure), dv(cells[1]))
                    put("goal page", "n_items", (arm, measure), dv(cells[2]))
    return got, why


def catalog_reader(p: Project, stub: str | None = None) -> tuple[dict[str, FactMap], dict[str, list[str]]]:
    out = p.proj / "catalog-export"
    shutil.rmtree(out, ignore_errors=True)
    cmd = (
        [
            sys.executable,
            str(PROC),
            "evh",
            *(["--stub", stub] if stub else []),
            "--",
            "catalog",
            "--out",
            str(out),
        ]
        if stub
        else [sys.executable, str(CLI), "catalog", "--out", str(out)]
    )
    r = subprocess.run(  # nosec B603 - this interpreter and the harness's own command
        cmd,
        cwd=p.proj,
        env=p.env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=900,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"catalog --out failed: {(r.stdout + r.stderr)[-600:]}")
    return catalog_facts(out)


# ── the whole of one project ─────────────────────────────────────────────────────────────────────────────────────────
def gather(p: Project) -> tuple[dict[str, FactMap], dict[str, list[str]]]:
    facts: dict[str, FactMap] = {}
    why: dict[str, list[str]] = {}
    marks: dict[str, float] = {}

    def add(got: tuple[dict[str, FactMap], dict[str, list[str]]]) -> None:
        facts.update(got[0])
        why.update(got[1])

    t = time.time()
    c = cli_reader(p)
    add(prefixed("cli", c))
    marks["cli"] = time.time() - t
    t = time.time()
    c2 = api_reader(p)
    add(prefixed("api", c2))
    marks["api"] = time.time() - t
    t = time.time()
    add(mcp_reader(p))
    marks["mcp"] = time.time() - t
    t = time.time()
    add(catalog_reader(p))
    marks["catalog"] = time.time() - t
    t = time.time()
    insp, insp_why = api_inspector(p, {k: v for d in c.facts.values() for k, v in d.items()})
    facts.update(insp)
    why.update(insp_why)
    marks["inspector"] = time.time() - t
    SPENT[p.name].update(marks)
    return facts, why


# ── agreement and the matrix ─────────────────────────────────────────────────────────────────────────────────────────
def compare(facts: dict[str, FactMap]) -> list[dict[str, Any]]:
    return list(FD.disagreements(facts))


def matrix(per_project: dict[str, dict[str, FactMap]]) -> list[str]:
    readers = sorted({r for f in per_project.values() for r in f})
    gives: dict[str, dict[str, int]] = {r: dict.fromkeys(KINDS, 0) for r in readers}
    for f in per_project.values():
        for r, d in f.items():
            for kind, _key in d:
                gives[r][kind] += 1
    short = {
        "arms": "arms", "value": "value", "n_items": "items", "direction": "dir", "runs": "runs", "n_runs": "n_runs",
        "latest": "latest", "latest_day": "l_day", "reference": "ref", "cost_state": "cost", "baseline_run": "b_run",
        "baseline_arm": "b_arm", "public": "public",
    }  # fmt: skip
    w = max(len(r) for r in readers)
    lines = [f"  {'reader':<{w}}  " + " ".join(f"{short[k]:>7}" for k in KINDS)]
    for r in readers:
        lines.append(f"  {r:<{w}}  " + " ".join(f"{('gives' if gives[r][k] else '-'):>7}" for k in KINDS))
    return lines


def explain(dis: list[dict[str, Any]], n: int = 3) -> str:
    return "; ".join(
        f"{d['fact']} {'/'.join(d['key'])}: " + ", ".join(f"{r}={d['values'][r]!r}" for r in d["readers"])
        for d in dis[:n]
    ) + (f" (+{len(dis) - n} more)" if len(dis) > n else "")


def matches(entry: tuple, d: dict[str, Any]) -> bool:
    _pr, fact, key, readers = entry
    return d["fact"] == fact and tuple(d["key"][: len(key)]) == key and frozenset(d["readers"]) == readers


def assert_agreement(project: str, facts: dict[str, FactMap]) -> None:
    dis = compare(facts)
    open_ = [d for d in dis if not any(e[0] == project and matches(e, d) for e in KNOWN)]
    for kind in KINDS:
        bad = [d for d in open_ if d["fact"] == kind]
        givers = {r for r, d in facts.items() if any(k == kind for k, _ in d)}
        check(f"agree: {project}: {kind} ({len(givers)} readers give it)", not bad, explain(bad))
    for entry, where in KNOWN.items():
        if entry[0] == project:
            check(
                f"known: {project}: {entry[1]} {'/'.join(entry[2])} still differs in {sorted(entry[3])} ({where})",
                any(matches(entry, d) for d in dis),
                "it no longer differs: remove it from KNOWN",
            )


def arms_shown(project: str, facts: dict[str, FactMap], why: dict[str, list[str]]) -> None:
    """Every arm `arm-list` lists, `arm-show` shows, through the CLI, the API and the MCP reads: the arm-show answer of an
    arm is its `reference` fact. A reader's refusal of a listed arm (`not-found`) is a disagreement, not an arm this evh
    is unable to say."""
    for reader in ("cli", "api", "mcp"):
        listed = {
            a for (kind, _k), v in facts.get(f"{reader}:arm-list", {}).items() if kind == "arms" for a in v
        }
        shown = {key[0] for kind, key in facts.get(f"{reader}:arm-show", {}) if kind == "reference"}
        refused = why.get(f"{reader}:arm-show", [])
        check(
            f"arms: {project}: {reader}: every arm arm-list lists ({len(listed)}) is shown by arm-show",
            bool(listed) and not listed - shown and not refused,
            (sorted(listed - shown)[:3], refused[:2]),
        )


def hand_checks(project: str, facts: dict[str, FactMap]) -> None:
    """Facts known by hand, from the CLI's answer: the agreement above is not agreement on nothing."""
    cli = {fk: v for r, d in facts.items() if r.startswith("cli:arm-show") for fk, v in d.items()}

    def say(kind: str, *key: str) -> Any:
        return cli.get((kind, key))

    if project == "tutorial":
        check(
            "hand: tutorial: s1_v1's two passes are one arm of two runs on tk_v1",
            say("n_runs", "runs/tk_v1/s1_v1") == 2,
            say("n_runs", "runs/tk_v1/s1_v1"),
        )
        check(
            "hand: tutorial: overlap_f1 goes up, cost_usd down, output_words neither",
            (
                say("direction", "tk_v1", "overlap_f1"),
                say("direction", "tk_v1", "cost_usd"),
                say("direction", "tk_v1", "output_words"),
            )
            == ("higher", "lower", "neutral"),
            None,
        )
        check(
            "hand: tutorial: the arm run before its dataset had a reference is read against gold, its latest run's",
            say("reference", "runs/tk_late_v1/s1_v1") == "gold/tk_late_v1"
            and say("n_runs", "runs/tk_late_v1/s1_v1") == 1,
            (say("reference", "runs/tk_late_v1/s1_v1"), say("n_runs", "runs/tk_late_v1/s1_v1")),
        )
        public = {
            fk[1][0]: v
            for r, d in facts.items()
            if r == "cli:dataset-items"
            for fk, v in d.items()
            if fk[0] == "public"
        }
        check(
            "hand: tutorial: a hidden dataset's text is not public, another's is",
            public == {"tk_v1": True, "tk_late_v1": True, "tk_hidden_v1": False},
            public,
        )
    if project == "fleet":
        check(
            "hand: fleet: the repeat that joined makes arm_x three runs",
            say("n_runs", "runs/queue_triage_v1/arm_x_v1") == 3,
            say("n_runs", "runs/queue_triage_v1/arm_x_v1"),
        )
        check(
            "hand: fleet: the changed-setting repeat is its own arm",
            say("n_runs", "repeats/queue_triage_v1/arm_y_v1") == 1,
            None,
        )
    if project == "bakeoff":
        check(
            "hand: bakeoff: a zero price is zero and no price is unknown",
            (
                say("cost_state", "runs/task_set_small_v1/local_alpha"),
                say("cost_state", "runs/task_set_small_v1/local_delta"),
            )
            == ("zero", "unknown"),
            (
                say("cost_state", "runs/task_set_small_v1/local_alpha"),
                say("cost_state", "runs/task_set_small_v1/local_delta"),
            ),
        )
        check(
            "hand: bakeoff: a declared descriptive kind is neutral, `pass` is higher",
            (say("direction", "task_set_small_v1", "turns"), say("direction", "task_set_small_v1", "pass"))
            == ("neutral", "higher"),
            None,
        )
    if project == "rescored":
        arm = "rescored-3d3a6afd-repeats/tickets_rescored_v1/arm_w_v1"
        check(
            "hand: rescored: the re-scored 0.7 repeat set is one arm of two runs, named by the label's slug",
            say("n_runs", arm) == 2 and say("n_runs", "repeats/tickets_rescored_v1/arm_w_v1") == 2,
            (say("n_runs", arm), say("n_runs", "repeats/tickets_rescored_v1/arm_w_v1")),
        )
    if project == "imported":
        bare = sum(
            1
            for (kind, key), v in cli.items()
            if kind == "reference" and "/meeting_clips_v1/" in key[0] and v == "none"
        )
        check("hand: imported: 64 arms on the big dataset, none with a reference", bare == 64, bare)


def dumper_checks(p: Project) -> None:
    """tools/facts_dump.py as a user runs it: one document, sorted keys, the same twice, each fact naming its command or
    saying why it is unavailable; `--diff` prints old -> new per fact and exits 0."""

    def dump(out: Path) -> subprocess.CompletedProcess:
        return subprocess.run(  # nosec B603 - this interpreter and the tool under test
            [sys.executable, str(HARNESS / "tools" / "facts_dump.py"), "--project", str(p.proj), "--evh", p.evh, "--out", str(out)],
            cwd=p.proj, env=p.env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600, check=False,
        )  # fmt: skip

    a, b = p.proj / "dump-a.json", p.proj / "dump-b.json"
    ra, rb = dump(a), dump(b)
    check(
        "facts_dump: runs, exit 0, twice",
        ra.returncode == 0 and rb.returncode == 0,
        (ra.stderr + rb.stderr)[-400:],
    )
    text_a = a.read_text()
    doc = json.loads(text_a)
    check("facts_dump: the same document twice (stable order)", text_a == b.read_text())
    check(
        "facts_dump: sorted keys",
        text_a == json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
    )
    check(
        "facts_dump: names its schema, evh version and the project's data format",
        doc.get("schema") == FD.SCHEMA
        and bool(doc.get("evh_version"))
        and isinstance(doc.get("data_format"), int),
        [doc.get(k) for k in ("schema", "evh_version", "data_format")],
    )
    leaves = list(FD.flat(doc["datasets"]))
    sourced = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            if ("value" in n or "unavailable" in n) and set(n) <= {"value", "from", "unavailable"}:
                sourced.append(("from" in n) != ("unavailable" in n))
            else:
                for v in n.values():
                    walk(v)

    walk(doc["datasets"])
    check(
        "facts_dump: every fact names the command it came from, or says why it is unavailable",
        bool(sourced) and all(sourced),
        len(leaves),
    )
    arm = next(iter(next(iter(doc["datasets"].values()))["arms"]))
    first = next(iter(doc["datasets"]))
    doc2 = json.loads(text_a)
    doc2["datasets"][first]["arms"][arm]["n_runs"]["value"] = 99
    doc2["evh_version"] = "9.9.9"
    c = p.proj / "dump-c.json"
    c.write_text(json.dumps(doc2))
    same = subprocess.run([sys.executable, str(HARNESS / "tools" / "facts_dump.py"), "--diff", str(a), str(b)], capture_output=True, text=True, check=False)  # fmt: skip # nosec B603
    diff = subprocess.run([sys.executable, str(HARNESS / "tools" / "facts_dump.py"), "--diff", str(a), str(c)], capture_output=True, text=True, check=False)  # fmt: skip # nosec B603
    check(
        "facts_dump --diff: a dump against itself says 0 changed and exits 0",
        same.returncode == 0 and " 0 changed" in same.stdout,
        same.stdout[-300:],
    )
    check(
        "facts_dump --diff: a changed fact is printed old -> new under its fact, and the exit is 0",
        diff.returncode == 0
        and "n_runs (1 changed)" in diff.stdout
        and f"{doc['datasets'][first]['arms'][arm]['n_runs']['value']!r} -> 99" in diff.stdout
        and "9.9.9" in diff.stdout,
        diff.stdout[-400:],
    )


def runs_list_states_no_value() -> None:
    """runs-list gives an arm's runs, not its value: the dump takes `value` from the readers that state one. Two runs of
    one arm with different item counts: a mean of the runs' means (0.75) is not the arm's item-pooled mean (arm-show)."""
    runs = [
        {"run_id": "a", "dataset_id": "d", "system_id": "s", "arm": "runs/d/s", "scores": {"m": 1.0}},
        {"run_id": "b", "dataset_id": "d", "system_id": "s", "arm": "runs/d/s", "scores": {"m": 0.5}},
    ]
    got = FD.from_runs_list({"runs": runs}, "")
    check(
        "facts_dump: runs-list states an arm's runs and no value of it (a mean of run means is no arm's mean)",
        any(f[0] == "runs" for f in got) and not any(f[0] == "value" for f in got),
        [f for f in got if f[0] == "value"],
    )


def thin(facts: dict[str, FactMap]) -> int:
    """How many facts two readers or more give: what the agreement was checked over."""
    n: dict[tuple, int] = {}
    for d in facts.values():
        for fk in d:
            n[fk] = n.get(fk, 0) + 1
    return sum(1 for v in n.values() if v > 1)


def main() -> int:
    t0 = time.time()
    print(f"store: {STORE}")
    names = list(BUILDERS)
    try:
        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            projects = dict(zip(names, pool.map(Project, names)))
        print(
            "built: "
            + ", ".join(f"{n} {SPENT[n]['build']:.0f}s" for n in names)
            + f" ({time.time() - t0:.0f}s)"
        )

        def one(name: str) -> tuple[dict[str, FactMap], dict[str, list[str]]]:
            return gather(projects[name])

        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            gathered = dict(zip(names, pool.map(one, names)))
        print(
            "read: "
            + "; ".join(
                f"{n} " + " ".join(f"{k} {v:.0f}s" for k, v in SPENT[n].items() if k != "build")
                for n in names
            )
            + f" ({time.time() - t0:.0f}s)"
        )
        per_project = {n: g[0] for n, g in gathered.items()}
        for name in names:
            facts, why = gathered[name]
            print(f"\n{name}: {len(facts)} readers, {thin(facts)} facts given by two readers or more")
            for r in sorted(why):
                print(f"    {r}: no answer for part: {why[r][0][:150]}")
            check(
                f"{name}: setup: the CLI saw the project's arms",
                any(k == "arms" for d in facts.values() for k, _ in d),
            )
            for kind in ("value", "direction", "runs", "n_runs", "reference", "cost_state", "latest"):
                n = len({r for r, d in facts.items() if any(k == kind for k, _ in d)})
                check(
                    f"{name}: coverage: {kind} is given by 2 readers or more, else the agreement means nothing",
                    n >= 2,
                    n,
                )
            assert_agreement(name, facts)
            arms_shown(name, facts, why)
            hand_checks(name, facts)
        dumper_checks(projects["tutorial"])
        runs_list_states_no_value()
        print("\nfact x reader (gives / -), over the five projects:")
        print("\n".join(matrix(per_project)))

        # ── it bites ────────────────────────────────────────────────────────────────────────────────────────────
        print("\nbites (a reader made to work a fact out itself; the check must fail and name it):")
        bites = [
            # (stub, project, the reader's surface, the facts that must differ)
            ("catalog-direction-by-name", "bakeoff", "catalog", {"direction"}),
            ("runs-keep-other-references", "tutorial", "cli", {"n_runs", "runs", "latest", "value"}),
        ]
        for stub, name, surface, facts_hit in bites:
            p = projects[name]
            facts = dict(per_project[name])
            t = time.time()
            if surface == "catalog":
                got = catalog_reader(p, stub)[0]
            else:
                evh = f"{sys.executable} {PROC} evh --stub {stub} --"
                got = prefixed("cli", cli_reader(p, evh, only={"leaderboard", "runs-list"}))[0]
            facts.update(got)
            hit = [
                d
                for d in compare(facts)
                if d["fact"] in facts_hit and not any(e[0] == name and matches(e, d) for e in KNOWN)
            ]
            readers = sorted({r for d in hit for r in d["readers"]})
            print(f"  {stub} on {name} ({time.time() - t:.0f}s): {explain(hit, 3)}")
            check(
                f"bites: {stub}: the check fails on {sorted(facts_hit)}, naming only {surface} readers",
                bool(hit) and all(r.startswith(f"{surface}:") for r in readers),
                readers or "no disagreement: the check did not notice",
            )
    finally:
        for d in PROJECTS:
            shutil.rmtree(d, ignore_errors=True)
    print(f"\nwhole test {time.time() - t0:.0f}s")
    return summary()


if __name__ == "__main__":
    sys.exit(main())
