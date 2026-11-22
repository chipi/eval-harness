# Reproduce this repository's evals. Run from the repository root.
#
#   make verify                          every number in every report, from the committed runs
#   make list                            the evals, their arms and what they cost
#   make plan      EXP=scifact           what a rerun involves, before anything is spent
#   make data      EXP=scifact           environment + public data + hash check
#   make reproduce EXP=scifact LEVEL=local      (local | baselines | hosted | all)
#   make compare   EXP=scifact           the replication card: does every finding hold?
#   make reproduce EXP=scifact SYSTEM=path/to/sf_mine_v1.yaml  add a model of your own (a system id or file)
#   make serve [STORE=sqlite]   the catalog and inspector on 127.0.0.1 (in SQLite, a copy of the data)
#   make serve-dev / mcp-dev    the same, or the MCP server, reporting to the dev observability (environment=dev,
#                               worktree=<branch>); read what the branch sent with the o11y-dev skill before a PR
#   make browser-check                   the inspector and the public site in headless Chromium
#   make guard-check                     the checks can fail: each checker catches its planted defects
#   make quality                         lint, types, security, dead code, docstrings, spelling, shell, llms.txt
#   make llms                            llms.txt, the agent-facing index of the docs (tools/llms_txt.py)
#   make deploy-dry, then make deploy    the production deploy (a merge to main deploys nothing); deploy refuses without a dry run
#
# docs/REPRODUCE.md walks through it. The harness's own verbs live in harness/Makefile
# (`make -C harness help`); this file drives the worked examples and the repository-wide checks.

PY := harness/.venv/bin/python
BIN := harness/.venv/bin
EXP ?=
LEVEL ?= local
ARMS ?=
SYSTEM ?=

.DEFAULT_GOAL := help
.PHONY: help setup verify list plan data reproduce compare site docs deploy-dry deploy deploy-check serve serve-dev mcp-dev obs-vendor llms llms-check browser-check browser-real-check budget-check guard-check commands-check stores-check \
	quality-install quality lint format type security audit-locks deadcode docstrings spelling shell complexity

help:
	@sed -n '1,20p' Makefile | sed 's/^# \{0,1\}//'

$(PY):
	$(MAKE) -C harness install

setup: $(PY)

verify: $(PY)
	$(MAKE) -C harness ci

list: $(PY)
	@$(PY) examples/reproduce.py list

define need_exp
	@if [ -z "$(EXP)" ]; then echo "EXP= is required. One of:"; $(PY) examples/reproduce.py list; exit 2; fi
endef

plan: $(PY)
	$(need_exp)
	@$(PY) examples/reproduce.py plan $(EXP) --level $(LEVEL) $(if $(ARMS),--arms $(ARMS))

data: $(PY)
	$(need_exp)
	@$(PY) examples/reproduce.py data $(EXP)

reproduce: $(PY)
	$(need_exp)
	@$(PY) examples/reproduce.py run $(EXP) --level $(LEVEL) $(if $(ARMS),--arms $(ARMS)) $(if $(SYSTEM),--system $(SYSTEM))

compare: $(PY)
	$(need_exp)
	@$(PY) examples/reproduce.py compare $(EXP)

site: $(PY)
	$(MAKE) -C harness site

# The front ends in headless Chromium: the catalog and run inspector, the Workbench mockup, then the public site
# served with production's headers. Needs `make -C harness browser-install` once.
serve: $(PY)
	$(MAKE) -C harness serve STORE=$(STORE) FRESH=$(FRESH) ARGS="$(ARGS)"

browser-check: $(PY)
	$(MAKE) -C harness browser-check
	$(PY) site/test_browser.py

guard-check: $(PY)
	$(MAKE) -C harness guard-check

browser-real-check: $(PY)
	$(MAKE) -C harness browser-real-check

commands-check: $(PY)
	$(MAKE) -C harness commands-check

stores-check: $(PY)
	$(MAKE) -C harness stores-check

# The inspector's budgets: the harness alone, then with this deployment's hooks and their SDKs
# (infra/inspector/), vendored into .build/vendor as render.sh vendors them for prod.
# This deployment's observability SDKs (infra/inspector/requirements.txt), vendored into harness/.build/vendor as
# render.sh vendors them for prod: pure-Python wheels, pinned, on PYTHONPATH; nothing goes into the venv.
obs-vendor: $(PY)
	$(PY) -m pip install --quiet --no-deps --no-compile --target harness/.build/vendor --upgrade \
	  --only-binary=:all: --platform any --implementation py --python-version 3.12 \
	  -r infra/inspector/requirements.txt

# Dev observability (agentic-ai-homelab docs/recipes/o11y-dev.md): the servers with this deployment's hooks in dev
# mode (infra/inspector/hooks_env.py): errors to GlitchTip evals-dev, traces to VictoriaTraces, log lines to
# VictoriaLogs, each labelled environment=dev and worktree=<this branch>. Settings from
# ~/.config/evals/observability-dev.env (infra/README.md says what it holds), never from the repository.
serve-dev: obs-vendor
	EVALS_ENV=dev PYTHONPATH=$(abspath harness/.build/vendor) $(MAKE) -C harness serve STORE=$(STORE) FRESH=$(FRESH) \
	  ARGS="--hooks $(abspath infra/inspector/hooks.py) $(ARGS)"

mcp-dev: obs-vendor
	EVALS_ENV=dev PYTHONPATH=$(abspath harness/.build/vendor) $(MAKE) -C harness mcp \
	  ARGS="--http --hooks $(abspath infra/mcp/hooks.py) $(ARGS)"

budget-check: obs-vendor
	$(MAKE) -C harness budget-check
	printf 'SENTRY_DSN=http://k@127.0.0.1:9/1\nOTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:9/v1/traces\n' > harness/.build/obs-unreachable.env
	cd harness && PYTHONPATH=.build/vendor EVALS_OBS_ENV=.build/obs-unreachable.env $(abspath $(PY)) tests/test_inspector_budget.py --catalog .build/budget-catalog --hooks ../infra/inspector/hooks.py
	# This deployment's hooks with the same SDKs: which requests become traces.
	PYTHONPATH=harness/.build/vendor $(abspath $(PY)) infra/inspector/test_hooks.py
	# Dev and prod observability for both servers (hooks_env.py): the labels, the refusals, Umami prod only.
	PYTHONPATH=harness/.build/vendor $(abspath $(PY)) infra/inspector/test_hooks_env.py

docs:
	mkdocs build --strict

# A merge to main deploys nothing (deploy-prod.yml has no push trigger). `deploy-dry` dispatches it with
# dry_run=true on origin/main's head and watches it; `deploy` dispatches the real one and refuses unless a dry
# run of that same commit passed (infra/deploy/dispatch.sh). Needs an authenticated `gh`.
deploy-dry:
	bash infra/deploy/dispatch.sh dry

deploy:
	bash infra/deploy/dispatch.sh real

deploy-check:
	PYTHON=$(abspath $(PY)) bash infra/deploy/test_dispatch.sh

# ── code quality ─────────────────────────────────────────────────────────────────────────
# The tools are pinned in harness/requirements-dev.txt. Every gate fails the target; only
# `complexity` reports. Ruff and codespell run from here (their config is at the root),
# mypy and interrogate from harness/ (theirs is in harness/pyproject.toml).
SPELLED := '*.py' '*.md' '*.sh' '*.yml' '*.yaml' '*.toml' '*.html' '*.js' '*.css' '*.txt' \
	':!:harness/data/**' ':!:examples/*/data/**' ':!:harness/workbench/mockup/mock.js'

# llms.txt (llmstxt.org), made from tools/llms.in.txt and the docs' titles and status lines: `llms` writes it,
# `llms-check` fails when it is stale, a link, an anchor or a path in it does not resolve, or a per-type index
# misses one of its documents (the guard proves each: harness/tests/test_checks_can_fail.py).
llms: $(PY)
	$(PY) tools/llms_txt.py

llms-check: $(PY)
	$(PY) tools/llms_txt.py --check

quality-install: $(PY)
	$(BIN)/pip install -q -r harness/requirements-dev.txt

quality: lint type security deadcode docstrings spelling shell complexity llms-check

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:
	$(BIN)/ruff format .

type:
	cd harness && .venv/bin/mypy

# Medium severity and up. Each accepted finding carries `# nosec <id>` and its reason on the line.
security:
	$(BIN)/bandit -q -r harness examples site docs infra -ll -x '*/.venv/*,*/node_modules/*,*/.build/*'
	$(BIN)/pip-audit --progress-spinner off -r harness/requirements.txt \
		-r harness/requirements-browser.txt -r harness/requirements-dev.txt -r site/requirements-docs.txt

# The examples' uv.lock files, audited per platform (a plain pip-audit skips every fork but this
# machine's). Reported, not failed: upgrading a pin changes the instrument. Needs uv.
audit-locks:
	$(PY) examples/audit_locks.py

deadcode:
	$(BIN)/vulture harness/scripts harness/tests harness/tools examples site --min-confidence 80 --exclude '*/.venv/*'

docstrings:
	cd harness && .venv/bin/interrogate scripts tests tools

spelling:
	git ls-files -z -- $(SPELLED) | xargs -0 $(BIN)/codespell

shell:
	git ls-files -z -- '*.sh' | xargs -0 $(BIN)/shellcheck
	$(BIN)/actionlint -shellcheck $(BIN)/shellcheck

complexity:
	$(BIN)/radon cc harness/scripts harness/tests harness/tools -nc -s --total-average
