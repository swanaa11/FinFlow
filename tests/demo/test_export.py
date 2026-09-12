"""Tests for the static demo-site exporter (Vercel deployment artifact)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finflow.datagen.run import run_datagen
from finflow.demo.export import export_demo_site


def test_export_refuses_non_synthetic_data(tmp_path: Path) -> None:
    """The exporter must hard-fail unless the manifest marks the data synthetic."""
    sample = tmp_path / "sample"
    sample.mkdir()
    manifest = {"synthetic": False, "files": [], "period": {"start": "2026-01-01", "end": "2026-01-31"}}
    (sample / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="synthetic"):
        export_demo_site(tmp_path / "site", sample_dir=sample)


def test_export_produces_selfcontained_site(tmp_path: Path) -> None:
    sample = tmp_path / "sample"
    run_datagen(out_dir=sample, seed=42, months=2)

    site = export_demo_site(tmp_path / "site", sample_dir=sample)
    html = site.read_text(encoding="utf-8")

    assert html.startswith("<!DOCTYPE html>")
    assert "SYNTHETIC DEMO DATA" in html
    assert "window.FINFLOW_DATA" not in html  # data is inlined as `const D`, not fetched
    assert "__FINFLOW_DATA__" not in html  # placeholder fully replaced
    # no external resources: fully self-contained (CSP- and offline-friendly)
    assert "http://" not in html and "https://" not in html.replace("https://github.com", "")
    assert "<script src=" not in html and "<link" not in html

    data = json.loads(html.split("const D = ", 1)[1].split(";\n", 1)[0].replace("<\\/", "</"))
    assert data["meta"]["synthetic"] is True
    assert data["kpis"]["transactions"] > 50
    assert data["kpis"]["expenses"] > 0
    assert len(data["monthly"]) >= 2
    assert data["budgets"]["month"] == data["meta"]["period"]["end"][:7]


def test_export_planted_outlier_is_visible(tmp_path: Path) -> None:
    sample = tmp_path / "sample"
    run_datagen(out_dir=sample, seed=42, months=3)
    site = export_demo_site(tmp_path / "site", sample_dir=sample)

    data = json.loads(site.read_text(encoding="utf-8").split("const D = ", 1)[1].split(";\n", 1)[0])
    labels = [t["label"] for t in data["largest"]]
    assert any("Croma" in label for label in labels), "planted Croma outlier must appear in largest txns"
