# Eval harness — the verbs. `make help` is the entry point.
#
# Point `data/sources/` at your inputs, write adapter.py beside this Makefile (start from
# a copy of scripts/adapter.py; call_system() is the one function to change), and the
# loop below works.

# Prefer the venv `make install` creates, so `make install` is not immediately followed by
# having to pass PYTHON=.venv/bin/python to every other target. Overridable as before.
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
VENV ?= .venv
DATASET_ID ?= smoke_v1
SYSTEM ?= demo_v1
REPEAT ?= 1
OUT ?=
NOISE ?=
TIER ?= silver

.PHONY: help demo init env-check install venv-init catalog catalog-serve serve \
        round-open round-carry round-retire round-close \
        dataset-create dataset-materialize dataset-profile dataset-items reference-manifest \
        mcp search self-test \
        reference-promote arm-smoke model-onboard score-preview importer-check capture \
        dataset-split capture-scrub label-sheet label-import sheet-import label-from-run label-from-capture pick \
        picks dataset-extend deploy-sheet arm-from-capture dataset-from-capture \
        holdout pair-test rank-stability \
        run-dry-run run sweep \
        runs-list run-compare leaderboard run-promote \
        validate format-check judge judge-score check guide-check browser-install browser-check budget-check browser-real-check guard-check commands-check catalog-render-check upgrade-check stores-check coverage ci test smoke-fixture cost-report facts-dump reader-agreement-repo clean clean-cache \
        bootstrap-test family-test import-run rescore silver-calibrate site site-check docs

# ── getting started ─────────────────────────────────────────────────────────
help:
	@echo "Eval harness — a frozen dataset, a run, a comparison, a baseline."
	@echo ""
	@echo "START HERE"
	@echo "  make install                  create $(VENV) and install deps"
	@echo "  make demo                     the whole loop on bundled data (no API key)"
	@echo "  make env-check                are my keys and caps set?"
	@echo ""
	@echo "YOUR DATA"
	@echo "  1. put your inputs in data/sources/"
	@echo "  2. cp .env.example .env       and fill in the keys you need"
	@echo "  3. make dataset-create  DATASET_ID=my_v1"
	@echo "  4. make dataset-materialize DATASET_ID=my_v1"
	@echo "  5. write adapter.py           call_system() -> YOUR system (copy scripts/adapter.py)"
	@echo "  6. evh label-from-run --run <run_id of your best arm> --set best_v1"
	@echo "     evh reference-promote --dataset-id my_v1 --labels best_v1 --tier silver --reason \"…\" --by <you>"
	@echo ""
	@echo "MEASURE  (dry-run first — it costs nothing and tells you what the sweep will)"
	@echo "  make run-dry-run SYSTEM=arm_a_v1 DATASET_ID=smoke_v1"
	@echo "  make run     SYSTEM=arm_a_v1 DATASET_ID=smoke_v1 REPEAT=3"
	@echo "  make sweep SYSTEMS=\"arm_a_v1 arm_b_v1\" DATASET_ID=smoke_v1 REPEAT=2"
	@echo ""
	@echo "TRUST THE REFERENCE?  (free — no API calls)"
	@echo "  make silver-calibrate DATASET_ID=my_v1 REF_MATCH=_v1 ARM_MATCH=_v2"
	@echo "      does a model-authored reference rank arms the way GOLD does?"
	@echo "      every arm on disk is tried as the silver author; read it against"
	@echo "      the ceiling it prints, not against 1.0"
	@echo ""
	@echo "RE-MEASURE  (free — recomputes scores from stored outputs, no API calls)"
	@echo "  make rescore DATASET_ID=my_v1 MATCH=_v2   after changing a metric (or GOAL=g ROUND=r1 WHY=\"...\")"
	@echo "  make leaderboard DATASET_ID=my_v1 ARGS='--label \"rescored <scorer>\"'   the re-scores, under their label"
	@echo ""
	@echo "RE-MEASURE WITH A VALIDATED JUDGE  (BILLED and cost-capped; --dry-run first, it is free)"
	@echo "  make judge-score DATASET_ID=my_v1 SCORER=<id> ARGS=--dry-run   calls, tokens, estimated cost"
	@echo "  make judge-score DATASET_ID=my_v1 SCORER=<id>                  resumable; verdicts are stored"
	@echo "  make leaderboard DATASET_ID=my_v1 ARGS='--label judged/<id>'          the verdicts, under their label"
	@echo ""
	@echo "ASK ONE QUESTION  (free — no API calls)"
	@echo "  make pair-test DATASET_ID=my_v1 A=<arm> B=<arm> [FAMILY=n]"
	@echo "  make family-test DATASET_ID=my_v1 A=<arm> AGAINST=<substring> [ITEMS=f]"
	@echo "      the pair: one pair you named BEFORE reading the table, sign-flip permutation"
	@echo "      the family: one arm vs a family named in advance; real Holm step-down"
	@echo "  make rank-stability DATASET_ID=my_200"
	@echo "      how many items before the ordering stops moving? measured, not assumed"
	@echo "  make holdout DATASET_ID=my_200 EXCLUDE=my_20"
	@echo "      the same significance block, minus the items the smaller set already had"
	@echo ""
	@echo "DECIDE"
	@echo "  make leaderboard DATASET_ID=my_v1        rank every arm: quality, cost, speed"
	@echo "  make run-compare BASE=<run> CAND=<run> NOISE=<measured spread>"
	@echo "  make run-promote RUN=<run> REASON=\"...\""
	@echo ""
	@echo "INSPECT / GATE"
	@echo "  make runs-list | baselines-list | validate | judge (the panel)"
	@echo "  make catalog | catalog-serve   pages over the runs; the run inspector on 127.0.0.1"
	@echo "  make serve [STORE=sqlite] [FRESH=1]   the catalog on 127.0.0.1; in SQLite a copy of data/"
	@echo ""
	@echo "SCOPING  (a dataset accumulates arms across system versions)"
	@echo "  make leaderboard DATASET_ID=my_v1 MATCH=_v2   only v2 arms"
	@echo "  make leaderboard DATASET_ID=my_v1 ARGS='--label <label>'   one label's arms (runs-list names them)"
	@echo "  make check                    validate + test + guide-check"
	@echo ""
	@echo "Read docs/INTEGRATION.md first, then docs/RUNBOOK.md."

install venv-init:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r requirements.txt
	@echo "$(VENV) ready; every target uses it."

# The inspector's browser test: Playwright and its Chromium, in this checkout's venv. A
# development extra, like the docs build: `make ci` runs without it, and CI runs
# browser-check as its own job.
browser-install:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-browser.txt
	$(VENV)/bin/python -m playwright install chromium $(ARGS)

# The inspector's budgets on this repository's runs: memory under --warm and the Workbench's reads (the mem_limit in infra/compose.yml)
# and how long an answer takes, cached and cold (tests/test_inspector_budget.py).
budget-check:
	$(PYTHON) tests/test_inspector_budget.py $(ARGS)

# The inspector's test runs on both stores (the store matrix skips every *_browser.py, so
# this is where the SQLite store meets a browser, as does browser-real-check). The viewer runs on both too: the deployed
# site's store is SQLite. The other workbench tests are files only.
browser-check:
	EVAL_STORE=files $(PYTHON) tests/test_inspector_browser.py
	EVAL_STORE=sqlite $(PYTHON) tests/test_inspector_browser.py
	$(PYTHON) tests/test_workbench_browser.py
	$(PYTHON) tests/test_workbench_live_browser.py
	$(PYTHON) tests/test_workbench_spend_browser.py
	EVAL_STORE=files $(PYTHON) tests/test_workbench_viewer_browser.py
	EVAL_STORE=sqlite $(PYTHON) tests/test_workbench_viewer_browser.py
	$(PYTHON) tests/test_workbench_replay_browser.py
	$(PYTHON) tests/test_workbench_store_browser.py
	$(PYTHON) tests/test_workbench_heldout_browser.py
	$(PYTHON) tests/test_workbench_paid_browser.py
	$(PYTHON) tests/test_inspector_names_browser.py
	$(PYTHON) tests/test_judge_gold_browser.py
	$(PYTHON) tests/test_screenshot_sticky_browser.py

# The catalog of this repository's own runs in Chromium (tests/test_catalog_real_browser.py): the
# pages at the size the deployment serves. Reuses budget-check's catalog, else builds it.
browser-real-check:
	@test -f .build/budget-catalog/index.html || $(PYTHON) scripts/cli.py catalog --out .build/budget-catalog
	EVAL_STORE=files $(PYTHON) tests/test_catalog_real_browser.py --catalog .build/budget-catalog
	EVAL_STORE=sqlite $(PYTHON) tests/test_catalog_real_browser.py --catalog .build/budget-catalog

# The checks can fail: every checker, run once over a copy of the repository with all its planted
# defects, must name each one (tests/test_checks_can_fail.py). Not in `make ci`: it proves the
# checkers' code, so CI runs it when that code changes (.github/workflows/guards.yml).
guard-check:
	$(PYTHON) tests/test_checks_can_fail.py

# The report tools and the operational commands, run as a user runs them, on data where the answer
# is known (tests/test_report_tools.py, tests/test_ops_commands.py). A few minutes, so not in
# `make ci`: CI runs it as its own job, beside verify.
commands-check:
	$(PYTHON) tests/test_report_tools.py
	$(PYTHON) tests/test_ops_commands.py

# This repository's own catalog, every page rendered on its own and over HTTP against its export, the p-value cache off,
# empty and full (tests/test_catalog_render_real.py, RFC-040). Every p of the 673 arms is drawn in four passes, about 11
# minutes of CPU together: about a third of the self-test's CPU time when it was in it, so it is not in `make check`;
# `make ci` runs it, and CI runs it as its own job, beside verify.
catalog-render-check:
	$(PYTHON) tests/test_catalog_render_real.py

# The previous release's wheel installed, a project on it per store, this tree's build installed over it, and the
# reads UPGRADING ends on (tests/check_upgrade_install.py). Needs the network and an authenticated `gh`, and a minute
# or two, so it is not in `make ci`: run it on the release pull request (RELEASING.md, step 4b).
upgrade-check:
	$(PYTHON) tests/check_upgrade_install.py $(ARGS)

# Every test file on the sqlite store (RFC-025), each in its own process: the self-test runs them on files, and the
# store's other mode is exactly as safe as the tests that run on it (architecture review, 2026-11-06).
# SHARD=I/N runs the I-th of N parts of the files (CI runs two parts, one job each).
stores-check:
	$(PYTHON) tools/store_matrix.py --store sqlite --jobs 4 $(if $(SHARD),--shard $(SHARD))

# Line coverage under the whole self-test and commands-check, subprocesses included (pyproject.toml's
# [tool.coverage.*]): which code no test runs. Needs `coverage` (requirements-dev.txt). Measured on
# demand, not a gate; harness/docs/TESTING.md records the last result.
coverage:
	rm -rf .build/coverage && mkdir -p .build/coverage
	-HARNESS=$(CURDIR) COVERAGE_FILE=$(CURDIR)/.build/coverage/data $(PYTHON) -m coverage run tests/self_test.py > .build/coverage/self_test.log 2>&1
	-HARNESS=$(CURDIR) COVERAGE_FILE=$(CURDIR)/.build/coverage/data $(PYTHON) -m coverage run tests/test_report_tools.py > .build/coverage/report_tools.log 2>&1
	-HARNESS=$(CURDIR) COVERAGE_FILE=$(CURDIR)/.build/coverage/data $(PYTHON) -m coverage run tests/test_ops_commands.py > .build/coverage/ops_commands.log 2>&1
	HARNESS=$(CURDIR) COVERAGE_FILE=$(CURDIR)/.build/coverage/data $(PYTHON) -m coverage combine -q
	HARNESS=$(CURDIR) COVERAGE_FILE=$(CURDIR)/.build/coverage/data $(PYTHON) -m coverage report

# A new project beside this checkout: make init DIR=../my-evals ARGS="--store files --tutorial" (--store files|sqlite is required)
init:
	$(PYTHON) scripts/init_project.py $(DIR) $(ARGS)

env-check:
	@$(PYTHON) scripts/env_check.py

demo:
	@test -n "$$(ls data/sources/*.txt 2>/dev/null)" || { \
	  echo "make demo needs the bundled sample data in data/sources/."; \
	  echo "If you stripped it for a real project, start at step 1 of docs/RUNBOOK.md:"; \
	  echo "  make dataset-create DATASET_ID=my_v1"; exit 1; }
	@test -f data/datasets/$(DATASET_ID).json || \
	  $(MAKE) --no-print-directory dataset-create DATASET_ID=$(DATASET_ID) ARGS="--glob '*.txt'"
	@$(MAKE) --no-print-directory dataset-materialize DATASET_ID=$(DATASET_ID)
	@$(MAKE) --no-print-directory run SYSTEM=$(SYSTEM) DATASET_ID=$(DATASET_ID) REPEAT=3 ARGS="--scratch"
	@$(MAKE) --no-print-directory validate
	@echo ""
	@echo "Now: read the spread the run printed above. It is a scratch pass under .build/scratch/runs: runs-list and leaderboard do not read it."

# ── data lifecycle ──────────────────────────────────────────────────────────
dataset-create:
	$(PYTHON) scripts/cli.py dataset-create --dataset-id $(DATASET_ID) $(ARGS)

dataset-materialize:
	$(PYTHON) scripts/cli.py dataset-materialize --dataset-id $(DATASET_ID) $(ARGS)

# What is inside a dataset, without its text (data/profiles/<id>.json): written where it is
# materialized, committed, read by the dataset page and dataset-items.
dataset-profile:
	$(PYTHON) scripts/cli.py dataset-profile --dataset-id $(DATASET_ID) $(ARGS)

dataset-items:
	$(PYTHON) scripts/cli.py dataset-items $(DATASET_ID) $(ARGS)

# Gold a fetch script builds, promoted where it is: its manifest, with whose labels they are and why.
reference-manifest:
	$(PYTHON) scripts/cli.py reference-manifest $(ARGS)

# ── the commands added in 0.5.0 and 0.6.0, each with its own flags in ARGS ─────────────────────────────
# promote a label set's labels to a reference, at a tier, with a reason
reference-promote:
	$(PYTHON) scripts/cli.py reference-promote $(ARGS)

# smoke an arm on a few items before its full run: checks, projection, flags
arm-smoke:
	$(PYTHON) scripts/cli.py arm-smoke $(ARGS)

# onboard a model once: probe a deployment, write what was found into its record
model-onboard:
	$(PYTHON) scripts/cli.py model-onboard $(ARGS)

# what the scorer in this tree would move in a goal's decision; writes nothing
score-preview:
	$(PYTHON) scripts/cli.py score-preview $(ARGS)

# check an importer: its records are well-formed, ids unique, two reads the same
importer-check:
	$(PYTHON) scripts/cli.py importer-check $(ARGS)

# keep a production system's records as a capture (data/captures/)
capture:
	$(PYTHON) scripts/cli.py capture $(ARGS)

# split a dataset into <id>_validation and <id>_test, stable across versions
dataset-split:
	$(PYTHON) scripts/cli.py dataset-split $(ARGS)

# run the project's own scrubber over a capture's records, and record it
capture-scrub:
	$(PYTHON) scripts/capture_scrub.py $(ARGS)



# a sheet of a dataset's items to label, with what production or an arm decided
label-sheet:
	$(PYTHON) scripts/cli.py label-sheet $(ARGS)

# a filled label sheet as a person's label set
label-import:
	$(PYTHON) scripts/cli.py label-import $(ARGS)

# a sheet filled elsewhere, read back: labels as a label set, picks or scores as judged runs
sheet-import:
	$(PYTHON) scripts/cli.py sheet-import $(ARGS)

# a finished run's outputs as a model's label set (calls nothing)
label-from-run:
	$(PYTHON) scripts/cli.py label-from-run $(ARGS)

# rules over a capture's recorded outcomes as a rule label set
label-from-capture:
	$(PYTHON) scripts/cli.py label-from-capture $(ARGS)

# pick production items for the next version of governed datasets, or drop a pick
pick:
	$(PYTHON) scripts/cli.py pick $(ARGS)

# the picks waiting: per target, where each came from, its labels, tags and note
picks:
	$(PYTHON) scripts/cli.py picks $(ARGS)

# the next version of a dataset: its items and the picks you choose
dataset-extend:
	$(PYTHON) scripts/cli.py dataset-extend $(ARGS)

# what production must match to run a promoted arm, and whether a capture says it did
deploy-sheet:
	$(PYTHON) scripts/cli.py deploy-sheet $(SYSTEM) $(ARGS)

# production's recorded decisions as an arm, scored like any (no call)
arm-from-capture:
	$(PYTHON) scripts/cli.py arm-from-capture $(ARGS)

# make a dataset version from a capture: choose records, freeze their bodies as items
dataset-from-capture:
	$(PYTHON) scripts/cli.py dataset-from-capture $(ARGS)



# Does the installed harness work here? (in a checkout: the full test suite)
self-test:
	$(PYTHON) scripts/self_check.py $(ARGS)

# ── evals ───────────────────────────────────────────────────────────────────
run-dry-run:
	$(PYTHON) scripts/cli.py run --system $(SYSTEM) --dataset $(DATASET_ID) --repeat $(REPEAT) --dry-run

run:
	$(PYTHON) scripts/cli.py run --system $(SYSTEM) --dataset $(DATASET_ID) --repeat $(REPEAT) $(ARGS)

# SYSTEMS is a list of system ids: make sweep SYSTEMS="arm_a_v1 arm_b_v1" DATASET_ID=smoke_v1
sweep:
	@test -n "$(SYSTEMS)" || { echo 'SYSTEMS="arm_a_v1 arm_b_v1" is required'; exit 1; }
	$(PYTHON) scripts/cli.py sweep --systems $(SYSTEMS) --dataset $(DATASET_ID) --repeat $(REPEAT) $(ARGS)

# ── inspect and decide ──────────────────────────────────────────────────────
runs-list:
	@$(PYTHON) scripts/cli.py runs-list


# Re-score finished runs from their stored outputs. No API calls, no money: the outputs
# are the expensive part, the scores are arithmetic over them. Writes to a SEPARATE
# directory so the originals -- the record of what was measured and paid for -- stay put.
# Is a MODEL-AUTHORED reference a usable stand-in for a trusted one? Free: every arm on
# disk is already a candidate silver author, since "author silver with model X using the
# same prompt and settings" is exactly what X produced. Read the result against the
# CEILING it prints -- two runs against the same gold do not agree perfectly either.
silver-calibrate:
	$(PYTHON) scripts/cli.py silver-calibrate --dataset-id $(DATASET_ID) \
	  $(if $(REF_MATCH),--ref-match $(REF_MATCH),) $(if $(ARM_MATCH),--arm-match $(ARM_MATCH),) \
	  $(if $(METRIC),--metric $(METRIC),) $(if $(GROUP_BY),--group-by $(GROUP_BY),)

# Without OUT the re-scores land where the tool designates (data/runs-rescored/<scorer>/<source>/, RFC-022).
rescore:
	$(PYTHON) scripts/cli.py rescore $(if $(ROUND),--goal $(GOAL) --round $(ROUND) --why "$(WHY)",--dataset-id $(DATASET_ID)) $(if $(MATCH),--match $(MATCH),) $(if $(REFERENCE),--reference-id $(REFERENCE),)

# What each arm actually cost, from `_meta.usage.cost` rather than the price table in
# its yaml. Added because RUNBOOK §7b documented this verb before it existed.
cost-report:
	$(PYTHON) scripts/cli.py cost-report $(ARGS)

# The facts every reader states (value, runs, direction, latest run, reference, cost state, baseline, public), from
# `evh <command> --json` alone, as one JSON document: run it under each version a project has and compare with
# `make facts-dump ARGS="--diff old.json new.json"` (tools/facts_dump.py; standard library only, so it also runs
# under an installed evh with another interpreter: `python tools/facts_dump.py --evh evh --project <dir>`).
facts-dump:
	$(PYTHON) tools/facts_dump.py $(ARGS)

# Every reader (CLI, API, MCP, catalog export, inspector) asked for the same facts of this repository's own data, on a
# copy in a temporary folder (nothing is written to data/). PROJECT names another project root (config.yaml and data/).
PROJECT ?= $(CURDIR)
reader-agreement-repo:
	EVH_AGREE_PROJECT=$(PROJECT) $(PYTHON) tests/test_reader_agreement.py


leaderboard:
	$(PYTHON) scripts/cli.py leaderboard $(DATASET_ID) $(if $(MATCH),--match $(MATCH),) $(ARGS)

# A dataset grown from a smaller one contains it. Arms chosen on the small set are being
# re-measured on a set that still holds the items that chose them, so "it replicated" can
# only be read on the rest.
holdout:
	$(PYTHON) scripts/cli.py holdout --dataset-id $(DATASET_ID) \
	  $(if $(EXCLUDE),--exclude-dataset $(EXCLUDE),) $(if $(METRIC),--metric $(METRIC),) \
	  $(if $(MATCH),--match $(MATCH),)

# How many items does a ranking actually need? Two DISJOINT halves of n items, ranked
# independently, correlated against each other — neither treated as truth. Free: it reads
# runs already on disk. The answer here was sobering, which is the point.
rank-stability:
	$(PYTHON) scripts/cli.py rank-stability $(DATASET_ID) \
	  $(if $(METRIC),--metric $(METRIC),) $(if $(MATCH),--match $(MATCH),)

# ONE pair, named before the table was read. The leaderboard's Nemenyi line prices in all
# k(k-1)/2 comparisons; a decision you came in with is one comparison and should not pay
# for the 275 nobody made. FAMILY=n applies BONFERRONI (alpha/n) -- one pair cannot do
# Holm, which needs the whole family's p-values at once. Use family-test for that.
# ITEMS=<file> restricts the test to one stratum, one item_id per line.
pair-test:
	@test -n "$(A)" -a -n "$(B)" || { echo 'A=<config_id> B=<config_id> are required'; exit 1; }
	$(PYTHON) scripts/cli.py pair-test $(DATASET_ID) --a $(A) --b $(B) \
	  $(if $(METRIC),--metric $(METRIC),) $(if $(EXCLUDE),--exclude-dataset $(EXCLUDE),) \
	  $(if $(FAMILY),--family $(FAMILY),) \
	  $(if $(ITEMS),--items $(ITEMS),) $(if $(ASC),--asc,)

# MACRO-F1 and friends: metrics with no per-item value, so the sign-flip test cannot
# take them. Paired bootstrap over items instead. ANTI-CONSERVATIVE relative to the exact
# test (11 vs 8 separations on the same data) -- read the interval, not the p-value.
bootstrap-test:
	@test -n "$(A)" -a -n "$(AGAINST)" || { echo 'A=<config_id> AGAINST=<substring> are required'; exit 1; }
	$(PYTHON) scripts/cli.py bootstrap-test --dataset-id $(DATASET_ID) --a $(A) --against $(AGAINST) \
	  $(if $(METRIC),--metric $(METRIC),) $(if $(EXCLUDE),--exclude-dataset $(EXCLUDE),) \
	  $(if $(ITEMS),--items $(ITEMS),) $(if $(DRAWS),--draws $(DRAWS),)

# ONE arm against a DECLARED family of opponents, with the real Holm step-down rather than
# Bonferroni -- this has every p-value at once, so it can afford the looser later steps and
# rejects at least everything Bonferroni would. AGAINST=<substring> names the family, and
# naming it before reading the p-values is the honesty condition the correction assumes.
family-test:
	@test -n "$(A)" -a -n "$(AGAINST)" || { echo 'A=<config_id> AGAINST=<substring> are required'; exit 1; }
	$(PYTHON) scripts/cli.py family-test $(DATASET_ID) --a $(A) --against $(AGAINST) \
	  $(if $(METRIC),--metric $(METRIC),) $(if $(EXCLUDE),--exclude-dataset $(EXCLUDE),) \
	  $(if $(ITEMS),--items $(ITEMS),) \
	  $(if $(ASC),--asc,)

# Per-item scores made by ANOTHER tool, written as a run the tests above can read. Every
# flag is required except where marked; see scripts/cli.py import-run for what it refuses.
import-run:
	$(PYTHON) scripts/cli.py import-run $(ARGS)

run-compare:
	@test -n "$(BASE)" || { echo "BASE=<run_id> is required (see: make runs-list)"; exit 1; }
	@test -n "$(CAND)" || { echo "CAND=<run_id> is required (see: make runs-list)"; exit 1; }
	$(PYTHON) scripts/cli.py run-compare --baseline $(BASE) --candidate $(CAND) \
	  $(if $(NOISE),--noise $(NOISE),) $(ARGS)

# REASON reaches the script through the ENVIRONMENT, not the command line. Interpolated
# into the recipe it was re-parsed by the shell, so backticks in a reason EXECUTED and an
# embedded double quote silently mangled the text -- and a baseline's reason is a
# permanent record of why a number was promoted. A target-specific `export` hands the
# value over verbatim, with no shell in between.
run-promote: export EVAL_PROMOTE_REASON = $(REASON)
run-promote:
	@test -n "$(RUN)" || { echo "RUN=<run_id> is required (see: make runs-list)"; exit 1; }
	@test -n "$$EVAL_PROMOTE_REASON" || { echo 'REASON="why this run earned it" is required'; exit 1; }
	$(PYTHON) scripts/cli.py run-promote --run $(RUN) --reason "$$EVAL_PROMOTE_REASON" $(ARGS)

# ── gates ───────────────────────────────────────────────────────────────────
validate:
	$(PYTHON) scripts/cli.py validate

# The data is in the format this release reads (RFC-032): the deploy's gate (render.sh), met here first.
format-check:
	$(PYTHON) scripts/cli.py migrate --check

# THE CATALOG AND THE RUN INSPECTOR (ADR-0002): static pages over the runs, by dataset, into
# .build/catalog/ (counts and means only; item text only where a profile publishes it); then a server on 127.0.0.1
# that tests any arms on one dataset against a baseline with the same paired test as pair-test.
catalog:
	$(PYTHON) scripts/cli.py catalog $(ARGS)

catalog-serve:  # renders its pages on request (RFC-040): nothing to build first
	$(PYTHON) scripts/catalog_serve.py $(ARGS)

# The whole thing on 127.0.0.1, to try it: the catalog (rendered on request, RFC-040) and the run inspector over this
# project's data. STORE=sqlite
# serves a SQLite copy of data/ (.build/serve-sqlite/data/project.sqlite, made once by data-migrate; FRESH=1 makes it
# again), so trying it never touches the tracked files.
SERVE_COPY := .build/serve-sqlite
serve:
ifeq ($(STORE),sqlite)
	@if [ -n "$(FRESH)" ] || [ ! -f $(SERVE_COPY)/data/project.sqlite ]; then \
	  rm -rf $(SERVE_COPY) && mkdir -p $(SERVE_COPY) && cp -r data $(SERVE_COPY)/data && \
	  EVAL_DATA_DIR=$(SERVE_COPY)/data EVAL_STORE=sqlite $(PYTHON) scripts/cli.py data-migrate --to sqlite; fi
	EVAL_DATA_DIR=$(SERVE_COPY)/data EVAL_STORE=sqlite $(PYTHON) scripts/catalog_serve.py --build-dir $(SERVE_COPY)/catalog $(ARGS)
else
	$(PYTHON) scripts/catalog_serve.py $(ARGS)
endif

# The read commands as MCP tools, for an agent (RFC-018): stdio, or ARGS="--http ..." for a team.
mcp:
	$(PYTHON) scripts/mcp_server.py $(ARGS)

# The catalog's search in the terminal: TEXT="words".
search:
	@test -n "$(TEXT)" || { echo "TEXT=<words> is required"; exit 1; }
	$(PYTHON) scripts/cli.py search $(TEXT) $(ARGS)









# EVAL ROUNDS (ADR-0004), optional: a round of a goal, its decisions as commands.
# make round-open GOAL=g DATASET_ID=d ARGS='--from r1 --hypothesis "..." --keep a,b --retire c --reason "..."'
round-open:
	@test -n "$(GOAL)" -a -n "$(DATASET_ID)" || { echo "GOAL=<goal_id> DATASET_ID=<dataset> are required"; exit 1; }
	$(PYTHON) scripts/cli.py round-open --goal $(GOAL) --dataset $(DATASET_ID) $(ARGS)

round-carry:
	$(PYTHON) scripts/cli.py round-carry --goal $(GOAL) --round $(ROUND) $(ARGS)

round-retire:
	$(PYTHON) scripts/cli.py round-retire --goal $(GOAL) --round $(ROUND) $(ARGS)

round-close:
	$(PYTHON) scripts/cli.py round-close --goal $(GOAL) --round $(ROUND) $(ARGS)


# MATERIALIZE THE DEMO DATASET FIRST, or eleven assertions silently skip.
#
# `data/materialized/` is regenerated rather than committed, so in a FRESH CLONE
# smoke_v1 is absent, the demo arm cannot run, and the resume and cost-cap tests skip
# themselves -- honestly, but they skip. That is the whole of this harness's
# crash-durability and spend-guard coverage, absent for anyone who is not the author.
# smoke_v1's sources ARE committed (they are synthetic), so rebuilding it costs nothing
# and is deterministic: `all hashes verified` or the build fails.
#
# `-` so a machine that cannot materialize still runs the rest of the suite.
smoke-fixture:
	@test -d data/materialized/smoke_v1 || $(PYTHON) scripts/cli.py dataset-materialize --dataset-id smoke_v1 >/dev/null 2>&1 || true
# ...and the summarisation slice when its sources are present, because the two
# corpus tests need it materialized as well as fetched. The setup note said
# `fetch.py` was enough; it is not. Found by external review.
	@test ! -d data/sources/cnn_dailymail_200 || test -d data/materialized/cnn_dailymail_200 || \
	  $(PYTHON) scripts/cli.py dataset-materialize --dataset-id cnn_dailymail_200 >/dev/null 2>&1 || true

test: smoke-fixture
	$(PYTHON) tests/self_test.py

# docs/GUIDE.md run in a fresh project, every quoted output compared: the onboarding path
# a new reader follows cannot drift from what the commands print.
guide-check:
	$(PYTHON) tests/check_guide.py

check: format-check validate test guide-check
	@echo ""
	@echo "check: tree valid, self-tests pass, the GUIDE runs as written"

# THE SITE IS GENERATED FROM THE RUNS. A stale site/public -- a run added, a report
# figure changed, the build script edited without rebuilding -- fails here, so the public
# front door can never quietly disagree with the data. Rebuild with `make site`.
site:
	$(PYTHON) ../site/build.py

site-check:
	$(PYTHON) ../site/build.py --check

# The documentation site (published to GitHub Pages, evals.humancopilot.eu/docs). Needs
# `pip install -r ../site/requirements-docs.txt`; not part of `make ci`, which must run
# without it, but the Pages workflow builds it in strict mode on every deploy.
docs:
	cd .. && mkdocs build --strict

ci: check catalog-render-check site-check
	@echo "ci: green"

# The judging PASS (ADR-0001): a validated LLM judge re-measures every arm's frozen outputs,
# listwise and blind, into data/runs-judged/<SCORER>/. Billed, capped (the scorer's
# cost_cap_usd, EVAL_MAX_COST_USD), resumable. ARGS=--dry-run prices it without calling
# anything; ARGS=--no-calls re-reads stored verdicts for $0.
judge-score:
	@test -n "$(SCORER)" || { echo 'SCORER=<id in data/scorers/> is required'; exit 1; }
	$(PYTHON) scripts/cli.py judge-score --dataset-id $(DATASET_ID) --scorer $(SCORER) $(ARGS)

# ── housekeeping ────────────────────────────────────────────────────────────
clean:
	# NEVER delete a tracked file. `rm -rf data/runs/*` used to take data/runs/README.md with
	# it — the file documenting what a run directory IS — while the line below reassured you
	# about the directories it had NOT touched; four per-directory READMEs were lost that way.
	# It would now also delete the shipped worked example, and with it the run the committed
	# baseline points at, so `make clean` would leave the tree failing its own V6.
	#
	# "Is it tracked?" is the right question, not "is it named README.md": git already knows
	# which files someone decided to keep.
	@find data/materialized data/runs -mindepth 1 -maxdepth 1 -print 2>/dev/null \
	  | while read -r f; do \
	      git ls-files --error-unmatch "$$f" >/dev/null 2>&1 || rm -rf "$$f"; \
	    done
	@rm -rf out/
	@echo "cleaned materialized/, runs/ and out/ — every TRACKED file kept (READMEs, the shipped worked example, sources, datasets, references, baselines)"

clean-cache:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "cleaned __pycache__"
