# MANTIS — Detection results

*Day 4. Schema v1.1.0. Generated 2026-08-24 by `python -m mantis.defense`.*

## The operating point

> **Every recall in this document is measured at a threshold placed so that exactly 0.1% of legitimate test traffic is flagged.**

No accuracy figures appear anywhere here, and that is deliberate: at ~1% prevalence a model that approves everything is 99% accurate. The two metrics reported are **AUC-PR** and **recall@0.1%FPR**, the second always with its realised false-positive rate attached.

Each model variant gets its own threshold, because each has its own score distribution. What is held constant across every column of every table is the false-positive rate — which is the quantity an issuer actually budgets, and the only thing that makes two columns comparable.

## The evaluation dataset

Five independently generated worlds, seeds `1337, 7, 11, 23, 41`, pooled.

| | |
|---|---|
| events | 1,010,600 |
| fraud | 10,600 (1.0489%) |
| train / test | 707,420 / 303,180, **time-based** split at the 70% quantile |
| features | 204 |

Pooling is not resampling one file five times: each seed regenerates the whole population — its own customers, merchants, devices, agents and calendar — so the variance being averaged over is generator variance. Identifiers are namespaced per seed before concatenation, because letting `cus-00042` from two seeds collide would fuse two people's histories inside every velocity feature.

The reason for five rather than one is confidence intervals. At ~120 positives per card a per-family recall carries roughly ±9 points, which is wide enough that the leave-one-family-out comparison below could not be defended. Pooling puts the smallest family at 550 positives and the largest at 4,150.

## Layer performance

| layer | AUC-PR | ROC-AUC | recall@0.1%FPR | realised FPR |
|---|---|---|---|---|
| **L1** GBDT, supervised | 0.4910 | 0.8966 | **0.361** | 0.1000% |
| **L2** isolation forest, legitimate traffic only | 0.0194 | 0.6199 | **0.005** | 0.1000% |
| **L1 + L2** fused | 0.4210 | 0.8694 | **0.286** | 0.1000% |

Baseline precision (a coin flip) is the prevalence: 1.0941%. AUC-PR is only interpretable against it.

**Fusion is currently WORSE than L1 alone** (0.361 -> 0.286), and that is reported rather than hidden by quoting only the best row.

The cause is not subtle. The two layers are combined with an **unweighted** noisy-OR over their legitimate-traffic percentiles, and L2 is close to random (0.005 recall, 0.620 ROC). At a fixed 0.1% false-positive budget, giving a near-random layer equal say costs you: every legitimate event L2 happens to rank high consumes part of the budget that L1 would have spent on a real one.

The fix is a **weighted** fusion whose weights are fitted on the training window, which would learn to discount L2 to near-zero — and that is Day 6's fusion layer, not a number to reach for now by hand-tuning a coefficient until the table looks better. Until then the honest headline is **L1's** recall, not the fused one.

### Per rail, because the headline is partly measuring "is this agentic"

Fraud is concentrated on the agentic rail by design — 15% of volume carrying 51% of the fraud, a 5.7x concentration. A single number computed across both rails is therefore partly reading a field the issuer gets free off the authorisation message. Both rails, separately:

| rail | n positive | AUC-PR | recall@0.1%FPR |
|---|---|---|---|
| agentic | 1,702 | 0.7363 | 0.503 |
| classic | 1,615 | 0.2973 | 0.241 |

## Leave one family out — the headline experiment

For each family, L1 is retrained with that family **entirely removed from the training set** and then asked to catch it in the test set anyway. L2 never sees any attack at all, so its column is identical by construction whether or not the family was held out.

| family | n_pos | L1 (trained WITH it) | L1 (family HELD OUT) | L2 (never sees any attack) | fused | fused, held out |
|---|---|---|---|---|---|---|
| **F1** | 1,356 | 0.569 | 0.007 | 0.009 | 0.476 | 0.012 |
| **F2** | 433 | 0.060 | 0.016 | 0.005 | 0.042 | 0.014 |
| **F3** | 158 | 0.494 | 0.361 | 0.000 | 0.354 | 0.278 |
| **F4** | 567 | 0.056 | 0.026 | 0.002 | 0.042 | 0.026 |
| **F6** | 803 | 0.362 | 0.115 | 0.004 | 0.257 | 0.085 |
| *mean* | | *0.308* | *0.105* | *0.004* | *0.234* | *0.083* |

**Mean recall lost when a family is held out of training: +0.203** (30.8% → 10.5%).

### Reading it

**Supervised detection collapses on attacks it has never seen.** Held-out recall averages 10.5% against 30.8% when the family is in training — a loss of 0.203. This is the expected and the important result: an L1 trained on a labelled history is a detector for that history.

**The unsupervised layer does not rescue the held-out families.** L2 averages 0.4% recall at the same operating point, which is not enough to carry the argument on its own. Stated plainly because the alternative is quoting a number the table does not support: at 0.1% FPR an isolation forest on this feature space is a weak detector, and the layers that are supposed to close this gap — L3 on the provenance text, L4 on the graph — are not built yet. The claim that survives is the narrower one: L2's recall is *unaffected* by whether an attack was in training, which is the property no supervised layer has.

## Per attack card

At the same 0.1% FPR operating point, L1 trained on everything. Note the fused column inherits the weighting problem described above, so it is below L1 on most cards.

| card | n_pos | L1 | L2 | fused |
|---|---|---|---|---|
| F1-01 | 249 | 0.651 | 0.000 | 0.402 |
| F1-02 | 205 | 0.600 | 0.000 | 0.532 |
| F1-03 | 201 | 0.388 | 0.040 | 0.582 |
| F1-04 | 164 | 0.939 | 0.000 | 0.689 |
| F1-05 | 174 | 0.437 | 0.000 | 0.374 |
| F1-09 | 202 | 0.282 | 0.000 | 0.163 |
| F1-10 | 161 | 0.758 | 0.025 | 0.671 |
| F2-13 | 185 | 0.038 | 0.000 | 0.011 |
| F2-16 | 248 | 0.077 | 0.008 | 0.065 |
| F3-19 | 158 | 0.494 | 0.000 | 0.354 |
| F4-27 | 336 | 0.012 | 0.000 | 0.009 |
| F4-28 | 231 | 0.121 | 0.004 | 0.091 |
| F6-38 | 340 | 0.532 | 0.009 | 0.379 |
| F6-39 | 252 | 0.123 | 0.000 | 0.071 |
| F6-40 | 211 | 0.374 | 0.000 | 0.280 |

## The feature that was too good, ablated

`mnd_deliberation_residual_z` — the residual of an agent's deliberation latency against what a ticket that size deserves — separates F1-01 at **0.99 AUC on its own**. That is above the foundry's own 0.95 separability gate, and the gate never saw it: the gate probes **raw columns**, and this is a derived residual, so a trivially-derived feature walked straight past it.

The cause is in the generator. `collapse_deliberation` resamples latency from the population's low quantile band *unconditionally*, so a ₹50,000 purchase receives a ₹200 purchase's deliberation time. Real legitimate high-value purchases deliberate longer, so the residual is extreme in a way the attack itself does not require. The signal is real — an agent acting on injected text genuinely did not deliberate — but 0.99 is the generator's number, not the attack's.

It has **not** been silently removed, and it has not been silently kept. Here is what F1's recall rests on:

| family | recall with the feature | recall without it | delta |
|---|---|---|---|
| F1 | 0.569 | 0.549 | -0.020 |
| F2 | 0.060 | 0.058 | -0.002 |
| F3 | 0.494 | 0.418 | -0.076 |
| F4 | 0.056 | 0.055 | -0.002 |
| F6 | 0.362 | 0.321 | -0.041 |

Fixing it properly is a foundry change — collapse the latency *relative to what the amount deserves*, so "fast for this ticket" stays the signal without sitting off the end of the legitimate distribution. That re-rolls every Day 3 number and every injector docstring, so it is recorded as an outstanding item rather than done at the same time as standing up the firewall.

## What L1 actually uses

| feature | gain share |
|---|---|
| `mcc` | 6.47% |
| `mnd_mcc_in_scope` | 5.46% |
| `ent_merchant_customers` | 5.44% |
| `vel_mandate_hash_count_1h` | 3.90% |
| `mnd_amount_over_ceiling` | 3.77% |
| `txn_round_score` | 3.63% |
| `channel` | 3.26% |
| `ent_customer_n_events` | 3.24% |
| `vel_agent_amount_vs_mean` | 3.16% |
| `ent_mcc_amount_z` | 2.89% |
| `ent_merchant_refund_ratio` | 2.82% |
| `mnd_deliberation_residual_z` | 2.53% |
| `vel_agent_seconds_since_prior` | 2.25% |
| `vel_merchant_count_24h` | 1.97% |
| `ent_merchant_lag_vs_rail` | 1.85% |

## What this does not claim

- **This is not real-world performance.** It is measured on synthetic data whose attacks we wrote. The fidelity scorecard (Day 7) is the argument that the background is realistic; nothing here substitutes for it.
- **F5 is absent from every table.** It is the zero-day holdout family and has no implemented injector, so it is not in the data and cannot be scored yet. The leave-one-family-out columns are the closest available stand-in for it.
- **L3 and L4 do not exist yet.** The fused column is L1+L2 only. The text layer and the graph layer are the two that F1-01/F1-03 and F1-05 respectively are waiting on, and their absence is visible in those rows.
- **The current event's own outcome is never a feature.** `auth_response`, `settled` and `settlement_lag_hours` of the row being scored are blocked by name in the feature builder, alongside the label and post-hoc columns. Feeding them in would raise F4-27's recall substantially and mean nothing — an issuer cannot decline a transaction because it was declined.

