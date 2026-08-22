"""Contract tests for the legitimate population foundry.

Three things are being defended here, in descending order of how badly a failure
would hurt:

1. **No label leakage and no fraud in the background.** The whole evaluation
   rests on the base population being clean (HARD RULE 1). A single stray
   ``is_fraud=True`` here would silently corrupt every metric downstream.
2. **Determinism.** A judge re-running the pipeline must get the numbers on the
   slides (CLAUDE.md §5).
3. **Coherence of the agentic block.** A mandate that does not cover the
   purchase it authorised is an *attack*, and the base population must not
   accidentally contain any — otherwise the F1 injectors have nothing to add and
   the L0 rules fire on legitimate traffic.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mantis.core.events import AGENTIC_COLUMNS, ALL_COLUMNS, LABEL_COLUMNS, Channel, MandateType
from mantis.foundry.base.calibration import calibration_report
from mantis.foundry.base.entities import MAX_CARDS, MAX_DEVICES, build_population
from mantis.foundry.base.reference import ReferenceStats, load_reference_stats
from mantis.foundry.base.simulator import SimulationConfig, iter_events, simulate_frame

SMALL = SimulationConfig(n_events=4_000, seed=7, n_customers=400, n_merchants=900)


@pytest.fixture(scope="module")
def stats() -> ReferenceStats:
    return load_reference_stats()


@pytest.fixture(scope="module")
def frame(stats: ReferenceStats) -> pd.DataFrame:
    """One modest population, reused across the module. Generation is not free."""
    return simulate_frame(SMALL, stats)


# --------------------------------------------------------------------------- #
# Calibration object
# --------------------------------------------------------------------------- #


def test_prior_weights_are_normalised(stats: ReferenceStats) -> None:
    """Defaults must pass through the field validators, not skip them.

    Pydantic does not validate defaults unless asked. It is asked
    (``validate_default=True``); if that ever regresses, every ``rng.choice`` in
    the simulator fails at runtime instead of here.
    """
    assert sum(stats.hour_weights) == pytest.approx(1.0)
    assert sum(stats.dow_weights) == pytest.approx(1.0)
    assert sum(p.weight for p in stats.mcc_profiles) == pytest.approx(1.0)
    assert sum(stats.merchant_country_weights.values()) == pytest.approx(1.0)
    for table in (stats.entry_mode_weights, stats.threeds_weights):
        for channel in Channel:
            assert sum(table[channel.value].values()) == pytest.approx(1.0)


def test_missing_stats_file_falls_back_to_priors(tmp_path: Path) -> None:
    """A clean clone has no fitted file. That is not an error (HARD RULE 4)."""
    loaded = load_reference_stats(tmp_path / "absent.json")
    assert loaded.source == "indian-market-priors"
    assert not loaded.is_fitted


def test_malformed_stats_file_raises(tmp_path: Path) -> None:
    """A present-but-broken file must not silently revert to priors.

    Silently reverting would make the fidelity scorecard misreport its own
    provenance, which is worse than crashing.
    """
    bad = tmp_path / "reference_stats.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable"):
        load_reference_stats(bad)


def test_partial_override_inherits_the_rest(tmp_path: Path, stats: ReferenceStats) -> None:
    """A JSON naming only one block replaces that block and keeps the others."""
    path = tmp_path / "reference_stats.json"
    path.write_text(json.dumps({"burst_probability": 0.4}), encoding="utf-8")
    loaded = load_reference_stats(path)

    assert loaded.burst_probability == 0.4
    assert loaded.is_fitted
    assert len(loaded.mcc_profiles) == len(stats.mcc_profiles)


def test_legitimate_traffic_may_not_carry_mandate_none() -> None:
    """``mandate_type='none'`` is an F1 attack shape, not a base-population fact."""
    with pytest.raises(ValueError, match="always carries a mandate"):
        ReferenceStats(mandate_type_weights={"none": 0.5, "cart": 0.5})


# --------------------------------------------------------------------------- #
# HARD RULE 1: the background is clean
# --------------------------------------------------------------------------- #


def test_population_carries_no_fraud(frame: pd.DataFrame) -> None:
    """The base population is the background. Nothing in it is an attack."""
    assert not frame["is_fraud"].any()
    assert frame["attack_id"].isna().all()
    assert frame["attack_campaign"].isna().all()


def test_column_set_is_exactly_the_schema_contract(frame: pd.DataFrame) -> None:
    """No extra columns, no missing ones, same order as ``ALL_COLUMNS``."""
    assert tuple(frame.columns) == ALL_COLUMNS
    assert ALL_COLUMNS[-len(LABEL_COLUMNS) :] == LABEL_COLUMNS


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def test_same_seed_reproduces_the_population(stats: ReferenceStats) -> None:
    a = simulate_frame(SMALL, stats)
    b = simulate_frame(SMALL, stats)
    pd.testing.assert_frame_equal(a, b)


def test_different_seed_changes_the_population(stats: ReferenceStats) -> None:
    other = SimulationConfig(
        n_events=SMALL.n_events, seed=SMALL.seed + 1, n_customers=400, n_merchants=900
    )
    assert not simulate_frame(SMALL, stats)["event_id"].equals(
        simulate_frame(other, stats)["event_id"]
    )


def test_entities_depend_on_the_seed_alone(stats: ReferenceStats) -> None:
    """Changing the transaction count must not reshuffle the standing population.

    Injectors and the defense layer both key off customer and merchant ids. If
    those moved when ``--n`` changed, a 10k debugging run and a 200k demo run
    would describe different worlds.
    """
    small = build_population(stats, seed=7, n_customers=200, n_merchants=400)
    again = build_population(stats, seed=7, n_customers=200, n_merchants=400)
    assert np.array_equal(small.customer_ids, again.customer_ids)
    assert np.array_equal(small.merchant_ids, again.merchant_ids)
    assert np.array_equal(small.home_lat, again.home_lat)


# --------------------------------------------------------------------------- #
# Rail consistency
# --------------------------------------------------------------------------- #


def test_classic_rails_leave_every_agentic_column_null(frame: pd.DataFrame) -> None:
    classic = frame[frame["channel"] != Channel.AGENTIC.value]
    assert len(classic) > 0
    for column in AGENTIC_COLUMNS:
        assert classic[column].isna().all(), f"{column} populated on a classic rail"


def test_card_present_has_a_terminal_and_no_device_or_ip(frame: pd.DataFrame) -> None:
    """A chip transaction at a lane has a terminal, not a phone."""
    cp = frame[frame["channel"] == Channel.CARD_PRESENT.value]
    assert len(cp) > 0
    assert cp["terminal_id"].notna().all()
    assert cp["device_id"].isna().all()
    assert cp["ip"].isna().all()
    assert cp["lat"].notna().all()


def test_remote_rails_have_no_terminal(frame: pd.DataFrame) -> None:
    remote = frame[frame["channel"] != Channel.CARD_PRESENT.value]
    assert remote["terminal_id"].isna().all()
    assert remote["ip"].notna().all()


def test_geo_is_not_uniformly_populated(frame: pd.DataFrame) -> None:
    """A file with a location on every single row is an obvious synthetic tell."""
    missing = frame["lat"].isna().mean()
    assert 0.01 < missing < 0.30


# --------------------------------------------------------------------------- #
# Entity stability
# --------------------------------------------------------------------------- #


def test_customers_keep_a_small_stable_set_of_cards_and_devices(frame: pd.DataFrame) -> None:
    """Credentials and devices belong to the customer, not to the transaction."""
    per_customer = frame.groupby("customer_id")
    assert per_customer["card_bin"].nunique().max() <= MAX_CARDS
    assert per_customer["device_id"].nunique().max() <= MAX_DEVICES + 2  # + agent devices


def test_merchant_popularity_is_heavy_tailed(frame: pd.DataFrame) -> None:
    """Zipf, not uniform. A flat merchant distribution kills every graph feature."""
    counts = frame["merchant_id"].value_counts().to_numpy()
    top_share = counts[: max(1, len(counts) // 100)].sum() / counts.sum()
    assert top_share > 0.05


# --------------------------------------------------------------------------- #
# The agentic block must be internally coherent
# --------------------------------------------------------------------------- #


def test_agentic_share_hits_the_target(frame: pd.DataFrame, stats: ReferenceStats) -> None:
    share = (frame["channel"] == Channel.AGENTIC.value).mean()
    assert share == pytest.approx(stats.agentic_share, abs=0.005)


def test_legitimate_mandates_actually_cover_their_purchase(frame: pd.DataFrame) -> None:
    """The base population must contain zero mandate-scope violations.

    Every clause here is an L0 rule. If the background tripped any of them, the
    firewall would fire on legitimate traffic and the F1 injectors would have
    nothing left to demonstrate.
    """
    ag = frame[frame["channel"] == Channel.AGENTIC.value]
    assert len(ag) > 0

    assert (ag["amount"] <= ag["ag_scope_max_amount"]).all(), "spend exceeds the mandate ceiling"
    assert ag.apply(lambda r: r["mcc"] in r["ag_scope_categories"], axis=1).all(), (
        "purchased category outside the mandate scope"
    )

    bound = ag[ag["ag_mandate_type"] != MandateType.INTENT.value]
    assert bound.apply(
        lambda r: r["merchant_id"] in r["ag_scope_allowed_merchants"], axis=1
    ).all(), "cart/payment mandate paid a merchant it did not allow"

    age = (ag["ts"] - ag["ag_mandate_issued_ts"]).dt.total_seconds()
    assert (age > 0).all(), "mandate issued after the authorisation it authorised"
    assert (age < ag["ag_mandate_ttl_seconds"]).all(), "mandate expired before use"

    assert ag["ag_delegation_depth"].max() <= 3
    assert ag["ag_provenance_chain"].map(len).min() >= 2


def test_legitimate_spend_approaches_the_mandate_ceiling(frame: pd.DataFrame) -> None:
    """Otherwise "spent close to the limit" would be a free, fake detector."""
    ag = frame[frame["channel"] == Channel.AGENTIC.value]
    ratio = ag["amount"] / ag["ag_scope_max_amount"]
    assert ratio.max() > 0.9
    assert ratio.median() > 0.4


def test_l0_flags_are_not_perfect_separators(frame: pd.DataFrame) -> None:
    """A legitimate tail is unregistered / unverified, on purpose.

    If every legitimate agent were KYA-registered, ``kya_unregistered`` alone
    would score perfect recall on a generator artefact rather than on anything
    real. See modelling choice 1 in the simulator docstring.
    """
    ag = frame[frame["channel"] == Channel.AGENTIC.value]
    assert 0.0 < (~ag["ag_kya_registered"].astype(bool)).mean() < 0.10
    assert 0.0 < (~ag["ag_consent_sig_valid"].astype(bool)).mean() < 0.05


def test_human_presence_shows_up_in_the_telemetry(frame: pd.DataFrame) -> None:
    """F1-09 needs a real gap to forge: watched sessions look human, others do not."""
    ag = frame[frame["channel"] == Channel.AGENTIC.value]
    watched = ag[ag["ag_human_present"].astype(bool)]
    unwatched = ag[~ag["ag_human_present"].astype(bool)]

    assert watched["ag_cursor_entropy"].median() > 3 * unwatched["ag_cursor_entropy"].median()
    assert watched["ag_dwell_time_ms"].median() > 3 * unwatched["ag_dwell_time_ms"].median()


def test_provenance_chain_ends_at_the_merchant_paid(frame: pd.DataFrame) -> None:
    """L3 depends on the causal trail actually being causal."""
    ag = frame[frame["channel"] == Channel.AGENTIC.value].head(200)
    for _, row in ag.iterrows():
        assert row["ag_provenance_chain"][-1].startswith("https://shop.")
        assert len(row["ag_ingested_content_ids"]) == len(row["ag_provenance_chain"])


def test_agentic_rail_uses_agent_tokens_only(frame: pd.DataFrame) -> None:
    ag = frame[frame["channel"] == Channel.AGENTIC.value]
    assert (ag["entry_mode"] == "agent_token").all()


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


def test_population_tracks_its_own_reference(frame: pd.DataFrame, stats: ReferenceStats) -> None:
    """The sampler must reproduce the distribution it was handed.

    Thresholds are loose because this fixture is only 4k events; the 200k gate
    run lands roughly an order of magnitude tighter.
    """
    report = calibration_report(frame, stats)
    assert report["amount_ks_distance"] < 0.04
    assert report["hour_total_variation"] < 0.06
    assert report["mcc_mix_max_abs_delta"] < 0.02
    assert 0.5 < report["zipf_exponent_realised"] < 1.5


def test_events_are_ordered_and_inside_the_window(frame: pd.DataFrame) -> None:
    assert frame["ts"].is_monotonic_increasing
    span = (frame["ts"].max() - frame["ts"].min()).days
    assert 0 < span <= SMALL.window_days


def test_iter_events_yields_validated_models(stats: ReferenceStats) -> None:
    """Every event is constructed through ``TxEvent``, so the frozen schema's
    rail-consistency and label-integrity validators have all run."""
    cfg = SimulationConfig(n_events=200, seed=3, n_customers=60, n_merchants=200)
    events = list(iter_events(cfg, stats))

    assert len(events) == 200
    assert all(ev.is_fraud is False for ev in events)
    agentic = [ev for ev in events if ev.channel is Channel.AGENTIC]
    assert agentic and all(ev.agentic is not None for ev in agentic)


# --------------------------------------------------------------------------- #
# Regressions from the Day 1 adversarial audit
#
# Each test below pins a bug the audit actually found. They are written against
# the *mechanism*, not the symptom, so they keep holding if the priors move.
# --------------------------------------------------------------------------- #


def test_population_is_stable_across_hash_seeds() -> None:
    """A seeded run must not depend on PYTHONHASHSEED.

    The audit caught ``--seed 7`` producing four different populations on one
    machine: a set of strings was iterated inside a loop that consumes the RNG,
    and CPython randomises string hashing per process. Subprocesses are the only
    way to see this, because everything inside one process shares a hash seed.
    """
    import os
    import subprocess
    import sys

    root = str(Path(__file__).resolve().parents[1])
    probe = (
        f"import sys;sys.path.insert(0,{root!r});"
        "from mantis.foundry.base.simulator import SimulationConfig,simulate_frame;"
        "f=simulate_frame(SimulationConfig(n_events=600,seed=7,n_customers=120,n_merchants=300));"
        "print(int(f['amount'].sum()*100), f['entry_mode'].value_counts().to_dict())"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
        ).stdout.strip()
        for seed in ("0", "1", "12345")
    }
    assert len(outputs) == 1, f"population varies with PYTHONHASHSEED: {outputs}"


def test_no_device_belongs_exclusively_to_one_rail(frame: pd.DataFrame) -> None:
    """Some devices must carry both agentic and classic traffic.

    On-device agents run on hardware the cardholder already uses. Without them
    every device was 100% agentic or 0% agentic -- a perfect rail separator
    hiding inside an ordinary identity column.
    """
    by_device = frame.dropna(subset=["device_id"]).groupby("device_id")["channel"]
    agentic_share = by_device.apply(lambda s: float((s == "agentic").mean()))
    mixed = ((agentic_share > 0.0) & (agentic_share < 1.0)).sum()
    assert mixed > 0.05 * len(agentic_share), (
        f"only {mixed} of {len(agentic_share)} devices carry both rails"
    )


def test_no_customer_has_a_hard_zero_agent_propensity(stats: ReferenceStats) -> None:
    """Agent adoption is graded, never a binary flag.

    A binary adopter flag gave 70% of customers exactly zero chance of an agentic
    event, which made ``customer_id`` a 0.90-AUC predictor of the rail. Adoption
    stays concentrated -- L4 fan-out needs that -- but nobody is structurally
    excluded.
    """
    pop = build_population(stats, seed=7, n_customers=400, n_merchants=900)
    assert pop.agent_propensity.min() > 0.0
    # Still concentrated: the top fifth must carry a clearly outsized share.
    top = np.sort(pop.agent_propensity)[::-1][: len(pop.agent_propensity) // 5]
    assert top.sum() / pop.agent_propensity.sum() > 0.45


def test_agentic_authentication_has_a_failure_tail(stats: ReferenceStats) -> None:
    """Agentic 3DS must span the same outcomes as ecom, not a clean subset.

    Giving the agentic rail only frictionless/challenge_passed/not_applicable
    left three 3DS outcomes 100% non-agentic and turned ``threeds_result`` into a
    0.86-AUC rail detector.
    """
    agentic = stats.threeds_weights[Channel.AGENTIC.value]
    assert len(agentic) >= 5, f"agentic 3DS mix is too clean: {agentic}"
    assert agentic.get("challenge_failed", 0.0) > 0.0


def test_amount_is_rail_independent_given_mcc(frame: pd.DataFrame) -> None:
    """Within a category, agentic and classic amounts come from the same curve.

    This is the property that stops a fraud model from learning
    "unusual amount -> agentic -> fraud" once attacks land, since attacks skew
    agentic. Rail identity is unhideable; shared columns behaving identically is
    what keeps that from mattering.
    """
    from scipy.stats import ks_2samp

    worst = 0.0
    for _, grp in frame.groupby("mcc"):
        left = grp.loc[grp["channel"] == "agentic", "amount"].to_numpy()
        right = grp.loc[grp["channel"] != "agentic", "amount"].to_numpy()
        if len(left) < 100 or len(right) < 100:
            continue
        worst = max(worst, float(ks_2samp(left, right).statistic))
    assert worst < 0.15, f"amount distribution differs by rail within an MCC: KS {worst:.3f}"
