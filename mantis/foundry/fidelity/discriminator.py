"""The adversarial test: can a model tell our rows from real ones?

Every other metric in this package compares one statistic at a time. A generator
can pass all of them and still be obviously synthetic, because "obviously" lives
in the interactions — the combination of a 3 a.m. timestamp, a small ticket, and a
merchant nobody uses is what gives a file away, and no marginal contains it.

So: label the synthetic rows 1, the real rows 0, fit a gradient-boosted tree, and
score it out of fold. **The target is 0.5** — an AUC of 0.5 means the classifier
cannot do better than a coin, which is the only outcome that says the two panels
are indistinguishable on these features. 1.0 means the file announces itself.

Read it as a distance, not a grade
-----------------------------------
``2 * |AUC - 0.5|`` is the total-variation-like separation, and it is reported
beside the raw AUC because "0.62" is hard to place and "24% separable" is not.

The per-feature gain table is the part with the most information in it. A
discriminator that lands above 0.5 is *telling you which column gave you away*,
ranked, which is a to-do list rather than a verdict. That list is the reason this
module exists at the end of a scorecard rather than the beginning: it names the
next thing to fix, and this project's rule is to publish that list instead of
tuning against it three days before submission.

Two honesty constraints on the setup
-------------------------------------
1. **Balanced by subsampling, not by class weight.** With unequal panel sizes a
   classifier can reach a high AUC by learning the prior, and the AUC would then
   partly report how many rows each side happened to contribute.
2. **Out-of-fold scores only.** An in-sample AUC on a boosted tree is near 1.0
   whatever the data looks like, and reporting it would turn this section into a
   measure of model capacity.
"""

from __future__ import annotations

from typing import Any, Final

import numpy as np
import pandas as pd

from mantis.foundry.fidelity.common import SHAPE_FEATURES

__all__ = ["TARGET_AUC", "discriminate"]

#: What an indistinguishable pair of panels scores. Plotted as a line on the
#: scorecard's figure, because a bar chart of AUCs with no reference line invites
#: a reader to think higher is better, and here higher is worse.
TARGET_AUC: Final[float] = 0.5

_PARAMS: Final[dict[str, Any]] = {
    "objective": "binary",
    "n_estimators": 400,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 50,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "verbose": -1,
}


def discriminate(
    synthetic_shape: pd.DataFrame,
    real_shape: pd.DataFrame,
    *,
    seed: int = 1337,
    folds: int = 5,
    exclude: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Fit the real-vs-synthetic classifier and return its out-of-fold AUC.

    ``exclude`` drops named features before fitting. The scorecard runs this
    twice: once on everything, and once without the axes
    :mod:`mantis.foundry.fidelity.adjudicate` attributes to the reference panel.
    Reporting only the second would be the dishonest version - the ablation is a
    judgement, so both numbers are printed and the judgement is printed with the
    measurement that decided it.

    Also returns the same measurement **per feature** — one univariate model per
    column — because the multivariate gain table tells you which feature the tree
    *used* and the univariate table tells you how separable each column is on its
    own. A feature can score high on the second and near zero on the first, which
    means another column already carries the same tell.
    """
    from lightgbm import LGBMClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold

    rng = np.random.default_rng(seed)
    n = min(len(synthetic_shape), len(real_shape))
    a = synthetic_shape.iloc[rng.choice(len(synthetic_shape), n, replace=False)]
    b = real_shape.iloc[rng.choice(len(real_shape), n, replace=False)]

    columns = [name for name in SHAPE_FEATURES if name not in exclude]
    X = pd.concat([a[columns], b[columns]], ignore_index=True)
    y = np.concatenate([np.ones(n, dtype=int), np.zeros(n, dtype=int)])

    oof = np.zeros(len(y), dtype=float)
    gains = np.zeros(len(columns), dtype=float)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    for train_index, test_index in splitter.split(X, y):
        model = LGBMClassifier(random_state=seed, **_PARAMS)
        model.fit(X.iloc[train_index], y[train_index])
        oof[test_index] = model.predict_proba(X.iloc[test_index])[:, 1]
        gains += np.asarray(model.booster_.feature_importance("gain"), dtype=float)

    auc = float(roc_auc_score(y, oof))
    gains = gains / gains.sum() if gains.sum() > 0 else gains

    per_feature = []
    for index, name in enumerate(columns):
        # Univariate separability, by rank rather than by fitting 10 more models:
        # a single feature's ROC-AUC against the panel label *is* the Mann-Whitney
        # statistic, so there is nothing a stump would add.
        column_auc = float(roc_auc_score(y, X[name].to_numpy(dtype=float)))
        per_feature.append(
            {
                "feature": name,
                "alone_auc": max(column_auc, 1.0 - column_auc),
                "gain_share": float(gains[index]),
            }
        )
    per_feature.sort(key=lambda row: -row["alone_auc"])

    return {
        "auc": auc,
        "target": TARGET_AUC,
        "separability": float(2.0 * abs(auc - TARGET_AUC)),
        "n_per_side": int(n),
        "folds": folds,
        "features": columns,
        "excluded": list(exclude),
        "per_feature": per_feature,
        "reading": _reading(auc),
    }


def _reading(auc: float) -> str:
    """Prose picked from the number, so a future run that gets worse says so.

    Same discipline as ``mantis/loop/report.py``'s curve reading: the text is
    derived from the measurement rather than written once against the measurement
    that happened to come out first.
    """
    separability = 2.0 * abs(auc - TARGET_AUC)
    if auc < 0.55:
        return (
            "Indistinguishable on the shape features: a classifier given both panels "
            "cannot beat a coin flip."
        )
    if auc < 0.70:
        return (
            f"Partly separable ({separability:.0%}). The per-feature table below names "
            "which columns carry the tell; every one of them is a foundry to-do."
        )
    if auc < 0.90:
        return (
            f"Clearly separable ({separability:.0%}). The two panels differ in ways a "
            "model finds easily, and the top feature below is where to look first."
        )
    return (
        f"Separable at {separability:.0%}. On these features the synthetic population "
        "is not passing for the reference panel, and the scorecard says so."
    )
