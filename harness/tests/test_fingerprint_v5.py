#!/usr/bin/env python3
"""Fingerprint v5 (RFC-021): its parts, what is and is not in the hash, the three deployment sources, the
migration of a v4 record, and run-compare naming the part that moved.

python tests/test_fingerprint_v5.py
"""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import yaml  # noqa: E402
from evaluation_harness import _fingerprint as fpmod  # noqa: E402
from evaluation_harness import _models, compare_runs  # noqa: E402
from evaluation_harness import fingerprint_migrate as mig  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import _flat_conditions  # noqa: E402

DATASET = {"dataset_id": "d1", "items": [{"item_id": "i1", "source_sha256": "aaa"}]}


def build(params=None, **over):
    kw = {
        "root": HERE.parent,
        "dataset": DATASET,
        "reference_id": None,
        "reference_tier": None,
        "config_id": "c1",
        "adapter_id": "scripts/adapter.py",
        "adapter_path": HERE / "scripts" / "adapter.py",
    }
    kw.update(over)
    return fpmod.build_fingerprint(params=dict(params or {}), **kw)


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def moved(a, b):
    return sorted(
        k
        for k in ("instrument_sha256", "data_sha256", "deployment_sha256", "settings_sha256", "hash")
        if a[k] != b[k]
    )


# ── the parts, and the hash over the four ─────────────────────────────────────
base_params = {
    "model": "m:1b",
    "machine": "dgx",
    "provider": "openai",
    "base_url": "http://x/v1",
    "max_tokens": 64,
}
fp = build(base_params)
check("v5: version 5", fp["version"] == 5)
check(
    "v5: the parts are instrument, data, deployment, settings, runner and arm; no host or system_under_test",
    {"instrument", "data", "deployment", "settings", "runner", "arm"} <= set(fp)
    and not {"host", "system_under_test"} & set(fp),
    sorted(fp),
)
check("v5: the arm is its config id alone", fp["arm"] == {"config_id": "c1"}, fp["arm"])
check(
    "v5: each hashed part has its own sha256, over that part",
    all(fp[f"{p}_sha256"] == sha(fp[p]) for p in ("instrument", "data", "deployment", "settings")),
)
check(
    "v5: hash is one sha256 over the four parts' own hashes",
    fp["hash"] == sha({p: fp[f"{p}_sha256"] for p in ("instrument", "data", "deployment", "settings")}),
)
check("v5: stable across identical inputs", build(base_params)["hash"] == fp["hash"])

# ── the runner is outside the hash ────────────────────────────────────────────
real_host, real_libs = fpmod._host_identity, fpmod._installed_versions
try:
    fpmod._host_identity = lambda: {
        "label": "laptop",
        "platform": "Darwin/arm64",
        "release": "24",
        "processor": "arm",
        "cpu_count": 8,
        "python": "3.11",
    }
    fpmod._installed_versions = lambda: {"openai": "1.0", "numpy": "1.26"}
    on_laptop = build(base_params)
    fpmod._host_identity = lambda: {
        "label": "x3",
        "platform": "Linux/x86_64",
        "release": "7",
        "processor": None,
        "cpu_count": 32,
        "python": "3.14",
    }
    fpmod._installed_versions = lambda: {"openai": "3.41", "numpy": "2.5"}
    on_x3 = build(base_params)
finally:
    fpmod._host_identity, fpmod._installed_versions = real_host, real_libs
check(
    "runner: the same deployment run from two machines has the same hash and the same part hashes",
    on_laptop["hash"] == on_x3["hash"] and moved(on_laptop, on_x3) == [],
    moved(on_laptop, on_x3),
)
check(
    "runner: the machine and its client libraries are recorded, and differ",
    on_laptop["runner"]["label"] == "laptop"
    and on_x3["runner"]["libraries"] == {"openai": "3.41", "numpy": "2.5"}
    and fpmod.differing_paths(on_laptop, on_x3)
    and all(p.startswith("runner.") for p in fpmod.differing_paths(on_laptop, on_x3)),
    fpmod.differing_paths(on_laptop, on_x3),
)

# ── one part moves one sub-hash ───────────────────────────────────────────────
other_dep = build({**base_params, "machine": "mac"})
check(
    "a deployment change moves deployment_sha256 and the hash, nothing else",
    moved(fp, other_dep) == ["deployment_sha256", "hash"],
    moved(fp, other_dep),
)
check(
    "a model change is a deployment change",
    moved(fp, build({**base_params, "model": "m:2b"})) == ["deployment_sha256", "hash"],
)
check(
    "a settings change moves settings_sha256 and the hash, nothing else",
    moved(fp, build({**base_params, "max_tokens": 128})) == ["hash", "settings_sha256"],
)
check(
    "a data change moves data_sha256 and the hash, nothing else",
    moved(
        fp,
        build(
            base_params, dataset={"dataset_id": "d1", "items": [{"item_id": "i1", "source_sha256": "bbb"}]}
        ),
    )
    == ["data_sha256", "hash"],
)
check(
    "an instrument change moves instrument_sha256 and the hash, nothing else",
    moved(fp, build(base_params, adapter_id="other", adapter_path=None, adapter_sha256="f" * 64))
    == ["hash", "instrument_sha256"],
)
check(
    "a config id is a name: it moves no hash",
    moved(fp, build(base_params, config_id="renamed")) == [],
)
check("moved_parts names the parts", fpmod.moved_parts(fp, other_dep) == ["deployment"])

# ── settings: no deployment keys, no credentials ──────────────────────────────
every = dict.fromkeys(fpmod.DEPLOYMENT_KEYS, "v")
settings = build({**every, "api_key_env": "SECRET_VAR", "temperature": 0, "reasoning_effort": "none"})[
    "settings"
]
check(
    "settings: params that are neither a deployment key nor a credential",
    settings == {"temperature": 0, "reasoning_effort": "none"},
    settings,
)
check(
    "a credential is in no part",
    "SECRET_VAR" not in json.dumps(build({**base_params, "api_key_env": "SECRET_VAR"})),
)
check(
    "a credential does not move the hash",
    build({**base_params, "api_key_env": "A"})["hash"] == build({**base_params, "api_key_env": "B"})["hash"],
)

# ── the three deployment sources ──────────────────────────────────────────────
p = build(base_params)["deployment"]
check(
    "source params: model, url, machine and provider from the params, no digest",
    p["source"] == "params"
    and p["model"] == "m:1b"
    and p["id"] == "m:1b@dgx"
    and p["server"]["url"] == "http://x/v1"
    and p["where"]["machine"] == "dgx"
    and p["provider"] == "openai"
    and p["weights"]["digest"] is None
    and p["in_process"] is False
    and p["libraries"] is None,
    p,
)

hook = lambda params: {  # noqa: E731
    "id": "org/span",
    "revision": "abc123",
    "revision_source": "hf-snapshot",
    "device": "cpu",
    "precision": "fp32",
    "weight_files": ["model.safetensors:1"],
}
a = build({"model": "org/span"}, model_hook=hook)["deployment"]
check(
    "source adapter: the hook's identity, in process, with the runner's libraries in the deployment",
    a["source"] == "adapter"
    and a["in_process"] is True
    and a["weights"]["revision"] == "abc123"
    and a["weights"]["revision_source"] == "hf-snapshot"
    and a["weights"]["precision"] == "fp32"
    and a["where"]["device"] == "cpu"
    and isinstance(a["libraries"], dict)
    and a["declared"] == {"weight_files": ["model.safetensors:1"]},
    a,
)
in_proc = build({"model": "org/span"}, model_hook=hook)
check("an in-process deployment leaves no libraries on the runner", in_proc["runner"]["libraries"] is None)
hosted_hook = lambda p: {"id": p["model"], "revision": "gpt-x-2026", "revision_source": "api-model-string"}  # noqa: E731
for remote in (
    {"model": "eval-x", "provider": "litellm"},
    {"model": "m", "url": "http://h:11434/v1"},
    {"model": "m", "provider": "gateway"},
):
    h = build(remote, model_hook=hosted_hook)
    check(
        f"source adapter, called elsewhere ({next(k for k in ('provider', 'url') if k in remote)}): not in process, "
        "the runner keeps its libraries, so a runner's upgrade does not move the deployment",
        h["deployment"]["source"] == "adapter"
        and h["deployment"]["in_process"] is False
        and h["deployment"]["libraries"] is None
        and isinstance(h["runner"]["libraries"], dict),
        h["deployment"],
    )


def alias_hook(p):
    return {
        "id": "openrouter/anthropic/claude-x",
        "revision_source": "api-model-string",
        "prompt_sha256": p["prompt"],
    }


g1 = build({"model": "eval-x", "provider": "litellm", "prompt": "a" * 64}, model_hook=alias_hook)
check(
    "a hosted arm records its provider and the upstream id behind the alias",
    g1["deployment"]["hosted"]
    == {"provider": "litellm", "provider_id": "openrouter/anthropic/claude-x", "route": None},
    g1["deployment"]["hosted"],
)
g2 = build({"model": "eval-x", "provider": "litellm", "prompt": "b" * 64}, model_hook=alias_hook)
check(
    "a declared prompt hash is a setting: a new prompt moves the settings' hash, not the deployment's",
    g1["settings"]["declared"] == {"prompt_sha256": "a" * 64}
    and g1["deployment_sha256"] == g2["deployment_sha256"]
    and g1["settings_sha256"] != g2["settings_sha256"],
    (g1["settings"], g2["settings"]),
)
check(
    "a served deployment keeps the client libraries on the runner",
    isinstance(fp["runner"]["libraries"], dict),
)
no_claim = build({"model": "m"}, model_hook=lambda params: {"identity_declared": False, "code_sha256": "cc"})[
    "deployment"
]
check(
    "a hook that declines to claim an identity is the params source, with what it did return kept",
    no_claim["source"] == "params" and no_claim["declared"] == {"code_sha256": "cc"},
    no_claim,
)

with tempfile.TemporaryDirectory() as td:
    data = Path(td) / "data"
    (data / "models").mkdir(parents=True)
    (data / "models" / "gem.yaml").write_text(
        yaml.safe_dump(
            {
                "model_id": "gem",
                "kind": "llm",
                "aliases": ["gem:1b"],
                "deployments": [
                    {
                        "id": "dgx",
                        "where": "dgx",
                        "backend": "cuda",
                        "server": "ollama 0.40.13",
                        "server_settings": {"context_length": 32768},
                        "tag": "gem:1b",
                        "digest": "d" * 64,
                        "quantization": "Q4_K_M",
                    },
                    {"id": "mac", "where": "mac", "backend": "metal", "tag": "gem:1b", "digest": "e" * 64},
                    {
                        "id": "or-nebius",
                        "where": "openrouter",
                        "provider_id": "vendor/gem",
                        "provider_routing": ["nebius"],
                    },
                ],
            }
        )
    )
    cfg = {"model_record": "gem", "deployment": "dgx"}
    params = {"model": "gem:1b", "base_url": "http://tunnel/v1", "max_tokens": 64}
    r = build(params, cfg=cfg, data_dir=data, model_hook=hook)
    d = r["deployment"]
    check(
        "source record: the deployment entry's weights, server, hardware, best first (over the adapter)",
        d["source"] == "record"
        and d["id"] == "gem@dgx"
        and d["weights"]["digest"] == "d" * 64
        and d["weights"]["quantization"] == "Q4_K_M"
        and d["server"]["name"] == "ollama"
        and d["server"]["version"] == "0.40.13"
        and d["server"]["settings"] == {"context_length": 32768}
        and d["where"] == {"machine": "dgx", "backend": "cuda", "device": None}
        and d["hosted"] is None
        and d["in_process"] is False,
        d,
    )
    check(
        "source record: the tunnel's url is not part of the deployment, and settings keep only the settings",
        "tunnel" not in json.dumps(d) and r["settings"] == {"max_tokens": 64},
    )
    mac = build(params, cfg={**cfg, "deployment": "mac"}, data_dir=data)
    check(
        "two deployments of one record are two deployment hashes, the same settings hash",
        moved(r, mac) == ["deployment_sha256", "hash"] and mac["deployment"]["id"] == "gem@mac",
        moved(r, mac),
    )
    hosted = build(params, cfg={**cfg, "deployment": "or-nebius"}, data_dir=data)["deployment"]
    check(
        "a hosted deployment pins its route",
        hosted["hosted"] == {"provider": "openrouter", "provider_id": "vendor/gem", "route": ["nebius"]},
        hosted,
    )
    check(
        "a config that names no deployment, or one the record lacks, falls back below the record",
        build(params, cfg={"model_record": "gem"}, data_dir=data)["deployment"]["source"] == "params",
    )

    resolved = _models.resolve({"model_record": "gem", "deployment": "dgx", "params": {}}, data)
    check(
        "resolve keeps both the record and the deployment",
        resolved["model_record"] == "gem" and resolved["deployment"] == "dgx",
    )
    errs = []
    for bad in ({"model_record": "gem", "deployment": "nope"}, {"deployment": "dgx"}):
        try:
            _models.resolve(bad, data)
        except ValueError as exc:
            errs.append(str(exc))
    check(
        "resolve refuses a deployment the record lacks, and one without a record",
        len(errs) == 2 and "no such deployment" in errs[0] and "names no model_record" in errs[1],
        errs,
    )


# ── the migration of a v4 record ──────────────────────────────────────────────
def v4(model_decl, params, derived=False):
    return {
        "version": 4,
        "instrument": {
            "harness": {"version": "0.5.0", "commit": "abc"},
            "adapter": {"id": "a.py", "sha256": "s"},
        },
        "system_under_test": {"model": model_decl, "libraries": {"openai": "3.1", "numpy": "2.0"}},
        "data": {
            "dataset_id": "d1",
            "items_sha256": "i",
            "n_items": 1,
            "reference_id": None,
            "reference_tier": None,
            "references_sha256": None,
        },
        "host": {
            "label": None,
            "platform": "Linux/x86_64",
            "release": "7",
            "processor": None,
            "cpu_count": 32,
            "python": "3.14",
        },
        "arm": {"config_id": "c1", "params": params},
        "hash": None if derived else "0" * 64,
    }


declared = {
    "identity_declared": True,
    "id": "org/span",
    "revision": "abc123",
    "revision_source": "hf-snapshot",
    "device": "cpu",
    "precision": "fp32",
    "prompt_sha256": "p" * 64,
}
m_adapter = mig.migrate_fingerprint(
    v4(
        declared,
        {"model": "org/span", "device": "cpu", "precision": "fp32", "num_beams": 4, "api_key_env": "K"},
    )
)
check(
    "migrate: an adapter-declared v4 identity is source adapter, in process, with v4's libraries; its declared prompt hash is a setting",
    m_adapter["version"] == 5
    and m_adapter["deployment"]["source"] == "adapter"
    and m_adapter["deployment"]["in_process"] is True
    and m_adapter["deployment"]["libraries"] == {"openai": "3.1", "numpy": "2.0"}
    and m_adapter["deployment"]["weights"]["revision"] == "abc123"
    and m_adapter["deployment"]["declared"] is None
    and m_adapter["runner"]["libraries"] is None
    and m_adapter["runner"]["platform"] == "Linux/x86_64"
    and m_adapter["settings"] == {"num_beams": 4, "declared": {"prompt_sha256": "p" * 64}}
    and "host" not in m_adapter
    and "system_under_test" not in m_adapter,
    m_adapter,
)
m_params = mig.migrate_fingerprint(
    v4({"identity_declared": False}, {"model": "gw-alias", "provider": "gateway", "usd_per_mtok_in": 2.0})
)
check(
    "migrate: an undeclared v4 identity is source params, and the libraries stay with the runner",
    m_params["deployment"]["source"] == "params"
    and m_params["deployment"]["model"] == "gw-alias"
    and m_params["deployment"]["weights"]["digest"] is None
    and m_params["deployment"]["libraries"] is None
    and m_params["runner"]["libraries"] == {"openai": "3.1", "numpy": "2.0"}
    and m_params["settings"] == {"usd_per_mtok_in": 2.0},
    m_params,
)
check(
    "migrate: the hashes are those a fresh build computes (parts, then the hash over them)",
    all(m_params[f"{p}_sha256"] == sha(m_params[p]) for p in fpmod.PARTS)
    and m_params["hash"] == fpmod.combined_hash(m_params),
)
check(
    "migrate: a derived run keeps its whole hash null and re-hashes its parts",
    mig.migrate_fingerprint(v4({"identity_declared": False}, {"model": "m"}, derived=True))["hash"] is None,
)
check("migrate: a v5 fingerprint is returned as it is", mig.migrate_fingerprint(m_params) is m_params)

# the tool, over a small tree: counts, the baseline's hash, idempotence, derived runs take their source's parts
with tempfile.TemporaryDirectory() as td:
    data = Path(td) / "data"

    def put(rel, doc):
        f = data / rel / "metrics.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        return f

    put(
        "runs/r1",
        {"run_id": "r1", "params": {"model": "org/span"}, "fingerprint": v4(declared, {"model": "org/span"})},
    )
    put(
        "runs/r2",
        {
            "run_id": "r2",
            "params": {"model": "gw"},
            "fingerprint": v4({"identity_declared": False}, {"model": "gw"}),
        },
    )
    put(
        "runs-rescored/r1",
        {
            "run_id": "r1",
            "derived": {"kind": "rescore", "from": "r1"},
            "params": {"model": "org/span"},
            "fingerprint": v4(declared, {"model": "org/span"}, derived=True),
        },
    )
    (data / "baselines").mkdir()
    b = data / "baselines" / "b.json"
    b.write_text(
        json.dumps(
            {"baseline_id": "b", "promoted_from": "r1", "fingerprint_hash": "0" * 64},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    cmd = [sys.executable, str(HERE / "scripts" / "fingerprint_migrate.py"), "--data-dir", str(data)]
    first = subprocess.run(cmd, capture_output=True, text=True)
    docs = {
        p.parent.name + "/" + p.parent.parent.name: json.loads(p.read_text())
        for p in data.glob("runs*/*/metrics.json")
    }
    check(
        "migration tool: prints before and after, the runs migrated and the deployment sources",
        "before: 3 v4" in first.stdout
        and "after:  3 v5" in first.stdout
        and "runs migrated: 3" in first.stdout
        and "deployment source adapter: 2" in first.stdout
        and "deployment source params: 1" in first.stdout
        and "baselines whose fingerprint_hash was updated: 1" in first.stdout,
        first.stdout + first.stderr,
    )
    r1 = docs["r1/runs"]["fingerprint"]
    check(
        "migration tool: only the fingerprint changed; the run keeps its other fields",
        docs["r1/runs"]["params"] == {"model": "org/span"} and r1["version"] == 5 and r1["hash"] != "0" * 64,
    )
    check(
        "migration tool: a derived run carries its source run's deployment and settings, and its hash stays null",
        docs["r1/runs-rescored"]["fingerprint"]["deployment"] == r1["deployment"]
        and docs["r1/runs-rescored"]["fingerprint"]["settings"] == r1["settings"]
        and docs["r1/runs-rescored"]["fingerprint"]["hash"] is None,
    )
    check(
        "migration tool: the baseline carries the run's new hash",
        json.loads(b.read_text())["fingerprint_hash"] == r1["hash"],
    )
    before_bytes = {p: p.read_bytes() for p in [*data.glob("runs*/*/metrics.json"), b]}
    second = subprocess.run(cmd, capture_output=True, text=True)
    check(
        "migration tool: idempotent, a v5 fingerprint is left as it is",
        "runs migrated: 0" in second.stdout and before_bytes == {p: p.read_bytes() for p in before_bytes},
        second.stdout,
    )


# ── run-compare names the part that moved ────────────────────────────────────
def report(a, b):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        compare_runs._report_fingerprint_delta({"fingerprint": a}, {"fingerprint": b})
    return buf.getvalue()


on_dgx = build({**base_params})
on_mac = build({**base_params, "machine": "mac"})
out = report(on_dgx, on_mac)
check(
    "run-compare: a deployment change is named, with both deployments, and the settings are not blamed",
    "deployment differs: m:1b@dgx vs m:1b@mac" in out
    and "settings differ" not in out
    and "instrument differs" not in out,
    out,
)
out = report(on_dgx, build({**base_params, "max_tokens": 128}))
check(
    "run-compare: a settings change is named by key and value",
    "settings differ: max_tokens (64 vs 128)" in out and "deployment differs" not in out,
    out,
)
out = report(
    on_dgx,
    build(base_params, dataset={"dataset_id": "d1", "items": [{"item_id": "i1", "source_sha256": "bbb"}]}),
)
check(
    "run-compare: a data change is named and marked as not the arm",
    "data differs: items_sha256" in out and "NOT the arm" in out,
    out,
)
out = report(on_dgx, build(base_params, adapter_id="other", adapter_path=None, adapter_sha256="f" * 64))
check(
    "run-compare: an instrument change is named", "instrument differs:" in out and "NOT the arm" in out, out
)
out = report(on_dgx, on_mac)
check("run-compare: a deployment change alone is not a confound", "NOT the arm" not in out, out)
both = report(on_dgx, build({**base_params, "machine": "mac", "max_tokens": 128}))
check(
    "run-compare: the deployment and the settings both moving is said to be two things",
    "deployment differs" in both and "settings differ" in both and "two things were varied" in both,
    both,
)
same_runner_moved = json.loads(json.dumps(on_dgx))
same_runner_moved["runner"]["platform"] = "Darwin/arm64"
out = report(on_dgx, same_runner_moved)
check(
    "run-compare: a runner difference is a condition, not a mismatch",
    "Fingerprints MATCH" in out
    and "Runner (where evh ran" in out
    and "platform Linux/x86_64 vs Darwin/arm64" in out,
    out,
)
check(
    "run-compare: identical fingerprints match with no runner note",
    "Fingerprints MATCH" in report(on_dgx, on_dgx) and "Runner" not in report(on_dgx, on_dgx),
)
legacy = {"version": 4, "hash": "x"}
check(
    "run-compare: a fingerprint of another version is not compared part by part",
    "versions differ" in report(legacy, on_dgx),
)

with tempfile.TemporaryDirectory() as td:
    runs = Path(td) / "data" / "runs"
    for rid, f in (("run_a", on_dgx), ("run_b", on_mac)):
        (runs / rid).mkdir(parents=True)
        (runs / rid / "metrics.json").write_text(
            json.dumps(
                {
                    "run_id": rid,
                    "dataset_id": "d1",
                    "build": {"ref": rid, "dirty": False},
                    "scores": {"f1": 0.5},
                    "fingerprint": f,
                }
            )
        )
    run = subprocess.run(
        [
            sys.executable,
            str(HERE / "scripts" / "compare_runs.py"),
            "--baseline",
            "run_a",
            "--candidate",
            "run_b",
        ],
        capture_output=True,
        text=True,
        cwd=td,
        env={**os.environ, "EVAL_HOME": td},
    )
    check(
        "evh run-compare: names the deployment that differs",
        run.returncode == 0 and "deployment differs: m:1b@dgx vs m:1b@mac" in run.stdout,
        run.stdout[-600:] + run.stderr[-300:],
    )

# ── the inspector's conditions ───────────────────────────────────────────────
c_served = _flat_conditions(
    json.loads(
        json.dumps(
            {
                **on_dgx,
                "deployment": {**on_dgx["deployment"], "server": {"name": "ollama", "version": "0.40"}},
            }
        )
    )
)
check(
    "conditions: a served model's libraries are the runner's, its machine and server the deployment's",
    c_served["deployment.machine"] == "dgx"
    and c_served["deployment.server"] == "ollama 0.40"
    and any(k.startswith("library.") for k in c_served)
    and c_served["machine.platform"] == on_dgx["runner"]["platform"]
    and "machine.libraries" not in c_served,
    c_served,
)
c_in = _flat_conditions(in_proc)
check(
    "conditions: an in-process model's libraries are the deployment's",
    any(k.startswith("library.") for k in c_in) and in_proc["runner"]["libraries"] is None,
)
check("conditions: the fingerprint version is a condition", c_in["fingerprint.version"] == "5")

# ── end to end: experiment-run with a record and a deployment, and V18 ───────
import shutil  # noqa: E402

KIT = HERE / "tutorial"
proj = Path(tempfile.mkdtemp(prefix="evh-fp5-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-fp5", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    words = text.split()[:5]
    return SimpleNamespace(output=" ".join(words), tokens_in=1, tokens_out=len(words), cost_usd=None,
                           latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"words": float(len(output.split()))}
"""


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "scripts" / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
    )


def config(name, extra):
    f = proj / "data" / "configs" / f"{name}.yaml"
    f.write_text(
        f"config_id: {name}_v1\ndataset_id: tickets_v1\nadapter: adapter.py\n{extra}params:\n  max_tokens: 9\n"
    )
    return f"data/configs/{name}.yaml"


try:
    (proj / "data" / "configs").mkdir(parents=True)
    (proj / "data" / "models").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is frozen and materialized", r.returncode == 0, r.stderr[-300:])
    (proj / "data" / "models" / "gem.yaml").write_text(
        yaml.safe_dump(
            {
                "model_id": "gem",
                "kind": "llm",
                "aliases": ["gem:1b"],
                "deployments": [
                    {
                        "id": "dgx",
                        "where": "dgx",
                        "backend": "cuda",
                        "server": "ollama 0.40",
                        "tag": "gem:1b",
                        "digest": "d" * 64,
                    }
                ],
            }
        )
    )
    r = evh("experiment-run", "--config", config("named", "model_record: gem\ndeployment: dgx\n"))
    run_dir = next((proj / "data" / "runs").glob("named_v1_*"), None)
    m = json.loads((run_dir / "metrics.json").read_text()) if run_dir else {}
    d = (m.get("fingerprint") or {}).get("deployment") or {}
    check(
        "experiment-run: a config naming a record and a deployment fingerprints the deployment from the record",
        r.returncode == 0
        and d.get("source") == "record"
        and d.get("id") == "gem@dgx"
        and (d.get("weights") or {}).get("digest") == "d" * 64
        and (m.get("fingerprint") or {}).get("version") == 5,
        (r.stdout + r.stderr)[-500:],
    )
    check(
        "experiment-run: metrics.json records model_record and deployment_id",
        m.get("model_record") == "gem" and m.get("deployment_id") == "dgx",
        {k: m.get(k) for k in ("model_record", "deployment_id")},
    )
    r = evh("experiment-run", "--config", config("plain", ""))
    run_dir = next((proj / "data" / "runs").glob("plain_v1_*"), None)
    m2 = json.loads((run_dir / "metrics.json").read_text()) if run_dir else {}
    check(
        "experiment-run: a config naming neither is the params source and records no deployment_id",
        r.returncode == 0
        and (m2["fingerprint"]["deployment"]["source"] == "params")
        and "deployment_id" not in m2,
        (r.stdout + r.stderr)[-300:],
    )
    r = evh("experiment-run", "--config", config("typo", "model_record: gem\ndeployment: x3\n"))
    check(
        "experiment-run: a deployment the record lacks is refused before anything runs",
        r.returncode != 0 and "no such deployment" in r.stdout + r.stderr,
        (r.stdout + r.stderr)[-300:],
    )
    config("orphan", "deployment: dgx\n")
    v = evh("validate")
    check(
        "V18: a deployment the record lacks, and a deployment without a model_record, are named and fail",
        v.returncode != 0
        and "typo.yaml: deployment 'x3' is not one of gem's deployments" in v.stdout
        and "orphan.yaml: deployment 'dgx' is used without a model_record" in v.stdout,
        v.stdout[-900:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

# the inspector's speed warning: a deployment that differs, and a runner that differs, say different things
from evaluation_harness import catalog_serve  # noqa: E402


class _Conds:
    def __init__(self, by_arm):
        self.by_arm = by_arm

    def conditions(self, arm):
        return self.by_arm[arm]


catalog_serve.A = _Conds(
    {
        "a": {"deployment.machine": "dgx", "machine.platform": "Linux"},
        "b": {"deployment.machine": "mac", "machine.platform": "Linux"},
    }
)
w = " ".join(catalog_serve._conditions(["a", "b"], "latency_ms")["warnings"])
check("inspector: latency across deployments is named as the deployment's", "across deployments" in w, w)
catalog_serve.A = _Conds(
    {
        "a": {"deployment.machine": "dgx", "machine.platform": "Linux"},
        "b": {"deployment.machine": "dgx", "machine.platform": "Darwin"},
    }
)
w = " ".join(catalog_serve._conditions(["a", "b"], "latency_ms")["warnings"])
check(
    "inspector: latency from different runners is named as the runners'",
    "different runners" in w and "deployments" not in w,
    w,
)
w = " ".join(catalog_serve._conditions(["a", "b"], "correct")["warnings"])
check("inspector: a quality measure from different runners carries no warning", w == "", w)

sys.exit(summary())
