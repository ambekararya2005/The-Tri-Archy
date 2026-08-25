# MANTIS — Detection results

*Day 5. Schema v1.1.0. Generated 2026-08-25 by `python -m mantis.defense`.*

## The operating point, and why it is a curve

> **Every recall in this document is measured at a threshold placed so that a fixed share of legitimate test traffic is flagged.** The headline share is **0.1%**.

No accuracy figures appear anywhere here, and that is deliberate: at ~1% prevalence a model that approves everything is 99% accurate. The metrics reported are **AUC-PR** and **recall at a fixed FPR**, the second always with its realised false-positive rate attached.

Day 4 quoted one operating point. Day 5 quotes 0.1%, 0.5%, 1.0% — a curve rather than a point, because one number at one budget is something a reader has to trust you did not pick, and three is a shape. 0.1% stays the headline because it is the tightest, and the tightest is the one an issuer can actually staff. 1.0% is roughly the top of what a review queue absorbs, which is why the curve stops there.

Each model variant gets its own threshold, because each has its own score distribution. What is held constant across every column of every table is the false-positive rate — the quantity an issuer budgets, and the only thing that makes two columns comparable.

### Two kinds of recall, both labelled

Day 4 reported **event-level** recall only, and event-level recall is the wrong question for half of this atlas. A mule ring that runs 40 authorisations and is flagged on 3 of them scores 7.5% event-level and is **caught**: one alert opens a case, and the case takes the ring. So every layer is also reported at **campaign level** — was the campaign flagged at all, and on which of its events.

Neither is the real number. Event-level flatters a layer that fires on every event of an obvious attack; campaign-level flatters a layer that fires once on something subtle. They appear side by side, always, with their names on them.

## The evaluation dataset

5 independently generated worlds, seeds `1337, 7, 11, 23, 41`, pooled.

| | |
|---|---|
| events | 1,010,600 |
| fraud | 10,600 (1.0489%) |
| train / test | 707,420 / 303,180, **time-based** split at the 70% quantile |
| features | 232 (of which 28 are the new `gph_` entity-graph block) |

Pooling is not resampling one file five times: each seed regenerates the whole population — its own customers, merchants, devices, agents and calendar — so the variance being averaged over is generator variance. Identifiers are namespaced per seed before concatenation, because letting `cus-00042` from two seeds collide would fuse two people's histories inside every velocity, entity and graph feature.

## Layer performance

| layer | AUC-PR | ROC-AUC | recall@0.1% | recall@0.5% | recall@1.0% | realised FPR | campaign recall | first alert |
|---|---|---|---|---|---|---|---|---|
| **L1** GBDT, supervised, time-split, isotonic-calibrated | 0.5903 | 0.9248 | 0.450 | 0.572 | 0.623 | 0.1000% | 0.916 (120/131) | event 3 of 23 |
| **L2** isolation forest on events, legitimate traffic only — **residual monitor** | 0.0151 | 0.5785 | 0.002 | 0.009 | 0.021 | 0.1000% | 0.031 (4/131) | event 12 of 23 |
| **L2e** isolation forest on **entity** aggregates — the time-boxed experiment | 0.0098 | 0.4421 | 0.000 | 0.003 | 0.005 | 0.1881% | 0.008 (1/131) | event 1 of 23 |
| **L3** page classifier over ingested text, **fitted on no transaction labels** | 0.1687 | 0.6919 | 0.138 | 0.149 | 0.167 | 0.1024% | 0.214 (28/131) | event 1 of 23 |
| **fused** weighted logistic stacker over the four | 0.5881 | 0.9119 | 0.483 | 0.580 | 0.606 | 0.1000% | 0.908 (119/131) | event 2 of 23 |

Baseline precision (a coin flip) is the prevalence: 1.0941%. AUC-PR is only interpretable against it.

**Fusion is now better than L1 alone** (0.450 → 0.483 at 0.1% FPR). On Day 4 it was worse — 0.361 → 0.286 — because the layers were combined with an *unweighted* noisy-OR, which gave a near-random L2 equal say inside a fixed false-positive budget. The fix was not to delete L2 but to fit the weights on a slice of the training window none of the base layers had seen, and let the stacker discount it. The coefficients below are what it decided.

### What the fusion learned

| layer | weight on the percentile | weight on the raw score | weight on "had an opinion" |
|---|---|---|---|
| L1 | +5.723 | +0.381 | n/a |
| L2 | +0.789 | -0.225 | n/a |
| L2e | +0.428 | +0.233 | n/a |
| L3 | -0.943 | +0.353 | -0.268 |

The coefficients are the interesting output, more than the fused recall is. A weight near zero is the stacker saying that layer carries no information the others do not already have — which is a cleaner statement than any table of recalls, and it is how the Day 4 problem got fixed without anyone hand-tuning a number.

### Per rail, because the headline is partly measuring "is this agentic"

Fraud is concentrated on the agentic rail by design — 15% of volume carrying 51% of the fraud, a 5.7x concentration. A single number across both rails is therefore partly reading a field the issuer gets free off the authorisation message.

| rail | n positive | AUC-PR | recall@0.1%FPR |
|---|---|---|---|
| agentic | 1,702 | 0.8088 | 0.606 |
| classic | 1,615 | 0.3912 | 0.318 |

## Leave one family out — the headline experiment

For each family, L1 is retrained with that family **entirely removed from the training set** and then asked to catch it in the test set anyway. L2 never sees any attack at all, and L3 never sees a transaction, so neither of their columns changes with the hold-out.

| family | n_pos | L1 (trained WITH it) | L1 (family HELD OUT) | L2 | L3 | fused | fused, held out |
|---|---|---|---|---|---|---|---|
| **F1** | 1,356 | 0.681 | 0.004 | 0.005 | 0.338 | 0.786 | 0.011 |
| **F2** | 433 | 0.176 | 0.016 | 0.000 | 0.000 | 0.157 | 0.014 |
| **F3** | 158 | 0.595 | 0.405 | 0.000 | 0.000 | 0.544 | 0.361 |
| **F4** | 567 | 0.086 | 0.028 | 0.000 | 0.002 | 0.086 | 0.023 |
| **F6** | 803 | 0.437 | 0.137 | 0.000 | 0.000 | 0.415 | 0.127 |
| *mean* | | *0.395* | *0.118* | *0.001* | *0.068* | *0.398* | *0.107* |

**Mean event-level recall lost when a family is held out of training: +0.277** (39.5% → 11.8%).

### The same experiment at campaign level

| family | campaigns | median size | fused (with) | fused (held out) | first alert at event | elapsed before alert |
|---|---|---|---|---|---|---|
| **F1** | 60 | 22 | 1.000 | 0.183 | 1 | 0% |
| **F2** | 14 | 32 | 0.714 | 0.214 | 8 | 24% |
| **F3** | 9 | 17 | 0.889 | 1.000 | 3 | 9% |
| **F4** | 22 | 23 | 0.818 | 0.227 | 12 | 54% |
| **F6** | 26 | 29 | 0.885 | 0.615 | 3 | 9% |

Read the last two columns together with the first: a campaign caught on its third event of forty is a case opened before most of the money moved. A campaign caught on its thirty-fifth is a post-mortem.

### Reading it

**Supervised detection collapses on attacks it has never seen.** Held-out recall averages 11.8% against 39.5% when the family is in training. This is the expected and the important result: an L1 trained on a labelled history is a detector for that history.

**The unsupervised layer does not rescue it.** L2 averages 0.1% at the same operating point. Day 5 stopped treating that as a gap to be closed and reframed it as the finding it is — see the next two sections. The architecture's answer to an unseen attack is now **L0's protocol invariants**, which need no training data because a violated mandate is a broken contract rather than an outlier, and **the closed loop**, which manufactures the attack before an attacker does.

## The closed loop — the other half of the zero-day answer

An evolutionary adversary mutates the **operational parameters** of a known attack — pacing, ring fan-out, device rotation, ticket size, how many injected pages the agent reads — and selects on **evasion x payoff** against the live detector. Between rounds the detector retrains on everything the arena has produced. That is the loop an operator runs when their attempts start getting declined, except that here the defender runs it first.

### The evasion curve

| generation | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| mean evasion | 0.626 | 0.334 | 0.338 | 0.363 | 0.381 |
| max evasion | 0.998 | 0.797 | 0.777 | 0.767 | 0.777 |

Evasion falls from **0.626 to 0.381** over 5 generations. Almost all of that fall happens at the **first** retrain — generation 0 is scored against a detector that has never seen a mutated variant, and generation 1 against one that has.

After that the curve **rebounds**, from a floor of 0.334 at generation 1 back to 0.381, and that is the more interesting half of the shape. It is what a real arms race looks like: the defender's first response is worth far more than any subsequent one, and the adversary then claws back a fraction of it by finding a corner of the gene space the retrain has not covered. A curve that fell monotonically to zero would be a curve to distrust — it would mean the adversary had stopped searching, which with a mutation operator that never stops would mean the search space was too small to be interesting.

The claim the chart supports is therefore the bounded one: **retraining on manufactured variants cuts evasion by 39% and holds it down**, not that it drives evasion to zero. Nothing drives evasion to zero.

Full per-generation detail, the surviving genomes and which genes moved are in `data/generated/arena.json`.

6 genuinely mutated variant(s) survived three or more consecutive rounds against a retraining detector and were written back to `mantis/atlas/discovered/` as validated attack cards with `discovered_by: adversarial_loop`. They live beside the atlas rather than inside it: `mantis/atlas/cards/` is the frozen 42, and the implemented count is a ratchet that moves only when an injector lands. Each card ships a `.genome.json` sidecar, so a variant is reproducible rather than merely described.

**3 further survivor(s) were the *unmutated* attack** — every gene at its default — and they are **not** written back. Each card's population is seeded with an identity genome so the curve carries its own no-evolution reference row, and on cards the detector is already weak at, that individual simply wins: F2-16 evades **77.8%** of decisions without being mutated at all. That is a result about the parent card, not a discovery, and recording it as one would be the exact overclaim the atlas ratchet exists to prevent. It also points at where the next detection work is: F1-01, F1-05, F2-16.

### The zero-day demonstration

This is the comparison the submission's argument rests on.

| detector | recall@0.1%FPR on the 544 real F1 test events |
|---|---|
| trained **with** family F1 | 0.811 |
| family F1 **held out** of training | 0.013 |
| held out, **plus 4,442 loop-manufactured variant events** | **0.539** |

The loop recovers **66%** of the collapse that holding the family out caused.

**What this claims, exactly.** The loop had access to F1's *atlas cards* — a written description of a class of attack and an executable generator for it. It did not have a single one of the F1 rows it is then evaluated on, and the variants are not those rows: every gene moved them, and they were **selected for evading the detector**, so they are off-distribution from the canonical attack in exactly the direction that makes the transfer hard.

So the claim is *"an attack family described in the atlas but never observed in the data can be manufactured, and training on the manufactured version transfers to the real one"*. It is **not** *"the detector caught something nobody had thought of"*. No model does that, which is the whole point of the reframing: we stopped pretending an isolation forest could, and built the thing that actually works instead.

Measured on the loop's own two-seed background rather than the five-seed pool above, so all three rows share one dataset and one operating point. The Day 4 five-seed figures (0.569 trained, 0.007 held out) are the same experiment at a different scale, not a directly comparable row.


## L3, and why a near-perfect number here is honest

L3 classifies **a page**, and an event's score is the worst page its agent read. It is fitted on the committed content corpus using each artefact's own `injected` flag — **it never sees `is_fraud`, and `L3Model.fit` has no `y` parameter to pass one to**. That is why it sits with L0 in the reframed architecture rather than with L1: it works on an attack it has never seen in the payment data, because the thing it was trained on is not payment data.

| card | n_pos | recall | on unseen *phrasing* | n unseen | on an unseen *kind* |
|---|---|---|---|---|---|
| F1-01 | 249 | 1.000 | 1.000 | 134 | 1.000 |
| F1-02 | 205 | 0.020 | n/a | 0 | 0.020 |
| F1-03 | 201 | 1.000 | 1.000 | 93 | 1.000 |
| F1-05 | 174 | 0.017 | n/a | 0 | 0.017 |

**The injected instruction *is* the attack.** F1-01 is defined as an agent acting on text that told it to change the cart, and F1-03 as one acting on a refund request that told it to skip verification. A classifier reading that text and finding the instruction is not cheating and is not leakage — it is the detection working. The comparison that makes it concrete is L1's: on F1-01, L3 reaches 1.000 reading the text while L1 reaches 0.759 off 232 tabular features, because the tabular trace of "the agent read a bad page" is faint and the page itself is not.

What would be dishonest is claiming that generalises when it does not, so the last two columns are the ones the writeup may lean on. **Unseen phrasing**: the highest-numbered variant of every adversarial kind is withheld from the vocabulary and from training. **Unseen kind**: every `refund_ticket` specimen is withheld — all of them — so F1-03 is scored on an injection type the classifier has never seen in any wording.

Measured directly on the withheld texts themselves: 34 artefacts that were never in the vocabulary or the training set score P(injected) between 0.24 and 0.91, median 0.76. If the layer had memorised rather than learned, these would sit with the benign artefacts.

L3's *overall* recall is low, and that is correct rather than disappointing: it has an opinion about two of the fifteen cards and no opinion at all about the classic rail, where there is no provenance chain to read. A layer that scored highly on everything would be a layer reading something other than the text.

## The negative result worth publishing

> **Attacks built to be distributionally faithful are, by construction, invisible to distributional anomaly detection.**

L2 scores events: AUC-PR 0.0151, ROC 0.5785, recall 0.002 at 0.1000%. The stated reason it *should* have worked better is a ring — every event in a mule network is bland, but the entity is not. So Day 5 tested exactly that, time-boxed to thirty minutes: **L2e**, an isolation forest over entity aggregates rather than event rows, scoring customers and merchants instead of authorisations. Result: AUC-PR 0.0098, ROC 0.4421, recall 0.000 at 0.1881%.

It did not move — it went **backwards**. A ROC of 0.4421 is *below chance*, which is a stronger statement than "weak": entity aggregates are mildly **anti-correlated** with fraud on this data. The reason is the foundry's own realism discipline pointed at the entity level: attacks ride established customers and busy merchants by construction, while the genuinely unusual entities in this population are ordinary people with three transactions. An outlier detector at entity level finds the quiet, and the quiet is innocent. The negative result is worth more than the layer would have been. L2e is also *generous* to the hypothesis in a way that has to be stated: an entity's vector is aggregated over the whole scoring window, so the score attached to that entity's first event was computed with knowledge of their last. That is a legitimate deployment mode — a nightly entity-risk queue, which is what AML and merchant-monitoring teams actually run — but it is not an authorisation scorer, and it still did not work.

**Our own fidelity work caused this.** Every foundry decision pushed the attacks toward the legitimate manifold: clone real background rows, resample amounts inside the target MCC's own empirical band, redraw the hour of day from the population's diurnal curve, widen three legitimate tails specifically so an attack would not be free, keep provenance planting length-preserving. The Day 2 separability gate is literally a rule forbidding any single raw column from separating an attack above 0.95 AUC. An isolation forest measures distance from that manifold; we spent two days minimising it.

And that is the property real agentic fraud has. An agent paying with a validly-signed mandate, on a real cardholder's real device, for a plausible amount at a real merchant, **is** legitimate in every marginal. The fraud lives in the *intent* — which is L3, the text — and in the *relations* — which is L4, the graph — not in the marginals. That is why "just run an autoencoder on it" is not an answer to agentic fraud, and it is why the two layers Day 5 built are the two that read intent and relations.

**Corollary, and it is a sharp one:** a fidelity scorecard and an anomaly-detection recall number are in tension *by construction*. A project reporting both as high is reporting one of them wrongly.

What survives for L2 is the narrow claim, and it is real: its recall is completely **unaffected** by whether an attack was in training, which is a property no supervised layer has. Its job in the architecture is now **residual monitor and drift canary** — "has the shape of legitimate traffic moved" — and no table in this repo presents it as a detector.

## Per attack card

At the same 0.1% FPR operating point. The last column is campaign-level: the share of that card's campaigns in which **at least one** event was flagged by the fused score.

| card | n_pos | L1 | L2 | L2e | L3 | fused | campaigns caught |
|---|---|---|---|---|---|---|---|
| F1-01 | 249 | 0.759 | 0.000 | 0.000 | 1.000 | 0.984 | 1.000 |
| F1-02 | 205 | 0.693 | 0.000 | 0.000 | 0.020 | 0.688 | 1.000 |
| F1-03 | 201 | 0.443 | 0.010 | 0.000 | 1.000 | 0.940 | 1.000 |
| F1-04 | 164 | 0.982 | 0.000 | 0.000 | 0.006 | 0.982 | 1.000 |
| F1-05 | 174 | 0.868 | 0.000 | 0.000 | 0.017 | 0.839 | 1.000 |
| F1-09 | 202 | 0.356 | 0.000 | 0.000 | 0.000 | 0.312 | 1.000 |
| F1-10 | 161 | 0.745 | 0.031 | 0.000 | 0.000 | 0.752 | 1.000 |
| F2-13 | 185 | 0.232 | 0.000 | 0.000 | 0.000 | 0.205 | 1.000 |
| F2-16 | 248 | 0.133 | 0.000 | 0.000 | 0.000 | 0.121 | 0.429 |
| F3-19 | 158 | 0.595 | 0.000 | 0.000 | 0.000 | 0.544 | 0.889 |
| F4-27 | 336 | 0.036 | 0.000 | 0.000 | 0.003 | 0.033 | 0.875 |
| F4-28 | 231 | 0.160 | 0.000 | 0.004 | 0.000 | 0.165 | 0.786 |
| F6-38 | 340 | 0.632 | 0.000 | 0.000 | 0.000 | 0.618 | 1.000 |
| F6-39 | 252 | 0.139 | 0.000 | 0.000 | 0.000 | 0.135 | 0.700 |
| F6-40 | 211 | 0.479 | 0.000 | 0.000 | 0.000 | 0.422 | 1.000 |

## The decision layer

A score is not an action. The fused score maps to one of four responses, with each boundary placed at a false-positive budget on legitimate traffic rather than at a hard-coded score — so a retrain re-prices nothing. Over the test window:

| decision | events | share |
|---|---|---|
| approve | 298,170 | 98.348% |
| challenge | 1,515 | 0.500% |
| review | 1,593 | 0.525% |
| decline | 1,902 | 0.627% |

A deterministic L0 clause firing overrides all four, because "the mandate had expired" is a defensible thing to tell a cardholder and "the ensemble scored 0.83" is not.

## What an alert actually says

Per-event attribution comes from LightGBM's own `pred_contrib`, not from SHAP. For a tree ensemble that is the *same* computation — `TreeExplainer` calls into LightGBM for it — without a wrapper on the scoring path. The three highest-scoring test events, with the features that put them there (contributions are in log-odds of the raw margin, which is what the ranking, and therefore the alert, is made of):

```
  #1  score 1.0000  upi_p2m  4,000 INR  [F3-19]
        + 3.289  mcc                                    = 6012
        + 1.503  ent_merchant_customers                 = absent
        + 1.477  ent_customer_n_events                  = 14
        + 1.129  vel_customer_count_24h                 = 4
        + 0.993  vel_customer_seconds_since_prior       = 2,251
        + 0.771  ent_merchant_refund_ratio              = absent

  #2  score 1.0000  agentic  6,502 INR  [F1-02]
        + 5.285  mnd_mcc_in_scope                       = 0
        + 2.238  mnd_amount_over_ceiling                = 1.192
        + 1.782  mnd_ceiling_breached                   = 1
        + 0.637  ent_mcc_amount_z                       = 1.422
        + 0.552  mnd_deliberation_residual_z            = -1.884
        + 0.509  vel_agent_amount_vs_mean               = 2.072

  #3  score 1.0000  agentic  1,358 INR  [F1-05]
        + 2.303  vel_mandate_hash_count_1h              = 5
        + 1.755  gph_agent_customers                    = 11
        + 1.441  gph_new_edge_share                     = 0.6667
        + 1.042  vel_bin_seconds_since_prior            = 0
        + 0.840  vel_agent_seconds_since_prior          = 0
        + 0.763  ent_customer_n_events                  = 21
```

## The feature that was too good, ablated

`mnd_deliberation_residual_z` — the residual of an agent's deliberation latency against what a ticket that size deserves — separates F1-01 at **0.99 AUC on its own**. That is above the foundry's own 0.95 separability gate, and the gate never saw it: the gate probes **raw columns**, and this is a derived residual.

It has not been silently removed and it has not been silently kept:

| family | recall with the feature | recall without it | delta |
|---|---|---|---|
| F1 | 0.681 | 0.664 | -0.018 |
| F2 | 0.176 | 0.173 | -0.002 |
| F3 | 0.595 | 0.538 | -0.057 |
| F4 | 0.086 | 0.085 | -0.002 |
| F6 | 0.437 | 0.437 | +0.000 |

## What L1 actually uses

| feature | gain share |
|---|---|
| `mcc` | 5.68% |
| `mnd_mcc_in_scope` | 4.98% |
| `ent_merchant_customers` | 4.77% |
| `mnd_amount_over_ceiling` | 4.06% |
| `ent_mcc_amount_z` | 3.28% |
| `ent_customer_n_events` | 2.98% |
| `vel_agent_amount_vs_mean` | 2.98% |
| `txn_round_score` | 2.88% |
| `ent_merchant_refund_ratio` | 2.85% |
| `channel` | 2.80% |
| `mnd_deliberation_residual_z` | 2.37% |
| `gph_device_customers` | 2.36% |
| `vel_merchant_count_7d` | 2.36% |
| `ent_merchant_n_events` | 2.26% |
| `vel_mandate_hash_count_1h` | 2.09% |

## What this does not claim

- **This is not real-world performance.** It is measured on synthetic data whose attacks we wrote. The fidelity scorecard (Day 7) is the argument that the background is realistic; nothing here substitutes for it.
- **F5 is absent from every table.** It is the zero-day holdout family and has no implemented injector, so it is not in the data and cannot be scored. The leave-one-family-out columns and the loop experiment are the closest available stand-ins.
- **L2 is not a detector and is no longer presented as one.** See the section above.
- **L3 covers two of fifteen cards.** It is a specialist, and its overall recall should be read as coverage of the agentic-injection rail rather than as a headline.
- **The current event's own outcome is never a feature.** `auth_response`, `settled` and `settlement_lag_hours` of the row being scored are blocked by name in the feature builder, alongside the label and post-hoc columns. Feeding them in would raise F4-27's recall substantially and mean nothing — an issuer cannot decline a transaction because it was declined.
- **Latency is not measured here.** The feature pass is 0.052 ms/row and the graph pass 0.021 ms/row, but an end-to-end p99 for the whole firewall is a Day 7 number and is not quoted before it is measured.

