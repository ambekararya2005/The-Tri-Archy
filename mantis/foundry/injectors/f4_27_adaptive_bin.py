"""F4-27 — adaptive BIN attack: probe wide and cheap, then concentrate value.

The attack
----------
The operator holds credentials across a small number of BIN ranges and can see
which authorisations approve. Rather than maximising value per attempt, they
*search*: many low-value authorisations spread thinly across the BIN and across
an implausibly wide set of unrelated merchants, reading the outcome pattern to
locate where the decision boundary sits, then pushing higher-value attempts
through the merchants and categories that just approved.

Modelling decisions worth defending
-----------------------------------
* **Probe amounts are resampled from the population's own low quantile band**
  for whatever category the probe landed in, not drawn from an attacker-chosen
  distribution. A ₹40 probe at a jeweller would be a cartoon; a ₹40 probe at a
  bus operator is Tuesday. Sampling per-MCC keeps every probe individually
  ordinary, which is the attack's entire objective function.
* **Escalation reuses probe merchants.** The high-value tail goes back through
  merchants the campaign already touched — that is what "escalating on success"
  means when the only feedback channel is the approve/decline oracle. It also
  produces the merchant fan-in the L4 layer is supposed to see.
* **Two to three BINs per campaign, different ones per campaign.** A campaign
  concentrated on one BIN would make a single BIN indicator a near-perfect
  classifier, which is a property of a lazy generator rather than of BIN attacks.

What the frozen schema cannot represent, stated plainly
-------------------------------------------------------
``TxEvent`` is an *authorisation request*. It carries no response code, so the
decline half of the oracle — the signal ``decline_ratio_1h`` on the card is
named for — is not in this dataset. What is representable, and what this
injector produces, is the request-side footprint: attempt velocity within a BIN
range, probe-band amount clustering, and merchant fan-out. The card keeps
``decline_ratio_1h`` because a deployed issuer has it; the foundry does not
pretend to.

Realism check (measured, not asserted)
--------------------------------------
Best single-feature depth-1 stump AUC: **0.663** (``amount``) — and that is the probe
band, diluted by the escalation tail. No single column separates this attack; it
is only visible in aggregate structure across the BIN, which is the claim the
card makes and the reason the adversarial loop attacks it first.

Measured by ``mantis.foundry.injectors.probe`` against a 200k-event background at
seed 1337, over every column an issuer can read off one authorisation message.
Re-measure with ``python -m mantis.foundry --attacks F4-27``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mantis.foundry.injectors.base import (
    BaseAttack,
    campaign_id,
    card_entry_point,
    demo_main,
    register,
    split_count,
)

__all__ = ["AdaptiveBinAttack", "inject", "main"]

#: Rails an operator can submit card-not-present probes on. ``card_present`` is
#: included because probing a stolen credential at an unattended terminal is a
#: real technique, not because it is convenient.
_RAILS: tuple[str, ...] = ("ecom", "agentic", "card_present")

#: Share of a campaign's volume spent searching rather than extracting.
_PROBE_SHARE: float = 0.78

#: Quantile bands the two phases resample amounts from, per category.
_PROBE_BAND: tuple[float, float] = (0.02, 0.30)
_ESCALATION_BAND: tuple[float, float] = (0.70, 0.95)


@register
class AdaptiveBinAttack(BaseAttack):
    """Wide low-value search across a BIN range, then value concentration."""

    card_id = "F4-27"
    base_events = 200
    base_campaigns = 5

    def inject(
        self, population: pd.DataFrame, intensity: float, rng: np.random.Generator
    ) -> pd.DataFrame:
        """Emit probe-then-escalate campaigns across two or three BINs each."""
        view = self.view
        card_bin = view.frame["card_bin"].to_numpy()
        rail_ok = np.isin(view.frame["channel"].to_numpy(), _RAILS)
        bins = np.unique(card_bin)

        merchant_ids = view.merchants.index.to_numpy()
        merchant_p = view.merchants["n_events"].to_numpy(dtype=float)
        merchant_p /= merchant_p.sum()

        counts = split_count(self.n_events(intensity), self.n_campaigns(intensity), rng)
        starts = view.spread_epochs(len(counts), rng)

        blocks: list[pd.DataFrame] = []
        for c, n in enumerate(counts):
            n = int(n)
            n_probe = max(1, round(n * _PROBE_SHARE))
            n_escalate = max(0, n - n_probe)

            target_bins = rng.choice(bins, size=int(rng.integers(2, 4)), replace=False)
            pool = np.flatnonzero(np.isin(card_bin, target_bins) & rail_ok)
            # A finite stolen-credential set: attempts are spread thinly over it,
            # which is what makes per-card velocity useless and per-BIN velocity
            # the feature that works.
            n_credentials = int(min(pool.size, rng.integers(28, 48)))
            credentials = rng.choice(pool, size=n_credentials, replace=False)
            rows = view.clone(rng.choice(credentials, size=n, replace=True))

            probe_merchants = merchant_ids[
                rng.choice(merchant_ids.size, size=n_probe, p=merchant_p)
            ]
            escalate_merchants = (
                rng.choice(probe_merchants, size=n_escalate)
                if n_escalate
                else np.empty(0, dtype=object)
            )
            view.retarget(rows, np.concatenate([probe_merchants, escalate_merchants]))

            mcc = rows["mcc"].to_numpy()
            amount = np.empty(n, dtype=float)
            amount[:n_probe] = view.draw_amounts(mcc[:n_probe], *_PROBE_BAND, rng)
            if n_escalate:
                amount[n_probe:] = view.draw_amounts(mcc[n_probe:], *_ESCALATION_BAND, rng)
            rows["amount"] = amount

            # The search runs hot for a day or so; the payoff follows it.
            search_seconds = int(rng.integers(20, 40) * 3_600)
            ts = np.empty(n, dtype=np.int64)
            ts[:n_probe] = starts[c] + rng.integers(0, search_seconds, n_probe)
            if n_escalate:
                ts[n_probe:] = starts[c] + search_seconds + rng.integers(0, 14 * 3_600, n_escalate)
            # Each attempt is independent, so each gets its own hour of day.
            view.set_timestamps(rows, ts, rng=rng)

            blocks.append(
                view.finalise(
                    rows,
                    card_id=self.card_id,
                    campaigns=np.full(n, campaign_id(self.card_id, c), dtype=object),
                    rng=rng,
                )
            )
        return pd.concat(blocks, ignore_index=True)


inject = card_entry_point(AdaptiveBinAttack)


def main() -> None:
    """Print a sample campaign. Run: ``python -m mantis.foundry.injectors.f4_27_adaptive_bin``."""
    demo_main(AdaptiveBinAttack)


if __name__ == "__main__":
    main()
