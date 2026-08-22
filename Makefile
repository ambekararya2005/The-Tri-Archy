.PHONY: help install lint fmt test atlas schema population figure gate demo clean

PY ?= python

help:
	@echo "MANTIS targets:"
	@echo "  install  install the package plus dev tools (editable)"
	@echo "  lint     ruff check"
	@echo "  fmt      ruff format + autofix imports"
	@echo "  test     pytest"
	@echo "  atlas    print the attack-atlas family summary"
	@echo "  schema   print the frozen event-schema contract"
	@echo "  population  generate data/generated/population.parquet (200k events)"
	@echo "  figure   redraw the calibration figure from the existing parquet"
	@echo "  gate     the daily acceptance gate"
	@echo "  demo     THE acceptance test - must pass from a clean clone"

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

test:
	$(PY) -m pytest

atlas:
	$(PY) -m mantis.atlas.loader

schema:
	$(PY) -m mantis.core.events

# Day 1: the calibrated legitimate population. No network, no Kaggle token.
population:
	$(PY) -m mantis.foundry.base --n 200000 --seed 7

figure:
	$(PY) -m mantis.foundry.base.calibration

# Gate: the schema imports, the atlas validates, the population generates.
gate:
	$(PY) -c "from mantis.core.events import TxEvent; print('schema import OK')"
	$(PY) -m mantis.atlas.loader
	$(PY) -m mantis.foundry.base --n 200000 --seed 7
	$(PY) -m pytest

# The acceptance test. Grows a stage per day; must always run end to end with
# no network, no GPU, no API key, no Kaggle token. See CLAUDE.md HARD RULE 4.
demo: schema atlas population test
	@echo ""
	@echo "MANTIS demo complete."
	@echo "  Day 0-1 stages: schema contract, 42-card atlas, legitimate population,"
	@echo "                  calibration figure, tests."
	@echo "  Pending stages: injectors, fidelity scorecard, mandate firewall, adversary loop."

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find data/generated -type f ! -name ".gitkeep" -delete
