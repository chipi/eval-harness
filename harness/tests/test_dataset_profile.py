#!/usr/bin/env python3
"""Assertions for dataset profiles: `evh dataset-profile`, `evh dataset-items`, the dataset page's
"what's inside", V1 over data/profiles/.

    python tests/test_dataset_profile.py

In a throwaway project ($0, offline): three small datasets whose gold is labels, JSON lists and
free text; a rows map gives one of them a link per item. The profile counts items and words,
reads the gold's shape, links each item; `--with-text` refuses text git does not track and adds
text it does; the page shows the section, a profile of another version is marked stale, and a
dataset without a profile says how to write one.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-profile-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-profile")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def dataset(ds: str, texts: dict[str, str], gold: dict[str, str]) -> None:
    src = proj / "src" / ds
    src.mkdir(parents=True)
    for k, t in texts.items():
        (src / f"{k}.txt").write_text(t, encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", ds, "--source-dir", f"src/{ds}")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", ds)
    check(f"setup: {ds} is created and materialized", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    g = proj / "data" / "references" / "gold" / ds
    g.mkdir(parents=True)
    for k, t in gold.items():
        (g / f"{k}.txt").write_text(t, encoding="utf-8")


def items_of(ds: str) -> list[dict]:
    return json.loads((proj / "data" / "datasets" / f"{ds}.json").read_text())["items"]


def item_ids(ds: str) -> list[str]:
    return [it["item_id"] for it in items_of(ds)]


try:
    (proj / "data").mkdir()
    dataset(
        "topics",
        {
            "a": "the market fell today",
            "b": "the team won",
            "c": "a new chip ships",
            "d": "rates rose again",
            "e": "a faster laptop",
            "f": "the cup final",
        },
        {"a": "Business", "b": "Sports", "c": "Sci/Tech", "d": "Business", "e": "Sci/Tech", "f": "Sports"},
    )
    # A short answer per item, none repeated: the items' gold, never listed as labels.
    dataset(
        "answers",
        {"a": "capital of France", "b": "two plus two", "c": "largest ocean"},
        {"a": "Paris", "b": "four", "c": "Pacific"},
    )
    dataset(
        "ents",
        {"a": "Ada met Alan in London", "b": "nothing here"},
        {"a": '[{"text":"Ada","type":"person"},{"text":"London","type":"location"}]', "b": "[]"},
    )
    long_ref = " ".join(["word"] * 12)
    dataset("notes", {"a": "one two three", "b": "four five"}, {"a": long_ref, "b": long_ref + " more"})
    ids = item_ids("topics")
    (proj / "data" / "sources").mkdir(parents=True, exist_ok=True)
    (proj / "data" / "sources" / "topics.rows.json").write_text(
        json.dumps(
            {
                "source": {"name": "acme/news", "url": "https://example.org/acme/news"},
                "item_url": "https://example.org/acme/news?row={row}",
                # keyed by id, matched by the item's bytes: ents and notes reuse the ids a and b
                "rows": {
                    it["item_id"]: {"row": i, "sha256": it["source_sha256"]}
                    for i, it in enumerate(items_of("topics"))
                },
            }
        )
    )

    r = evh("dataset-profile", "--dataset-id", "topics")
    p = json.loads((proj / "data" / "profiles" / "topics.json").read_text()) if r.returncode == 0 else {}
    check("profile: written for a materialized dataset", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    check(
        "profile: counts the items and their words",
        p.get("items", {}).get("n") == 6 and p["items"]["words"]["max"] == 4,
    )
    gold = (p.get("references") or [{}])[0]
    check(
        "profile: a gold of few short values reads as labels, with their counts",
        gold.get("shape") == "labels" and gold.get("labels") == {"Business": 2, "Sci/Tech": 2, "Sports": 2},
        json.dumps(gold),
    )
    check(
        "profile: each item links to its row from the rows map, and the source is named",
        p.get("source", {}).get("name") == "acme/news"
        and all(
            r_["source_url"] == f"https://example.org/acme/news?row={ids.index(r_['item_id'])}"
            for r_ in p["rows"]
        ),
    )
    evh("dataset-profile", "--dataset-id", "answers")
    pa = (proj / "data" / "profiles" / "answers.json").read_text()
    check(
        "profile: short answers that do not repeat are summarised, never listed per item",
        json.loads(pa)["references"][0]["shape"] == "text" and "Paris" not in pa and "Pacific" not in pa,
        pa[:300],
    )
    check("profile: no text unless asked for", not any("text" in r_ for r_ in p.get("rows", [])))

    evh("dataset-profile", "--dataset-id", "ents")
    pe = json.loads((proj / "data" / "profiles" / "ents.json").read_text())
    check(
        "profile: a JSON-list gold reads as entries per item",
        pe["references"][0]["shape"] == "lists" and pe["references"][0]["entries"]["max"] == 2,
        json.dumps(pe["references"]),
    )
    check("profile: an item with no source has no link", not any("source_url" in r_ for r_ in pe["rows"]))
    evh("dataset-profile", "--dataset-id", "notes")
    pn = json.loads((proj / "data" / "profiles" / "notes.json").read_text())
    check(
        "profile: a gold of longer text reads as words per reference", pn["references"][0]["shape"] == "text"
    )

    r = evh("dataset-profile", "--dataset-id", "topics", "--with-text")
    check(
        "--with-text: refused when git does not track the items' source files",
        r.returncode != 0 and "tracked by git" in r.stderr,
        (r.stdout + r.stderr)[-300:],
    )
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    r = evh("dataset-profile", "--dataset-id", "topics", "--with-text")
    check(
        "--with-text: refused in a git checkout that does not track the files",
        r.returncode != 0,
        r.stdout[-200:],
    )
    subprocess.run(["git", "add", "src/topics"], cwd=proj, check=True)
    r = evh("dataset-profile", "--dataset-id", "topics", "--with-text")
    check(
        "--with-text: refused while the files are only staged, not committed",
        r.returncode != 0,
        r.stdout[-200:],
    )
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "commit", "-qm", "items"], cwd=proj, check=True)
    r = evh("dataset-profile", "--dataset-id", "topics", "--with-text")
    pt = json.loads((proj / "data" / "profiles" / "topics.json").read_text())
    check(
        "--with-text: adds each item's text once git tracks it",
        r.returncode == 0 and all(r_.get("text") for r_ in pt["rows"]),
        (r.stdout + r.stderr)[-300:],
    )
    evh("dataset-profile", "--dataset-id", "topics")

    r = evh("dataset-items", "--dataset-id", "topics")
    check(
        "dataset-items: prints the shape and a row per item",
        r.returncode == 0
        and "6 items" in r.stdout
        and "Business 2" in r.stdout
        and r.stdout.count("example.org") >= 6,
        r.stdout[-400:],
    )
    r = evh("dataset-items", "--dataset-id", "topics", "--item", ids[0][:10])
    check(
        "dataset-items --item: one item, with its text when it is materialized here",
        r.returncode == 0
        and any(t in r.stdout for t in ("the market fell", "the team won", "a new chip", "rates rose")),
        r.stdout[-300:],
    )
    r = evh("dataset-items", "--dataset-id", "nothing")
    check(
        "dataset-items: no profile is refused, saying how to write one",
        r.returncode != 0 and "dataset-profile" in r.stderr,
    )

    r = evh("validate")
    v1 = next((ln for ln in r.stdout.splitlines() if " V1 " in ln), "")
    check("V1: the profiles match profile.schema.json", "ok" in v1, v1 or r.stdout[-300:])

    # A profile of another version of the items: the page says it is stale.
    prof = proj / "data" / "profiles" / "notes.json"
    doc = json.loads(prof.read_text())
    doc["items_sha256"] = "0" * 64
    prof.write_text(json.dumps(doc))
    (proj / "data" / "profiles" / "ents.json").unlink()
    out = proj / "catalog"
    r = evh("catalog", "--out", str(out))
    check("catalog: builds", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    page = (out / "d" / "topics.html").read_text() if (out / "d" / "topics.html").is_file() else ""
    check(
        "page: what's inside, with the item count, the labels, a link per item and the source",
        "what&#x27;s inside" in page
        and "6 items" in page
        and "Sci/Tech" in page
        and page.count("source ↗") == 6
        and "acme/news" in page,
    )
    check(
        "page: no inline style attribute (the deployment's CSP)",
        ' style="' not in page.split("what&#x27;s inside")[1],
    )
    notes = (out / "d" / "notes.html").read_text() if (out / "d" / "notes.html").is_file() else ""
    check("page: a profile of another version is marked stale", "items changed since this profile" in notes)
    ents = (out / "d" / "ents.html").read_text() if (out / "d" / "ents.html").is_file() else ""
    check(
        "page: without a profile, it says how to write one",
        "No profile yet" in ents and "dataset-profile" in ents,
    )

    # Every page names the read command that answers it; with --mcp, the same as a tool call.
    import html as _html
    import re

    from evaluation_harness.mcp_server import READ_TOOLS

    term = re.compile(r"<span data-elsewhere=term>(.*?)</span>")
    lines = {
        f.relative_to(out).as_posix(): [
            _html.unescape(c) for c in re.findall(r"<code>(.*?)</code>", m.group(1))
        ]
        for f in sorted(out.rglob("*.html"))
        for m in [term.search(f.read_text())]
        if m
    }
    check(
        "every page: names its command in the footer (the home, the lists, each dataset)",
        {"index.html", "datasets.html", "d/topics.html", "inspect.html"} <= set(lines),
        sorted(lines),
    )
    bad = []
    for where, cmds in lines.items():
        for c in cmds:
            words = c.split()
            if words[:1] != ["evh"] or words[1] not in READ_TOOLS:
                bad.append((where, c, "not a read tool"))
            elif where != "inspect.html":  # the inspector's is filled in from the arms picked
                r = evh(*words[1:])
                if r.returncode != 0:
                    bad.append((where, c, r.stderr[-120:]))
    check("every page: its command is a read tool, and runs as named", not bad, bad[:5])
    check(
        "without --mcp: no tool call is named", "data-elsewhere=mcp" not in (out / "index.html").read_text()
    )
    r = evh("catalog", "--out", str(out), "--mcp", "https://evals.example.test/mcp")
    d = (out / "d" / "topics.html").read_text()
    check(
        "--mcp: each page names its tool call, the server and how to connect",
        r.returncode == 0
        and "From an agent: the tool" in d
        and "<code>datasets</code> with <code>{&quot;dataset-id&quot;: &quot;topics&quot;}</code>" in d
        and "https://evals.example.test/mcp" in d
        and "how to connect" in d,
        d.split("<footer>")[-1][:600],
    )
    r = evh("catalog", "--out", str(out), "--mcp", "javascript:alert(1)")
    check("--mcp: only an http(s) address", r.returncode != 0, r.stderr[-120:])
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
