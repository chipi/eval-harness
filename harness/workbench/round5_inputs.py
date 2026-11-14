"""The Workbench mockup's round-5 inputs: the harness's own answers for what this project does not hold yet (a held-out
side and its reads, a study, prompt versions, a job, a replay with its faithfulness and periods, outcome labels joined
from another system), each made in a throwaway project under build/round5/ from the tutorial's tickets or the replay
example, by the commands a person would run. Nothing is invented: each JSON file is a command's own `--json` answer.

    python workbench/round5_inputs.py            (from harness/; writes build/round5/*.json; about two minutes)

mock_data.py reads them into the mockup's `round5` key, beside this project's own baselines (`evh baselines`).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

H = Path(__file__).resolve().parents[1]
OUT = H / "build" / "round5"
CLI = H / "scripts" / "cli.py"
KIT = H / "tutorial"
EXAMPLE = H.parent / "examples" / "replay-filing"
WORDS = [
    "login",
    "invoice",
    "export",
    "api",
    "delete",
    "mobile",
    "cache",
    "queue",
    "retry",
    "token",
    "audit",
    "backup",
]


def project(name: str) -> tuple[Path, dict]:
    p = OUT / "projects" / name
    shutil.rmtree(p, ignore_errors=True)
    (p / "data" / "configs").mkdir(parents=True)
    env = dict(os.environ, EVAL_HOME=str(p), EVH_ACTOR="person:owner", EVAL_BUILD_REF="workbench-round5")
    env["PYTHONPATH"] = str(H) + os.pathsep + env.get("PYTHONPATH", "")
    for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_STORE"):
        env.pop(k, None)
    subprocess.run(["git", "init", "-q"], cwd=p, check=True)
    return p, env


def evh(p: Path, env: dict, *args: str, ok: tuple = (0,)) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, str(CLI), *args], cwd=p, env=env, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)  # fmt: skip
    if r.returncode not in ok:
        raise SystemExit(
            f"evh {' '.join(args)} exited {r.returncode}:\n{r.stdout[-800:]}\n{r.stderr[-1500:]}"
        )
    return r


def save(name: str, r: subprocess.CompletedProcess) -> dict:
    """A command's --json envelope, saved as build/round5/<name>.json; its result returned."""
    doc = json.loads(r.stdout)
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return doc.get("result") or {}


def commit(p: Path, msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=p, check=True)
    subprocess.run(["git", "-c", "user.name=owner", "-c", "user.email=o@example.com", "commit", "-q", "-m", msg],
                   cwd=p, check=True)  # fmt: skip


def config(p: Path, cid: str, ds: str, sentences: int, extra: str = "") -> None:
    (p / "data" / "configs" / f"{cid}.yaml").write_text(
        f"config_id: {cid}\ndataset_id: {ds}\ngoal: g\nparams:\n  provider: echo\n  sentences: {sentences}\n{extra}"
    )


def this_project() -> None:
    env = dict(os.environ, EVAL_HOME=str(H))
    for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_STORE"):
        env.pop(k, None)
    save("baselines", evh(H, env, "baselines", "--json"))


def tickets() -> None:
    """A goal with validation and test sets, a grid study and its confirmation (one look), prompt versions, a job,
    and a sealed side: its counts, its reads, the leak check and a paired score that leaves the read items out."""
    p, env = project("tickets")
    kinds = ["bug", "question", "bug", "access", "bug", "question"]
    for side, rng in (("val", range(12)), ("test", range(12, 24))):
        src, gold = p / f"src_{side}", p / f"gold_{side}"
        src.mkdir()
        gold.mkdir()
        for i in rng:
            s = [
                f"Ticket{i} " + " ".join(WORDS[(i + j * 3 + w) % len(WORDS)] for w in range(5)) + "."
                for j in range(4)
            ]
            (src / f"t{i:02d}.txt").write_text(" ".join(s) + "\n")
            (gold / f"t{i:02d}.txt").write_text(" ".join(s[:2]) + "\n")
    for ds, side in (("tk_val", "val"), ("tk_test", "test")):
        evh(p, env, "dataset-create", "--dataset-id", ds, "--source-dir", f"src_{side}")
        evh(p, env, "dataset-materialize", "--dataset-id", ds)
        evh(p, env, "label-import", f"gold_{side}", "--dataset-id", ds, "--set", "g", "--by", "person:owner")
        evh(p, env, "reference-promote", "--dataset-id", ds, "--labels", "g", "--tier", "gold",
            "--reason", "the first two sentences of each ticket", "--by", "person:owner")  # fmt: skip
    (p / "data" / "goals").mkdir()
    (p / "data" / "goals" / "g.yaml").write_text(
        "goal_id: g\ntitle: Ticket summaries\nstatement: A ticket's summary keeps what support needs\n"
        "decision: which summariser support uses\nsuccess_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tk_val, role: validation}\n  - {dataset_id: tk_test, role: test}\n"
    )
    config(p, "one_v1", "tk_val", 1)
    evh(p, env, "run", "--config", "data/configs/one_v1.yaml")
    spec = p / "study.yaml"
    spec.write_text(
        "dataset: tk_val\nbaseline: {config: one_v1}\nmeasure: overlap_f1\nsampler: grid\n"
        "accept: {point: {min_gain: 0}}\nstop: {trials: 5}\n"
        "space:\n  groups:\n    - {name: length, reason: how much of a ticket to keep, params: {sentences: [2, 3, 4]}}\n"
    )
    evh(p, env, "study-run", "g/s1", "--spec", str(spec))
    save("study", evh(p, env, "studies", "--study", "g/s1", "--json"))
    save("studies", evh(p, env, "studies", "--json"))
    save(
        "study_confirm",
        evh(p, env, "study-confirm", "g/s1", "--test", "tk_test", "--rule", "superiority", "--json"),
    )
    save("looks", evh(p, env, "looks", "--dataset", "tk_test", "--json"))
    save("baseline_history", evh(p, env, "baselines", "--goal", "g", "--all-versions", "--json"))
    # prompt versions: the CNN example's own prompt, recorded
    prompt = H.parent / "examples" / "summarization-cnn-dailymail" / "prompt.txt"
    evh(p, env, "prompt-version", "cnn_summary", "--from-file", str(prompt), "--note", "the example's prompt")
    save("prompts", evh(p, env, "prompts", "--json"))
    # a real job, with its cap
    save("job_start", evh(p, env, "jobs-start", "run", "--arg", "config=one_v1", "--max-cost-usd", "1",
                          "--json"))  # fmt: skip
    for _ in range(120):
        st = json.loads(evh(p, env, "jobs-status", "--json").stdout)
        jobs = ((st.get("result") or {}).get("values") or {}).get("jobs") or []
        if jobs and all(j.get("state") not in ("queued", "running") for j in jobs):
            break
        subprocess.run(["sleep", "0.5"], check=True)
    save("jobs", evh(p, env, "jobs-status", "--json"))
    # a sealed held-out side, from the tutorial's tickets with a kind and an alert id
    shutil.copytree(KIT / "tickets", p / "tutorial_tickets")
    (p / "data" / "fields").mkdir(exist_ok=True)
    (p / "data" / "fields" / "t.yaml").write_text(
        "fieldset_id: t\nfields:\n  - name: opened\n    type: date\n    required: true\n"
        "  - name: kind\n    type: choice\n    values: [bug, question, access]\n  - name: alert\n    type: text\n"
    )
    names = sorted(x.stem for x in (p / "tutorial_tickets").glob("*.txt"))
    dates = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-08", "2026-11-09", "2026-11-10"]
    (p / "f.csv").write_text("item_id,opened,kind,alert\n" + "".join(
        f"{n},{d},{k},ALERT-{i}\n" for i, (n, d, k) in enumerate(zip(names, dates, kinds))))  # fmt: skip
    evh(p, env, "dataset-create", "--dataset-id", "sup_v1", "--source-dir", "tutorial_tickets", "--fieldset", "t",
        "--fields", "f.csv")  # fmt: skip
    evh(p, env, "dataset-split", "sup_v1", "--split-by", "time", "--key", "opened", "--at", "2026-11-02T00:00:00Z",
        "--seal", "--count-by", "kind")  # fmt: skip
    evh(p, env, "dataset-materialize", "--dataset-id", "sup_v1_test")
    save("sealed_counts", evh(p, env, "sealed-counts", "--dataset-id", "sup_v1_test", "--json"))
    evh(p, env, "exposure-add", "--dataset-id", "sup_v1_test", "--item", names[1], "--what", "decision and reason",
        "--read-by", "agent:homelab", "--at", "2026-11-11T09:00:00Z")  # fmt: skip
    pub = OUT / "projects" / "tickets-public"
    shutil.rmtree(pub, ignore_errors=True)
    pub.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=pub, check=True)
    (pub / "plan.md").write_text("we read ALERT-4 while fixing the gate\n")
    commit(pub, "a plan that names a held-out alert")
    (p / "config.yaml").write_text(f"exposure:\n  public_repos: [{pub}]\n  ids: [alert]\n")
    save("exposure_check", evh(p, env, "exposure-check", "--dataset-id", "sup_v1_test", "--out", "leaks.tsv", "--json",
                               ok=(0, 6)))  # fmt: skip
    evh(p, env, "exposure-add", "--dataset-id", "sup_v1_test", "--from", "leaks.tsv")
    save("exposure", evh(p, env, "exposure", "--dataset-id", "sup_v1_test", "--json"))
    hyp2 = (
        "hypothesis:\n  against: sup_base_v1\n  measure: overlap_f1\n"
        "  direction: better\n  statement: two sentences keep what support needs\n"
    )
    for cid, n, hyp in (("sup_base_v1", 1, ""), ("sup_cand_v1", 2, hyp2)):
        (p / "data" / "configs" / f"{cid}.yaml").write_text(
            f"config_id: {cid}\ndataset_id: sup_v1_test\nparams:\n  provider: echo\n  sentences: {n}\n{hyp}")  # fmt: skip
    commit(p, "the candidate and its hypothesis, before the held-out side is read")
    save("unseal", evh(p, env, "dataset-unseal", "sup_v1_test", "--config", "sup_cand_v1",
                       "--reason", "the two-sentence candidate, frozen before the side is read", "--json"))  # fmt: skip
    gold = p / "gold_sup"
    gold.mkdir()
    for f in (KIT / "gold").iterdir():
        if f.stem in names[1:]:
            shutil.copy(f, gold / f.name)
    evh(
        p,
        env,
        "label-import",
        "gold_sup",
        "--dataset-id",
        "sup_v1_test",
        "--set",
        "g",
        "--by",
        "person:owner",
    )
    evh(p, env, "reference-promote", "--dataset-id", "sup_v1_test", "--labels", "g", "--tier", "gold",
        "--reason", "the kit's summaries, for the held-out side", "--by", "person:owner")  # fmt: skip
    for cid in ("sup_cand_v1", "sup_base_v1"):
        evh(p, env, "run", "--config", f"data/configs/{cid}.yaml")
    save("heldout_pair", evh(p, env, "pair-test", "--dataset-id", "sup_v1_test", "--a", "sup_cand_v1", "--b",
                             "sup_base_v1", "--metric", "overlap_f1", "--include-exposed", "--json", ok=(0, 6)))  # fmt: skip


def replay() -> None:
    """The replay example: production, the replay and its faithfulness, writes hidden and the confound, periods."""
    p, env = project("replay")
    mine = p / "examples" / "replay-filing"
    shutil.copytree(EXAMPLE, mine, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.run([sys.executable, str(mine / "make_history.py"), "--out", "replay-filing"], cwd=p, env=env,
                   check=True, capture_output=True)  # fmt: skip
    evh(p, env, "capture", "--importer", "jsonl", "--query", json.dumps({"path": "replay-filing/rows.jsonl"}),
        "--capture", "filing_prod")  # fmt: skip
    evh(p, env, "dataset-from-capture", "filing_prod", "--dataset-id", "filing_history_v1", "--fieldset", "filing",
        "--field", "ts", "--field", "started", "--field", "production_issue")  # fmt: skip
    evh(p, env, "dataset-materialize", "--dataset-id", "filing_history_v1")
    evh(p, env, "label-import", "replay-filing/gold", "--dataset-id", "filing_history_v1", "--set", "gold",
        "--by", "person:owner")  # fmt: skip
    evh(p, env, "reference-promote", "--dataset-id", "filing_history_v1", "--labels", "gold", "--tier", "gold",
        "--reason", "what each decision should have done", "--by", "person:owner")  # fmt: skip
    prod = json.loads(
        evh(p, env, "run", "--config", "data/configs/filing_production_v1.yaml", "--json").stdout
    )
    prod_id = prod["result"]["values"]["runs"][0]["run_id"]
    save("faithfulness", evh(p, env, "faithfulness", "--config", "data/configs/filing_replay_hidden_v1.yaml",
                             "--production", prod_id, "--json"))  # fmt: skip
    hid = json.loads(
        evh(p, env, "run", "--config", "data/configs/filing_replay_hidden_v1.yaml", "--json").stdout
    )
    hid_id = hid["result"]["values"]["runs"][0]["run_id"]
    cand = json.loads(
        evh(p, env, "run", "--config", "data/configs/filing_candidate_v3_hidden.yaml", "--json").stdout
    )
    cand_id = cand["result"]["values"]["runs"][0]["run_id"]
    (OUT / "replay_runs.json").write_text(json.dumps({
        "production": prod_id, "replay": hid_id, "candidate": cand_id,
        "replay_metrics": json.loads((p / "data" / "runs" / hid_id / "metrics.json").read_text()),
        "candidate_metrics": json.loads((p / "data" / "runs" / cand_id / "metrics.json").read_text()),
    }, indent=1) + "\n")  # fmt: skip
    save("periods", evh(p, env, "periods", "--model", "toy_filing", "--config", "data/configs/filing_replay_hidden_v1.yaml",
                        "--json"))  # fmt: skip
    for n in (1, 2, 3):
        save(f"period_compare_{n}", evh(p, env, "period-compare", "--config", "data/configs/filing_replay_hidden_v1.yaml",
                                        "--candidate", "filing_candidate_v3_hidden", "--production", "filing_production_v1",
                                        "--period", str(n), "--metric", "exact", "--json"))  # fmt: skip
    save("models_code", evh(p, env, "models", "--json"))


def outcomes() -> None:
    """Decisions joined to the issues they filed, by fingerprint and a window: coverage, a relabel, the mutants."""
    p, env = project("outcomes")
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    day, minute = dt.timedelta(days=1), dt.timedelta(minutes=1)
    shutil.copytree(KIT / "tickets", p / "tickets")
    evh(p, env, "dataset-create", "--dataset-id", "decisions_v1", "--source-dir", "tickets")
    items = sorted(x.stem for x in (p / "tickets").glob("*.txt"))
    t = [now - 30 * day, now - 3 * day, now - 30 * day, now - 30 * day, now - 30 * day, now - 20 * day]

    def iso(x):
        return x.isoformat().replace("+00:00", "Z")

    decisions = [{"id": items[i], "created_at": iso(t[i]), "fp": f"fp{i}", "first_seen": f"s{i}",
                  "action": "file" if i == 0 else "dismiss", "body": "x"} for i in range(6)]  # fmt: skip
    issues = [
        {"id": "is0", "created_at": iso(t[0] + 5 * minute), "fp": "fp0", "first_seen": "s0", "state_reason": "completed",
         "closed_at": iso(t[0] + 2 * day)},
        {"id": "is2", "created_at": iso(t[2] + 120 * minute), "fp": "fp2", "first_seen": "s2", "state_reason": "completed",
         "closed_at": iso(t[2] + day)},
        {"id": "is4", "created_at": iso(t[4] + minute), "fp": "fp4", "first_seen": "another", "state_reason": "completed",
         "closed_at": iso(t[4] + day)},
    ]  # fmt: skip
    for name, rows in (("decisions", decisions), ("issues", issues)):
        (p / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        evh(
            p,
            env,
            "capture",
            "--importer",
            "jsonl",
            "--query",
            json.dumps({"path": f"{name}.jsonl"}),
            "--capture",
            name,
        )
    (p / "rules.yaml").write_text(
        "- {when: {issue.state_reason: completed}, date: issue.closed_at, under: action, label: file}\n"
        "- {when: {issue.count: 0}, min_age_days: 14, label: dismiss}\n"
    )
    join = ["--outcomes", "issues", "--outcomes-as", "issue", "--join", "fp=fp", "--within", "-1m,+15m",
            "--identity", "first_seen=first_seen"]  # fmt: skip
    base = ["--dataset-id", "decisions_v1", "--capture", "decisions", "--map", "rules.yaml"]
    save("label_coverage", evh(p, env, "label-coverage", *base, *join, "--json"))
    save("label_set", evh(p, env, "label-from-capture", *base, "--set", "outcomes_1", *join, "--action-field", "action",
                          "--json"))  # fmt: skip
    save("label_mutants", evh(p, env, "label-mutants", *base, *join, "--json", ok=(0, 6)))
    doc = json.loads((p / "data" / "labels" / "decisions_v1" / "outcomes_1" / "labels.json").read_text())
    (OUT / "label_set_doc.json").write_text(json.dumps(doc, indent=1) + "\n")


if __name__ == "__main__":
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    this_project()
    tickets()
    replay()
    outcomes()
    print(f"wrote {len(list(OUT.glob('*.json')))} file(s) to {OUT}")
