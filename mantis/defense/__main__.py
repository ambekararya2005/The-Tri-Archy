"""Run the Day 4 firewall experiment and write RESULTS.md.

    python -m mantis.defense                 # uses the cached 5-seed pool
    python -m mantis.defense --rebuild-pool  # regenerates it (about a minute)

Produces, in order: the pooled evaluation dataset, L1/L2/fused headline numbers
at a fixed 0.1% FPR, per-rail and per-family breakdowns, the leave-one-family-out
table, and the ablation of the one feature that turned out to be too good.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

from mantis.core.paths import GENERATED_DIR, REPO_ROOT, ensure_dir
from mantis.defense.experiment import ExperimentResult, run_experiment
from mantis.defense.metrics import OPERATING_FPR
from mantis.defense.pool import POOL_SEEDS, build_pool
from mantis.defense.report import write_results

POOL_PARQUET: Path = GENERATED_DIR / "pool_5seed.parquet"


def load_pool(rebuild: bool) -> pd.DataFrame:
    """Load the pooled dataset, generating it when absent or when asked."""
    if rebuild or not POOL_PARQUET.exists():
        print(f"building the pooled dataset over {len(POOL_SEEDS)} seeds...")
        pool = build_pool()
        ensure_dir(POOL_PARQUET.parent)
        pool.to_parquet(POOL_PARQUET, index=False)
        print(f"  wrote {POOL_PARQUET}")
        return pool
    print(f"loading cached pool from {POOL_PARQUET}")
    return pd.read_parquet(POOL_PARQUET)


def print_summary(result: ExperimentResult) -> None:
    """The block a judge reads off the terminal."""
    print()
    print("=" * 84)
    print("MANDATE FIREWALL - Day 4 results")
    print("=" * 84)
    print(f"  train {result.n_train:,}  test {result.n_test:,}  "
          f"features {result.n_features}  test prevalence {result.prevalence:.4%}")
    print(f"  OPERATING POINT: every recall below is at {OPERATING_FPR:.1%} FPR "
          "on legitimate traffic.")
    print()
    print(result.l1_full.line("L1 GBDT (all families)"))
    print(result.l2.line("L2 novelty (legit only)"))
    print(result.fused.line("L1 + L2 fused"))
    print()

    if result.l1_rail:
        print("  per rail (L1) - because fraud is 5.7x concentrated on the agentic rail")
        for rail, report in result.l1_rail.items():
            print(report.line(f"    {rail}"))
        print()

    print("-" * 84)
    print("LEAVE ONE FAMILY OUT - the headline experiment")
    print("-" * 84)
    print()
    frame = result.per_family
    print(f"  {'family':<8} {'n_pos':>7} {'L1 trained':>11} {'L1 HELD':>9} "
          f"{'L2 unsup':>9} {'fused':>8} {'fused HELD':>11}")
    print(f"  {'-' * 8} {'-' * 7} {'-' * 11} {'-' * 9} {'-' * 9} {'-' * 8} {'-' * 11}")
    for row in frame.itertuples():
        print(
            f"  {row.family:<8} {row.n_pos:>7,} {row.l1_with:>11.3f} {row.l1_heldout:>9.3f} "
            f"{row.l2:>9.3f} {row.fused_with:>8.3f} {row.fused_heldout:>11.3f}"
        )
    if len(frame):
        drop = (frame["l1_with"] - frame["l1_heldout"]).mean()
        print()
        print(f"  mean recall lost when the family is held out of training: {drop:+.3f}")
    print()

    if len(result.per_attack):
        print("-" * 84)
        print("per attack card, at the same operating point")
        print("-" * 84)
        print()
        print(f"  {'card':<8} {'n_pos':>7} {'L1':>8} {'L2':>8} {'fused':>8}")
        print(f"  {'-' * 8} {'-' * 7} {'-' * 8} {'-' * 8} {'-' * 8}")
        for row in result.per_attack.itertuples():
            print(f"  {row.attack_id:<8} {row.n_pos:>7,} {row.l1:>8.3f} "
                  f"{row.l2:>8.3f} {row.fused:>8.3f}")
        print()

    print("-" * 84)
    print("top L1 features by gain")
    print("-" * 84)
    print()
    for row in result.importance.head(12).itertuples():
        print(f"  {row.feature:<38} {row.share:>7.2%}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mantis.defense")
    parser.add_argument("--rebuild-pool", action="store_true", help="regenerate the 5-seed pool")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--results", type=Path, default=REPO_ROOT / "RESULTS.md", help="where to write RESULTS.md"
    )
    args = parser.parse_args(argv)

    t0 = time.perf_counter()
    pool = load_pool(args.rebuild_pool)
    print(f"  {len(pool):,} events, {int(pool['is_fraud'].sum()):,} fraud "
          f"({pool['is_fraud'].mean():.4%})")
    print()

    result = run_experiment(pool, seed=args.seed)
    print_summary(result)

    write_results(result, pool, args.results)
    print(f"wrote {args.results}")
    print(f"total {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
