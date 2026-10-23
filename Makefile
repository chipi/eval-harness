# Reproduce this repository's experiments. Run from the repository root.
#
#   make verify                          every number in every report, from the committed runs
#   make list                            the experiments, their arms and what they cost
#   make plan      EXP=scifact           what a rerun involves, before anything is spent
#   make data      EXP=scifact           environment + public data + hash check
#   make reproduce EXP=scifact LEVEL=local      (local | baselines | hosted | all)
#   make compare   EXP=scifact           the replication card: does every finding hold?
#   make reproduce EXP=scifact CONFIG=path/to/your_arm.yaml    add a model of your own
#   make browser-check                   the inspector and the public site in headless Chromium
#   make quality                         lint, types, security, dead code, docstrings, spelling, shell
#
# docs/REPRODUCE.md walks through it. The harness's own verbs live in harness/Makefile
# (`make -C harness help`); this file drives the worked examples and the repository-wide checks.

PY := harness/.venv/bin/python
BIN := harness/.venv/bin
EXP ?=
LEVEL ?= local
ARMS ?=
CONFIG ?=

.DEFAULT_GOAL := help
.PHONY: help setup verify list plan data reproduce compare site docs browser-check \
	quality-install quality lint format type security audit-locks deadcode docstrings spelling shell complexity

help:
	@sed -n '1,14p' Makefile | sed 's/^# \{0,1\}//'

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
	@$(PY) examples/reproduce.py run $(EXP) --level $(LEVEL) $(if $(ARMS),--arms $(ARMS)) $(if $(CONFIG),--config $(CONFIG))

compare: $(PY)
	$(need_exp)
	@$(PY) examples/reproduce.py compare $(EXP)

site: $(PY)
	$(MAKE) -C harness site

# Both front ends in headless Chromium: the catalog and run inspector, then the public site
# served with production's headers. Needs `make -C harness browser-install` once.
browser-check: $(PY)
	$(MAKE) -C harness browser-check
	$(PY) site/test_browser.py

docs:
	mkdocs build --strict

# ── code quality ─────────────────────────────────────────────────────────────────────────
# The tools are pinned in harness/requirements-dev.txt. Every gate fails the target; only
# `complexity` reports. Ruff and codespell run from here (their config is at the root),
# mypy and interrogate from harness/ (theirs is in harness/pyproject.toml).
SPELLED := '*.py' '*.md' '*.sh' '*.yml' '*.yaml' '*.toml' '*.html' '*.js' '*.css' '*.txt' \
	':!:harness/data/**' ':!:examples/*/data/**'

quality-install: $(PY)
	$(BIN)/pip install -q -r harness/requirements-dev.txt

quality: lint type security deadcode docstrings spelling shell complexity

lint:
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:
	$(BIN)/ruff format .

type:
	cd harness && .venv/bin/mypy

# Medium severity and up. Each accepted finding carries `# nosec <id>` and its reason on the line.
security:
	$(BIN)/bandit -q -r harness examples site docs infra -ll -x '*/.venv/*,*/node_modules/*'
	$(BIN)/pip-audit --progress-spinner off -r harness/requirements.txt \
		-r harness/requirements-browser.txt -r harness/requirements-dev.txt -r site/requirements-docs.txt

# The examples' uv.lock files, audited per platform (a plain pip-audit skips every fork but this
# machine's). Reported, not failed: upgrading a pin changes the instrument. Needs uv.
audit-locks:
	$(PY) examples/audit_locks.py

deadcode:
	$(BIN)/vulture harness/scripts harness/judges.py harness/runner.py examples site --min-confidence 80 --exclude '*/.venv/*'

docstrings:
	cd harness && .venv/bin/interrogate scripts judges.py runner.py

spelling:
	git ls-files -z -- $(SPELLED) | xargs -0 $(BIN)/codespell

shell:
	git ls-files -z -- '*.sh' | xargs -0 $(BIN)/shellcheck
	$(BIN)/actionlint -shellcheck $(BIN)/shellcheck

complexity:
	$(BIN)/radon cc harness/scripts harness/judges.py harness/runner.py -nc -s --total-average
