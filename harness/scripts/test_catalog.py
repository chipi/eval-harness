#!/usr/bin/env python3
"""Assertions for the catalog and the run inspector (catalog_build.py, catalog_serve.py).

    python scripts/test_catalog.py

On a small data tree written here: the build, that no item text reaches the static pages, the
inspector's numbers against pair-test's, its refusals (mixed datasets, unknown arms), and the
server's rules (127.0.0.1 Host only, only the catalog and the data tree, no dot-folders).
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import catalog_build as cb  # noqa: E402
import catalog_serve as cs  # noqa: E402
import stats  # noqa: E402
from catalog_adapter import HarnessAdapter  # noqa: E402

ok = []


def check(label, cond, detail=""):
    ok.append((label, bool(cond)))
    print(f"  {'ok  ' if cond else 'FAIL'} {label}" + (f"  ({detail})" if detail and not cond else ""))


SECRET = "zebra-quokka-unique-output-text"
tmp = Path(tempfile.mkdtemp(prefix="evh-catalog-"))
data = tmp / "data"


def run(runs_dir, run_id, dataset, config, scores, text=SECRET, kinds=None, ref=None, root=None):
    d = (root or data) / runs_dir / run_id
    (d / "outputs").mkdir(parents=True)
    (d / "metrics.json").write_text(json.dumps({
        "run_id": run_id, "dataset_id": dataset, "config_id": config, "primary_metric": "acc",
        "metric_kinds": kinds or {"acc": "quality", "words": "descriptive"},
        "fingerprint": {"data": {"reference_id": ref or f"gold/{dataset}"}}}))
    rows = []
    for i, s in enumerate(scores):
        rows.append(json.dumps({"item_id": f"i{i:02d}", "acc": s, "words": 10.0 + i}))
        (d / "outputs" / f"i{i:02d}.txt").write_text(f"{text} {config} {i}")
    (d / "predictions.jsonl").write_text("\n".join(rows) + "\n")


try:
    base = [0.5] * 12
    run("runs", "a_1", "ds1", "arm_a", base)
    run("runs", "b_1", "ds1", "arm_b", [0.6] * 10 + [0.5, 0.4])
    run("runs", "b_2", "ds1", "arm_b", [0.8] * 10 + [0.5, 0.4])  # a repeat: averaged per item
    run("runs", "c_1", "ds2", "arm_c", base)
    (data / "references" / "gold" / "ds1").mkdir(parents=True)
    (data / "references" / "gold" / "ds1" / "i00.txt").write_text(SECRET + " reference")
    (data / "runs" / ".hidden").mkdir()
    (data / "runs" / ".hidden" / "x.txt").write_text("hidden")

    A = HarnessAdapter(data)
    arms = sorted(A.arms())
    check("arms: one per config per dataset, repeats folded", arms == [
        "runs/ds1/arm_a", "runs/ds1/arm_b", "runs/ds2/arm_c"], arms)
    vals = A.scores("runs/ds1/arm_b")["acc"]["values"]
    check("scores: repeats averaged per item, as pair-test does", abs(vals["i00"] - 0.7) < 1e-12)
    check("descriptive metric kinds are neutral", A.is_neutral("words") and not A.is_neutral("acc"))

    out = tmp / ".build" / "catalog"
    counts = cb.build(A, out)
    check("build: datasets, arms and references counted", counts == {"goals": 0, "datasets": 2, "arms": 3, "references": 1}, counts)
    pages = {p.relative_to(out).as_posix() for p in out.rglob("*.html")}
    check("build: home, a page per dataset, the inspector", {"index.html", "d/ds1.html", "d/ds2.html", "inspect.html"} <= pages, pages)
    leaked = [p.name for p in out.rglob("*") if p.is_file() and SECRET in p.read_text(encoding="utf-8", errors="ignore")]
    check("build: no item text in any static file", not leaked, leaked)
    page_ds1 = (out / "d/ds1.html").read_text()
    check("build: one inspector link for all the dataset's arms, best first",
          "inspect.html?runs=runs/ds1/arm_b,runs/ds1/arm_a" in page_ds1)

    cs.set_adapter(A)
    r = cs.compare({"runs": ["runs/ds1/arm_a,runs/ds1/arm_b"], "baseline": ["runs/ds1/arm_a"]})
    check("compare: default metric is the primary one, never the descriptive one", r.get("metric") == "acc", r.get("metric"))
    row = r["rows"][0]
    deltas = [vals[i] - 0.5 for i in sorted(vals)]
    check("compare: p is stats.sign_flip_p on the per-item deltas", row["p"] == stats.sign_flip_p(deltas))
    check("compare: verdict and direction", row["verdict"] == "separated: better" and row["wins"] == 10)
    check("compare: shape metrics feed the scatter", "words" in r["shape"])
    bad = cs.compare({"runs": ["runs/ds1/arm_a,runs/ds2/arm_c"]})
    check("compare: refuses arms on different datasets", "different datasets" in bad.get("error", ""), bad)
    check("compare: refuses an unknown arm", "no arm known" in cs.compare({"runs": ["runs/nope"]}).get("error", ""))
    check("compare: a run directory selects its arm", A.arms_of("runs/b_2") == ["runs/ds1/arm_b"])
    it = cs.item({"arms": ["runs/ds1/arm_a,runs/ds1/arm_b"], "item": ["i00"], "ref": ["gold/ds1"]})
    check("item: each arm's output, the latest repeat", it["views"]["runs/ds1/arm_b"]["text"] == f"{SECRET} arm_b 0")
    check("item: the reference's text", it["reference"]["view"]["text"] == SECRET + " reference")
    check("item: refuses an unknown arm", "error" in cs.item({"arms": ["../etc"], "item": ["i00"]}))

    # the server's document root is the project root: serve this temp tree as one
    cs.ROOT = tmp
    prefixes = cs.served(out, data)
    check("served: the catalog and the data tree, nothing else", prefixes == ("/.build/catalog/", "/data/"), prefixes)
    cs.Handler.prefixes = prefixes
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(tmp)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def get(path, host=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": host or f"127.0.0.1:{port}"})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, ""

    st, body = get("/api/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b")
    check("http: /api/compare answers", st == 200 and json.loads(body)["metric"] == "acc", st)
    check("http: the catalog is served", get("/.build/catalog/index.html")[0] == 200)
    check("http: the data tree is served", get("/data/runs/a_1/metrics.json")[0] == 200)
    check("http: a foreign Host is refused (DNS rebinding)", get("/.build/catalog/index.html", "evil.example")[0] == 403)
    check("http: nothing outside the two trees", get("/scripts/catalog_serve.py")[0] == 404)
    check("http: no dot-folder inside them", get("/data/runs/.hidden/x.txt")[0] == 404)
    check("http: no climbing out", get("/data/../secret")[0] == 404)
    srv.shutdown()

    # PUBLIC mode: the API only, to the named host, rate-limited, arms capped, answers cached
    cs.LIMITS.update(hosts=("catalog.example.org",), rate=5, max_arms=2)
    cs.Handler.prefixes = ()
    cs._CACHE.clear(); cs._HITS.clear()
    pub = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(tmp)))
    port = pub.server_address[1]
    threading.Thread(target=pub.serve_forever, daemon=True).start()
    H = "catalog.example.org"
    check("public: answers the named host", get("/api/health", H)[0] == 200)
    check("public: refuses any other host, localhost included", get("/api/health")[0] == 403)
    check("public: serves no files, catalog or data", get("/.build/catalog/index.html", H)[0] == 404
          and get("/data/runs/a_1/metrics.json", H)[0] == 404)
    st, body = get("/api/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b", H)
    check("public: compares", st == 200 and json.loads(body)["metric"] == "acc", st)
    st, body = get("/api/compare?runs=runs/ds1/arm_a,runs/ds1/arm_b,runs/ds2/arm_c", H)
    capped = next((v for k, v in cs._CACHE.items() if "arm_c" in k), (0, {}))
    check("public: at most --max-arms arms in one comparison", st == 400 and "at most 2" in capped[1].get("error", ""), (st, capped))
    key = next(k for k in cs._CACHE if "arm_b" in k)
    check("public: an answer is cached by its exact question", cs._CACHE[key][0] == 200)
    codes = [get("/api/health", H)[0] for _ in range(2)] + [get("/api/item?arms=runs/ds1/arm_a&item=i00", H)[0] for _ in range(4)]
    check("public: a client over --rate requests a minute gets 429", 429 in codes, codes)
    pub.shutdown()
    cs.LIMITS.update(hosts=(), rate=0, max_arms=40)
    cs._CACHE.clear(); cs._HITS.clear()

    # Item fields (ADR-0003): a public choice field and a hidden text field on ds1.
    HIDDEN = "walrus-hidden-customer-name"
    (data / "fields").mkdir()
    (data / "fields" / "fs.yaml").write_text(
        "fieldset_id: fs\nfields:\n"
        "  - {name: product, type: choice, values: [x, y], public: true}\n"
        "  - {name: size, type: number}\n"
        f"  - {{name: customer, type: text}}\n")
    (data / "datasets").mkdir()
    (data / "datasets" / "ds1.json").write_text(json.dumps({
        "dataset_id": "ds1", "version": "1.0", "created_at": "x", "fieldset": "fs",
        "items": [{"item_id": f"i{k:02d}", "source_sha256": "0" * 64,
                   "fields": {"product": "x" if k < 6 else "y", "size": k, "customer": HIDDEN}}
                  for k in range(12)]}))
    AF = HarnessAdapter(data)
    cs.set_adapter(AF)
    out_f = tmp / ".build" / "catalog-fields"
    cb.build(AF, out_f)
    page_f = (out_f / "d/ds1.html").read_text()
    check("fields: the dataset page lists the declared fields and their coverage",
          "item fields" in page_f and "product" in page_f and "customer" in page_f and "12 of 12" in page_f)
    check("fields: a public field's values are summarised", "x <b>6</b>" in page_f and "y <b>6</b>" in page_f)
    ids = re.findall(r'\bid="([^"]+)"', page_f)
    check("fields: every element id on the page is unique", len(ids) == len(set(ids)),
          sorted(i for i in set(ids) if ids.count(i) > 1))
    leaked = [p.name for p in out_f.rglob("*") if p.is_file() and HIDDEN in p.read_text(encoding="utf-8", errors="ignore")]
    check("fields: a field not marked public shows no value on any static page",
          not leaked and page_f.count("not public") == 2 and "0 – 11" not in page_f and "distinct" not in page_f,
          leaked or page_f.count("not public"))
    two = ["runs/ds1/arm_a,runs/ds1/arm_b"]
    r = cs.compare({"runs": two, "baseline": ["runs/ds1/arm_a"], "where": ["product:x"]})
    check("fields: a filter compares only the matching items", r.get("rows") and r["rows"][0]["n"] == 6
          and any("Filtered to the 6" in w for w in r["warnings"]), r.get("error") or r.get("rows"))
    r = cs.compare({"runs": two, "baseline": ["runs/ds1/arm_a"], "where": ["size:..2"]})
    check("fields: a number filter takes a range", r.get("rows") and r["rows"][0]["n"] == 3, r.get("error"))
    check("fields: filtering by an undeclared field is refused",
          "error" in cs.compare({"runs": two, "where": ["colour:red"]}))
    r = cs.compare({"runs": two, "baseline": ["runs/ds1/arm_a"], "by": ["product"]})
    bd = r.get("breakdown") or {}
    joint = {(g["group"], x["arm"]): x["p"] for g in bd.get("groups", []) for x in g["rows"] if x["p"] is not None}
    check("fields: a breakdown tests each group, Holm over all of them together",
          [g["group"] for g in bd.get("groups", [])] == ["x", "y"] and bd.get("family_size") == len(joint) == 2
          and all(x["threshold"] == stats.holm(joint)[(g["group"], x["arm"])][0]
                  for g in bd["groups"] for x in g["rows"] if x["p"] is not None), r.get("error") or bd)
    check("fields: a breakdown by a number field is refused", "error" in cs.compare({"runs": two, "by": ["size"]}))
    it = cs.item({"arms": two, "item": ["i00"]})
    got = {f["name"]: f["value"] for f in it.get("fields", [])}
    check("fields: the local inspector shows every field of an item", got == {"product": "x", "size": 0, "customer": HIDDEN}, got)
    cs.LIMITS.update(hosts=("catalog.example.org",))
    it = cs.item({"arms": two, "item": ["i00"]})
    r = cs.compare({"runs": two})
    check("fields: a public deployment shows only public fields",
          {f["name"] for f in it.get("fields", [])} == {"product"} and [f["name"] for f in r.get("fields", [])] == ["product"])
    check("fields: a public deployment refuses a filter on a hidden field",
          "error" in cs.compare({"runs": two, "where": [f"customer:{HIDDEN}"]}))
    cs.LIMITS.update(hosts=())
    cs.set_adapter(A)

    # One reference per comparison: an arm scored against silver and one scored against gold
    # (runs/ and a rescored copy, say) both record `acc`, but the numbers measure different
    # things, so the inspector must not pair them on it. Output length needs no reference.
    data2 = tmp / "data2"
    run("runs", "g_1", "ds1", "arm_g", [0.5] * 12, root=data2)
    run("runs-silver", "s_1", "ds1", "arm_s", [0.9] * 12, ref="silver/ds1", root=data2)
    cs.set_adapter(HarnessAdapter(data2))
    mixed = cs.compare({"runs": ["runs/ds1/arm_g,runs-silver/ds1/arm_s"], "baseline": ["runs/ds1/arm_g"]})
    check("compare: an arm scored against another reference is not tested against the baseline",
          mixed.get("metric") == "acc" and "runs-silver/ds1/arm_s" not in mixed.get("series", {})
          and not mixed.get("rows"), list(mixed.get("series", {})))
    check("compare: ...and the answer names it and its reference",
          any("silver/ds1" in w and "arm_s" in w for w in mixed.get("warnings", []))
          and not any("on record" in w for w in mixed.get("warnings", [])), mixed.get("warnings"))
    words = cs.compare({"runs": ["runs/ds1/arm_g,runs-silver/ds1/arm_s"], "baseline": ["runs/ds1/arm_g"],
                        "metric": ["words"]})
    check("compare: a metric that needs no reference compares them anyway",
          "runs-silver/ds1/arm_s" in words.get("series", {}) and len(words.get("rows", [])) == 1, words.get("warnings"))
    # The dataset page offers one "inspect together" link per group the inspector can test as
    # a whole: same metric, same reference. One link over all four would mix gold and silver.
    run("runs", "g_2", "ds1", "arm_h", [0.6] * 12, root=data2)
    run("runs-silver", "s_2", "ds1", "arm_t", [0.8] * 12, ref="silver/ds1", root=data2)
    out2 = tmp / "out2"
    cb.build(HarnessAdapter(data2), out2)
    page2 = (out2 / "d" / "ds1.html").read_text(encoding="utf-8")
    together = re.findall(r'inspect\.html\?runs=([^"&]+)&metric=acc">Inspect the 2 arms on acc, scored against ([^<]+)<',
                          page2)
    check("build: one 'inspect together' link per reference, none mixing them",
          sorted(ref for _, ref in together) == ["gold/ds1", "silver/ds1"]
          and all(("runs-silver" in runs) == (ref == "silver/ds1") and runs.count(",") == 1
                  for runs, ref in together), together)

    # No primary metric on record (the bundled adapter declares none): the default yardstick
    # fell to the name order, so a fresh project's inspector opened on cost_usd. A score is the
    # yardstick; the bill and the clock only when nothing else was recorded.
    data3 = tmp / "data3"
    for arm, accs in (("arm_p", [0.5] * 8), ("arm_q", [0.7] * 8)):
        d = data3 / "runs" / f"{arm}_1"
        (d / "outputs").mkdir(parents=True)
        (d / "metrics.json").write_text(json.dumps({"run_id": f"{arm}_1", "dataset_id": "ds1", "config_id": arm,
                                                    "fingerprint": {"data": {"reference_id": "gold/ds1"}}}))
        (d / "predictions.jsonl").write_text("".join(
            json.dumps({"item_id": f"i{i}", "overlap_f1": v, "cost_usd": 0.0, "latency_ms": 1.0 + i}) + "\n"
            for i, v in enumerate(accs)))
    cs.set_adapter(HarnessAdapter(data3))
    plain = cs.compare({"runs": ["runs/ds1/arm_p,runs/ds1/arm_q"], "baseline": ["runs/ds1/arm_p"]})
    check("compare: with no primary metric on record, a score is the default, never cost or latency",
          plain.get("metric") == "overlap_f1", plain.get("metric"))
    cs.set_adapter(A)

    # the command line: evh catalog builds into the project
    env_root = tmp / "proj"
    shutil.copytree(data, env_root / "data")
    r = subprocess.run([sys.executable, str(HERE / "cli.py"), "catalog"], cwd=env_root, capture_output=True, text=True,
                       env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"})
    check("evh catalog: builds into <project>/.build/catalog", r.returncode == 0 and (env_root / ".build/catalog/index.html").is_file(),
          r.stderr[-300:])

    # a port another program holds: say so, never a traceback
    import socket
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        busy = held.getsockname()[1]
        r = subprocess.run([sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(busy)], cwd=env_root,
                           capture_output=True, text=True, timeout=60,
                           env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"})
    check("evh catalog-serve: a port in use is named, with --port as the way out",
          r.returncode != 0 and f"port {busy} is in use" in r.stderr and "--port" in r.stderr
          and "Traceback" not in r.stderr, r.stderr[-300:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

bad = [lb for lb, c in ok if not c]
print(f"\n{len(ok) - len(bad)}/{len(ok)} assertions passed")
if bad:
    print("FAILED:", *bad, sep="\n  ")
    sys.exit(1)
