"""Internal transaction model shared by the generator and the file writers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class Txn:
    """An internal, format-agnostic transaction before file rendering."""

    txn_date: date
    account_id: str
    amount_paise: int          # absolute magnitude (>= 0)
    direction: str             # "in" | "out"
    category: str
    merchant: str | None
    method: str
    txn_type: str
    is_transfer: bool = False
    ts: datetime | None = None
    description: str | None = None   # explicit override of the dialect pattern
    ref: str = ""
    seq: int = 0                     # insertion order; stable tie-break for sorting
    is_duplicate_row: bool = False   # in-file duplicated print (balance-neutral)
