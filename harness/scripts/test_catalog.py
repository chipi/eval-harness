#!/usr/bin/env python3
"""Assertions for the catalog and the run inspector (catalog_build.py, catalog_serve.py).

    python scripts/test_catalog.py

On a small data tree written here: the build, that no item text reaches the static pages, the
inspector's numbers against pair-test's, its refusals (mixed datasets, unknown arms), and the
server's rules (127.0.0.1 Host only, only the catalog and the data tree, no dot-folders).
"""
import json
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


def run(runs_dir, run_id, dataset, config, scores, text=SECRET, kinds=None):
    d = data / runs_dir / run_id
    (d / "outputs").mkdir(parents=True)
    (d / "metrics.json").write_text(json.dumps({
        "run_id": run_id, "dataset_id": dataset, "config_id": config, "primary_metric": "acc",
        "metric_kinds": kinds or {"acc": "quality", "words": "descriptive"},
        "fingerprint": {"data": {"reference_id": f"gold/{dataset}"}}}))
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

    # the command line: evh catalog builds into the project
    env_root = tmp / "proj"
    shutil.copytree(data, env_root / "data")
    r = subprocess.run([sys.executable, str(HERE / "cli.py"), "catalog"], cwd=env_root, capture_output=True, text=True,
                       env={"EVAL_HOME": str(env_root), "PATH": "/usr/bin:/bin"})
    check("evh catalog: builds into <project>/.build/catalog", r.returncode == 0 and (env_root / ".build/catalog/index.html").is_file(),
          r.stderr[-300:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

bad = [lb for lb, c in ok if not c]
print(f"\n{len(ok) - len(bad)}/{len(ok)} assertions passed")
if bad:
    print("FAILED:", *bad, sep="\n  ")
    sys.exit(1)
