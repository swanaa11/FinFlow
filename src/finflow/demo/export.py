"""Static demo-site export for Vercel (or any static host).

Reads the committed SYNTHETIC sample corpus (data/sample/), computes
presentation-level aggregates, and renders a fully self-contained
`site/index.html` (all data inlined — no CDN, no network calls).

Safety: refuses to run unless the manifest carries `synthetic: true`
(ADR-0007 — nothing public may ever be built from real statements).

This is a *preview* exporter: it uses lightweight readers until the real
ingestion adapters (M3) and warehouse marts (M8) exist, at which point it
switches to reading Gold marts instead of raw files.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber
import yaml

from finflow.config import get_settings
from finflow.datagen.catalog import Catalog
from finflow.utils.logging import get_logger

logger = get_logger("demo-export")

_UNSET = object()


def export_demo_site(site_dir: Path, sample_dir: Path | None = None) -> Path:
    """Render `site/index.html` from the synthetic sample corpus."""
    settings = get_settings()
    sample = sample_dir or settings.sample_dir
    manifest_path = sample / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest at {manifest_path} — run `make demo-data` first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("synthetic") is not True:
        raise RuntimeError(
            "REFUSING to export: dataset manifest is not marked synthetic=true. "
            "The public demo site can only be built from the synthetic corpus (ADR-0007)."
        )

    txns = _load_corpus(sample, manifest)
    data = _aggregate(txns, manifest)
    rendered = _render(data)

    site_dir = Path(site_dir)
    site_dir.mkdir(parents=True, exist_ok=True)
    out = site_dir / "index.html"
    out.write_text(rendered, encoding="utf-8")
    logger.info("demo site written: %s (%s txns)", out, len(txns))
    return out


# ---------------------------------------------------------------------------
# Lightweight readers (preview-only; replaced by M3 adapters + M8 marts)
# ---------------------------------------------------------------------------
def _money(value: Any) -> float:
    """Indian-comma money string -> float rupees (NaN-safe)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    return float(str(value).replace(",", "").strip() or 0)


def _text(value: Any) -> str:
    """NaN-safe string coercion (a blank statement cell must stay blank, not 'nan')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def _load_corpus(sample: Path, manifest: dict[str, Any]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for entry in manifest["files"]:
        path = sample / entry["path"]
        account = entry["account"]
        if path.suffix == ".csv" and account == "hdfc_savings":
            frames.append(_read_hdfc(path, account))
        elif path.suffix == ".csv" and account == "icici_savings":
            frames.append(_read_icici(path, account))
        elif path.suffix == ".xlsx":
            frames.append(_read_paytm(path, account))
        elif path.suffix == ".pdf":
            frames.append(_read_axis(path, account))
    txns = pd.concat(frames, ignore_index=True)

    # Preview dedup: identical (date, description, signed amount) reprints are
    # the generator's in-file duplicate prints. Formal dedup arrives in M6.
    before = len(txns)
    txns = txns.drop_duplicates(subset=["account", "date", "description", "amount"], keep="first")
    logger.info("preview dedup: %s duplicate reprints dropped", before - len(txns))
    return txns.sort_values("date").reset_index(drop=True)


def _read_hdfc(path: Path, account: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        wd, dp = _money(r.get("Withdrawal") or 0), _money(r.get("Deposit") or 0)
        if wd == 0 and dp == 0:
            continue
        amount = dp - wd
        rows.append(
            {
                "date": pd.to_datetime(r["Date"], format="%d/%m/%Y").date(),
                "description": str(r["Narration"] or ""),
                "amount": amount,
            }
        )
    return _frame(rows, account)


def _read_icici(path: Path, account: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        debit, credit = _money(r.get("Debit") or 0), _money(r.get("Credit") or 0)
        if debit == 0 and credit == 0:
            continue
        rows.append(
            {
                "date": pd.to_datetime(r["Txn Date"], format="%d-%m-%Y").date(),
                "description": str(r["Description"] or ""),
                "amount": credit - debit,
            }
        )
    return _frame(rows, account)


def _read_paytm(path: Path, account: str) -> pd.DataFrame:
    df = pd.read_excel(path)
    rows = []
    for _, r in df.iterrows():
        amount = round(float(r.get("Amount") or 0) * 100) / 100
        if amount == 0:
            continue
        rows.append(
            {
                "date": pd.to_datetime(r["Timestamp"]).date(),
                "description": str(r["Description"] or ""),
                "amount": amount,
            }
        )
    return _frame(rows, account)


def _read_axis(path: Path, account: str) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    if not row or not row[0] or str(row[0]).strip().lower() == "date":
                        continue
                    raw_amount = str(row[3] or "").strip()
                    if not raw_amount:
                        continue
                    value = _money(raw_amount)
                    rows.append(
                        {
                            "date": pd.to_datetime(row[0], format="%d/%m/%Y").date(),
                            "description": str(row[1] or ""),
                            "amount": value if raw_amount.startswith("-") else -value,
                        }
                    )
    return _frame(rows, account)


def _frame(rows: list[dict[str, Any]], account: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["account"] = account
    return df


# ---------------------------------------------------------------------------
# Categorization (preview of the M9 rule engine, driven by categories.yaml)
# ---------------------------------------------------------------------------
_TRANSFER_KEYWORDS = ("SELF TRANSFER", "ADDED TO PAYTM", "CREDIT CARD BILL", "CARD PAYMENT")


def _attach_categories(txns: pd.DataFrame) -> pd.DataFrame:
    catalog = Catalog.load()
    rules: list[tuple[str, str, list[str]]] = []  # (category, merchant, keywords)
    for cat in catalog.categories:
        for m in cat.merchants:
            rules.append((cat.name, m.name, [k.upper() for k in m.keywords]))

    categories, merchants = [], []
    for description in txns["description"].str.upper():
        hit_cat, hit_merchant = "Uncategorized", None
        for cat_name, merchant, keywords in rules:
            if any(k in description for k in keywords):
                hit_cat, hit_merchant = cat_name, merchant
                break
        categories.append(hit_cat)
        merchants.append(hit_merchant)

    txns = txns.copy()
    txns["category"], txns["merchant"] = categories, merchants
    txns["is_transfer"] = txns["category"].eq("Transfers") | txns["description"].str.upper().apply(
        lambda d: any(k in d for k in _TRANSFER_KEYWORDS)
    )
    txns["is_income"] = txns["category"].eq("Income") & txns["amount"].gt(0)
    return txns


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _aggregate(txns: pd.DataFrame, manifest: dict[str, Any]) -> dict[str, Any]:
    txns = _attach_categories(txns)
    txns["month"] = txns["date"].apply(lambda d: f"{d:%Y-%m}")
    expenses = txns[(~txns["is_transfer"]) & (~txns["is_income"]) & txns["amount"].lt(0)]
    income = txns[txns["amount"].gt(0) & (~txns["is_transfer"])]

    total_income = round(float(income["amount"].sum()), 2)
    total_expenses = round(-float(expenses["amount"].sum()), 2)

    monthly = (
        pd.DataFrame(
            {
                "month": sorted(txns["month"].unique()),
            }
        )
        .merge(
            income.groupby("month")["amount"].sum().rename("income"),
            on="month",
            how="left",
        )
        .merge(
            (-expenses.groupby("month")["amount"].sum()).rename("expense"),
            on="month",
            how="left",
        )
        .fillna(0.0)
    )
    monthly_rows = [
        {"month": str(r.month), "income": round(float(r.income), 2), "expense": round(float(r.expense), 2)}
        for r in monthly.itertuples(index=True)
    ]

    by_cat = (
        expenses.assign(spend=-expenses["amount"])
        .groupby("category")["spend"]
        .sum()
        .sort_values(ascending=False)
    )
    categories = [
        {"name": name, "total": round(float(total), 2), "share": round(100 * float(total) / total_expenses, 1) if total_expenses else 0}
        for name, total in by_cat.items()
    ]

    accounts = []
    for account, group in txns.groupby("account"):
        accounts.append(
            {
                "id": str(account),
                "in": round(float(group.loc[group["amount"].gt(0), "amount"].sum()), 2),
                "out": round(-float(group.loc[group["amount"].lt(0), "amount"].sum()), 2),
                "count": int(len(group)),
            }
        )

    merchants = (
        expenses[expenses["merchant"].notna()]
        .assign(spend=-expenses["amount"])
        .groupby("merchant")["spend"]
        .sum()
        .sort_values(ascending=False)
        .head(8)
    )
    top_merchants = [
        {"name": str(name), "total": round(float(total), 2), "share": round(100 * float(total) / total_expenses, 1) if total_expenses else 0}
        for name, total in merchants.items()
    ]

    largest = [
        {
            "date": str(r.date),
            "label": str(r.merchant or r.description)[:40],
            "account": str(r.account),
            "amount": round(-float(r.amount), 2),
        }
        for r in expenses.nsmallest(8, "amount").itertuples(index=False)
    ]

    budgets_month, budget_rows = _budget_rows(txns, expenses, manifest)

    return {
        "meta": {
            "synthetic": True,
            "generated_at": date.today().isoformat(),
            "period": manifest["period"],
            "generator_seed": manifest["seed"],
            "note": "All figures are synthetically generated for demonstration.",
        },
        "kpis": {
            "income": total_income,
            "expenses": total_expenses,
            "net": round(total_income - total_expenses, 2),
            "savings_rate": round(100 * (total_income - total_expenses) / total_income, 1) if total_income else 0,
            "transactions": int(len(txns)),
        },
        "monthly": monthly_rows,
        "categories": categories,
        "accounts": accounts,
        "top_merchants": top_merchants,
        "largest": largest,
        "budgets": {"month": budgets_month, "rows": budget_rows},
    }


def _budget_rows(txns: pd.DataFrame, expenses: pd.DataFrame, manifest: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    budgets_path = get_settings().config_dir / "budgets.yaml"
    budgets: dict[str, float] = yaml.safe_load(budgets_path.read_text(encoding="utf-8"))["budgets"]

    # Anchor to the latest COMPLETE month of the corpus period — future-dated
    # dirt rows (quarantine candidates) must not define the budget month.
    latest = str(manifest["period"]["end"])[:7]
    if not (txns["month"] == latest).any():
        latest = str(txns["month"].max())
    month_spend = (
        expenses[expenses["month"] == latest]
        .assign(spend=-expenses["amount"])
        .groupby("category")["spend"]
        .sum()
    )
    rows = []
    for category, budget in budgets.items():
        spend = round(float(month_spend.get(category, 0.0)), 2)
        rows.append(
            {
                "category": category,
                "budget": float(budget),
                "spend": spend,
                "pct": round(100 * spend / budget, 1) if budget else 0,
            }
        )
    rows.sort(key=lambda r: -r["pct"])
    return latest, rows


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _render(data: dict[str, Any]) -> str:
    template_path = Path(__file__).parent / "template.html"
    template = template_path.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__FINFLOW_DATA__", payload)
