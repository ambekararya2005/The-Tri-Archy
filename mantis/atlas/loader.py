"""Atlas loader — validates every card at import time and fails loudly.

Importing this module reads ``mantis/atlas/cards/*.yaml`` and validates all of
them. A malformed card is a hard, immediate ``AtlasError`` with the filename in
the message. This is deliberate: the atlas is a dependency of the foundry, and a
silently-skipped card would quietly shrink the diversity score without anyone
noticing until the demo.

Run ``python -m mantis.atlas.loader`` for the family summary.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Final

import yaml
from pydantic import ValidationError

from mantis.atlas.schema import FAMILY_NAMES, AttackCard, Family, Layer, Status

__all__ = [
    "ATLAS",
    "CARDS_DIR",
    "AtlasError",
    "by_family",
    "get",
    "implemented",
    "load_cards",
    "signals_by_layer",
    "summary",
]

#: Target size of the finished atlas. Reported against actual, honestly.
TARGET_CARD_COUNT: Final[int] = 42

CARDS_DIR: Final[Path] = Path(__file__).parent / "cards"


class AtlasError(RuntimeError):
    """Raised when a card is missing, malformed, duplicated, or misnamed."""


def load_cards(directory: Path | None = None) -> dict[str, AttackCard]:
    """Load and validate every ``*.yaml`` card in ``directory``.

    Args:
        directory: Card directory. Defaults to the packaged ``cards/``.

    Returns:
        Cards keyed by id, insertion-ordered by id.

    Raises:
        AtlasError: on a missing directory, unparseable YAML, a schema violation,
            a filename that disagrees with the card id, or a duplicate id.
    """
    directory = CARDS_DIR if directory is None else directory
    if not directory.is_dir():
        raise AtlasError(f"atlas card directory not found: {directory}")

    cards: dict[str, AttackCard] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise AtlasError(f"{path.name}: not valid YAML: {exc}") from exc

        if not isinstance(raw, dict):
            raise AtlasError(f"{path.name}: expected a YAML mapping, got {type(raw).__name__}")

        try:
            card = AttackCard.model_validate(raw)
        except ValidationError as exc:
            raise AtlasError(f"{path.name}: card failed validation:\n{exc}") from exc

        if path.stem != card.id:
            raise AtlasError(f"{path.name}: filename stem must equal card id {card.id!r}")
        if card.id in cards:
            raise AtlasError(f"{path.name}: duplicate card id {card.id!r}")

        cards[card.id] = card

    if not cards:
        raise AtlasError(f"no atlas cards found in {directory}")

    return dict(sorted(cards.items()))


#: The validated atlas. Import this; do not re-read the YAML yourself.
ATLAS: Final[dict[str, AttackCard]] = load_cards()


def get(card_id: str) -> AttackCard:
    """Return one card by id, with a useful error when it is missing."""
    try:
        return ATLAS[card_id]
    except KeyError:
        raise AtlasError(f"unknown atlas card {card_id!r}; known ids: {sorted(ATLAS)}") from None


def by_family(cards: dict[str, AttackCard] | None = None) -> dict[Family, list[AttackCard]]:
    """Group cards by family, families in enum order."""
    source = ATLAS if cards is None else cards
    grouped: dict[Family, list[AttackCard]] = {f: [] for f in Family}
    for card in source.values():
        grouped[card.family].append(card)
    return grouped


def implemented(cards: dict[str, AttackCard] | None = None) -> list[AttackCard]:
    """Cards the foundry can actually generate. This is the honest diversity count."""
    source = ATLAS if cards is None else cards
    return [c for c in source.values() if c.status is Status.IMPLEMENTED]


def signals_by_layer(cards: dict[str, AttackCard] | None = None) -> dict[Layer, set[str]]:
    """Distinct feature names each firewall layer owes us. The feature backlog."""
    source = ATLAS if cards is None else cards
    out: dict[Layer, set[str]] = defaultdict(set)
    for card in source.values():
        for sig in card.observable_signals:
            out[sig.layer].add(sig.feature)
    return dict(out)


def summary(cards: dict[str, AttackCard] | None = None) -> str:
    """Render the family summary table printed by ``python -m mantis.atlas.loader``."""
    source = ATLAS if cards is None else cards
    grouped = by_family(source)
    n_impl = len(implemented(source))

    lines = ["MANTIS attack atlas", ""]
    lines.append(f"  {'family':<6} {'cards':>5} {'impl':>5}  name")
    lines.append(f"  {'-' * 6} {'-' * 5} {'-' * 5}  {'-' * 40}")
    for family in Family:
        group = grouped[family]
        impl = sum(1 for c in group if c.status is Status.IMPLEMENTED)
        lines.append(f"  {family.value:<6} {len(group):>5} {impl:>5}  {FAMILY_NAMES[family]}")
    lines.append(f"  {'-' * 6} {'-' * 5} {'-' * 5}  {'-' * 40}")
    lines.append(f"  {'total':<6} {len(source):>5} {n_impl:>5}  target {TARGET_CARD_COUNT} cards")

    layers = signals_by_layer(source)
    lines.append("")
    lines.append("  feature backlog by layer (distinct features named by cards):")
    for layer in Layer:
        feats = sorted(layers.get(layer, set()))
        lines.append(f"    {layer.value}: {len(feats):>2}  {', '.join(feats) if feats else '-'}")

    lines.append("")
    lines.append("  cards:")
    for card in source.values():
        flag = "*" if card.status is Status.IMPLEMENTED else " "
        lines.append(f"   {flag} {card.id}  {card.name}")
    lines.append("")
    lines.append("  (* = injector implemented; others are mapped taxonomy only)")
    lines.append("")
    lines.append("  HONEST COUNT")
    lines.append(f"    {len(source)} vectors mapped; {n_impl} of them have a working injector.")
    lines.append(
        f"    The remaining {len(source) - n_impl} are taxonomy: each carries observable signals"
    )
    lines.append("    and mitigations, but the foundry does not generate them. Never blur the")
    lines.append("    two in a slide -- overclaiming coverage loses a technical room.")
    return "\n".join(lines)


def main() -> None:
    """Print the atlas family summary. Run: ``python -m mantis.atlas.loader``."""
    print(summary())


if __name__ == "__main__":
    main()
