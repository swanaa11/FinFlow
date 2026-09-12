"""CLI entry point for the synthetic data generator.

Usage:
    python -m finflow.datagen.run --out data/sample --seed 42 --months 12
    python -m finflow.datagen.run --scenario incoming   # latest month -> data/incoming/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from finflow.config import get_settings
from finflow.utils.logging import configure_logging, get_logger

logger = get_logger("datagen")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finflow-datagen", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/sample"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--scenario", choices=["history", "incoming"], default="history")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    from finflow.datagen.generator import SyntheticDataGenerator

    out_dir = settings.incoming_dir if args.scenario == "incoming" else args.out
    result = SyntheticDataGenerator(seed=args.seed).generate(out_dir=out_dir, months=args.months, scenario=args.scenario)
    logger.info("datagen complete: %s files, %s rows -> %s", result["file_count"], result["row_count"], result["out_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
