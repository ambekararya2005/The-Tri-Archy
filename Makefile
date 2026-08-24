.PHONY: help install lint fmt test atlas schema population figure dataset probe corpus gate demo clean

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
	@echo "  dataset  generate data/generated/dataset_v1.parquet (background + 8 attacks)"
	@echo "  probe    best-single-feature AUC per injector, on a small background"
	@echo "  corpus   build/inspect the committed LLM content corpus (no network)"
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

# Day 2: the labelled dataset. Prints class balance, per-attack counts and the
# best-single-feature AUC table, then writes the parquet and a manifest.
dataset:
	$(PY) -m mantis.foundry --attacks all --out data/generated/dataset_v1.parquet --show-content

# The subtlety gate on its own, against a small background. Fast enough to run
# after touching an injector.
probe:
	$(PY) -m mantis.foundry.injectors.probe

# Day 3: the text the agents read. Cache-first, so this runs identically with no
# Ollama, no GPU and no network -- see CLAUDE.md HARD RULE 3. Add --live --refresh
# to re-author it against a local model.
corpus:
	$(PY) -m mantis.foundry.llm --show

# Gate: the schema imports, the atlas validates and agrees with the injector
# registry, the population generates, the labelled dataset generates.
gate:
	$(PY) -c "from mantis.core.events import SCHEMA_VERSION; print(f'schema v{SCHEMA_VERSION} OK')"
	$(PY) -m mantis.atlas.loader
	$(PY) -c "from mantis.foundry.injectors import REGISTRY; print(f'{len(REGISTRY)} injectors, atlas agrees')"
	$(PY) -m mantis.foundry.llm
	$(PY) -m mantis.foundry.base --n 200000 --seed 7
	$(PY) -m mantis.foundry --attacks all --out data/generated/dataset_v1.parquet --show-content
	$(PY) -m pytest

# The acceptance test. Grows a stage per day; must always run end to end with
# no network, no GPU, no API key, no Kaggle token. See CLAUDE.md HARD RULE 4.
demo: schema atlas corpus population dataset test
	@echo ""
	@echo "MANTIS demo complete."
	@echo "  Day 0-1 stages: schema contract, 42-card atlas, legitimate population,"
	@echo "                  calibration figure, tests."
	@echo "  Day 2 stages:   injector framework, 8 labelled attacks, class balance,"
	@echo "                  per-attack counts, best-single-feature AUC table."
	@echo "  Day 3 stages:   schema v1.1.0 lifecycle block, LLM content corpus,"
	@echo "                  7 agentic F1 injectors split HARD/CLEAN, 15 cards."
	@echo "  Pending stages: fidelity scorecard, mandate firewall, adversary loop."

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find data/generated -type f ! -name ".gitkeep" -delete
