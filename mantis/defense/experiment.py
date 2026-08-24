"""The Day 4 experiment: L1, L2, fusion, and leave-one-family-out.

The headline result
--------------------
For each implemented family, retrain L1 with that family **entirely excluded from
training** and measure its recall anyway. Put that next to the recall L1 gets
when it *has* seen the family, and next to L2, which never sees any attack at
all. Three columns, one question:

    *What happens to your detector when the attacker does something you did not
    put in the training set?*

Every fraud system in production faces this and most benchmarks quietly avoid it
by splitting at random. The answer here is a measurement, and it is reported
whichever way it comes out.

The operating point, stated once
----------------------------------
Every recall in every table is measured at a threshold placed so that **exactly
0.1% of legitimate test traffic is flagged**. Each model variant gets its own
threshold, because each has its own score distribution; what is held constant is
the false-positive rate, which is the thing an issuer actually budgets. Holding
the *threshold* constant instead would compare models at different FP rates and
the columns would not mean anything next to each other.

That threshold is read off the legitimate rows of the test period. A deployment
does the same thing from unlabelled live traffic — at ~1% prevalence the
difference between "the 99.9th percentile of legitimate traffic" and "the 99.9th
percentile of all traffic" is third-order — but the labelled version is used here
because it is exact and because pretending otherwise would be theatre.

Fusion
-------
Each layer's score is converted to its own **legitimate-traffic percentile**, so
an isolation-forest path length and a boosting margin become comparable, then
combined with a noisy-OR. Noisy-OR rather than a maximum because agreement should
count for something: an event in the 99th percentile of both layers is more
suspicious than one in the 99th of either alone, and the maximum rule throws that
away. The fused score is thresholded by the same 0.1%-FPR rule as the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np
import pandas as pd

from mantis.defense.features import FeatureBuilder
from mantis.defense.l1_gbdt import L1Model
from mantis.defense.l2_novelty import L2Model
from mantis.defense.metrics import (
    OPERATING_FPR,
    ScoreReport,
    recall_at_fixed_threshold,
    score_report,
    threshold_at_fpr,
)

__all__ = ["FAMILIES", "ExperimentResult", "run_experiment"]

#: Share of the pooled chronology used for training.
TRAIN_SHARE: Final[float] = 0.70

#: Families with at least one implemented injector. F5 is deliberately absent:
#: it is the zero-day holdout family (CLAUDE.md §8).
FAMILIES: Final[tuple[str, ...]] = ("F1", "F2", "F3", "F4", "F6")


def _legit_percentile(scores: np.ndarray, legit_reference: np.ndarray) -> np.ndarray:
    """Map scores onto their percentile within the legitimate score distribution.

    This is what makes two layers commensurable. A raw L1 margin and a raw L2
    path length share no scale, but "this event is more extreme than 99.4% of
    legitimate traffic" means the same thing for both.
    """
    reference = np.sort(np.asarray(legit_reference, dtype=float))
    if reference.size == 0:
        return np.zeros_like(scores, dtype=float)
    return np.searchsorted(reference, np.asarray(scores, dtype=float), side="left") / reference.size


def _noisy_or(*percentiles: np.ndarray) -> np.ndarray:
    """Combine layer percentiles. Agreement raises the score; either alone still counts."""
    out = np.ones(len(percentiles[0]), dtype=float)
    for p in percentiles:
        out *= 1.0 - np.clip(p, 0.0, 1.0 - 1e-12)
    return 1.0 - out


@dataclass(slots=True)
class ExperimentResult:
    """Everything the CLI and RESULTS.md need, computed once."""

    n_train: int
    n_test: int
    n_features: int
    prevalence: float
    l1_full: ScoreReport = None  # type: ignore[assignment]
    l2: ScoreReport = None  # type: ignore[assignment]
    fused: ScoreReport = None  # type: ignore[assignment]
    l1_rail: dict[str, ScoreReport] = field(default_factory=dict)
    per_family: pd.DataFrame = field(default_factory=pd.DataFrame)
    per_attack: pd.DataFrame = field(default_factory=pd.DataFrame)
    importance: pd.DataFrame = field(default_factory=pd.DataFrame)
    ablation: pd.DataFrame = field(default_factory=pd.DataFrame)


def run_experiment(
    pool: pd.DataFrame,
    *,
    seed: int = 1337,
    fpr: float = OPERATING_FPR,
    verbose: bool = True,
) -> ExperimentResult:
    """Fit every layer, then run leave-one-family-out. Returns one result object."""

    def log(message: str) -> None:
        if verbose:
            print(message, flush=True)

    pool = pool.sort_values("ts", kind="stable").reset_index(drop=True)
    cut = pool["ts"].quantile(TRAIN_SHARE)
    train_mask = pool["ts"] <= cut

    log(f"  time split at {cut:%Y-%m-%d}: train {int(train_mask.sum()):,} / "
        f"test {int((~train_mask).sum()):,}")

    log("  building features (one continuous pass over the pooled chronology)...")
    builder = FeatureBuilder()
    X = builder.fit_transform_stream(pool, train_mask)
    y = pool["is_fraud"].to_numpy(dtype=bool)
    family = pool["attack_id"].fillna("").str.slice(0, 2).to_numpy()

    tr = train_mask.to_numpy()
    te = ~tr
    X_tr, X_te = X[tr], X[te]
    y_tr, y_te = y[tr], y[te]
    fam_te = family[te]
    log(f"  {X.shape[1]} features; train fraud {int(y_tr.sum()):,}, test fraud {int(y_te.sum()):,}")

    # -- L1, trained on everything --------------------------------------------- #
    log("  fitting L1 (all families)...")
    l1 = L1Model(seed=seed).fit(X_tr, y_tr, timestamps=pool.loc[tr, "ts"])
    s1_te = l1.score(X_te)
    l1_report = score_report(s1_te, y_te, fpr)
    l1_threshold = l1_report.threshold

    # -- L2, trained on legitimate traffic only --------------------------------- #
    log("  fitting L2 (LEGITIMATE ROWS ONLY)...")
    legit_tr = X_tr[~y_tr]
    l2 = L2Model(seed=seed).fit(legit_tr, np.zeros(len(legit_tr), dtype=bool))
    s2_te = l2.score(X_te)
    l2_report = score_report(s2_te, y_te, fpr)
    l2_threshold = l2_report.threshold

    # -- fusion ------------------------------------------------------------------ #
    p1 = _legit_percentile(s1_te, s1_te[~y_te])
    p2 = _legit_percentile(s2_te, s2_te[~y_te])
    fused_te = _noisy_or(p1, p2)
    fused_report = score_report(fused_te, y_te, fpr)
    fused_threshold = fused_report.threshold

    # -- per-rail L1, because the headline is partly measuring "is this agentic" -- #
    # CLAUDE.md: fraud is 5.7x concentrated on the agentic rail by design, so a
    # number computed across both rails is partly reading a field the issuer gets
    # free off the authorisation message. Both rails are reported separately.
    rail_reports: dict[str, ScoreReport] = {}
    is_agentic = pool["ag_agent_id"].notna().to_numpy()[te]
    for name, mask in (("agentic", is_agentic), ("classic", ~is_agentic)):
        if mask.sum() and y_te[mask].any():
            rail_reports[name] = score_report(s1_te[mask], y_te[mask], fpr)

    # -- THE HEADLINE: leave one family out -------------------------------------- #
    rows: list[dict[str, object]] = []
    for fam in FAMILIES:
        in_family_te = fam_te == fam
        n_pos = int(in_family_te.sum())
        if n_pos == 0:
            continue
        log(f"  leave-one-family-out: retraining L1 without {fam} "
            f"({int((family[tr] == fam).sum()):,} training positives removed)...")

        # Drop the family from TRAIN only. It stays in test, which is the point.
        keep = ~((family[tr] == fam) & y_tr)
        l1_held = L1Model(seed=seed).fit(
            X_tr[keep], y_tr[keep], timestamps=pool.loc[tr, "ts"][keep]
        )
        s_held = l1_held.score(X_te)
        # Its own threshold: a different model has a different score
        # distribution, and what is held fixed across columns is the FPR.
        held_threshold = threshold_at_fpr(s_held, y_te, fpr)

        p_held = _legit_percentile(s_held, s_held[~y_te])
        fused_held = _noisy_or(p_held, p2)
        fused_held_threshold = threshold_at_fpr(fused_held, y_te, fpr)

        rows.append(
            {
                "family": fam,
                "n_pos": n_pos,
                "l1_with": recall_at_fixed_threshold(s1_te, in_family_te, l1_threshold),
                "l1_heldout": recall_at_fixed_threshold(s_held, in_family_te, held_threshold),
                "l2": recall_at_fixed_threshold(s2_te, in_family_te, l2_threshold),
                "fused_with": recall_at_fixed_threshold(fused_te, in_family_te, fused_threshold),
                "fused_heldout": recall_at_fixed_threshold(
                    fused_held, in_family_te, fused_held_threshold
                ),
            }
        )
    per_family = pd.DataFrame(rows)

    # -- per attack card, at the full model's operating point --------------------- #
    attack_te = pool["attack_id"].fillna("").to_numpy()[te]
    attack_rows = []
    for card in sorted({a for a in attack_te if a}):
        mask = attack_te == card
        attack_rows.append(
            {
                "attack_id": card,
                "n_pos": int(mask.sum()),
                "l1": recall_at_fixed_threshold(s1_te, mask, l1_threshold),
                "l2": recall_at_fixed_threshold(s2_te, mask, l2_threshold),
                "fused": recall_at_fixed_threshold(fused_te, mask, fused_threshold),
            }
        )
    per_attack = pd.DataFrame(attack_rows)

    # -- the ablation the Day 4 review demanded ------------------------------------ #
    log("  ablating mnd_deliberation_residual_z...")
    ablation = _ablate(X_tr, y_tr, X_te, y_te, fam_te, pool.loc[tr, "ts"], seed, fpr)

    return ExperimentResult(
        n_train=int(tr.sum()),
        n_test=int(te.sum()),
        n_features=X.shape[1],
        prevalence=float(y_te.mean()),
        l1_full=l1_report,
        l2=l2_report,
        fused=fused_report,
        l1_rail=rail_reports,
        per_family=per_family,
        per_attack=per_attack,
        importance=l1.importance(20),
        ablation=ablation,
    )


#: The feature the Day 4 review found separating F1-01 at 0.99 AUC on its own.
#: See ``RESULTS.md`` and ``features/mandate.py``.
ABLATED_FEATURE: Final[str] = "mnd_deliberation_residual_z"


def _ablate(
    X_tr: pd.DataFrame,
    y_tr: np.ndarray,
    X_te: pd.DataFrame,
    y_te: np.ndarray,
    fam_te: np.ndarray,
    ts_tr: pd.Series,
    seed: int,
    fpr: float,
) -> pd.DataFrame:
    """Refit L1 without the one feature that is too good, and report the delta.

    ``mnd_deliberation_residual_z`` separates F1-01 at 0.99 AUC by itself, which
    is above the foundry's own 0.95 separability gate. The gate never saw it
    because the gate probes **raw columns** and this is a derived residual, so a
    trivially-derived feature walked straight past it. Reporting F1's recall both
    with and without the feature is the honest way to show how much of that
    recall rests on a generator artefact rather than on the attack.
    """
    if ABLATED_FEATURE not in X_tr.columns:
        return pd.DataFrame()
    columns = [c for c in X_tr.columns if c != ABLATED_FEATURE]
    model = L1Model(seed=seed).fit(X_tr[columns], y_tr, timestamps=ts_tr)
    scores = model.score(X_te[columns])
    threshold = threshold_at_fpr(scores, y_te, fpr)

    rows = []
    for fam in FAMILIES:
        mask = fam_te == fam
        if mask.sum():
            rows.append(
                {
                    "family": fam,
                    "n_pos": int(mask.sum()),
                    "recall_without": recall_at_fixed_threshold(scores, mask, threshold),
                }
            )
    return pd.DataFrame(rows)
