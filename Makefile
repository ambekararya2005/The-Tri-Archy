.PHONY: help install lint fmt test atlas schema population figure dataset probe corpus \n        features l0 firewall drift slices gate demo clean

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
	@echo "  features build the feature matrix and print the leakage assertion firing"
	@echo "  l0       run the deterministic clauses + the Day 3 bucket-contract verdict"
	@echo "  firewall THE Day 4 experiment: L1, L2, leave-one-family-out -> RESULTS.md"
	@echo "  drift    every marginal vs the reference, against a sampling-noise band"
	@echo "  slices   audit every probe_slice and print its denominator"
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

# Day 4: the Mandate Firewall.

# The feature layer, with the three-tier leakage assertion fired deliberately so
# a reader can watch it reject a label.
features:
	$(PY) -m mantis.defense.features

# L0's per-clause precision and FP rate, then the Day 3 HARD/CLEAN contract
# checked against a real L0 for the first time.
l0:
	$(PY) -m mantis.defense.l0_rules

# THE Day 4 deliverable. Pools five seeds, fits L1 and L2, runs
# leave-one-family-out, and writes RESULTS.md. ~10 minutes from a cold pool.
firewall:
	$(PY) -m mantis.defense

# Day 4 carry-overs: distribution drift, and the probe-slice audit.
drift:
	$(PY) scripts/drift_check.py

slices:
	$(PY) scripts/audit_probe_slices.py

# Gate: the schema imports, the atlas validates and agrees with the injector
# registry, the population generates, the labelled dataset generates.
gate:
	$(PY) -c "from mantis.core.events import SCHEMA_VERSION; print(f'schema v{SCHEMA_VERSION} OK')"
	$(PY) -m mantis.atlas.loader
	$(PY) -c "from mantis.foundry.injectors import REGISTRY; print(f'{len(REGISTRY)} injectors, atlas agrees')"
	$(PY) -m mantis.foundry.llm
	$(PY) -m mantis.foundry.base --n 200000 --seed 7
	$(PY) -m mantis.foundry --attacks all --out data/generated/dataset_v1.parquet --show-content
	$(PY) -m mantis.defense.l0_rules
	$(PY) -m pytest

# The acceptance test. Grows a stage per day; must always run end to end with
# no network, no GPU, no API key, no Kaggle token. See CLAUDE.md HARD RULE 4.
demo: schema atlas corpus population dataset features l0 test
	@echo ""
	@echo "MANTIS demo complete."
	@echo "  Day 0-1 stages: schema contract, 42-card atlas, legitimate population,"
	@echo "                  calibration figure, tests."
	@echo "  Day 2 stages:   injector framework, 8 labelled attacks, class balance,"
	@echo "                  per-attack counts, best-single-feature AUC table."
	@echo "  Day 3 stages:   schema v1.1.0 lifecycle block, LLM content corpus,"
	@echo "                  7 agentic F1 injectors split HARD/CLEAN, 15 cards."
	@echo "  Day 4 stages:   204-feature builder with a three-tier leakage assertion,"
	@echo "                  L0 clauses + bucket-contract verdict. Run 'make firewall'"
	@echo "                  for L1/L2 and the leave-one-family-out table (~10 min)."
	@echo "  Pending stages: fidelity scorecard, L3/L4, adversary loop."

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	find . -name "__pycache__" -type d -exec rm -rf {} +
	find data/generated -type f ! -name ".gitkeep" -delete
