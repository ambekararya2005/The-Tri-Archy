"""The foundry CLI — background plus attacks, labelled, measured, written.

    python -m mantis.foundry --attacks all --out data/generated/dataset_v1.parquet

What it does, in order:

1. Generates the calibrated legitimate population from the committed priors.
   The background is generated, not loaded, so a run depends on nothing but
   ``--n``, ``--seed`` and the repo — no stale parquet on disk can silently
   change the numbers a judge sees.
2. Runs each requested injector against that untouched background, each on its
   own card-derived RNG stream, so ``--attacks F4-27`` yields byte-identical
   rows to the same card inside ``--attacks all``.
3. Rebuilds every attack event through ``TxEvent`` so the frozen schema's
   validators — 4-digit MCC, ISO codes, rail consistency, label integrity —
   *prove* the output is well-formed rather than us asserting it.
4. Prints class balance, per-attack counts and the best-single-feature AUC
   table, then writes the parquet and a manifest recording everything.

No network, no credential, no download. HARD RULE 4.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

from mantis.atlas.loader import ATLAS
from mantis.core.paths import GENERATED_DIR, ensure_dir
from mantis.foundry.base.reference import load_reference_stats
from mantis.foundry.base.simulator import (
    DEFAULT_SEED,
    DEFAULT_WINDOW_DAYS,
    SimulationConfig,
    simulate_frame,
)
from mantis.foundry.injectors import REGISTRY, get_injector
from mantis.foundry.injectors.base import PopulationView, events_from_frame, run_injector
from mantis.foundry.injectors.probe import GATE_AUC, format_probe_table, probe_report

#: Default output. ``dataset_v1`` is the frame the defense layer trains on.
DEFAULT_OUT: Path = GENERATED_DIR / "dataset_v1.parquet"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m mantis.foundry",
        description="Generate the labelled attack dataset: background + injected campaigns.",
    )
    parser.add_argument(
        "--attacks",
        default="all",
        help="'all', or a comma-separated list of atlas card ids (e.g. F4-27,F6-38)",
    )
    parser.add_argument("--n", type=int, default=200_000, help="background events (default 200000)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="master seed")
    parser.add_argument("--customers", type=int, default=5_000, help="cardholder count")
    parser.add_argument("--merchants", type=int, default=12_000, help="approx merchant count")
    parser.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS, help="observation window"
    )
    parser.add_argument(
        "--intensity", type=float, default=1.0, help="attack volume multiplier (default 1.0)"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output parquet path")
    parser.add_argument(
        "--probe-negatives",
        type=int,
        default=60_000,
        help="background rows used in the AUC probe; AUC is rank-based so this "
        "changes runtime, not the answer",
    )
    parser.add_argument("--no-probe", action="store_true", help="skip the separability probe")
    return parser.parse_args(argv)


def _selected_cards(spec: str) -> list[str]:
    """Resolve the ``--attacks`` argument to a list of registered card ids."""
    if spec.strip().lower() == "all":
        return sorted(REGISTRY)
    wanted = [part.strip().upper() for part in spec.split(",") if part.strip()]
    for card_id in wanted:
        get_injector(card_id)  # raises with a useful message when unknown
    return wanted


def _attack_summary(attacks: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per-attack counts: the diversity claim, in numbers."""
    rows = []
    for card_id, frame in attacks.items():
        card = ATLAS[card_id]
        rows.append(
            {
                "attack_id": card_id,
                "family": card.family.value,
                "name": card.name,
                "events": len(frame),
                "campaigns": int(frame["attack_campaign"].nunique()),
                "customers": int(frame["customer_id"].nunique()),
                "merchants": int(frame["merchant_id"].nunique()),
                "median_amount": float(frame["amount"].median()),
                "agentic_share": float((frame["channel"] == "agentic").mean()),
            }
        )
    return pd.DataFrame(rows)


def _format_attack_table(summary: pd.DataFrame, n_background: int) -> str:
    """Render the per-attack block the gate prints."""
    total = int(summary["events"].sum())
    lines = [
        "per-attack counts",
        "",
        f"  {'card':<7} {'fam':<4} {'events':>7} {'camp':>5} {'cust':>6} {'merch':>6} "
        f"{'median amt':>11} {'agentic':>8}  name",
        f"  {'-' * 7} {'-' * 4} {'-' * 7} {'-' * 5} {'-' * 6} {'-' * 6} {'-' * 11} "
        f"{'-' * 8}  {'-' * 34}",
    ]
    for row in summary.itertuples():
        lines.append(
            f"  {row.attack_id:<7} {row.family:<4} {row.events:>7,} {row.campaigns:>5} "
            f"{row.customers:>6,} {row.merchants:>6,} {row.median_amount:>11,.0f} "
            f"{row.agentic_share:>7.1%}  {row.name[:34]}"
        )
    lines.append(
        f"  {'-' * 7} {'-' * 4} {'-' * 7} {'-' * 5} {'-' * 6} {'-' * 6} {'-' * 11} {'-' * 8}"
    )
    lines.append(f"  {'total':<7} {'':<4} {total:>7,}")
    lines.append("")
    lines.append("class balance")
    lines.append(f"  legitimate : {n_background:>9,}")
    lines.append(f"  fraud      : {total:>9,}")
    lines.append(
        f"  prevalence : {total / (n_background + total):>9.4%}  "
        "(card-fraud basis points, not a toy 50/50 split)"
    )
    lines.append("")
    lines.append("  Report AUC-PR and recall@0.1%FPR against this balance. Never accuracy:")
    lines.append("  a model that predicts 'legitimate' for everything scores 99.4%.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Build the labelled dataset. Run as ``python -m mantis.foundry``."""
    args = _parse_args(argv)
    card_ids = _selected_cards(args.attacks)

    cfg = SimulationConfig(
        n_events=args.n,
        seed=args.seed,
        n_customers=args.customers,
        n_merchants=args.merchants,
        window_days=args.window_days,
    )
    stats = load_reference_stats()

    t0 = time.perf_counter()
    background = simulate_frame(cfg, stats)
    t1 = time.perf_counter()
    view = PopulationView.build(background)
    t2 = time.perf_counter()

    print(
        f"background: {len(background):,} events, {view.customers.shape[0]:,} customers, "
        f"{view.merchants.shape[0]:,} merchants, seed {cfg.seed}"
    )
    print(
        f"            window {background['ts'].min():%Y-%m-%d} -> {background['ts'].max():%Y-%m-%d}"
    )
    print()

    attacks: dict[str, pd.DataFrame] = {}
    for card_id in card_ids:
        attacks[card_id] = run_injector(
            get_injector(card_id), view, intensity=args.intensity, seed=cfg.seed
        )
    t3 = time.perf_counter()

    fraud = pd.concat(list(attacks.values()), ignore_index=True)
    # Prove, do not assert: every injected event goes back through the frozen
    # schema's validators. A malformed row fails here, not in the defense layer.
    n_validated = sum(1 for _ in events_from_frame(fraud))
    t4 = time.perf_counter()

    dataset = pd.concat([background, fraud], ignore_index=True)
    dataset = dataset.sort_values("ts", kind="stable").reset_index(drop=True)

    summary = _attack_summary(attacks)
    print(_format_attack_table(summary, len(background)))
    print()

    report = None
    if not args.no_probe:
        report = probe_report(background, attacks, max_negatives=args.probe_negatives)
        print(format_probe_table(report))
        failed = report[~report["passes"]]["attack_id"].tolist()
        if failed:
            print()
            print(f"  WARNING: {failed} exceed the {GATE_AUC:.2f} gate and are too easy.")
        print()
    t5 = time.perf_counter()

    ensure_dir(args.out.parent)
    dataset.to_parquet(args.out, index=False)

    manifest = {
        "config": {
            "n_background": cfg.n_events,
            "seed": cfg.seed,
            "n_customers": cfg.n_customers,
            "n_merchants": cfg.n_merchants,
            "window_days": cfg.window_days,
            "intensity": args.intensity,
            "attacks": card_ids,
        },
        "class_balance": {
            "legitimate": len(background),
            "fraud": len(fraud),
            "prevalence": float(len(fraud) / len(dataset)),
        },
        "per_attack": summary.to_dict("records"),
        "separability_probe": (
            None if report is None else report.drop(columns=["runners_up"]).to_dict("records")
        ),
        "schema_validated_events": n_validated,
        "timings_seconds": {
            "simulate_background": round(t1 - t0, 3),
            "index_population": round(t2 - t1, 3),
            "inject": round(t3 - t2, 3),
            "schema_validate": round(t4 - t3, 3),
            "probe": round(t5 - t4, 3),
        },
    }
    manifest_path = args.out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, default=float), encoding="utf-8")

    size_mb = args.out.stat().st_size / 1024 / 1024
    print(
        f"wrote {len(dataset):,} rows x {dataset.shape[1]} cols -> {args.out}  ({size_mb:.1f} MB)"
    )
    print(f"      manifest -> {manifest_path}")
    print(f"      {n_validated:,} attack events re-validated against the frozen TxEvent schema")
    print(
        f"      timings  -> background {t1 - t0:.1f}s, inject {t3 - t2:.1f}s, "
        f"validate {t4 - t3:.1f}s, probe {t5 - t4:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
