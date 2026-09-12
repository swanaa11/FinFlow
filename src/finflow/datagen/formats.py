"""Statement file writers — one per institution format.

Each writer renders a month of internal `Txn` objects exactly the way that
institution's real export looks, so the ingestion adapters (Milestone 3+) can
be developed against realistic files. The column layouts are defined in
`config/sources.yaml` and mirrored here.

Money leaves the integer-paise domain only at this rendering boundary.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypeAlias

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from finflow.datagen.models import Txn
from finflow.utils.money import format_inr

Describer: TypeAlias = Callable[[Txn], str]

_ROWS_PER_PDF_PAGE = 38


def _fmt(paise: int) -> str:
    """Render paise as an Indian-grouped money string without the ₹ symbol."""
    return format_inr(abs(paise), with_decimals=True).lstrip("₹")


def _fmt_signed(paise: int) -> str:
    """Like _fmt but preserves the sign (credits negative)."""
    return format_inr(paise, with_decimals=True).lstrip("₹")


# --------------------------------------------------------------------------
# HDFC Bank — CSV: Date | Narration | Withdrawal | Deposit | Balance
# --------------------------------------------------------------------------
def write_hdfc_csv(
    path: Path, rows: list[Txn], opening_balance_paise: int, describe: Describer
) -> tuple[int, int]:
    balance = opening_balance_paise
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Date", "Narration", "Withdrawal", "Deposit", "Balance"])
        for t in rows:
            if not t.is_duplicate_row:  # a duplicated print does not move the balance again
                balance += t.amount_paise if t.direction == "in" else -t.amount_paise
            withdrawal = _fmt(t.amount_paise) if t.direction == "out" else ""
            deposit = _fmt(t.amount_paise) if t.direction == "in" else ""
            writer.writerow([t.txn_date.strftime("%d/%m/%Y"), describe(t), withdrawal, deposit, _fmt(balance)])
        return len(rows), balance


# --------------------------------------------------------------------------
# ICICI Bank — CSV: Txn Date | Description | Debit | Credit | Amount
# --------------------------------------------------------------------------
def write_icici_csv(path: Path, rows: list[Txn], describe: Describer) -> tuple[int, None]:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Txn Date", "Description", "Debit", "Credit", "Amount"])
        for t in rows:
            debit = _fmt(t.amount_paise) if t.direction == "out" else ""
            credit = _fmt(t.amount_paise) if t.direction == "in" else ""
            net = -t.amount_paise if t.direction == "out" else t.amount_paise
            writer.writerow([t.txn_date.strftime("%d-%m-%Y"), describe(t), debit, credit, _fmt_signed(net)])
    return len(rows), None


# --------------------------------------------------------------------------
# Paytm wallet — XLSX: Timestamp | Description | Amount | Type | Balance
# Amount is signed: negative = paid, positive = received.
# --------------------------------------------------------------------------
def write_paytm_xlsx(
    path: Path, rows: list[Txn], opening_balance_paise: int, describe: Describer
) -> tuple[int, int]:
    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(["Timestamp", "Description", "Amount", "Type", "Balance"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    balance = opening_balance_paise
    for t in rows:
        signed = t.amount_paise if t.direction == "in" else -t.amount_paise
        kind = "Received" if t.direction == "in" else "Paid"
        stamp = (t.ts or datetime.combine(t.txn_date, datetime.min.time())).strftime("%Y-%m-%d %H:%M:%S")
        ws.append([stamp, describe(t), round(signed / 100, 2), kind, round(balance / 100, 2)])
        if not t.is_duplicate_row:
            balance += signed
    wb.save(path)
    return len(rows), balance


# --------------------------------------------------------------------------
# Axis credit card — PDF: Date | Description | Ref | Amount (INR)
# Spends positive, payments negative.
# --------------------------------------------------------------------------
def write_axis_pdf(path: Path, rows: list[Txn], label: str, describe: Describer) -> tuple[int, None]:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Axis Bank Credit Card Statement — {label}",
    )

    story: list = [
        Paragraph("<b>Axis Bank — Credit Card Statement</b>", styles["Title"]),
        Paragraph(f"Statement period: {label}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]

    def render_page(page_rows: list[Txn]) -> Table:
        data = [["Date", "Description", "Ref", "Amount (INR)"]]
        for t in page_rows:
            amount = _fmt(t.amount_paise)
            if t.direction == "in":
                amount = f"-{amount}"
            data.append([t.txn_date.strftime("%d/%m/%Y"), describe(t), t.ref, amount])
        table = Table(
            data,
            colWidths=[22 * mm, 88 * mm, 24 * mm, 26 * mm],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d3df")),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ]
            )
        )
        return table

    for i in range(0, len(rows), _ROWS_PER_PDF_PAGE):
        if i:
            story.append(Spacer(1, 6 * mm))
        story.append(render_page(rows[i : i + _ROWS_PER_PDF_PAGE]))
        if i + _ROWS_PER_PDF_PAGE < len(rows):
            from reportlab.platypus import PageBreak

            story.append(PageBreak())
    doc.build(story)
    return len(rows), None
