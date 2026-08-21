.PHONY: help install lint fmt test atlas schema gate demo clean

PY ?= python

help:
	@echo "MANTIS targets:"
	@echo "  install  install the package plus dev tools (editable)"
	@echo "  lint     ruff check"
	@echo "  fmt      ruff format + autofix imports"
	@echo "  test     pytest"
	@echo "  atlas    print the attack-atlas family summary"
	@echo "  schema   print the frozen event-schema contract"
	@echo "  gate     the Day 0 acceptance gate"
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

# Day 0 gate: the schema imports and the atlas validates.
gate:
	$(PY) -c "from mantis.core.events import TxEvent; print('schema import OK')"
	$(PY) -m mantis.atlas.loader
	$(PY) -m pytest

# The acceptance test. Grows a stage per day; must always run end to end with
# no network, no GPU, no API key, no Kaggle token. See CLAUDE.md HARD RULE 4.
demo: schema atlas test
	@echo ""
	@echo "MANTIS demo complete."
	@echo "  Day 0 stages: schema contract, attack atlas, tests."
	@echo "  Pending stages: foundry, fidelity scorecard, mandate firewall, adversary loop."

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find data/generated -type f ! -name ".gitkeep" -delete
