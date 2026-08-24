"""The two numbers this project reports, and the one it never does.

CLAUDE.md HARD RULE 2: **never report accuracy.** At a 1% fraud rate a model that
approves everything is 99% accurate, so quoting accuracy signals either that you
do not know the domain or that you are hoping the reader does not. The metrics
here are the two that survive class imbalance:

``AUC-PR``
    Area under the precision-recall curve. Unlike ROC-AUC it does not flatter a
    model on an imbalanced problem, because the negative class does not dominate
    the denominator of precision.

``recall@0.1%FPR``
    The share of fraud caught when the threshold is set so that exactly 0.1% of
    **legitimate** traffic is flagged. This is the number an issuer cares about,
    because 0.1% of their volume is a real number of real customers they will
    have to call, and it is the number that makes two models comparable — an
    AUC-PR is a curve, and you cannot staff a curve.

Always with the operating point stated. A recall with no FPR attached is not a
result, it is a hope.

The threshold is fitted on legitimate traffic only
---------------------------------------------------
:func:`threshold_at_fpr` takes the negatives, sorts their scores, and reads off
the quantile. It never sees a positive. That matters because the alternative —
picking the threshold that maximises something on a labelled test set — is
fitting the operating point to the answer, and the resulting recall is not one a
deployment would reproduce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

__all__ = ["OPERATING_FPR", "ScoreReport", "recall_at_fpr", "score_report", "threshold_at_fpr"]

#: The operating point every headline number in this project is quoted at.
OPERATING_FPR: Final[float] = 0.001


def threshold_at_fpr(scores: np.ndarray, labels: np.ndarray, fpr: float = OPERATING_FPR) -> float:
    """Score threshold flagging exactly ``fpr`` of legitimate traffic.

    Fitted on the negatives alone; see the module docstring. Returns ``+inf``
    when there are too few negatives to place the quantile, so that a caller who
    ignores the degenerate case flags nothing rather than everything.
    """
    negatives = np.asarray(scores)[~np.asarray(labels, dtype=bool)]
    negatives = negatives[np.isfinite(negatives)]
    if negatives.size < int(1 / max(fpr, 1e-12)):
        # Fewer negatives than the reciprocal of the target FPR means the
        # quantile sits between two points and cannot be read honestly.
        return float("inf")
    return float(np.quantile(negatives, 1.0 - fpr))


def recall_at_fpr(
    scores: np.ndarray, labels: np.ndarray, fpr: float = OPERATING_FPR
) -> tuple[float, float]:
    """``(recall, realised_fpr)`` at the threshold that targets ``fpr``.

    The realised FPR is returned rather than assumed: with ties in the score
    distribution — and a tree ensemble produces plenty — the achieved rate can
    sit meaningfully off the target, and quoting the target when you achieved
    something else is the quiet way a recall number becomes untrue.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    cut = threshold_at_fpr(scores, labels, fpr)
    if not np.isfinite(cut):
        return float("nan"), float("nan")
    flagged = scores >= cut
    recall = float(flagged[labels].mean()) if labels.any() else float("nan")
    realised = float(flagged[~labels].mean()) if (~labels).any() else float("nan")
    return recall, realised


@dataclass(frozen=True, slots=True)
class ScoreReport:
    """Everything worth saying about one score vector, at one operating point."""

    n: int
    n_positive: int
    auc_pr: float
    auc_roc: float
    recall: float
    realised_fpr: float
    threshold: float
    baseline_precision: float

    def line(self, label: str) -> str:
        return (
            f"  {label:<26} AUC-PR {self.auc_pr:.4f}  ROC {self.auc_roc:.4f}  "
            f"recall@{self.realised_fpr:.4%}FPR {self.recall:.4f}  (n+={self.n_positive:,})"
        )


def score_report(
    scores: np.ndarray, labels: np.ndarray, fpr: float = OPERATING_FPR
) -> ScoreReport:
    """AUC-PR, ROC-AUC and recall at the fixed operating point."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    floor = float(np.nanmin(scores)) if np.isfinite(scores).any() else 0.0
    finite = np.nan_to_num(scores, nan=floor)

    degenerate = not labels.any() or labels.all()
    recall, realised = recall_at_fpr(finite, labels, fpr)
    return ScoreReport(
        n=len(labels),
        n_positive=int(labels.sum()),
        auc_pr=float("nan") if degenerate else float(average_precision_score(labels, finite)),
        auc_roc=float("nan") if degenerate else float(roc_auc_score(labels, finite)),
        recall=recall,
        realised_fpr=realised,
        threshold=threshold_at_fpr(finite, labels, fpr),
        # The precision a coin flip would get: the prevalence. Quoted next to
        # AUC-PR because AUC-PR is only interpretable against it.
        baseline_precision=float(labels.mean()) if len(labels) else float("nan"),
    )


def recall_at_fixed_threshold(
    scores: np.ndarray, labels: np.ndarray, threshold: float
) -> float:
    """Recall for a subset, at a threshold fitted somewhere else.

    Per-family recall **must** use this rather than re-fitting a threshold per
    family. A threshold refitted on one family's negatives is a different
    operating point for every row of the table, and the columns stop being
    comparable — which is exactly what the leave-one-family-out table needs them
    to be.
    """
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    if not labels.any() or not np.isfinite(threshold):
        return float("nan")
    return float((scores[labels] >= threshold).mean())
