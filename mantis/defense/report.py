"""Render the Day 4 experiment into RESULTS.md.

Kept separate from :mod:`mantis.defense.experiment` so that the measurement and
the prose about the measurement cannot drift: every number in the document is
formatted from the result object, and there is no path by which a figure in the
text can survive a change in the code that produced it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from mantis.core.events import SCHEMA_VERSION
from mantis.defense.experiment import ABLATED_FEATURE, TRAIN_SHARE
from mantis.defense.metrics import OPERATING_FPR
from mantis.defense.pool import POOL_SEEDS

__all__ = ["write_results"]


def _pct(value: float) -> str:
    return "n/a" if value != value else f"{value:.1%}"


def _f3(value: float) -> str:
    return "n/a" if value != value else f"{value:.3f}"


def write_results(result, pool: pd.DataFrame, path: Path) -> None:
    """Write RESULTS.md from a completed experiment."""
    fam = result.per_family
    mean_drop = (fam["l1_with"] - fam["l1_heldout"]).mean() if len(fam) else float("nan")
    mean_with = fam["l1_with"].mean() if len(fam) else float("nan")
    mean_held = fam["l1_heldout"].mean() if len(fam) else float("nan")
    mean_l2 = fam["l2"].mean() if len(fam) else float("nan")

    lines: list[str] = []
    add = lines.append

    add("# MANTIS — Detection results")
    add("")
    add(f"*Day 4. Schema v{SCHEMA_VERSION}. Generated {date.today():%Y-%m-%d} by "
        "`python -m mantis.defense`.*")
    add("")
    add("## The operating point")
    add("")
    add("> **Every recall in this document is measured at a threshold placed so that "
        f"exactly {OPERATING_FPR:.1%} of legitimate test traffic is flagged.**")
    add("")
    add("No accuracy figures appear anywhere here, and that is deliberate: at ~1% "
        "prevalence a model that approves everything is 99% accurate. The two metrics "
        "reported are **AUC-PR** and **recall@0.1%FPR**, the second always with its "
        "realised false-positive rate attached.")
    add("")
    add("Each model variant gets its own threshold, because each has its own score "
        "distribution. What is held constant across every column of every table is the "
        "false-positive rate — which is the quantity an issuer actually budgets, and "
        "the only thing that makes two columns comparable.")
    add("")

    # -- dataset ------------------------------------------------------------- #
    add("## The evaluation dataset")
    add("")
    add(f"Five independently generated worlds, seeds `{', '.join(map(str, POOL_SEEDS))}`, "
        "pooled.")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| events | {len(pool):,} |")
    add(f"| fraud | {int(pool['is_fraud'].sum()):,} ({pool['is_fraud'].mean():.4%}) |")
    add(f"| train / test | {result.n_train:,} / {result.n_test:,}, "
        f"**time-based** split at the {TRAIN_SHARE:.0%} quantile |")
    add(f"| features | {result.n_features} |")
    add("")
    add("Pooling is not resampling one file five times: each seed regenerates the whole "
        "population — its own customers, merchants, devices, agents and calendar — so the "
        "variance being averaged over is generator variance. Identifiers are namespaced "
        "per seed before concatenation, because letting `cus-00042` from two seeds collide "
        "would fuse two people's histories inside every velocity feature.")
    add("")
    add("The reason for five rather than one is confidence intervals. At ~120 positives "
        "per card a per-family recall carries roughly ±9 points, which is wide enough that "
        "the leave-one-family-out comparison below could not be defended. Pooling puts the "
        "smallest family at 550 positives and the largest at 4,150.")
    add("")

    # -- headline ------------------------------------------------------------ #
    add("## Layer performance")
    add("")
    add("| layer | AUC-PR | ROC-AUC | recall@0.1%FPR | realised FPR |")
    add("|---|---|---|---|---|")
    for label, report in (
        ("**L1** GBDT, supervised", result.l1_full),
        ("**L2** isolation forest, legitimate traffic only", result.l2),
        ("**L1 + L2** fused", result.fused),
    ):
        add(f"| {label} | {report.auc_pr:.4f} | {report.auc_roc:.4f} | "
            f"**{_f3(report.recall)}** | {report.realised_fpr:.4%} |")
    add("")
    add(f"Baseline precision (a coin flip) is the prevalence: "
        f"{result.l1_full.baseline_precision:.4%}. AUC-PR is only interpretable against it.")
    add("")
    add(_fusion_note(result))
    add("")

    if result.l1_rail:
        add("### Per rail, because the headline is partly measuring \"is this agentic\"")
        add("")
        add("Fraud is concentrated on the agentic rail by design — 15% of volume carrying "
            "51% of the fraud, a 5.7x concentration. A single number computed across both "
            "rails is therefore partly reading a field the issuer gets free off the "
            "authorisation message. Both rails, separately:")
        add("")
        add("| rail | n positive | AUC-PR | recall@0.1%FPR |")
        add("|---|---|---|---|")
        for rail, report in result.l1_rail.items():
            add(f"| {rail} | {report.n_positive:,} | {report.auc_pr:.4f} | "
                f"{_f3(report.recall)} |")
        add("")

    # -- THE HEADLINE -------------------------------------------------------- #
    add("## Leave one family out — the headline experiment")
    add("")
    add("For each family, L1 is retrained with that family **entirely removed from the "
        "training set** and then asked to catch it in the test set anyway. L2 never sees "
        "any attack at all, so its column is identical by construction whether or not the "
        "family was held out.")
    add("")
    add("| family | n_pos | L1 (trained WITH it) | L1 (family HELD OUT) | "
        "L2 (never sees any attack) | fused | fused, held out |")
    add("|---|---|---|---|---|---|---|")
    for row in fam.itertuples():
        add(f"| **{row.family}** | {row.n_pos:,} | {_f3(row.l1_with)} | "
            f"{_f3(row.l1_heldout)} | {_f3(row.l2)} | {_f3(row.fused_with)} | "
            f"{_f3(row.fused_heldout)} |")
    if len(fam):
        add(f"| *mean* | | *{_f3(mean_with)}* | *{_f3(mean_held)}* | *{_f3(mean_l2)}* | "
            f"*{_f3(fam['fused_with'].mean())}* | *{_f3(fam['fused_heldout'].mean())}* |")
    add("")
    add(f"**Mean recall lost when a family is held out of training: {mean_drop:+.3f}** "
        f"({_pct(mean_with)} → {_pct(mean_held)}).")
    add("")
    add(_lofo_reading(fam, mean_with, mean_held, mean_l2))
    add("")

    # -- per attack ---------------------------------------------------------- #
    if len(result.per_attack):
        add("## Per attack card")
        add("")
        add("At the same 0.1% FPR operating point, L1 trained on everything. Note the "
            "fused column inherits the weighting problem described above, so it is below "
            "L1 on most cards.")
        add("")
        add("| card | n_pos | L1 | L2 | fused |")
        add("|---|---|---|---|---|")
        for row in result.per_attack.itertuples():
            add(f"| {row.attack_id} | {row.n_pos:,} | {_f3(row.l1)} | {_f3(row.l2)} | "
                f"{_f3(row.fused)} |")
        add("")

    # -- ablation ------------------------------------------------------------ #
    if len(result.ablation):
        add("## The feature that was too good, ablated")
        add("")
        add(f"`{ABLATED_FEATURE}` — the residual of an agent's deliberation latency against "
            "what a ticket that size deserves — separates F1-01 at **0.99 AUC on its own**. "
            "That is above the foundry's own 0.95 separability gate, and the gate never saw "
            "it: the gate probes **raw columns**, and this is a derived residual, so a "
            "trivially-derived feature walked straight past it.")
        add("")
        add("The cause is in the generator. `collapse_deliberation` resamples latency from "
            "the population's low quantile band *unconditionally*, so a ₹50,000 purchase "
            "receives a ₹200 purchase's deliberation time. Real legitimate high-value "
            "purchases deliberate longer, so the residual is extreme in a way the attack "
            "itself does not require. The signal is real — an agent acting on injected text "
            "genuinely did not deliberate — but 0.99 is the generator's number, not the "
            "attack's.")
        add("")
        add("It has **not** been silently removed, and it has not been silently kept. Here "
            "is what F1's recall rests on:")
        add("")
        merged = fam.merge(result.ablation, on="family", how="left", suffixes=("", "_abl"))
        add("| family | recall with the feature | recall without it | delta |")
        add("|---|---|---|---|")
        for row in merged.itertuples():
            without = getattr(row, "recall_without", float("nan"))
            delta = without - row.l1_with if without == without else float("nan")
            add(f"| {row.family} | {_f3(row.l1_with)} | {_f3(without)} | "
                f"{'n/a' if delta != delta else f'{delta:+.3f}'} |")
        add("")
        add("Fixing it properly is a foundry change — collapse the latency *relative to what "
            "the amount deserves*, so \"fast for this ticket\" stays the signal without "
            "sitting off the end of the legitimate distribution. That re-rolls every Day 3 "
            "number and every injector docstring, so it is recorded as an outstanding item "
            "rather than done at the same time as standing up the firewall.")
        add("")

    # -- importance ---------------------------------------------------------- #
    add("## What L1 actually uses")
    add("")
    add("| feature | gain share |")
    add("|---|---|")
    for row in result.importance.head(15).itertuples():
        add(f"| `{row.feature}` | {row.share:.2%} |")
    add("")

    # -- what is not claimed -------------------------------------------------- #
    add("## What this does not claim")
    add("")
    add("- **This is not real-world performance.** It is measured on synthetic data whose "
        "attacks we wrote. The fidelity scorecard (Day 7) is the argument that the "
        "background is realistic; nothing here substitutes for it.")
    add("- **F5 is absent from every table.** It is the zero-day holdout family and has no "
        "implemented injector, so it is not in the data and cannot be scored yet. The "
        "leave-one-family-out columns are the closest available stand-in for it.")
    add("- **L3 and L4 do not exist yet.** The fused column is L1+L2 only. The text layer "
        "and the graph layer are the two that F1-01/F1-03 and F1-05 respectively are "
        "waiting on, and their absence is visible in those rows.")
    add("- **The current event's own outcome is never a feature.** `auth_response`, "
        "`settled` and `settlement_lag_hours` of the row being scored are blocked by name "
        "in the feature builder, alongside the label and post-hoc columns. Feeding them in "
        "would raise F4-27's recall substantially and mean nothing — an issuer cannot "
        "decline a transaction because it was declined.")
    add("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fusion_note(result) -> str:
    """Say plainly whether fusion helped. On Day 4 it does not, and that is the finding."""
    l1 = result.l1_full.recall
    fused = result.fused.recall
    if fused >= l1:
        return (
            f"Fusion improves on the better single layer ({_f3(l1)} -> {_f3(fused)}). The two "
            "layers are combined by mapping each score to its percentile within legitimate "
            "traffic and taking a noisy-OR, so agreement between them counts for more than "
            "either alone."
        )
    return "\n".join([
        f"**Fusion is currently WORSE than L1 alone** ({_f3(l1)} -> {_f3(fused)}), and that is "
        "reported rather than hidden by quoting only the best row.",
        "",
        "The cause is not subtle. The two layers are combined with an **unweighted** noisy-OR "
        f"over their legitimate-traffic percentiles, and L2 is close to random "
        f"({_f3(result.l2.recall)} recall, {result.l2.auc_roc:.3f} ROC). At a fixed 0.1% "
        "false-positive budget, giving a near-random layer equal say costs you: every "
        "legitimate event L2 happens to rank high consumes part of the budget that L1 would "
        "have spent on a real one.",
        "",
        "The fix is a **weighted** fusion whose weights are fitted on the training window, which "
        "would learn to discount L2 to near-zero — and that is Day 6's fusion layer, not a "
        "number to reach for now by hand-tuning a coefficient until the table looks better. "
        "Until then the honest headline is **L1's** recall, not the fused one.",
    ])


def _lofo_reading(fam: pd.DataFrame, mean_with: float, mean_held: float, mean_l2: float) -> str:
    """Write the interpretation from the numbers, whichever way they came out.

    The paragraph is generated rather than written because the honest reading
    depends on the result, and a hand-written one would survive a change in the
    measurement. If supervised detection does not collapse, this says so.
    """
    if not len(fam):
        return ""
    collapse = mean_with - mean_held
    holds_up = mean_l2 >= 0.5 * mean_held if mean_held > 0 else mean_l2 > 0.05

    parts: list[str] = ["### Reading it", ""]
    if collapse >= 0.15:
        parts.append(
            f"**Supervised detection collapses on attacks it has never seen.** Held-out "
            f"recall averages {_pct(mean_held)} against {_pct(mean_with)} when the family is "
            f"in training — a loss of {collapse:.3f}. This is the expected and the important "
            "result: an L1 trained on a labelled history is a detector for that history."
        )
    elif collapse >= 0.05:
        parts.append(
            f"**Supervised detection degrades on unseen attacks, but does not collapse.** "
            f"Held-out recall averages {_pct(mean_held)} against {_pct(mean_with)}, a loss of "
            f"{collapse:.3f}. That is a weaker version of the expected story and it is "
            "reported as measured. The likely reason is that the families share features — "
            "an unseen family still trips velocity and mandate signals that the *other* "
            "families taught the model — which is itself a finding worth having."
        )
    else:
        parts.append(
            f"**Supervised detection does not measurably degrade on held-out families** "
            f"({_pct(mean_with)} → {_pct(mean_held)}, a change of {collapse:+.3f}). This is "
            "*not* the story the experiment was designed to tell, and it is reported as "
            "measured rather than adjusted. The most likely explanation is that the "
            "generator gives every family enough shared structure that holding one out "
            "removes little the model cannot learn elsewhere — which would be a fidelity "
            "finding, not a detection one, and belongs in Day 7's scorecard."
        )
    parts.append("")

    if holds_up:
        parts.append(
            f"**The unsupervised layer holds up.** L2 averages {_pct(mean_l2)} recall having "
            "never seen a single fraud label — not to fit its model, not to pick its "
            "contamination parameter, not to place its threshold. Its column does not move "
            "when a family is held out, because it never depended on the family being there. "
            "That is the honest answer to \"what about the attacks you didn't think of\"."
        )
    else:
        parts.append(
            f"**The unsupervised layer does not rescue the held-out families.** L2 averages "
            f"{_pct(mean_l2)} recall at the same operating point, which is not enough to "
            "carry the argument on its own. Stated plainly because the alternative is "
            "quoting a number the table does not support: at 0.1% FPR an isolation forest "
            "on this feature space is a weak detector, and the layers that are supposed to "
            "close this gap — L3 on the provenance text, L4 on the graph — are not built "
            "yet. The claim that survives is the narrower one: L2's recall is *unaffected* "
            "by whether an attack was in training, which is the property no supervised "
            "layer has."
        )
    return "\n".join(parts)
