"""FinFlow command-line interface.

The pipeline is CLI-first (ADR-0004): every capability is invocable directly,
which keeps Airflow DAGs thin and makes every step testable without an
orchestrator.
"""

from __future__ import annotations

from pathlib import Path

import typer

from finflow import __version__
from finflow.config import get_settings
from finflow.utils.logging import configure_logging, get_logger

app = typer.Typer(
    name="finflow",
    help="FinFlow — personal finance intelligence platform (local-first data pipeline).",
    no_args_is_help=True,
    add_completion=False,
)
logger = get_logger("cli")


@app.command()
def version() -> None:
    """Print the FinFlow version."""
    typer.echo(f"finflow {__version__}")


@app.command()
def info() -> None:
    """Show resolved configuration (paths and safety switches; never secrets)."""
    settings = get_settings()
    typer.echo(f"finflow {__version__}")
    typer.echo(f"env:            {settings.env}")
    typer.echo(f"root:           {settings.root}")
    typer.echo(f"data dir:       {settings.data_path}")
    typer.echo(f"database:       {settings.active_db_file}")
    typer.echo(f"incoming dir:   {settings.incoming_dir}")
    typer.echo(f"demo mode:      {settings.demo_mode}")
    typer.echo(f"notify enabled: {settings.notify_enabled}")
    typer.echo(f"telegram:       {'configured' if settings.telegram_configured else 'not configured'}")


@app.command()
def datagen(
    out: Path = typer.Option(
        Path("data/sample"), "--out", help="Output directory for the synthetic dataset."
    ),
    seed: int = typer.Option(42, "--seed", help="Deterministic RNG seed."),
    months: int = typer.Option(12, "--months", min=1, max=60, help="Months of history to generate."),
    scenario: str = typer.Option(
        "history", "--scenario", help="'history' writes to OUT; 'incoming' copies the "
        "latest month into data/incoming/ to demo pipeline ingestion."
    ),
) -> None:
    """Generate the synthetic financial dataset (no real data, ever)."""
    from finflow.datagen.run import run_datagen

    settings = get_settings()
    configure_logging(settings.log_level)
    target = settings.incoming_dir if scenario == "incoming" else out
    if scenario != "incoming" and scenario != "history":
        raise typer.BadParameter("scenario must be 'history' or 'incoming'")
    result = run_datagen(out_dir=target, seed=seed, months=months, scenario=scenario)
    typer.echo(
        f"Generated {result['file_count']} files / {result['row_count']} rows "
        f"for {result['account_count']} accounts -> {result['out_dir']}"
    )
    logger.info("datagen complete: %s", result)


@app.command("export-demo")
def export_demo(
    site_dir: Path = typer.Option(
        Path("site"), "--site-dir", help="Output directory for the static demo site."
    ),
) -> None:
    """Export the public demo site from the SYNTHETIC sample dataset (Vercel-ready)."""
    from finflow.demo.export import export_demo_site

    settings = get_settings()
    configure_logging(settings.log_level)
    out = export_demo_site(site_dir)
    typer.echo(f"Demo site written: {out} (synthetic data only — safe to publish)")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
