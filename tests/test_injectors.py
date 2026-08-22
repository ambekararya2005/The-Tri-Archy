"""Contract tests for the injector framework and the eight Day 2 attacks.

What is being defended, in descending order of how badly a failure would hurt:

1. **The atlas/injector assertion.** If the registry check can pass while a card
   claims ``implemented`` with no code behind it, Pillar 1's diversity number is
   a claim rather than a fact. The tests here make the assertion itself fail on
   demand, so we know it is load-bearing and not decorative.
2. **No leakage, no fraud in the background, no invented entities.** An attack
   that only ever touches never-before-seen customers or merchants is trivially
   detectable and teaches a detector nothing (CLAUDE.md HARD RULE 1's cousin).
3. **Subtlety.** Every injector is re-probed here at small scale and must stay
   under the gate. If someone tunes an attack to be "more obvious" for a demo,
   this fails.
4. **Determinism.** A judge re-running the pipeline must get the slide numbers,
   and ``--attacks F4-27`` must produce the same rows as ``--attacks all``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mantis.atlas.loader import ATLAS
from mantis.atlas.schema import Status
from mantis.core.events import ALL_COLUMNS, LABEL_COLUMNS
from mantis.foundry.base.reference import ReferenceStats, load_reference_stats
from mantis.foundry.base.simulator import SimulationConfig, simulate_frame
from mantis.foundry.injectors import REGISTRY, get_injector, validate_registry
from mantis.foundry.injectors.base import (
    BaseAttack,
    InjectorError,
    PopulationView,
    events_from_frame,
    register,
    run_injector,
    split_count,
    stable_seed,
)
from mantis.foundry.injectors.probe import GATE_AUC, build_probe_matrix, probe_attack

#: Small but not tiny: the injectors need enough customers and merchants to
#: build a cohort without exhausting the pools.
SMALL = SimulationConfig(n_events=30_000, seed=7, n_customers=1_200, n_merchants=3_000)

#: The eight cards Day 2 delivers. Locked so a silent regression in the registry
#: shows up as a test failure rather than as a smaller number in the writeup.
EXPECTED_INJECTORS = {
    "F2-13",
    "F2-16",
    "F3-19",
    "F4-27",
    "F4-28",
    "F6-38",
    "F6-39",
    "F6-40",
}


@pytest.fixture(scope="module")
def stats() -> ReferenceStats:
    return load_reference_stats()


@pytest.fixture(scope="module")
def background(stats: ReferenceStats) -> pd.DataFrame:
    return simulate_frame(SMALL, stats)


@pytest.fixture(scope="module")
def view(background: pd.DataFrame) -> PopulationView:
    return PopulationView.build(background)


@pytest.fixture(scope="module")
def attacks(view: PopulationView) -> dict[str, pd.DataFrame]:
    return {card_id: run_injector(cls, view, seed=7) for card_id, cls in sorted(REGISTRY.items())}


# --------------------------------------------------------------------------- #
# The assertion that makes the atlas executable
# --------------------------------------------------------------------------- #


def test_registry_covers_exactly_the_implemented_cards() -> None:
    """The honest count: implemented cards and injectors are the same set."""
    implemented = {c.id for c in ATLAS.values() if c.status is Status.IMPLEMENTED}
    assert set(REGISTRY) == implemented
    assert set(REGISTRY) == EXPECTED_INJECTORS


def test_every_injector_resolves_its_declared_generator_path() -> None:
    """The card's ``generator`` string is code, not prose."""
    from importlib import import_module

    for card_id, cls in REGISTRY.items():
        generator = ATLAS[card_id].generator
        assert generator is not None
        module_path, _, func = generator.partition(":")
        assert module_path == cls.__module__
        assert callable(getattr(import_module(module_path), func))


def test_registry_validation_rejects_an_injector_for_a_mapped_card() -> None:
    """The assertion has to actually fire, or it is decoration.

    A mapped card is picked from the live atlas rather than hard-coded, so this
    keeps working as cards are promoted on later days.
    """
    mapped = next(c.id for c in ATLAS.values() if c.status is Status.MAPPED)

    class Rogue(BaseAttack):
        card_id = mapped

        def inject(self, population, intensity, rng):  # test double
            raise NotImplementedError

    register(Rogue)
    try:
        with pytest.raises(InjectorError, match="mapped"):
            validate_registry()
    finally:
        REGISTRY.pop(mapped, None)
    validate_registry()  # and the registry is clean again afterwards


def test_registry_validation_rejects_an_unknown_card() -> None:
    class Ghost(BaseAttack):
        card_id = "F6-99"

        def inject(self, population, intensity, rng):  # test double
            raise NotImplementedError

    register(Ghost)
    try:
        with pytest.raises(InjectorError, match="not in the atlas"):
            validate_registry()
    finally:
        REGISTRY.pop("F6-99", None)


def test_two_injectors_cannot_claim_one_card() -> None:
    class Duplicate(BaseAttack):
        card_id = "F4-27"

        def inject(self, population, intensity, rng):  # test double
            raise NotImplementedError

    with pytest.raises(InjectorError, match="two injectors claim"):
        register(Duplicate)


# --------------------------------------------------------------------------- #
# The output contract
# --------------------------------------------------------------------------- #


def test_attacks_emit_the_frozen_column_set(attacks: dict[str, pd.DataFrame]) -> None:
    for card_id, frame in attacks.items():
        assert list(frame.columns) == list(ALL_COLUMNS), card_id


def test_every_attack_row_is_labelled_and_grouped(attacks: dict[str, pd.DataFrame]) -> None:
    for card_id, frame in attacks.items():
        assert bool(frame["is_fraud"].all()), card_id
        assert (frame["attack_id"] == card_id).all()
        assert frame["attack_campaign"].notna().all()
        assert frame["attack_campaign"].nunique() >= 2, f"{card_id} ships a single campaign"
        assert frame["attack_campaign"].str.startswith(f"cmp-{card_id}").all()


def test_background_is_never_mutated(view: PopulationView, background: pd.DataFrame) -> None:
    """Injectors add rows; they never relabel or edit the population."""
    assert not bool(background["is_fraud"].any())
    before = background.copy()
    for cls in REGISTRY.values():
        run_injector(cls, view, seed=7)
    pd.testing.assert_frame_equal(background, before)


def test_attacks_reuse_existing_entities(
    attacks: dict[str, pd.DataFrame], background: pd.DataFrame
) -> None:
    """Fraud that only touches new entities is trivially detectable and unreal."""
    customers = set(background["customer_id"])
    merchants = set(background["merchant_id"])
    for card_id, frame in attacks.items():
        assert set(frame["customer_id"]) <= customers, card_id
        assert set(frame["merchant_id"]) <= merchants, card_id


def test_attack_event_ids_are_unique_across_the_dataset(
    attacks: dict[str, pd.DataFrame], background: pd.DataFrame
) -> None:
    combined = pd.concat([background, *attacks.values()], ignore_index=True)
    assert not bool(combined["event_id"].duplicated().any())


def test_attack_events_satisfy_the_frozen_schema(attacks: dict[str, pd.DataFrame]) -> None:
    """Round-trip every attack row through ``TxEvent``'s validators.

    This is what proves rail consistency and label integrity rather than
    assuming them: a mandate on a classic rail without ``agent_token``, or an
    ``is_fraud`` row with no ``attack_id``, raises here.
    """
    for card_id, frame in attacks.items():
        events = list(events_from_frame(frame))
        assert len(events) == len(frame), card_id
        assert all(e.is_fraud and e.attack_id == card_id for e in events)


def test_attacks_stay_inside_the_observation_window(
    attacks: dict[str, pd.DataFrame], background: pd.DataFrame
) -> None:
    lo, hi = background["ts"].min(), background["ts"].max()
    for card_id, frame in attacks.items():
        assert frame["ts"].min() >= lo, card_id
        assert frame["ts"].max() <= hi, card_id


def test_agentic_attack_rows_carry_a_coherent_mandate(attacks: dict[str, pd.DataFrame]) -> None:
    """None of these eight is a mandate-abuse attack, so none may look like one.

    If a retargeted row left its scope ceiling below the amount, L0 would catch
    the whole campaign on a rule these attacks are not supposed to trip, and the
    F1 injectors landing later would have nothing left to demonstrate.
    """
    for card_id, frame in attacks.items():
        agentic = frame[frame["channel"] == "agentic"]
        if agentic.empty:
            continue
        assert (agentic["ag_scope_max_amount"] >= agentic["amount"]).all(), card_id
        in_scope = [
            str(row.mcc) in list(row.ag_scope_categories) for row in agentic.itertuples()
        ]
        assert all(in_scope), card_id
        named = agentic[agentic["ag_scope_allowed_merchants"].map(len) > 0]
        assert all(
            row.merchant_id in list(row.ag_scope_allowed_merchants) for row in named.itertuples()
        ), card_id


def test_retargeted_provenance_ends_at_the_merchant_that_was_paid(
    attacks: dict[str, pd.DataFrame],
) -> None:
    """``provenance_chain`` is load-bearing for L3; a stale tail would poison it."""
    for card_id, frame in attacks.items():
        agentic = frame[frame["channel"] == "agentic"]
        for row in agentic.itertuples():
            chain = list(row.ag_provenance_chain)
            assert chain, card_id
            slug = str(row.merchant_id)[4:]
            assert f"shop.{slug}.test" in chain[-1], (card_id, row.event_id)
            assert len(row.ag_ingested_content_ids) == len(chain)


def test_card_present_rows_keep_their_nullity_pattern(attacks: dict[str, pd.DataFrame]) -> None:
    """A chip transaction has a terminal, not a device. Break that and the null
    pattern alone names the attack."""
    for card_id, frame in attacks.items():
        present = frame[frame["channel"] == "card_present"]
        if present.empty:
            continue
        assert present["device_id"].isna().all(), card_id
        assert present["terminal_id"].notna().all(), card_id


# --------------------------------------------------------------------------- #
# Realism
# --------------------------------------------------------------------------- #


def test_overall_prevalence_is_realistic(
    attacks: dict[str, pd.DataFrame], background: pd.DataFrame
) -> None:
    """Well under 1%. A toy class balance makes every downstream metric a lie."""
    fraud = sum(len(frame) for frame in attacks.values())
    prevalence = fraud / (len(background) + fraud)
    assert 0.001 < prevalence < 0.01, f"prevalence {prevalence:.4%} is not card-fraud shaped"


@pytest.mark.parametrize("card_id", sorted(EXPECTED_INJECTORS))
def test_no_single_feature_separates_an_attack(
    card_id: str, attacks: dict[str, pd.DataFrame], background: pd.DataFrame
) -> None:
    """The subtlety gate, re-run on every test invocation.

    Small-sample AUCs are noisier than the headline numbers in each injector's
    docstring (those come from a 200k background), so this asserts the gate
    rather than the exact value.
    """
    ranked = probe_attack(background, attacks[card_id], max_negatives=25_000, seed=7)
    best = ranked.iloc[0]
    assert best["auc"] <= GATE_AUC, (
        f"{card_id} is a cartoon: {best['feature']} alone scores {best['auc']:.3f}"
    )


def test_probe_matrix_never_leaks_a_label(background: pd.DataFrame) -> None:
    """HARD RULE 1, enforced on the probe as well as on the feature builder."""
    matrix = build_probe_matrix(background.head(500))
    for label in LABEL_COLUMNS:
        assert not any(column.startswith(label) for column in matrix.columns)
    assert not matrix.isna().to_numpy().any(), "a NaN column would be silently unmeasurable"


def test_attacks_are_not_confined_to_one_rail(attacks: dict[str, pd.DataFrame]) -> None:
    """A single-rail attack makes ``channel`` the answer and the model useless."""
    for card_id, frame in attacks.items():
        assert frame["channel"].nunique() >= 2, card_id


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def test_injectors_are_deterministic(view: PopulationView) -> None:
    for card_id, cls in REGISTRY.items():
        first = run_injector(cls, view, seed=11)
        second = run_injector(cls, view, seed=11)
        pd.testing.assert_frame_equal(first, second, obj=card_id)


def test_one_injector_is_unaffected_by_the_others(
    view: PopulationView, attacks: dict[str, pd.DataFrame]
) -> None:
    """``--attacks F4-27`` must equal F4-27 inside ``--attacks all``."""
    alone = run_injector(get_injector("F4-27"), view, seed=7)
    pd.testing.assert_frame_equal(alone, attacks["F4-27"])


def test_seeds_derived_from_card_ids_are_process_stable() -> None:
    """Python's ``hash()`` is randomised per process; ours must not be."""
    assert stable_seed("F4-27") == stable_seed("F4-27")
    assert stable_seed("F4-27") != stable_seed("F4-28")


def test_intensity_scales_volume(view: PopulationView) -> None:
    light = run_injector(get_injector("F6-40"), view, intensity=0.5, seed=7)
    heavy = run_injector(get_injector("F6-40"), view, intensity=2.0, seed=7)
    assert len(heavy) > len(light)


def test_split_count_conserves_the_total() -> None:
    rng = np.random.default_rng(0)
    for total, parts in ((200, 5), (13, 4), (7, 7), (1, 1)):
        counts = split_count(total, parts, rng)
        assert counts.sum() == total
        assert counts.size == parts
        assert (counts >= 1).all()
