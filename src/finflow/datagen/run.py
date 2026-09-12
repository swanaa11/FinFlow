"""CLI entry point for the synthetic data generator.

Usage:
    python -m finflow.datagen.run --out data/sample --seed 42 --months 12
    python -m finflow.datagen.run --scenario incoming   # latest month -> data/incoming/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from finflow.config import get_settings
from finflow.utils.logging import configure_logging, get_logger

logger = get_logger("datagen")


def run_datagen(out_dir: Path, seed: int = 42, months: int = 12, scenario: str = "history") -> dict[str, Any]:
    """Programmatic entry point used by both the module CLI and `finflow datagen`."""
    from finflow.datagen.generator import SyntheticDataGenerator

    result = SyntheticDataGenerator(seed=seed).generate(out_dir=Path(out_dir), months=months, scenario=scenario)
    logger.info(
        "datagen complete: %s files, %s rows, %s accounts -> %s",
        result["file_count"],
        result["row_count"],
        result["account_count"],
        result["out_dir"],
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finflow-datagen", description="Synthetic financial data generator")
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--scenario", choices=["history", "incoming"], default="history")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    out_dir = settings.incoming_dir if args.scenario == "incoming" else args.out
    result = run_datagen(out_dir=out_dir, seed=args.seed, months=args.months, scenario=args.scenario)
    print(
        f"Generated {result['file_count']} files / {result['row_count']} rows "
        f"for {result['account_count']} accounts -> {result['out_dir']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
