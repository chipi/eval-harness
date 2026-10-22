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
#
# docs/REPRODUCE.md walks through it. The harness's own verbs live in harness/Makefile
# (`make -C harness help`); this file drives the worked examples and the repository-wide checks.

PY := harness/.venv/bin/python
EXP ?=
LEVEL ?= local
ARMS ?=
CONFIG ?=

.DEFAULT_GOAL := help
.PHONY: help setup verify list plan data reproduce compare site docs browser-check

help:
	@sed -n '1,13p' Makefile | sed 's/^# \{0,1\}//'

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
