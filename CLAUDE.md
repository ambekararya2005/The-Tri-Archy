# MANTIS — Project Constitution

> Read this file **first**, every session. It outranks your defaults.
> Mastercard Innovation Challenge @ Global Fintech Fest 2026. Solo build,
> ~36 engineering hours total. If a decision is not covered here, prefer the
> option that a judge can see working in 4 minutes on a laptop with no network.

---

## 1. The pitch (compressed)

Agentic commerce — AI agents that pay on a human's behalf via **Mastercard Agent
Pay / AP2 mandates** — has created a live payment rail with **zero labelled
fraud data**. You cannot train a fraud detector on data that does not exist. So
you *manufacture* it, adversarially.

MANTIS is a red-team / blue-team lab in three pillars:

1. **IDENTIFY** — an *executable* atlas of 42 GenAI payment-fraud vectors as
   YAML cards that the generator **imports**. Not documentation: a dependency.
2. **GENERATE** — a foundry that synthesises a calibrated legitimate payment
   population and injects those attacks into it, with a **measured** fidelity
   scorecard (not a vibe check).
3. **DEFEND** — a five-layer **Mandate Firewall** that scores every
   authorisation and reports **recall at a fixed 0.1% false-positive rate**.

Then the closed loop that makes it a *lab* rather than a demo: an evolutionary
adversary reads the detector's own SHAP output, mutates to evade it, the
detector retrains, and the **evasion rate falls**. That curve is the money shot.

---

## 2. Judging criteria and the artifact that scores each one

Every hour of work should be traceable to a row in this table. If it is not, it
is a cut candidate.

| # | Criterion | Artifact that scores it | What we must be able to show |
|---|-----------|-------------------------|------------------------------|
| 1 | **Diversity of attacks** | `mantis/atlas/` — 42 cards across families F1–F6, each with `observable_signals` wired to real features | Atlas summary table; count of *implemented* (not merely mapped) injectors; the zero-day holdout family |
| 2 | **Fidelity of simulation** | `mantis/foundry/fidelity/` — the fidelity scorecard | Marginal KS distances, MCC / amount / hour-of-day mixes vs. reference, a TSTR (train-synthetic-test-real) number. Measured, printed, and honestly imperfect. |
| 3 | **Detection efficacy** | `mantis/defense/` — the five-layer Mandate Firewall | AUC-PR and **recall@0.1%FPR** per layer and fused; per-family recall; the zero-day holdout result |
| 4 | **Novelty** | `mantis/loop/` — evolutionary adversary + retrain harness | Evasion-rate-vs-generation curve; SHAP-guided mutation; cards found by the discovery agent |
| 5 | **Real-world feasibility** | `mantis/core/events.py` — the schema | `TxEvent` is a **superset of a real card authorisation** plus an agentic extension. An issuer could drop this in behind an existing auth stream without re-platforming. Plus: L0 rules are deployable today, and the latency budget is reported. |

**Criterion 5 is won or lost in the schema.** That is why the schema is frozen
(§4) and why `events.py` carries a docstring that argues the case explicitly.

---

## 3. Repo layout

```
mantis/
  mantis/core/          events.py — THE schema, imported by everything
  mantis/atlas/         schema.py, loader.py, cards/*.yaml, discovery/
  mantis/foundry/       base/  injectors/  llm/  fidelity/
  mantis/defense/       features/ l0_rules/ l1_gbdt/ l2_novelty/
                        l3_text/ l4_graph/ fusion/ policy/ explain/
  mantis/loop/          evolutionary adversary + retrain harness
  mantis/api/           FastAPI + SSE (live defense console backend)
  web/                  React + Vite
  data/reference/       calibration tables (committed, small)
  data/generated/       synthetic output (gitignored except .gitkeep)
  data/cache/           LLM output cache — COMMITTED, see HARD RULES
  docs/  tests/  scripts/
```

Dependency direction is one-way and must stay that way:

```
core  <-  atlas  <-  foundry  <-  defense  <-  loop  <-  api  <-  web
```

`core` imports nothing of ours. `atlas` imports `core` (card rails are
validated against the `Channel` enum). Nothing imports `api`. No cycles, ever.

---

## 4. The event-schema contract — FROZEN

`mantis/core/events.py` is frozen as of Day 0. Every other module codes against
it. **Do not add, rename, retype, or reorder a field** without doing all four
of: updating `events.py`, updating `tests/test_schema.py`, updating this
section, and grepping every `ag_` string literal in the repo.

Additive-only escape hatch: if a new attack genuinely needs a field, add it to
`AgenticContext` with a default of `None` so every existing call site keeps
working. Never repurpose an existing field's meaning.

**Classic block** (a real card authorisation): `event_id`, `ts`, `amount`,
`currency`, `mcc` (4 digits, validated), `channel`, `entry_mode`,
`customer_id`, `card_bin`, `merchant_id`, `merchant_country`, `terminal_id`,
`device_id`, `ip`, `lat`, `lon`, `threeds_result`.

**Agentic block** (`AgenticContext`, `None` on classic rails): `agent_id`,
`agent_platform`, `kya_token`, `kya_registered`, `mandate_type`, `mandate_id`,
`mandate_hash`, `mandate_issued_ts`, `mandate_ttl_seconds`, `mandate_scope`
(nested `MandateScope`), `human_present`, `consent_sig_valid`,
`delegation_depth`, `provenance_chain`, `ingested_content_ids`,
`tool_call_count`, `deliberation_latency_ms`, `cursor_entropy`,
`dwell_time_ms`.

**Ground truth** (never a feature — see HARD RULES): `is_fraud`, `attack_id`,
`attack_campaign`.

Exports: `LABEL_COLUMNS`, `flatten(ev) -> dict` (agentic fields prefixed `ag_`).

**`provenance_chain` is the highest-value field in the schema.** It is the
ordered list of URLs / content the agent read before it decided to transact. It
is what turns indirect prompt injection from something you can *describe* into
something you can *detect*. It is the input to the L3 text layer. Treat it as
load-bearing.

---

## 5. Coding conventions

- **Python 3.11+**, **pydantic v2** (`field_validator` / `model_validator`, not
  v1 `@validator`). Type hints on every signature; no bare `Any` without a
  one-line comment justifying it.
- **ruff-clean** before any commit: `make lint`. Line length 100.
- **No notebook-only code.** Nothing lives in a `.ipynb`. If it is worth running
  twice, it is a module.
- **Every module runnable via `python -m`**, with a `main()` and an
  `if __name__ == "__main__":` block that prints something a human can read.
  This is how the demo is assembled and how you debug at 3am.
- **Determinism**: every stochastic entry point takes `seed: int`, default
  `1337`. A judge re-running the pipeline must get the numbers on the slides.
- Paths via `pathlib`, never string concatenation; repo-relative paths resolved
  from a single helper module, never `os.getcwd()`.
- Frontend: React + Vite + TypeScript. Nothing heavier than the chart library.
  The console is a dashboard, not an app.

---

## 6. HARD RULES

Violating any of these is a build failure, not a style nit.

1. **NEVER let label columns reach a model's feature matrix.**
   `is_fraud`, `attack_id`, `attack_campaign` — and anything derived from them —
   must be dropped *by name* in the feature builder, with an assertion that
   fires if they survive. Leakage is the #1 way hackathon fraud models silently
   cheat, and a judge who sees 0.999 AUC will assume exactly that. Any metric
   that looks too good is leakage until proven otherwise.

2. **NEVER report accuracy.** The class balance makes it meaningless, and
   quoting it signals you do not know the domain. Report **AUC-PR** and
   **recall@0.1%FPR**, always with the operating point stated. Confusion
   matrices only at a declared threshold.

3. **ALWAYS cache LLM output to disk and commit the cache.** A judge cloning
   this repo will not have Ollama running. Every LLM call goes through the cache
   layer in `mantis/foundry/llm/`, keyed by a hash of prompt + model + params.
   A cache miss with no backend available falls back to the committed cache or a
   deterministic stub — never a crash, never a hang, never a network wait.

4. **The repo must run from a clean clone with no Kaggle token, no GPU, and no
   API key.** `make demo` is the acceptance test. Run it against a scratch clone
   before you sleep on the last night. No download-at-runtime, no credentials,
   no environment variables that only exist on the build machine.

5. **Generated attack content is demonstrative, never operational tooling.**
   The atlas describes attack *classes* with observable signals and mitigations
   so that they can be detected. Injection payloads in the foundry are short,
   obviously synthetic, clearly labelled, and exist to be caught. We do not
   write working exploits against real platforms, real merchants, or named
   third-party products. If a card cannot be written defensively, it stays
   `status: mapped` and never gets an injector.

---

## 7. The cut line

When time runs out — and it will — sacrifice in **this order**, top first:

1. **L4 graph layer** (fall back to four layers, and say so out loud)
2. **Adversary loop generations** (3 instead of 10; the curve still has a slope)
3. **Live LLM** (cache-only mode — already the default path)
4. **Discovery agent** (ship the cards it already found, drop the live run)
5. **React frontend** (fall back to Streamlit; the numbers matter, not the CSS)

**Never cut, at any cost:**

- The **live defense console** — a judge must watch a transaction get scored
- **recall@0.1%FPR** — the one number that proves the detector is real
- The **zero-day holdout** — an attack family the detector never trained on
- The **fidelity scorecard** — proves the synthetic data is not a toy
- The **.docx** submission document — no document, no score, regardless of code

---

## 8. Current state

- **Day 0 complete**: constitution, scaffold, frozen `TxEvent` schema, atlas
  schema + loader, first 8 attack cards, schema round-trip tests.
- **Day 1 complete**:
  - **Atlas finished at 42 cards** (F1 12, F2 6, F3 8, F4 6, F5 5, F6 5), of
    which **exactly 15 are `implemented`** and 27 are `mapped`. Every family has
    at least one implemented card. `python -m mantis.atlas.loader` prints the
    split under an "HONEST COUNT" heading; `tests/test_atlas.py` locks the
    numbers so the writeup cannot drift from the repo.
  - **Legitimate population simulator** in `mantis/foundry/base/`:
    `reference.py` (calibration + Indian-market priors), `entities.py` (standing
    customer/card/device/merchant/agent map), `simulator.py` (the draw),
    `calibration.py` (metrics + figure), `__main__.py` (CLI).
  - `scripts/fit_reference.py` fits shape parameters from the Kaggle Sparkov CSV
    if one is dropped into `data/reference/`, and exits cleanly when none is.
  - `mantis/core/paths.py` is the single repo-relative path helper (see §5).
- **Day 1 gate (passing)**: `python -m mantis.foundry.base --n 200000 --seed 7`
  writes `data/generated/population.parquet` (~15 MB, ~8 s) plus a manifest and
  `docs/population_calibration.png`; amount KS 0.0051, hour TV 0.0066, MCC mix
  max delta 0.0010; 42 cards load clean; 65 tests pass; ruff clean.
- **Next up**: injectors (`foundry/injectors/`) for the 15 implemented cards,
  then the fidelity scorecard, then the firewall. Do not start these before the
  day they are scheduled.

- **Day 1 audit complete** (`scripts/audit_population.py`, 30/30 checks). It is
  adversarial by design and re-runnable: `python scripts/audit_population.py`.
  It found and we fixed three real defects, all now pinned by regression tests:
  1. **Reproducibility was broken.** A set of strings was iterated inside a loop
     that consumes the RNG, so `--seed 7` produced a different population on
     every process (CPython randomises string hashing). The numbers on the
     slides would not have survived a judge re-running the pipeline.
  2. **`device_id` was a perfect rail separator** (AUC 1.000, zero of 8,796
     devices carried both rails). Agents now run on-device about half the time,
     on the cardholder's existing hardware.
  3. **Two more separators from over-clean modelling**: a binary adopter flag
     gave 70% of customers a hard-zero agentic probability (`customer_id`
     AUC 0.90 -> 0.75, now a graded Beta propensity), and the agentic 3DS mix
     had no failure tail (`threeds_result` AUC 0.86 -> 0.75).

### Day 1 decisions worth not relitigating

- **Rail identity is unhideable, and that is fine.** `channel == "agentic"` names
  the rail and every `ag_*` column is non-null exactly on it, so "can a model
  detect the rail" is not a meaningful leakage test. The audit therefore tiers
  columns: definitional (no bound), correlated-by-design (bound 0.85, each with
  a written causal reason), and neutral (bound 0.70). `device_id` sits in tier 1
  on reflection - a hosted agent runtime genuinely is a device that only ever
  transacts agentically, and exposing that is what KYA is *for*. The test that
  actually protects Day 2 is different and now runs: **amount must be
  rail-independent given MCC** (worst per-MCC KS 0.076), so that once attacks
  land - and attacks skew agentic - the detector cannot pass by learning
  "unusual amount -> agentic -> fraud".
- **F1-03 (refund-logic hijack) stays `mapped`.** Refunds are not representable
  in the frozen schema, so it must not carry a generator path.
- **Convention: `implemented` iff `generator` is set.** A `mapped` card names no
  generator, because a path implies an injector that does not exist. Enforced by
  `tests/test_atlas.py`.
- **Legitimate agentic traffic has messy tails on purpose**: ~2.8% not
  KYA-registered, ~0.3% consent signature invalid, `amount/scope_max` reaching
  0.99. Without them L0 would score perfect recall on a generator artefact.
- **Amount KS is non-zero by design** (round-number snapping) and the national
  Zipf curve is flatter than the per-pool exponent (locality-conditioned
  merchant choice). Both are explained on the figure rather than tuned away.
