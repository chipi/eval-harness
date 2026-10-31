#!/usr/bin/env python3
"""The catalog's Models page, a page per model, the arms page's badge and `evh models` (RFC-020, UXS-001).

python tests/test_catalog_models.py

On a small data tree written here (a vetted self-hosted LLM whose build differs between two machines, a hosted
LLM that needs a check, an ML model nobody onboarded, a bare record no arm uses, and an arm whose model has no
record), and on a copy of the project's committed records (the migrated ones and gemma4-12b).
"""

import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from evaluation_harness import catalog_build as cb
from evaluation_harness import catalog_models as cm
from evaluation_harness import catalog_views as cv
from evaluation_harness._check import check, summary
from evaluation_harness.catalog_adapter import HarnessAdapter

COMMITTED = Path(__file__).resolve().parents[1] / "data" / "models"


def run(data, run_id, config, params, record=None, deployment=None):
    d = data / "runs" / run_id
    (d / "outputs").mkdir(parents=True)
    m = {
        "run_id": run_id,
        "dataset_id": "ds1",
        "config_id": config,
        "primary_metric": "acc",
        "metric_kinds": {"acc": "quality"},
        "fingerprint": {"data": {"reference_id": "gold/ds1"}},
        "params": params,
        "created_at": "2026-10-30T10:00:00Z",
    }
    if record:
        m["model_record"] = record
    if deployment:
        m["deployment_id"] = deployment
    (d / "metrics.json").write_text(json.dumps(m))
    (d / "predictions.jsonl").write_text(
        "".join(json.dumps({"item_id": f"i{i}", "acc": 0.5}) + "\n" for i in range(4))
    )
    (d / "outputs" / "i0.txt").write_text("out")


def record(data, doc):
    (data / "models").mkdir(exist_ok=True)
    (data / "models" / f"{doc['model_id']}.yaml").write_text(yaml.safe_dump(doc))


def view(A, argv):
    buf = io.StringIO()
    real = cv.load_catalog_adapter
    cv.load_catalog_adapter = lambda spec=None: A
    try:
        with contextlib.redirect_stdout(buf):
            cv.VIEWS[argv[0]](argv[1:])
    finally:
        cv.load_catalog_adapter = real
    return buf.getvalue()


def refused(A, argv):
    try:
        view(A, argv)
    except SystemExit as e:
        return str(e)
    return ""


def rows_of(page, key):
    return next((r for r in page.split("<tr") if f'data-key="{key}"' in r), "")


with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    data = tmp / "data"
    (data / "runs").mkdir(parents=True)
    record(
        data,
        {
            "model_id": "gem",
            "kind": "llm",
            "name": "Gem 1B",
            "aliases": ["gem:1b", "gem-alias"],
            "weights": "open",
            "licence": "Apache-2.0",
            "deployments": [
                {
                    "id": "mac",
                    "where": "mac",
                    "server": "ollama 0.40",
                    "tag": "gem:1b",
                    "digest": "a" * 64,
                    "checked_at": "2026-10-31",
                    "onboarding": {
                        "status": "pass",
                        "at": "2026-10-31T09:00:00Z",
                        "where": "mac",
                        "flags": [],
                        "report": {"deterministic": True, "chosen": {"s": 0.8, "reasoned": False}},
                    },
                },
                {
                    "id": "dgx",
                    "where": "dgx",
                    "backend": "cuda",
                    "server": "vllm 26",
                    "tag": "gem:1b",
                    "digest": "b" * 64,
                    "checked_at": "2020-01-01",
                    "onboarding": {
                        "status": "pass",
                        "at": "2026-10-30T09:00:00Z",
                        "where": "dgx",
                        "flags": [],
                        "report": {"tokens_per_second": 41},
                    },
                },
            ],
            "settings": {"reasoning_effort": "none"},
            "settings_why": {"reasoning_effort": "at the default it never answered"},
            "history": [
                {
                    "at": "2026-10-31",
                    "what": "reasoning_effort",
                    "from": "(server default)",
                    "to": "none",
                    "why": "it looped",
                }
            ],
            "smokes": {
                "cfg_a": {"status": "pass", "at": "2026-10-31"},
                "cfg_b": {"status": "check", "at": "2026-10-31", "flags": ["slow"]},
            },
        },
    )
    record(
        data,
        {
            "model_id": "hosted-x",
            "kind": "llm",
            "aliases": ["hosted-x"],
            "weights": "proprietary",
            "deployments": [
                {
                    "id": "openrouter",
                    "where": "openrouter",
                    "provider_id": "vendor/x",
                    "onboarding": {
                        "status": "check",
                        "at": "2026-10-30",
                        "flags": ["reasons without a bound"],
                        "report": {},
                    },
                }
            ],
        },
    )
    record(
        data,
        {
            "model_id": "span",
            "kind": "ml",
            "aliases": ["org/span"],
            "weights": "open",
            "settings": {"device": "cpu", "precision": "fp32", "batch_size": 1},
        },
    )
    record(data, {"model_id": "bare", "kind": "baseline", "aliases": ["bare"]})
    (data / "goals").mkdir()
    (data / "goals" / "g1.yaml").write_text(
        yaml.safe_dump(
            {
                "goal_id": "g1",
                "schema_version": "0.1",
                "title": "Goal one",
                "statement": "Pick a model.",
                "status": "active",
                "decision": "Which model.",
                "output_contract": [{"id": "label", "format": "label"}],
                "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}},
                "datasets": [{"dataset_id": "ds1", "role": "heldout"}],
                "measures": [{"id": "acc", "kind": "metric", "validity": "partial"}],
            }
        )
    )
    run(data, "r1", "cfg_a", {"model": "gem:1b"}, record="gem", deployment="mac")
    run(data, "r2", "cfg_b", {"model": "gem-alias", "max_tokens": 2048})
    run(data, "r3", "cfg_c", {"model": "org/span"})
    run(data, "r4", "cfg_d", {"model": "unlisted-model"})

    A = HarnessAdapter(data)
    used = {x["record"]["model_id"]: [a.rsplit("/", 1)[-1] for a in x["arms"]] for x in A.models()}
    check(
        "adapter.models: an arm uses a record by model_record or by an alias; an unlisted model uses none",
        used == {"bare": [], "gem": ["cfg_a", "cfg_b"], "hosted-x": [], "span": ["cfg_c"]},
        used,
    )

    rec = {x["record"]["model_id"]: x["record"] for x in A.models()}
    check(
        "hosting: provider id is hosted, a deployment on a machine is self-hosted, no deployments is neither",
        [cm.hosting(rec[k]) for k in ("gem", "hosted-x", "span", "bare")]
        == ["self-hosted", "hosted", "", ""],
    )
    check(
        "settings line: an LLM's reasoning, tokens and limit; an ML model's device, precision, batch; defaults",
        [cm.settings_line(rec[k]) for k in ("gem", "span", "bare")]
        == ["reasoning off", "cpu · fp32 · batch 1", "defaults"],
    )
    smoked = {"smokes": {"arm_v1": {"status": "pass", "at": "2026-10-31"}}}
    one_dep = lambda status, **kw: {  # noqa: E731
        "deployments": [{"id": "a", "where": "x", "onboarding": {"status": status}}],
        **kw,
    }
    mixed = {"deployments": [*one_dep("pass")["deployments"], {"id": "b", "where": "y"}], **smoked}
    check(
        "status: vetted needs every probe passed and an arm smoke passed; probes alone are onboarded; any "
        "flagged probe is check; none otherwise (or no deployment)",
        [
            cm.status_of(r)
            for r in (
                one_dep("pass", **smoked),
                one_dep("pass"),
                one_dep("pass", smokes={"arm_v1": {"status": "check", "at": "2026-10-31"}}),
                {
                    "deployments": [*one_dep("pass")["deployments"], *one_dep("check")["deployments"]],
                    **smoked,
                },
                one_dep("check", **smoked),
                mixed,
                {"deployments": [{"id": "a", "where": "x", "onboarding": {"status": "pass"}}] * 2, **smoked},
                {},
            )
        ]
        == ["vetted", "onboarded", "onboarded", "check", "check", "none", "vetted", "none"],
    )
    check(
        "build differs: the same tag with another digest on a machine is named, the first build is the record's",
        cm.build_diffs(rec["gem"])[0] == "" and "on mac" in cm.build_diffs(rec["gem"])[1],
        cm.build_diffs(rec["gem"]),
    )

    out = tmp / "site"
    counts = cb.build(A, out)
    models = (out / "models.html").read_text()
    check(
        "models.html and a page per record are written",
        all((out / "models" / f"{k}.html").is_file() for k in rec),
    )
    check(
        "models page: a row per record, linked, with its kind under the name",
        all(f'href="models/{k}.html"' in models for k in rec)
        and len(re.findall(r'<tr[^>]* data-key="', models)) == 4,
    )
    check(
        "models page: hero counts vetted, to check and not onboarded",
        "4 models: 1 vetted, 0 onboarded with no arm smoked, 1 to check, 2 not onboarded yet" in models,
    )
    gem = rows_of(models, "gem")
    check(
        "models page: a differing build is badged, settings and onboarding shown, the stale machine muted",
        "differs" in gem
        and "reasoning off" in gem
        and "pass" in gem
        and re.search(r'<span class="muted" title="[^"]*">dgx</span>', gem)
        and 'data-differs="yes"' in gem
        and 'data-where="self-hosted"' in gem
        and 'data-status="vetted"' in gem,
    )
    check(
        "models page: the goals that use it, and its best arm's place on each",
        "Goal one" in gem and re.search(r"#\d+ of \d+", gem),
        gem,
    )
    check(
        "models page: the arms count opens the arms page filtered to them",
        'href="arms.html?q=gem"' in gem,
    )
    check(
        "models page: a hosted record, an ML model and a bare record render with em dashes and 'not onboarded'",
        'data-where="hosted"' in rows_of(models, "hosted-x")
        and "not onboarded" in rows_of(models, "span")
        and "not onboarded" in rows_of(models, "bare")
        and 'data-where="unknown"' in rows_of(models, "bare"),
    )
    check(
        "models page: the chips for kind, where, weights, status and builds that differ",
        all(
            f'data-facet="{f}" data-value="{v}"' in models
            for f, v in (
                ("kind", "llm"),
                ("kind", "ml"),
                ("where", "self-hosted"),
                ("where", "hosted"),
                ("weights", "open"),
                ("status", "vetted"),
                ("status", "check"),
                ("status", "none"),
                ("differs", "yes"),
            )
        ),
    )
    check(
        "models page: what changed lists the onboardings and the settings change",
        "mac onboarding: pass" in models
        and "dgx onboarding: pass" in models
        and "reasoning_effort (server default) → none (it looped)" in models,
    )
    page = (out / "models" / "gem.html").read_text()
    check(
        "model page: facts, deployments with what differs, each one's onboarding probes, history and its arms",
        all(
            x in page
            for x in (
                "Apache-2.0",
                "gem-alias",
                "at the default it never answered",
                "differs:",
                "vllm 26",
                "deterministic",
                "tokens per second",
                "<code>mac</code>",
                "<code>dgx</code>",
                "it looped",
            )
        )
        and 'href="../a/' in page
        and "reasoning_effort: (server default) → none" in page,
    )
    check(
        "model page: each arm's smoke from the record's smokes, and the settings the arm sets",
        "max_tokens 2048" in page and "slow" in page and "pass" in page,
    )
    check(
        "model page: one collapsible block per deployment holding its build and its own onboarding, no second section",
        page.count('<details class="rounddetail" id="dep-') == 2
        and 'id="dep-mac"' in page
        and 'id="dep-dgx"' in page
        and "deployments and their onboarding" in page
        and ">onboarding</" not in page.replace("<dt>onboarding</dt>", ""),
        (
            page.count('<details class="rounddetail" id="dep-'),
            [x for x in ("dep-mac", "dep-dgx", "deployments and their onboarding") if x not in page],
            page[page.find(">onboarding</") - 120 : page.find(">onboarding</") + 20]
            if ">onboarding</" in page
            else "",
        ),
    )
    check(
        "model page: the arms table names each arm's deployment",
        ">deployment<" in page[page.find("modelarms") :],
    )
    gem_row = models[models.find('href="models/gem.html"') :][:3000]
    check(
        "models page: the best-result cell is one place, with a count of the others linked to the model's page",
        "#1 of" in gem_row and gem_row.count("#1 of") + gem_row.count("#2 of") == 1,
        gem_row[-800:],
    )
    bare = (out / "models" / "bare.html").read_text()
    check(
        "model page: a record with no deployments, history or arms says so",
        all(
            x in bare
            for x in (
                "No deployment is recorded",
                "Not onboarded yet",
                "No change of settings",
                "No arm uses this model",
            )
        ),
    )

    arms_html = (out / "arms.html").read_text()
    a_row, b_row, c_row, d_row = (
        rows_of(arms_html, f"runs/ds1/{c}") for c in ("cfg_a", "cfg_b", "cfg_c", "cfg_d")
    )
    check(
        "arms page: the model record under the model column, linked, with smoked / smoke: check / not smoked",
        'href="models/gem.html"' in a_row
        and '<span class="role">smoked</span>' in a_row
        and '<span class="role">smoke: check</span>' in b_row
        and '<span class="role">not smoked</span>' in c_row
        and 'href="models/span.html"' in c_row,
    )
    check(
        "arms page: the deployment an arm's config named is beside its record",
        "@ mac</small>" in a_row and "@" not in b_row.split("models/gem.html")[-1].split("</td>")[0],
    )
    check(
        "arm config: the deployment the run recorded, empty for none",
        A.arm_config("runs/ds1/cfg_a")["deployment"] == "mac"
        and A.arm_config("runs/ds1/cfg_b")["deployment"] == "",
    )
    check("arms page: an arm with no record gets no badge", "smoke" not in d_row and "models/" not in d_row)
    home = (out / "index.html").read_text()
    check(
        "home: a models tile beside arms opens the models page, and it counts the records",
        'href="models.html"' in home and 'title="4 models"' in home and counts["arms"] == 4,
        counts,
    )
    nav = re.findall(r'<nav class="nav">(.*?)</nav>', home)[0]
    check("nav: Models is under Experiments", ">Models<" in nav and nav.count("<a ") == 10)

    listing = view(A, ["models"])
    check(
        "evh models: a row per record with kind, where, settings, onboarding and arms",
        all(k in listing for k in ("gem", "hosted-x", "span", "bare"))
        and "reasoning off" in listing
        and "pass 2026-10-31" in listing
        and "gem:1b@aaaaaaaaaaaa, gem:1b@bbbbbbbbbbbb (differs)" in listing
        and re.search(r"gem .*g1 .*g1 #\d+ of \d+", listing),
        listing,
    )
    names = lambda text: {ln.split()[0] for ln in text.splitlines()[2:] if ln.strip()}  # noqa: E731
    check(
        "evh models --kind / --where / --status: the page's chips",
        names(view(A, ["models", "--kind", "ml"])) == {"span"}
        and names(view(A, ["models", "--where", "hosted"])) == {"hosted-x"}
        and names(view(A, ["models", "--where", "self-hosted"])) == {"gem"}
        and names(view(A, ["models", "--status", "check"])) == {"hosted-x"}
        and names(view(A, ["models", "--status", "none"])) == {"span", "bare"}
        and names(view(A, ["models", "--status", "vetted"])) == {"gem"},
    )
    check(
        "evh models: a filter nothing matches says so",
        "no model matches" in view(A, ["models", "--kind", "baseline", "--status", "vetted"]),
    )
    one = view(A, ["models", "--model", "gem"])
    check("evh models --model: each arm's own settings, as on its page", "max_tokens 2048" in one, one[-800:])
    check(
        "evh models --model: facts, deployments with what differs, each one's onboarding, history, arms with their smoke",
        all(
            x in one
            for x in (
                "Gem 1B",
                "Apache-2.0",
                "setting reasoning_effort",
                "at the default it never answered",
                "differs:",
                "deployments:",
                "onboarding:",
                "mac: pass 2026-10-31",
                "dgx: pass 2026-10-30",
                "settings history:",
                "it looped",
                "runs/ds1/cfg_a",
                "smoked",
                "smoke: check",
            )
        ),
        one,
    )
    check(
        "evh models --model: an unknown record is refused",
        "no model 'nope'" in refused(A, ["models", "--model", "nope"]),
    )
    arms_cli = view(A, ["arms"])
    check(
        "evh arms: a model record column with the smoke, only when an arm has a record",
        "model record" in arms_cli and "gem@mac (smoked)" in arms_cli and "span (not smoked)" in arms_cli,
        arms_cli,
    )

    empty = tmp / "empty"
    (empty / "runs").mkdir(parents=True)
    run(empty, "r1", "cfg_x", {"model": "m"})
    E = HarnessAdapter(empty)
    shutil.rmtree(tmp / "site_empty", ignore_errors=True)
    cb.build(E, tmp / "site_empty")
    check(
        "no records: the page says how to add one, the tile counts 0, evh models says none",
        "No model record yet" in (tmp / "site_empty" / "models.html").read_text()
        and 'title="0 models"' in (tmp / "site_empty" / "index.html").read_text()
        and "no model records" in view(E, ["models"]),
    )

with tempfile.TemporaryDirectory() as td:
    committed = Path(td) / "data"
    shutil.copytree(COMMITTED, committed / "models")
    n = len(list(COMMITTED.glob("*.yaml")))
    A = HarnessAdapter(committed)
    out = Path(td) / "site"
    cb.build(A, out)
    models = (out / "models.html").read_text()
    check(
        "committed records: the migrated ones and gemma4-12b all render on the page",
        len(re.findall(r'<tr[^>]* data-key="', models)) == n
        and 'href="models/gemma4-12b.html"' in models
        and "not onboarded" in models,
        n,
    )
    g = (out / "models" / "gemma4-12b.html").read_text()
    check(
        "committed records: the gemma4-12b page has its build, onboarding report, settings and history",
        all(
            x in g
            for x in (
                "ollama 0.40.13",
                "Q4_K_M",
                "reasoning_effort",
                "never answered",
                "looped in its reasoning",
                "digest found",
            )
        ),
    )
    row = rows_of(models, "gemma4-12b")
    check(
        "committed records: gemma4-12b is onboarded (no arm smoked yet) and self-hosted on mac",
        'data-status="onboarded"' in row
        and 'data-where="self-hosted"' in row
        and "reasoning off" in row
        and "1024 tokens" not in row,
    )
    cli = view(A, ["models", "--model", "gemma4-12b"])
    check(
        "evh models --model gemma4-12b: its facts, build and history",
        all(
            x in cli
            for x in (
                "Gemma 4 12B",
                "ollama 0.40.13",
                "reasoning_effort: (server default) → none",
                "pass 2026-10-31 on mac",
            )
        ),
        cli,
    )
    check("evh models: every committed record listed", len(view(A, ["models"]).splitlines()) == n + 2)

sys.exit(summary())
