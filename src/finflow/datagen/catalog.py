"""Typed configuration models + loaders for the synthetic data generator.

All YAML configuration lives in `config/` and is validated with pydantic at
load time so a malformed config fails fast with a clear message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from finflow.config.settings import get_settings


# --------------------------------------------------------------------------
# sources.yaml
# --------------------------------------------------------------------------
class FormatSpec(BaseModel):
    file_type: Literal["csv", "xlsx", "pdf"]
    columns: dict[str, str]
    date_format: str = "%d/%m/%Y"
    sign_convention: str


class AccountSpec(BaseModel):
    account_id: str
    institution: str
    display_name: str
    account_type: Literal["savings", "wallet", "credit_card", "current"]
    currency: str = "INR"
    format: FormatSpec


class SourcesConfig(BaseModel):
    version: int
    accounts: list[AccountSpec]

    def account(self, account_id: str) -> AccountSpec:
        for acc in self.accounts:
            if acc.account_id == account_id:
                return acc
        raise KeyError(f"Unknown account_id: {account_id!r}")

    @classmethod
    def load(cls, path: Path | None = None) -> "SourcesConfig":
        p = path or (get_settings().config_dir / "sources.yaml")
        return cls.model_validate(_read_yaml(p))


# --------------------------------------------------------------------------
# categories.yaml
# --------------------------------------------------------------------------
class MerchantSpec(BaseModel):
    name: str
    keywords: list[str]
    gen_min: float = 0.0  # rupees
    gen_max: float = 0.0  # rupees
    weight: float = 1.0
    methods: list[str] = Field(default_factory=lambda: ["upi", "card"])


class CategorySpec(BaseModel):
    name: str
    merchants: list[MerchantSpec] = Field(default_factory=list)


class Catalog(BaseModel):
    version: int
    categories: list[CategorySpec]

    def merchant(self, name: str) -> MerchantSpec:
        for cat in self.categories:
            for m in cat.merchants:
                if m.name == name:
                    return m
        raise KeyError(f"Unknown merchant: {name!r}")

    def category_of(self, merchant_name: str) -> str:
        for cat in self.categories:
            for m in cat.merchants:
                if m.name == merchant_name:
                    return cat.name
        raise KeyError(f"Unknown merchant (no category): {merchant_name!r}")

    @classmethod
    def load(cls, path: Path | None = None) -> "Catalog":
        p = path or (get_settings().config_dir / "categories.yaml")
        return cls.model_validate(_read_yaml(p))


# --------------------------------------------------------------------------
# datagen.yaml
# --------------------------------------------------------------------------
class StreamSpec(BaseModel):
    stream: str
    account: str
    category: str
    merchants: list[str] = Field(default_factory=list)
    kind: Literal["probabilistic", "fixed"] = "probabilistic"
    prob_per_day: float = 0.0
    per_month: float = 0.0
    day_of_month: int | None = None
    jitter_days: int = 0
    fixed_amount: float | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    method: str = "upi"
    txn_type: str = "purchase"
    is_transfer: bool = False


class WalletReload(BaseModel):
    wallet_account: str
    funding_account: str
    trigger_below: float
    reload_amount: float


class CardPayment(BaseModel):
    card_account: str
    payer_account: str
    day_of_month: int


class InterestCredit(BaseModel):
    account: str
    months: list[int]
    min_amount: float
    max_amount: float


class DirtConfig(BaseModel):
    duplicate_row_rate: float = 0.015
    blank_description_rate: float = 0.004
    unknown_merchant_rate: float = 0.03
    zero_amount_rows: int = 2
    future_date_rows: int = 2
    future_date_offset_days: int = 3


class PlantedAnomaly(BaseModel):
    account: str
    category: str
    merchant: str
    amount: float
    days_back: int
    method: str = "card"


class NearDuplicateConfig(BaseModel):
    count: int = 3
    min_amount: float = 300.0


class GenProfile(BaseModel):
    version: int
    accounts: dict[str, dict[str, float | str]]
    streams: list[StreamSpec]
    wallet_reload: WalletReload
    card_payment: CardPayment
    interest_credit: InterestCredit
    dirt: DirtConfig = Field(default_factory=DirtConfig)
    planted_anomalies: list[PlantedAnomaly] = Field(default_factory=list)
    near_duplicates: NearDuplicateConfig = Field(default_factory=NearDuplicateConfig)

    def account_meta(self, account_id: str) -> dict[str, float | str]:
        return self.accounts[account_id]

    @classmethod
    def load(cls, path: Path | None = None) -> "GenProfile":
        p = path or (get_settings().config_dir / "datagen.yaml")
        return cls.model_validate(_read_yaml(p))


# --------------------------------------------------------------------------
def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a YAML mapping")
    return data
