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
  - **Atlas finished at 42 cards** (F1 12, F2 6, F3 8, F4 6, F5 5, F6 5).
    `python -m mantis.atlas.loader` prints the implemented/mapped split under an
    "HONEST COUNT" heading; `tests/test_atlas.py` locks the numbers so the
    writeup cannot drift from the repo. (Day 1 claimed 15 implemented on the
    strength of planned generator paths; Day 2 made that claim enforceable and
    the count is now **8**. See §8 Day 2.)
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
- **Day 2 complete**:
  - **Injector framework** in `mantis/foundry/injectors/base.py`: `BaseAttack`
    (ABC, `inject(population, intensity, rng) -> DataFrame`), a `PopulationView`
    of read-only indices over the background, and the `REGISTRY`.
    **`validate_registry()` runs at package import and fails the import** unless
    the atlas and the code agree in *both* directions - every `implemented` card
    has an injector, every injector names a real `implemented` card, and each
    card's `generator` path resolves to a callable in that injector's own
    module. This is the seam that makes Pillar 1 executable rather than
    decorative, and `tests/test_injectors.py` fires it deliberately to prove it
    is load-bearing.
  - **Eight tabular injectors**, one per card: F4-27 adaptive BIN, F4-28
    threshold probing / just-under structuring, F2-13 synthetic identity
    onboarding, F2-16 synthetic-identity bust-out, F3-19 digital-arrest APP
    scam, F6-38 mule-network fan-in/fan-out, F6-39 transaction laundering via
    miscoded MCC, F6-40 stored-value cash-out ring.
  - **Separability probe** in `injectors/probe.py`: a depth-1 stump on every
    single column (categoricals exploded per level, null patterns and list
    lengths included, raw identifiers excluded with written reasons), reporting
    the stronger of the stump AUC and the column's own rank AUC. Gate is 0.95.
  - `mantis/foundry/__main__.py` is the Day 2 CLI and gate.
- **Day 2 gate (passing)**:
  `python -m mantis.foundry --attacks all --out data/generated/dataset_v1.parquet`
  writes 201,290 rows (~15 MB, ~40 s including the probe) plus a manifest.
  Prevalence **0.6409%** (200,000 legitimate / 1,290 fraud). Best-single-feature
  AUC per attack: F2-13 0.639, F2-16 0.627, F3-19 0.872, F4-27 0.663,
  F4-28 0.801, F6-38 0.787, F6-39 0.792, F6-40 0.676; **all fraud combined
  0.609**. 102 tests pass; ruff clean.
- **Next up**: the fidelity scorecard (`foundry/fidelity/`), then the firewall.
  Do not start these before the day they are scheduled.

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

### Day 2 decisions worth not relitigating

- **The implemented count went 15 -> 8, and that is a tightening, not a
  regression.** Day 1's convention was "implemented iff a `generator` path is
  named". Day 2 replaced it with "implemented iff an injector exists, is
  registered, and its declared path resolves" - checked at import. Nine cards
  (F1-01, F1-02, F1-09, F1-10, F2-14, F3-20, F4-29, F5-33, F5-34) named a path
  with no code and went back to `mapped`; F2-16 and F6-40 gained injectors and
  were promoted. The number is now a **ratchet**: it moves only when code lands.
  F1 and F5 have no implemented card today; they return on Day 3 with the
  agentic injectors, and `tests/test_atlas.py` pins the family set so that is a
  deliberate act rather than a drift.
- **Four of the Day 2 attack ids were remapped to the cards that actually carry
  those semantics.** The requested list named F2-17 for bust-out, F2-18 for
  mule fan-in, F5-34 for miscoded-MCC laundering and F4-28 for card
  enumeration; in the frozen atlas those ids are merchant onboarding, agent
  reputation farming, platform compromise and threshold structuring. Injectors
  were written against **F2-16, F6-38, F6-39 and F4-28** - the cards whose
  `description` and `observable_signals` match the attack - because an injector
  that generates something other than what its card describes is exactly the
  overclaim the registry assertion exists to prevent.
- **Chargeback / refund abuse is not representable and was substituted, not
  faked.** `TxEvent` is an authorisation message: no refund flag, no dispute
  outcome, no authorisation response code. F6-40 (stored-value cash-out ring)
  ships in its place - same actor, same ring topology, same objective, every
  claimed signal present in the data. This is the same constraint that keeps
  F1-03 at `mapped`, and it is recorded in `f6_40_stored_value.py`'s docstring
  so the substitution is visible rather than quietly absent.
- **Injectors return only new rows and never mutate the background.** The Day 1
  calibration was measured on that background; editing it in place would make
  the fidelity scorecard measure the attacks instead of the simulation. It also
  makes per-attack accounting and the zero-day holdout separable by
  construction.
- **Attack events are clones of real background rows, retargeted.** Card BIN,
  device, IP, geo, entry mode, 3DS outcome and the nullity pattern all come from
  the legitimate population. Amounts are resampled from the population's *own*
  per-MCC empirical distribution inside a quantile band. Fraud that only touches
  freshly-minted entities is trivially detectable; a test asserts every attack
  customer and merchant already exists.
- **The probe caught two generator artefacts, both now fixed in the framework.**
  Injectors originally scheduled uniformly across the 24 hours, which against a
  diurnal population made `ts_hour` the strongest single feature on three
  attacks; `set_timestamps` now redraws each event's time of day from the
  background's own hour curve (blended 18% toward uniform), shifting whole
  bursts together via a `groups` argument so escalation gaps and cultivation
  cadence survive intact. Campaign starts were also drawn uniformly and left
  calendar gaps the probe read as a `ts_epoch` signal; `spread_epochs` is now
  stratified. Two attack-level artefacts went the same way: F2-13's cohort was
  filtered to a late first-seen date (0.81 AUC on `ts_epoch`) and F3-19 used one
  fixed amount cap that pinned most of a campaign to a single repeated number.
- **F3-19 at 0.872 on `amount` is the honest ceiling, not a bug.** A coerced
  transfer really does sit at the top of its victim's range. What the number
  does not support is a threshold - the population's 87th percentile is ordinary
  traffic - so recall must come from `amount_vs_customer_p99` and beneficiary
  fan-in. Every injector records its measured number in its module docstring.
- **Prevalence, not raw count, is the invariant.** `BaseAttack.n_events` scales
  `base_events` by the actual background size against a 200k reference, so a
  40k smoke run and a 200k gate run both land near 0.64%. Letting prevalence
  swing with `--n` would make AUC-PR incomparable between runs.
