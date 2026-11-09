#!/usr/bin/env python3
"""Prompt versions, and the code a system runs (RFC-028), $0 and offline.

    python tests/test_prompts.py

A config declares a prompt file and a prompt root; a run records each version once, gives the adapter the text and a
per-run copy of the root (removed after), and records the hashes under the fingerprint's settings. Editing the file
makes a second version; the same bytes reuse one; two arms that differ only in a prompt differ only in
`settings.prompts`; a config with no prompts keeps its fingerprint; eight runs recording the same new bytes make one
version; the run after a recorded version is not dirty. `code:` records a checkout's commit and changed files, its
path outside the hash. The commands list, diff, record and export versions; V24 catches a changed snapshot.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import _fingerprint  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-prompts-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-prompts")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)

# An adapter that answers with what it was given: the prompt's text and a file from the root's copy.
ECHO = """from pathlib import Path
from evaluation_harness.adapter import Result, score  # noqa: F401
def call_system(text, params):
    p = (params.get("prompts") or {}).get("summary/user") or {}
    root = params.get("prompt_root")
    side = Path(root, "sub", "b.txt").read_text().strip() if root else ""
    Path(".build").mkdir(exist_ok=True)
    Path(".build/seen_root.txt").write_text(str(root))
    out = p.get("text", "").strip() + " | " + side + " | " + text.split(".")[0] + "."
    Path(".build/seen_output.txt").write_text(out)
    return Result(output=out, cost_usd=0.0)
"""


def evh(*args):
    return subprocess.run([sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL)  # fmt: skip


def config(name, cid, extra=""):
    _runstore.write_text(
        proj,
        f"configs/{name}.yaml",
        f"config_id: {cid}\ndataset_id: tk_v1\nadapter: echo.py\n{extra}params:\n  provider: echo\n",
    )
    return f"data/configs/{name}.yaml"


def metrics_of(prefix):
    out = []
    for n in _runstore.listdir(proj, "runs"):
        if n.startswith(prefix) and _runstore.is_file(proj, f"runs/{n}/metrics.json"):
            out.append(_runstore.read_json(proj, f"runs/{n}/metrics.json"))
    return sorted(out, key=lambda m: m["run_id"])


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=False)


try:
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    (proj / "echo.py").write_text(ECHO)
    (proj / "prompts").mkdir()
    (proj / "prompts" / "user.txt").write_text("Summarise in one line.\n")
    root = proj / "lib_prompts"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("unvaried\n")
    (root / "sub" / "b.txt").write_text("system v1\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"\0")
    (proj / ".gitignore").write_text(".build/\n")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    check("setup: a dataset and an adapter that answers with its prompts", r.returncode == 0, r.stderr[-300:])

    declared = (
        "prompts:\n  summary/user: {file: prompts/user.txt}\n"
        "prompt_root:\n  name: lib\n  path: lib_prompts\n  vary: [sub/b.txt]\n"
    )
    c1 = config("p1", "p1_v1", declared)
    # The project committed as a person would before running: data/ tracked, so its new parts show one by one.
    git(proj, "init", "-q")
    git(proj, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(proj, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    r = evh("run", "--config", c1)
    m = metrics_of("p1_v1")
    fp = (m[-1].get("fingerprint") or {}) if m else {}
    s = fp.get("settings") or {}
    seen_out = proj / ".build" / "seen_output.txt"
    out_rows = seen_out.read_text() if seen_out.exists() else ""
    seen = proj / ".build" / "seen_root.txt"
    seen_root = seen.read_text() if seen.exists() else ""
    check(
        "a run records each declared prompt, gives the adapter the text and a copy of the root, removed after",
        r.returncode == 0
        and set(s.get("prompts") or {}) == {"summary/user", "lib/sub/b.txt"}
        and bool(s.get("prompt_root_sha256"))
        and "Summarise in one line. | system v1 |" in out_rows
        and ".build/prompt-roots/" in seen_root
        and not Path(seen_root).exists(),
        (r.returncode, r.stderr[-300:], s, out_rows[:200], seen_root),
    )
    v = evh("prompts", "--json")
    rows = (
        (json.loads(v.stdout).get("result") or {}).get("values", {}).get("prompts", [])
        if v.returncode == 0
        else []
    )
    check(
        "evh prompts: both names, one version each, the run that used them",
        sorted((x["name"], x["versions"], x["runs"]) for x in rows)
        == [("lib/sub/b.txt", 1, 1), ("summary/user", 1, 1)],
        (v.stdout[-300:], v.stderr[-300:]),
    )
    if not _runstore.sqlite():  # in SQLite every run changes the tracked database, prompts or not (RFC-025)
        status = git(proj, "status", "--porcelain").stdout
        check(
            "recording versions leaves the tree clean (data/prompts/ ignored as run output is)",
            "data/prompts/" in status and not _fingerprint.filter_dirt(status, "data/"),
            status,
        )

    # The same bytes reuse the version; an edit is a new one; the two runs differ only in that prompt.
    r = evh("run", "--config", c1)
    (proj / "prompts" / "user.txt").write_text("Summarise in one short line.\n")
    r2 = evh("run", "--config", c1)
    m = metrics_of("p1_v1")
    vers = evh("prompts", "summary/user", "--json")
    vs = (
        (json.loads(vers.stdout).get("result") or {}).get("values", {}).get("versions", [])
        if vers.returncode == 0
        else []
    )
    f1, f3 = (m[0].get("fingerprint") or {}), (m[-1].get("fingerprint") or {})
    parts_moved = [p for p in _fingerprint.PARTS if f1.get(f"{p}_sha256") != f3.get(f"{p}_sha256")]
    check(
        "the same bytes reuse a version; an edit makes the second; only the settings' hash moves",
        r.returncode == 0 and r2.returncode == 0 and len(vs) == 2 and parts_moved == ["settings"]
        and f1["settings"]["prompts"]["lib/sub/b.txt"] == f3["settings"]["prompts"]["lib/sub/b.txt"],
        (len(vs), parts_moved),
    )  # fmt: skip
    d = evh("prompt-diff", vs[0]["id"] if vs else "x", vs[-1]["id"] if vs else "y")
    check(
        "prompt-diff: the change as a unified diff, and each version's runs",
        d.returncode == 0
        and "-Summarise in one line." in d.stdout
        and "+Summarise in one short line." in d.stdout,
        d.stdout[-400:] + d.stderr[-200:],
    )

    # A config with no prompts keeps its fingerprint as it was (no new key).
    plain = config("plain", "plain_v1")
    r = evh("run", "--config", plain)
    pm = metrics_of("plain_v1")
    check(
        "a config with no prompts and no code: neither key in its fingerprint",
        r.returncode == 0 and pm and "prompts" not in pm[-1]["fingerprint"]["settings"]
        and "code" not in pm[-1]["fingerprint"]["deployment"],
        r.stderr[-200:],
    )  # fmt: skip

    # Eight runs recording the same new bytes at once: one version.
    (proj / "prompts" / "user.txt").write_text("A third wording.\n")
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda _: evh("run", "--config", c1).returncode, range(8)))
    vers = evh("prompts", "summary/user", "--json")
    vs = (
        (json.loads(vers.stdout).get("result") or {}).get("values", {}).get("versions", [])
        if vers.returncode == 0
        else []
    )
    check(
        "eight runs at once on new bytes: all succeed, one version recorded",
        codes == [0] * 8 and len(vs) == 3,
        (codes, len(vs)),
    )

    # code: a checkout's commit and changed files; its path is provenance.
    sysrepo = proj / "system"
    sysrepo.mkdir()
    (sysrepo / "app.py").write_text("x = 1\n")
    git(sysrepo, "init", "-q")
    git(sysrepo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(sysrepo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "one")
    c2 = config("code", "code_v1", "code: {path: system}\n")
    r = evh("run", "--config", c2)
    (sysrepo / "app.py").write_text("x = 2\n")
    r2 = evh("run", "--config", c2)
    git(sysrepo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "two")
    r3 = evh("run", "--config", c2)
    cm = metrics_of("code_v1")
    codes3 = [(x["fingerprint"]["deployment"].get("code") or {}) for x in cm]
    check(
        "code: the commit and changed files recorded; a new commit moves deployment.code.commit",
        r.returncode == r2.returncode == r3.returncode == 0 and len(codes3) == 3
        and codes3[0]["dirty"] == [] and codes3[1]["dirty"] == ["app.py"]
        and codes3[0]["commit"] == codes3[1]["commit"] != codes3[2]["commit"],
        codes3,
    )  # fmt: skip
    same = dict(cm[-1]["fingerprint"])
    moved = json.loads(json.dumps(same))
    moved["deployment"]["code"]["path"] = "/elsewhere/system"
    check(
        "the checkout's path is outside the hash: two clones of one commit are one system",
        _fingerprint.seal(json.loads(json.dumps(same)))["deployment_sha256"]
        == _fingerprint.seal(moved)["deployment_sha256"],
    )

    # prompt-version with a parent; export; V24.
    vid = vs[-1]["id"] if vs else "x"
    pv = evh(
        "prompt-version",
        "summary/user",
        "--text",
        "A fourth wording.\n",
        "--parent",
        vid,
        "--note",
        "shorter",
    )
    vers = evh("prompts", "summary/user", "--json")
    vs = (
        (json.loads(vers.stdout).get("result") or {}).get("values", {}).get("versions", [])
        if vers.returncode == 0
        else []
    )
    check(
        "prompt-version records a version with its parent and note; the same bytes again are named, not doubled",
        pv.returncode == 0 and len(vs) == 4 and vs[-1]["parent"] == vid and vs[-1]["note"] == "shorter"
        and "already recorded" in evh("prompt-version", "summary/user", "--text", "A fourth wording.\n", "--note", "x").stdout,
        (pv.stdout[-300:], pv.stderr[-300:]),
    )  # fmt: skip
    ex = evh("prompt-export", vs[-1]["id"] if vs else "x", "--to", "exported.txt")
    bad = evh("prompt-export", vid, "--to", str(proj / "venv/lib/site-packages/p.txt"))
    check(
        "prompt-export writes the bytes; a path inside an installed package is refused",
        ex.returncode == 0 and (proj / "exported.txt").read_text() == "A fourth wording.\n"
        and bad.returncode != 0 and "installed package" in bad.stderr,
        (ex.stderr[-200:], bad.stderr[-200:]),
    )  # fmt: skip
    # The catalog's prompts page: names and versions always; the text only when the project publishes it.
    r = evh("catalog")
    page = (proj / ".build" / "catalog" / "prompts.html").read_text() if r.returncode == 0 else ""
    (proj / "config.yaml").write_text("catalog: {publish: [prompts]}\n")
    r2 = evh("catalog")
    page2 = (proj / ".build" / "catalog" / "prompts.html").read_text() if r2.returncode == 0 else ""
    (proj / "config.yaml").unlink()
    check(
        "the prompts page: names and versions; the text and diffs only with catalog: {publish: [prompts]}",
        "summary/user" in page and "lib/sub/b.txt" in page and "A third wording" not in page
        and "A third wording" in page2 and "the change from v1" in page2,
        (r.stderr[-200:], r2.stderr[-200:]),
    )  # fmt: skip
    ok = evh("validate")
    name, sha16 = vs[0]["id"].rsplit("/", 1) if vs else ("x", "y")
    _runstore.write_text(proj, f"prompts/{name}/{sha16}.txt", "tampered\n")
    tampered = evh("validate")
    check(
        "V24: passes on recorded versions, fails on a changed snapshot",
        "ok   V24" in ok.stdout and "FAIL V24" in tampered.stdout and "do not hash" in tampered.stdout,
        (next((x for x in ok.stdout.splitlines() if "V24" in x), ""), tampered.stdout[-500:]),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
