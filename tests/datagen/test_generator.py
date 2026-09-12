"""Tests for the synthetic data generator: determinism, structure, dirt, planted signals."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pdfplumber

from finflow.datagen.generator import SyntheticDataGenerator
from finflow.datagen.run import run_datagen

EXPECTED_COLUMNS = {
    "hdfc_savings": ["Date", "Narration", "Withdrawal", "Deposit", "Balance"],
    "icici_savings": ["Txn Date", "Description", "Debit", "Credit", "Amount"],
}


def _generate(tmp_path: Path, seed: int = 42, months: int = 3) -> Path:
    out = tmp_path / f"ds-{seed}-{months}"
    run_datagen(out_dir=out, seed=seed, months=months)
    return out


def test_generation_is_deterministic(tmp_path: Path) -> None:
    out1 = _generate(tmp_path, seed=7, months=2)
    out2 = _generate(tmp_path, seed=7, months=2)

    m1 = json.loads((out1 / "manifest.json").read_text())
    m2 = json.loads((out2 / "manifest.json").read_text())
    m1.pop("generated_at"), m2.pop("generated_at")
    assert m1 == m2, "same seed must produce an identical corpus"

    # byte-identical data files
    for f in m1["files"]:
        assert (Path(out1) / f["path"]).read_bytes() == (Path(out2) / f["path"]).read_bytes()


def test_different_seed_produces_different_corpus(tmp_path: Path) -> None:
    out1 = _generate(tmp_path, seed=1, months=2)
    out2 = _generate(tmp_path, seed=2, months=2)
    m1 = json.loads((out1 / "manifest.json").read_text())
    m2 = json.loads((out2 / "manifest.json").read_text())
    assert m1["files"] != m2["files"]


def test_dataset_structure_and_row_counts(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=3)
    manifest = json.loads((out / "manifest.json").read_text())

    assert manifest["synthetic"] is True
    assert manifest["row_count"] == sum(f["rows"] for f in manifest["files"])
    assert set(manifest["rows_per_account"]) == {
        "hdfc_savings", "icici_savings", "paytm_wallet", "axis_credit_card",
    }

    # every account has a file for each of the 3 months (+ possible future-dirt month)
    per_account: dict[str, int] = {}
    for f in manifest["files"]:
        assert (out / f["path"]).exists(), f"manifest references missing file {f['path']}"
        per_account[f["account"]] = per_account.get(f["account"], 0) + 1
    for account, count in per_account.items():
        assert 3 <= count <= 4, f"{account}: expected 3-4 monthly files, got {count}"


def test_csv_formats_have_expected_columns_and_parse(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=2)

    hdfc_file = sorted((out / "hdfc_savings").glob("*.csv"))[0]  # chronological: the first full month
    df = pd.read_csv(hdfc_file)
    assert list(df.columns) == EXPECTED_COLUMNS["hdfc_savings"]
    assert len(df) > 20  # ~15 rows/month across 2 months (streams + dirt)
    # withdrawals xor deposits are populated (two-column convention)
    both = df["Withdrawal"].notna() & df["Deposit"].notna()
    assert not both.any()
    # income lands in the Deposit column
    assert df.loc[df["Narration"].str.contains("SALARY", na=False), "Deposit"].notna().all()

    icici_file = next((out / "icici_savings").glob("*.csv"))
    df = pd.read_csv(icici_file)
    assert list(df.columns) == EXPECTED_COLUMNS["icici_savings"]


def test_xlsx_wallet_format_parses(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=2)
    xlsx = next((out / "paytm_wallet").glob("*.xlsx"))
    df = pd.read_excel(xlsx)
    assert list(df.columns) == ["Timestamp", "Description", "Amount", "Type", "Balance"]
    assert set(df["Type"].unique()) <= {"Paid", "Received"}
    # wallet reloads must have been inserted at least once
    assert df["Description"].str.contains("Added to Paytm", na=False).any()


def test_pdf_statement_parses_with_expected_header(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=2)
    pdf = next((out / "axis_credit_card").glob("*.pdf"))
    with pdfplumber.open(pdf) as document:
        text = document.pages[0].extract_text()
    assert "Axis Bank" in text
    assert "Description" in text and "Amount (INR)" in text


def test_dirt_is_present_in_corpus(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=3)
    manifest = json.loads((out / "manifest.json").read_text())

    hdfc = pd.concat([pd.read_csv(out / f["path"]) for f in manifest["files"] if f["account"] == "hdfc_savings"])
    # blank descriptions
    assert hdfc["Narration"].isna().sum() >= 1
    # zero-amount rows
    zero = hdfc["Withdrawal"].fillna("0").str.replace(",", "").astype(float)
    assert (zero == 0).sum() >= 1
    # unknown merchants
    assert hdfc["Narration"].str.contains("UNKNOWN-MCH", na=False).any()
    # in-file duplicated prints: exact (Date, Narration, Withdrawal) repeats exist
    dup_pairs = hdfc.duplicated(subset=["Date", "Narration", "Withdrawal"], keep=False)
    assert dup_pairs.sum() >= 2


def test_future_dated_rows_exist(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=3)
    manifest = json.loads((out / "manifest.json").read_text())
    period_end = date.fromisoformat(manifest["period"]["end"])

    hdfc = pd.concat([pd.read_csv(out / f["path"]) for f in manifest["files"] if f["account"] == "hdfc_savings"])
    dates = pd.to_datetime(hdfc["Date"], format="%d/%m/%Y").dt.date
    assert (dates > period_end).any(), "future-dated dirt rows must exist beyond the period end"


def test_planted_anomalies_are_present(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=3)
    manifest = json.loads((out / "manifest.json").read_text())

    axis_text = ""
    for f in manifest["files"]:
        if f["account"] == "axis_credit_card":
            with pdfplumber.open(out / f["path"]) as document:
                axis_text += "\n".join(page.extract_text() or "" for page in document.pages)
    # planted: Croma 42,500 and BookMyShow 2,400 on the card
    assert "42,500.00" in axis_text
    assert "CROMA" in axis_text

    hdfc = pd.concat([pd.read_csv(out / f["path"]) for f in manifest["files"] if f["account"] == "hdfc_savings"])
    assert (hdfc["Narration"].str.contains("BARBEQUE NATION", na=False)).any()


def test_card_bill_payment_rows_exist_every_month(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=3)
    manifest = json.loads((out / "manifest.json").read_text())
    hdfc = pd.concat([pd.read_csv(out / f["path"]) for f in manifest["files"] if f["account"] == "hdfc_savings"])
    bills = hdfc[hdfc["Narration"].str.contains("AXIS CREDIT CARD BILL", na=False)]
    assert len(bills) >= 3, "one card-bill payment per generated month expected"


def test_hdfc_running_balance_is_consistent(tmp_path: Path) -> None:
    out = _generate(tmp_path, seed=42, months=2)
    manifest = json.loads((out / "manifest.json").read_text())
    files = sorted((f for f in manifest["files"] if f["account"] == "hdfc_savings"), key=lambda f: f["month"])

    balance = 150000.0  # opening balance from config/datagen.yaml
    for f in files:
        df = pd.read_csv(out / f["path"]).fillna({"Withdrawal": 0, "Deposit": 0})
        for _, row in df.iterrows():
            wd = float(str(row["Withdrawal"]).replace(",", "") or 0)
            dp = float(str(row["Deposit"]).replace(",", "") or 0)
            printed = float(str(row["Balance"]).replace(",", ""))
            balance += dp - wd
            # printed balance moves with every real row (dup prints keep it unchanged,
            # which shows up as a repeat of the previous printed value)
            assert abs(printed - balance) < 0.01 or abs(printed - (balance - dp + wd)) < 0.01
            if abs(printed - balance) >= 0.01:
                balance = printed  # duplicate print: real balance unchanged


def test_period_covers_complete_months_only() -> None:
    gen = SyntheticDataGenerator(seed=42)
    start, month_firsts, end = gen._period(3)  # noqa: SLF001 - unit test of internal helper
    assert len(month_firsts) == 3
    assert start == month_firsts[0]
    assert all(m.day == 1 for m in month_firsts)
    assert end.day >= 28
    assert end < date.today(), "period must not include the incomplete current month"


def test_run_datagen_returns_summary(tmp_path: Path) -> None:
    result = run_datagen(out_dir=tmp_path / "x", seed=42, months=1)
    assert set(result) == {"file_count", "row_count", "account_count", "out_dir"}
    assert result["account_count"] == 4
    assert result["row_count"] > 0
