#!/usr/bin/env python3
"""Rerun any experiment in this repository and see whether its findings hold.

    python examples/reproduce.py plan     scifact [--level local|hosted|baselines|all]
    python examples/reproduce.py data     scifact
    python examples/reproduce.py run      scifact  --level local [--arms bm25,e5_base]
    python examples/reproduce.py compare  scifact

(or `make plan|data|reproduce|compare EXP=scifact` from the repository root.)

plan     what a rerun involves before anything is spent: every arm, what it cost and how
         long it took when it was measured, what is installed, which data is present and
         which route a hosted arm would take. Free, offline.
data     the example's environment (`uv sync`), its public data (`fetch.py`), and the
         hash check against the committed dataset files (`make dataset-materialize`).
run      reruns the chosen arms into harness/data/runs-repro/<experiment>/ -- gitignored,
         never beside the committed runs, which stay the record. A hosted arm's spend is
         capped at twice what it was billed when measured (EVAL_MAX_COST_USD per run).
compare  a replication card: each rerun arm against its committed run on the same items,
         and every committed separation and tie re-tested with your reruns substituted
         in. Written to harness/data/runs-repro/<experiment>/REPLICATION.md.

What counts as reproduced is different for the two kinds of arm, and the card says which
applies. A local model with pinned weights should give the same answers, so its card
reports exact item agreement. A hosted model is not deterministic even at temperature 0,
and can be updated or retired upstream, so its digits are not expected to match: what
must hold is the VERDICT -- which arms are separated from which. The committed
predictions remain the record either way.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HARNESS = ROOT / "harness"
DATA = HARNESS / "data"
REPRO = DATA / "runs-repro"
sys.path.insert(0, str(HERE / "_shared"))
sys.path.insert(0, str(HARNESS))  # the evaluation_harness package (a link to scripts/)

#: Arms that are not models -- floors that check the scorer. Free and deterministic.
BASELINES = {"lead3", "keyword", "constant", "capitalized", "nothing", "random", "first_k", "length"}
HOSTED_PROVIDERS = {"litellm", "rerank"}


def registry() -> dict:
    return {e["slug"]: e for e in json.loads((HERE / "experiments.json").read_text())["experiments"]}


def _load_dotenv() -> None:
    """harness/.env, read by the harness's own loader -- an exported variable always wins."""
    from evaluation_harness._common import load_dotenv  # noqa: PLC0415 - harness/ is on sys.path above

    load_dotenv(HARNESS / ".env")


# ── what was measured ───────────────────────────────────────────────────────────────────
def committed(exp: dict) -> dict:
    """{arm: {cid, dir, score, kind, cost, minutes, model}} from the committed record."""
    out = {}
    for f in sorted((DATA / exp["base"]).glob(f"{exp['prefix']}*/metrics.json")):
        m = json.loads(f.read_text())
        cid = m.get("config_id", "")
        if m.get("dataset_id") != exp["dataset"] or not cid.endswith(exp["suffix"]):
            continue
        arm = cid[len(exp["prefix"]) : -len(exp["suffix"])]
        params = m.get("params") or {}
        kind = (
            "baseline"
            if arm in BASELINES
            else "hosted"
            if params.get("provider") in HOSTED_PROVIDERS
            else "local"
        )
        out[arm] = {
            "cid": cid,
            "dir": f.parent,
            "score": m["scores"][exp["metric"]],
            "kind": kind,
            "model": params.get("model"),
            "n": m.get("n_items"),
        }
    # Cost and time come from data/runs, where the provider's response was recorded.
    table = json.loads((HERE / "local_models.json").read_text())
    pins, safe = table["revisions"], table.get("safetensors", {})
    for _arm, a in out.items():
        a["cost"], a["minutes"] = 0.0, None
        # A rerun loads the safetensors conversion where one was verified to give identical
        # outputs, so it never unpickles a checkpoint; otherwise the revision that was measured.
        a["safetensors"] = a["kind"] == "local" and a["model"] in safe
        a["revision"] = (
            (safe[a["model"]]["revision"] if a["safetensors"] else pins.get(a["model"]))
            if a["kind"] == "local"
            else None
        )
        for f in (DATA / "runs").glob(f"{a['cid']}_*/metrics.json"):
            m = json.loads(f.read_text())
            if m.get("dataset_id") != exp["dataset"]:
                continue
            pj = f.parent / "predictions.jsonl"
            rows = [json.loads(x) for x in pj.read_text().splitlines() if x.strip()] if pj.is_file() else []
            a["cost"] = sum(float(((r.get("_meta") or {}).get("usage") or {}).get("cost") or 0) for r in rows)
            lat = (m.get("scores") or {}).get("latency_ms")
            if lat is not None:
                a["minutes"] = (lat * (m.get("n_items") or 0) + (m.get("warmup_ms") or 0)) / 60000
    return out


def configs(exp: dict) -> dict:
    """{config_id: path} for the example's configs."""
    out = {}
    for p in sorted((HERE / exp["example"] / "configs").glob("*.yaml")):
        cfg = yaml.safe_load(p.read_text()) or {}
        if cfg.get("config_id"):
            out[cfg["config_id"]] = p
    return out


def select(arms: dict, level: str, only: str | None) -> list:
    if only:
        names = [a.strip() for a in only.split(",") if a.strip()]
        unknown = [a for a in names if a not in arms]
        if unknown:
            raise SystemExit(
                f"not a measured arm of this experiment: {', '.join(unknown)}\n"
                f"arms: {', '.join(sorted(arms))}"
            )
        return names
    kinds = {
        "local": {"local", "baseline"},
        "hosted": {"hosted"},
        "baselines": {"baseline"},
        "all": {"local", "baseline", "hosted"},
    }[level]
    return sorted(a for a, v in arms.items() if v["kind"] in kinds)


def _venv_python(exp: dict) -> Path:
    return HERE / exp["example"] / ".venv" / "bin" / "python"


def _route() -> str:
    import gateway  # noqa: PLC0415

    try:
        r = gateway.route({"model": next(iter(gateway.models()))})
        return "proxy " + r["endpoint"] if r["mode"] == "proxy" else "OpenRouter, directly"
    except SystemExit:
        return ""


# ── plan ────────────────────────────────────────────────────────────────────────────────
def plan(exp: dict, level: str, only: str | None) -> int:
    _load_dotenv()
    arms = committed(exp)
    chosen = select(arms, level, only)
    print(
        f"\n{exp['bench']} · {exp['dataset']} · metric {exp['metric']} · "
        f"{len(arms)} measured arms, committed record: harness/data/{exp['base']}/\n"
    )
    print(f"  {'arm':16s} {'kind':9s} {'committed':>10s} {'billed':>9s} {'time':>9s}")
    for a in sorted(chosen, key=lambda a: (arms[a]["kind"], a)):
        v = arms[a]
        m = v["minutes"]
        t = "?" if m is None else "<1 min" if m < 1 else f"{m:.0f} min"
        print(f"  {a:16s} {v['kind']:9s} {v['score']:10.4f} {'${:.3f}'.format(v['cost']):>9s} {t:>9s}")
    cost = sum(arms[a]["cost"] for a in chosen)
    mins = sum(arms[a]["minutes"] or 0 for a in chosen)
    print(
        f"\n  {len(chosen)} arm(s): billed ${cost:.2f} when measured; about {mins / 60:.1f} h of "
        "compute on the machine that measured them\n  (local timings depend on the machine that measured them; "
        "hosted timings are mostly waiting on the provider)"
    )

    venv = _venv_python(exp)
    have = {d: (DATA / "materialized" / d).is_dir() for d in exp["datasets"]}
    needs_hosted = any(arms[a]["kind"] == "hosted" for a in chosen)
    route = _route()
    print("\n  ready?")
    print(f"    environment   {'yes' if venv.is_file() else 'no  -> make data EXP=' + exp['slug']}")
    for d, ok in have.items():
        print(f"    data {d:14s} {'yes, hash-checked' if ok else 'no  -> make data EXP=' + exp['slug']}")
    if needs_hosted:
        print(f"    hosted route  {route or 'NONE -> put OPENROUTER_API_KEY in harness/.env'}")
    if exp.get("note"):
        print(f"\n  note: {exp['note']}")
    if exp["slug"] == "summarization-dailymail":
        print(
            "\n  note: only the five local arms were measured on this slice; the hosted arms"
            " were not, so there is nothing to compare them against"
        )
    print(
        f"\n  then:  make reproduce EXP={exp['slug']} LEVEL={level}"
        + (f" ARMS={only}" if only else "")
        + f"\n         make compare EXP={exp['slug']}\n"
    )
    return 0


# ── data ────────────────────────────────────────────────────────────────────────────────
def data(exp: dict, light: bool = False) -> int:
    ex = HERE / exp["example"]
    if not shutil.which("uv"):
        raise SystemExit(
            "uv is not installed: https://docs.astral.sh/uv/ "
            "(curl -LsSf https://astral.sh/uv/install.sh | sh)"
        )
    # --light: the base environment only -- hosted arms, BM25 and the baselines, no
    # PyTorch. What CI uses; a full rerun of the local models needs the extras.
    sync = ["uv", "sync"] + ([] if light else [f"--extra={x}" for x in exp.get("extras", [])])
    _run(sync, cwd=ex)
    for args in exp["fetch"]:
        _run(["uv", "run", "fetch.py", *args], cwd=ex)
    for d in exp["datasets"]:
        _run([str(_venv_python(exp)), "scripts/materialize.py", "--dataset-id", d], cwd=HARNESS)
    print(f"\ndata for {exp['slug']} fetched and hash-checked against the committed dataset files")
    return 0


def _run(cmd: list, cwd: Path, env: dict | None = None) -> None:
    print("  $", " ".join(cmd), f"   (in {cwd.relative_to(ROOT)})", flush=True)
    r = subprocess.run(cmd, cwd=cwd, env=env)
    if r.returncode != 0:
        raise SystemExit(f"failed ({r.returncode}): {' '.join(cmd)}")


# ── run ─────────────────────────────────────────────────────────────────────────────────
def run(exp: dict, level: str, only: str | None, extra: str | None = None) -> int:
    _load_dotenv()
    arms = committed(exp)
    chosen = [] if extra and not only else select(arms, level, only)
    cfgs = configs(exp)
    venv = _venv_python(exp)
    if not venv.is_file():
        raise SystemExit(f"no environment for {exp['slug']} yet: make data EXP={exp['slug']}")
    missing = [d for d in exp["datasets"] if not (DATA / "materialized" / d).is_dir()]
    if missing:
        raise SystemExit(f"data not fetched ({', '.join(missing)}): make data EXP={exp['slug']}")
    if any(arms[a]["kind"] == "hosted" for a in chosen) and not _route():
        raise SystemExit(
            "hosted arms selected but no route: put OPENROUTER_API_KEY in "
            "harness/.env (see docs/REPRODUCE.md)"
        )
    out = REPRO / exp["slug"]
    out.mkdir(parents=True, exist_ok=True)
    for a in chosen:
        cid = arms[a]["cid"]
        if cid not in cfgs:
            raise SystemExit(f"no config with config_id {cid} under {exp['example']}/configs")
        env = {**os.environ, "EVAL_RUNS_DIR": str(out)}
        if arms[a]["kind"] == "hosted":
            # Twice what it was billed, never less than five cents: room for a dearer
            # provider route, not for a runaway loop.
            env["EVAL_MAX_COST_USD"] = f"{max(0.05, 2 * arms[a]['cost']):.2f}"
        print(f"\n── {a} ({arms[a]['kind']})", flush=True)
        _run(
            [str(venv), "scripts/experiment_run.py", "--config", str(_pinned(cfgs[cid], arms[a], out))],
            cwd=HARNESS,
            env=env,
        )
    if extra:
        _run_new_arm(exp, arms, Path(extra).resolve(), venv, out)
    print(f"\nreruns are in {out.relative_to(ROOT)}/   next: make compare EXP={exp['slug']}")
    return 0


def _pinned(cfg_path: Path, arm: dict, out: Path) -> Path:
    """The config, pinned to the weights the committed run loaded.

    The example configs name a model, not a revision, so a fresh machine downloads whatever
    Hugging Face serves today -- which may not be what was measured. Every committed local
    run recorded the snapshot it loaded, so the rerun asks for exactly that one. Written to
    a copy beside the reruns; the committed config is the record and is not edited.
    """
    if not arm.get("revision"):
        return cfg_path
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["adapter"] = str((cfg_path.parent / cfg.get("adapter", "")).resolve())
    cfg.setdefault("params", {})["revision"] = arm["revision"]
    pinned = out / "configs" / cfg_path.name
    pinned.parent.mkdir(parents=True, exist_ok=True)
    what = (
        "the verified safetensors conversion of the committed run's weights"
        if arm.get("safetensors")
        else "the committed run's weights"
    )
    pinned.write_text(
        f"# {cfg_path.relative_to(ROOT)}, pinned to {what}\n" + yaml.safe_dump(cfg, sort_keys=False)
    )
    print(
        f"  weights pinned to {arm['revision'][:12]}"
        + (
            " (the verified safetensors conversion of the committed weights)"
            if arm.get("safetensors")
            else " (the committed revision)"
        )
    )
    return pinned


def _run_new_arm(exp: dict, arms: dict, path: Path, venv: Path, out: Path) -> None:
    """Your own arm, measured on the same items and scored by the same code."""
    if not path.is_file():
        raise SystemExit(f"no config at {path}")
    cfg = yaml.safe_load(path.read_text()) or {}
    cid, ds = cfg.get("config_id", ""), cfg.get("dataset_id")
    if ds != exp["dataset"]:
        raise SystemExit(f"{path.name}: dataset_id must be {exp['dataset']} (got {ds})")
    if not (cid.startswith(exp["prefix"]) and cid.endswith(exp["suffix"])):
        raise SystemExit(
            f"{path.name}: config_id must look like "
            f"{exp['prefix']}<name>{exp['suffix']} to join the comparison (got {cid})"
        )
    if cid in {a["cid"] for a in arms.values()}:
        raise SystemExit(f"{cid} is a committed arm; give yours a new name")
    env = {**os.environ, "EVAL_RUNS_DIR": str(out)}
    if not env.get("EVAL_MAX_COST_USD"):
        env["EVAL_MAX_COST_USD"] = "1.00"
        print("  EVAL_MAX_COST_USD not set -- capping this arm at $1.00")
    print(f"\n── {cid[len(exp['prefix']) : -len(exp['suffix'])]} (yours)", flush=True)
    _run([str(venv), "scripts/experiment_run.py", "--config", str(path)], cwd=HARNESS, env=env)


# ── compare ─────────────────────────────────────────────────────────────────────────────
def _items(run_dir: Path, metric: str) -> dict:
    out = {}
    for line in (run_dir / "predictions.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if metric in r:
                out[r["item_id"]] = float(r[metric])
    return out


def _latest_repro(exp: dict) -> dict:
    """{arm: run_dir} -- the newest rerun of each measured arm."""
    out: dict = {}
    for f in sorted((REPRO / exp["slug"]).glob(f"{exp['prefix']}*/metrics.json")):
        m = json.loads(f.read_text())
        cid = m.get("config_id", "")
        if m.get("dataset_id") == exp["dataset"] and cid.endswith(exp["suffix"]):
            arm = cid[len(exp["prefix"]) : -len(exp["suffix"])]
            if arm not in out or m.get("created_at", "") >= out[arm][1]:
                out[arm] = (f.parent, m.get("created_at", ""))
    return {a: d for a, (d, _) in out.items()}


def _paired_p(a: list, b: list, perms: int = 10000, seed: int = 20261014) -> float:
    """The harness's paired sign-flip p (stats.sign_flip_p) on the per-item differences."""
    from evaluation_harness.stats import sign_flip_p  # noqa: PLC0415 - harness/ is on sys.path above

    return sign_flip_p([x - y for x, y in zip(a, b)], permutations=perms, seed=seed)


def _family(exp: dict, runs_dir: Path, arm: str | None = None) -> tuple[list, list]:
    """(not separated, separated) opponents of `arm` (the leader by default), Holm-corrected."""
    a_cid = f"{exp['prefix']}{arm or exp['leader']}{exp['suffix']}"
    r = subprocess.run(
        [
            sys.executable,
            str(HARNESS / "scripts" / "family_test.py"),
            "--dataset-id",
            exp["dataset"],
            "--a",
            a_cid,
            "--against",
            exp["suffix"],
            "--metric",
            exp["metric"],
            "--runs-dir",
            str(runs_dir),
        ],
        capture_output=True,
        text=True,
        cwd=HARNESS,
    )
    if r.returncode != 0:
        raise SystemExit(f"family test failed:\n{r.stderr[-800:]}")
    tied, sep = [], []
    for ln in r.stdout.splitlines():
        parts = ln.split()
        if parts and parts[0].endswith(exp["suffix"]) and parts[0] != a_cid:
            arm = parts[0][len(exp["prefix"]) : -len(exp["suffix"])]
            (tied if ln.strip().endswith("--") else sep).append(arm)
    return tied, sep


def compare(exp: dict) -> int:
    arms = committed(exp)
    reruns = _latest_repro(exp)
    if not reruns:
        raise SystemExit(
            f"no reruns yet under {(REPRO / exp['slug']).relative_to(ROOT)}: make reproduce EXP={exp['slug']}"
        )
    lines = [
        f"# Replication card · {exp['bench']}",
        "",
        (
            f"Dataset `{exp['dataset']}`, metric `{exp['metric']}`. Committed record: "
            f"`harness/data/{exp['base']}/`. Reruns: `harness/data/runs-repro/{exp['slug']}/`."
        ),
        "",
        "| arm | kind | committed | rerun | Δ | identical items | paired p | upstream | status |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    statuses = {}
    for a in sorted(reruns):
        if a not in arms:
            continue
        c = _items(arms[a]["dir"], exp["metric"])
        r = _items(reruns[a], exp["metric"])
        common = sorted(set(c) & set(r))
        if not common:
            continue
        ca, ra = [c[i] for i in common], [r[i] for i in common]
        same = sum(abs(x - y) < 1e-9 for x, y in zip(ca, ra))
        p = _paired_p(ca, ra)
        m_new = json.loads((reruns[a] / "metrics.json").read_text())
        m_old = json.loads((arms[a]["dir"] / "metrics.json").read_text())
        up_new, up_old = (_upstream(x) for x in (m_new, m_old))
        upstream = (
            "—"
            if arms[a]["kind"] != "hosted"
            else ("same" if up_new == up_old else f"`{up_old}` → `{up_new}`")
        )
        if len(common) < len(c):
            status = f"PARTIAL ({len(common)}/{len(c)} items)"
        elif same == len(common):
            status = "exact"
        elif p >= 0.05:
            status = "consistent" if arms[a]["kind"] == "hosted" else "within noise, not exact"
        else:
            status = "DIFFERS"
        statuses[a] = status
        lines.append(
            f"| `{a}` | {arms[a]['kind']} | {st.fmean(ca):.4f} | {st.fmean(ra):.4f} | "
            f"{st.fmean(ra) - st.fmean(ca):+.4f} | {same}/{len(common)} | {p:.3f} | "
            f"{upstream} | {status} |"
        )

    # VERDICTS. Substitute every rerun for its committed run and re-test the leader against
    # the same family: the committed findings are statements about separations, so that is
    # what a replication has to check.
    with tempfile.TemporaryDirectory() as tmp:
        merged = Path(tmp)
        for a, v in arms.items():
            src = reruns.get(a, v["dir"])
            (merged / src.name).symlink_to(src.resolve(), target_is_directory=True)
        tied_c, sep_c = _family(exp, DATA / exp["base"])
        tied_m, sep_m = _family(exp, merged)
        new = sorted(a for a in reruns if a not in arms)
        placed = {}
        if new:
            # Each new arm against the committed field only -- one family per new arm.
            for a in new:
                with tempfile.TemporaryDirectory() as tmp2:
                    field = Path(tmp2)
                    for _b, v in arms.items():
                        (field / v["dir"].name).symlink_to(v["dir"].resolve(), target_is_directory=True)
                    (field / reruns[a].name).symlink_to(reruns[a].resolve(), target_is_directory=True)
                    placed[a] = _family(exp, field, a)
    moved = sorted(set(tied_c) ^ set(tied_m))
    lines += [
        "",
        f"## Verdicts: `{exp['leader']}` against the field, Holm-corrected",
        "",
        f"With {len(reruns)} rerun arm(s) substituted for their committed runs:",
        "",
        f"- not separated from the leader — committed: {len(tied_c)}, with reruns: {len(tied_m)}",
        f"- separated — committed: {len(sep_c)}, with reruns: {len(sep_m)}",
    ]
    if moved:
        for a in moved:
            was = "tied" if a in tied_c else "separated"
            now = "tied" if a in tied_m else "separated"
            lines.append(f"- **`{a}` moved: {was} → {now}**")
    else:
        lines.append("- **every committed separation and tie holds**")
    if placed:
        lines += [
            "",
            "## Your arms, against the committed field",
            "",
            "| arm | score | rank | not separated from | separated from | vs the leader |",
            "|---|---:|---:|---|---:|---|",
        ]
        for a, (tied, sep) in placed.items():
            score = st.fmean(_items(reruns[a], exp["metric"]).values())
            rank = 1 + sum(v["score"] > score for v in arms.values())
            vs = "not separated" if exp["leader"] in tied else "separated"
            lines.append(
                f"| `{a}` | {score:.4f} | {rank} of {len(arms) + 1} | "
                f"{', '.join(f'`{t}`' for t in sorted(tied)) or '—'} | {len(sep)} | {vs} |"
            )
    lines += [
        "",
        (
            "*exact*: every item scored identically. *consistent*: a hosted arm whose "
            "rerun is not distinguishable from its committed run (paired permutation test, "
            "p ≥ 0.05) — hosted models are not deterministic, so the digits are not expected "
            "to match. *DIFFERS*: distinguishable; check the upstream column, the provider "
            "that served it, and the fingerprint diff (`make run-compare`)."
        ),
    ]
    card = "\n".join(lines) + "\n"
    (REPRO / exp["slug"] / "REPLICATION.md").write_text(card)
    print(card)
    print(f"written to {(REPRO / exp['slug'] / 'REPLICATION.md').relative_to(ROOT)}")
    return 1 if moved or any(s.startswith("DIFFERS") for s in statuses.values()) else 0


def _upstream(m: dict) -> object:
    """The model a run's adapter says answered: the id it declared, else the model asked for."""
    dep = (m.get("fingerprint") or {}).get("deployment") or {}
    return (dep.get("declared") or {}).get("id") or dep.get("model")


def main() -> int:
    reg = registry()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=("plan", "data", "run", "compare", "list"))
    ap.add_argument("experiment", nargs="?", help=" | ".join(reg))
    ap.add_argument("--level", default="local", choices=("local", "hosted", "baselines", "all"))
    ap.add_argument("--arms", help="comma-separated arm names; overrides --level")
    ap.add_argument("--config", help="run: also measure YOUR arm from this config")
    ap.add_argument(
        "--light",
        action="store_true",
        help="data: skip the local-model extras (no PyTorch); enough for hosted arms, BM25 and the baselines",
    )
    a = ap.parse_args()
    if a.command == "list" or not a.experiment:
        for e in reg.values():
            arms = committed(e)
            kinds = {k: sum(v["kind"] == k for v in arms.values()) for k in ("local", "baseline", "hosted")}
            cost = sum(v["cost"] for v in arms.values())
            print(
                f"  {e['slug']:24s} {e['bench']:32s} {kinds['local']:2d} local, "
                f"{kinds['baseline']} baselines, {kinds['hosted']:2d} hosted   billed ${cost:.2f}"
            )
        return 0
    if a.experiment not in reg:
        raise SystemExit(f"unknown experiment {a.experiment!r}; one of: {', '.join(reg)}")
    exp = reg[a.experiment]
    return {
        "plan": lambda: plan(exp, a.level, a.arms),
        "data": lambda: data(exp, a.light),
        "run": lambda: run(exp, a.level, a.arms, a.config),
        "compare": lambda: compare(exp),
    }[a.command]()


if __name__ == "__main__":
    raise SystemExit(main())
