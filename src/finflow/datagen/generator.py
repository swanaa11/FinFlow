"""Synthetic transaction generator.

Builds a deterministic "digital twin" of a person's finances from
`config/datagen.yaml`: salaries, rent, subscriptions, probabilistic daily
spend, wallet reloads, credit-card bills, interest credits — then injects
controlled dirt (duplicates, blanks, unknown merchants, zero amounts, future
dates) and planted outliers so the pipeline can demonstrate validation,
dedup, quarantine and anomaly detection without any real data.

All randomness flows from a single seeded RNG: the same seed + same config +
same period produces byte-identical output files.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from finflow.datagen.catalog import Catalog, GenProfile, SourcesConfig
from finflow.datagen.formats import (
    write_axis_pdf,
    write_hdfc_csv,
    write_icici_csv,
    write_paytm_xlsx,
)
from finflow.datagen.models import Txn
from finflow.utils.hashing import sha256_file
from finflow.utils.money import to_paise

_PHONE = "9876543210"
_TS_HOUR_RANGE = (8, 22)


class SyntheticDataGenerator:
    """Deterministic generator for the full multi-account synthetic corpus."""

    def __init__(
        self,
        seed: int = 42,
        sources: SourcesConfig | None = None,
        catalog: Catalog | None = None,
        profile: GenProfile | None = None,
    ) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.sources = sources or SourcesConfig.load()
        self.catalog = catalog or Catalog.load()
        self.profile = profile or GenProfile.load()
        self._seq = 0
        self._validate_config()

    # ------------------------------------------------------------------ public
    def generate(self, out_dir: Path, months: int = 12, scenario: str = "history") -> dict[str, Any]:
        """Generate the corpus and write per-month statement files.

        scenario="history" writes every month into `out_dir`;
        scenario="incoming" writes only the most recent complete month
        (simulating statements that just arrived).
        """
        out_dir = Path(out_dir)
        period = self._period(months)
        txns = self._build_transactions(period)
        files = self._write_files(txns, period, out_dir, scenario)

        manifest = self._build_manifest(period, txns, files)
        (out_dir / "manifest.json").write_text(
            json_manifest(manifest), encoding="utf-8"
        )
        return {
            "file_count": len(files),
            "row_count": sum(f["rows"] for f in files),
            "account_count": len(self.sources.accounts),
            "out_dir": str(out_dir),
        }

    # ------------------------------------------------------------- period math
    @staticmethod
    def _shift_month(day: date, k: int) -> date:
        """First-of-month shifted by k months."""
        idx = day.year * 12 + (day.month - 1) + k
        return date(idx // 12, idx % 12 + 1, 1)

    def _period(self, months: int) -> tuple[date, list[date], date]:
        """Return (start, month_firsts, end) covering the last *months* COMPLETE months."""
        last_complete_first = self._shift_month(date.today(), -1)
        start = self._shift_month(last_complete_first, -(months - 1))
        month_firsts = [self._shift_month(start, i) for i in range(months)]
        end = self._shift_month(last_complete_first, 1) - timedelta(days=1)
        return start, month_firsts, end

    def _month_last(self, month_first: date) -> date:
        return self._shift_month(month_first, 1) - timedelta(days=1)

    # ------------------------------------------------------------- build phase
    def _build_transactions(self, period: tuple[date, list[date], date]) -> list[Txn]:
        start, month_firsts, end = period
        txns: list[Txn] = []

        # 1. recurring + probabilistic streams
        for stream in self.profile.streams:
            for month_first in month_firsts:
                txns.extend(self._stream_month_txns(stream, month_first))

        # 2. quarter-end interest, planted outliers, near-duplicate charges
        txns.extend(self._interest_txns(month_firsts))
        txns.extend(self._planted_txns(start, end))
        txns.extend(self._near_duplicate_txns(start, end))

        # 3. card bill needs the full previous-month card spend -> computed post hoc
        txns.extend(self._card_payment_txns(txns, month_firsts))

        # 4. wallet reloads keep the wallet balance above the trigger
        txns.extend(self._wallet_reload_txns(txns))

        # 5. controlled dirt (mutates some rows, appends impossible rows)
        txns = self._apply_dirt(txns, start, end)

        txns.sort(key=lambda t: (t.account_id, t.txn_date, t.seq))
        return txns

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _stream_month_txns(self, stream: Any, month_first: date) -> list[Txn]:
        last = self._month_last(month_first)
        txns: list[Txn] = []

        def on(day: date) -> Txn:
            return Txn(
                txn_date=day,
                account_id=stream.account,
                amount_paise=self._amount(stream),
                direction="in" if stream.txn_type == "income" else "out",
                category=stream.category,
                merchant=self.rng.choice(stream.merchants) if stream.merchants else None,
                method=stream.method,
                txn_type=stream.txn_type,
                is_transfer=stream.is_transfer,
                ts=self._ts(day) if stream.account == "paytm_wallet" else None,
                ref=self._ref(),
                seq=self._next_seq(),
            )

        if stream.kind == "fixed":
            day = min((stream.day_of_month or 1) + self.rng.randint(0, stream.jitter_days), last.day)
            txns.append(on(date(month_first.year, month_first.month, day)))
        elif stream.per_month > 0:
            count = int(stream.per_month) + (1 if self.rng.random() < stream.per_month % 1 else 0)
            for _ in range(count):
                txns.append(on(date(month_first.year, month_first.month, self.rng.randint(1, last.day))))
        else:
            expected = stream.prob_per_day
            for day in range(1, last.day + 1):
                n = int(expected)
                if self.rng.random() < expected - n:
                    n += 1
                for _ in range(n):
                    txns.append(on(date(month_first.year, month_first.month, day)))
        return txns

    def _amount(self, stream: Any) -> int:
        """Stream amount in paise: fixed streams use fixed_amount; others uniform."""
        if stream.fixed_amount is not None:
            return to_paise(stream.fixed_amount)
        rupees = round(self.rng.uniform(stream.min_amount or 0.0, stream.max_amount or 0.0))
        paise = rupees * 100
        if stream.method == "card" and self.rng.random() < 0.3:
            paise += 50
        return paise

    def _interest_txns(self, month_firsts: list[date]) -> list[Txn]:
        cfg = self.profile.interest_credit
        out: list[Txn] = []
        for month_first in month_firsts:
            if month_first.month not in cfg.months:
                continue
            day = self._month_last(month_first)
            out.append(
                Txn(
                    txn_date=day,
                    account_id=cfg.account,
                    amount_paise=round(self.rng.uniform(cfg.min_amount, cfg.max_amount)) * 100,
                    direction="in",
                    category="Income",
                    merchant="Savings Interest",
                    method="netbanking",
                    txn_type="interest",
                    ref=self._ref(),
                    seq=self._next_seq(),
                )
            )
        return out

    def _planted_txns(self, start: date, end: date) -> list[Txn]:
        out: list[Txn] = []
        for planted in self.profile.planted_anomalies:
            day = max(start + timedelta(days=1), end - timedelta(days=planted.days_back))
            out.append(
                Txn(
                    txn_date=day,
                    account_id=planted.account,
                    amount_paise=to_paise(planted.amount),
                    direction="out",
                    category=planted.category,
                    merchant=planted.merchant,
                    method=planted.method,
                    txn_type="purchase",
                    ts=self._ts(day) if planted.account == "paytm_wallet" else None,
                    ref=self._ref(),
                    seq=self._next_seq(),
                )
            )
        return out

    def _near_duplicate_txns(self, start: date, end: date) -> list[Txn]:
        """Same merchant/amount on consecutive days — the classic duplicate charge."""
        cfg = self.profile.near_duplicates
        candidates = [s for s in self.profile.streams if s.txn_type in ("purchase", "autopay") and s.merchants]
        out: list[Txn] = []
        for _ in range(cfg.count):
            stream = self.rng.choice(candidates)
            day = start + timedelta(days=self.rng.randint(1, max(1, (end - start).days - 1)))
            amount = self._amount(stream)
            for offset in (0, 1):
                d = day + timedelta(days=offset)
                out.append(
                    Txn(
                        txn_date=d,
                        account_id=stream.account,
                        amount_paise=amount,
                        direction="out",
                        category=stream.category,
                        merchant=self.rng.choice(stream.merchants),
                        method=stream.method,
                        txn_type=stream.txn_type,
                        ts=self._ts(d) if stream.account == "paytm_wallet" else None,
                        ref=self._ref(),
                        seq=self._next_seq(),
                    )
                )
        return out

    def _card_payment_txns(self, txns: list[Txn], month_firsts: list[date]) -> list[Txn]:
        """HDFC pays the previous calendar month's card spends on the configured day."""
        cfg = self.profile.card_payment
        out: list[Txn] = []
        for idx, month_first in enumerate(month_firsts):
            if idx == 0:
                rupees = round(self.rng.uniform(14000, 22000))
            else:
                prev_first = month_firsts[idx - 1]
                prev_last = self._month_last(prev_first)
                prev_spend = sum(
                    t.amount_paise
                    for t in txns
                    if t.account_id == cfg.card_account
                    and t.direction == "out"
                    and prev_first <= t.txn_date <= prev_last
                )
                rupees = max(1, round(prev_spend / 100))

            day = date(month_first.year, month_first.month, min(cfg.day_of_month, self._month_last(month_first).day))
            paise = rupees * 100
            out.append(
                Txn(
                    txn_date=day,
                    account_id=cfg.payer_account,
                    amount_paise=paise,
                    direction="out",
                    category="Transfers",
                    merchant="Credit Card Bill",
                    method="upi",
                    txn_type="transfer",
                    is_transfer=True,
                    ref=self._ref(),
                    seq=self._next_seq(),
                )
            )
            out.append(
                Txn(
                    txn_date=day,
                    account_id=cfg.card_account,
                    amount_paise=paise,
                    direction="in",
                    category="Transfers",
                    merchant="Credit Card Bill",
                    method="netbanking",
                    txn_type="transfer",
                    is_transfer=True,
                    ref=self._ref(),
                    seq=self._next_seq(),
                )
            )
        return out

    def _wallet_reload_txns(self, txns: list[Txn]) -> list[Txn]:
        """Insert 'Added to Paytm' reload pairs whenever the wallet would run low."""
        cfg = self.profile.wallet_reload
        opening = to_paise(float(self.profile.account_meta(cfg.wallet_account)["opening_balance"]))
        trigger = to_paise(cfg.trigger_below)
        balance = opening
        reloads: list[Txn] = []
        for t in sorted((t for t in txns if t.account_id == cfg.wallet_account), key=lambda t: (t.txn_date, t.seq)):
            delta = t.amount_paise if t.direction == "in" else -t.amount_paise
            if balance + delta < trigger and not t.is_duplicate_row:
                day = t.txn_date
                reloads.append(
                    Txn(
                        txn_date=day,
                        account_id=cfg.wallet_account,
                        amount_paise=to_paise(cfg.reload_amount),
                        direction="in",
                        category="Transfers",
                        merchant="Own Account Transfer",
                        method="upi",
                        txn_type="transfer",
                        is_transfer=True,
                        ts=self._ts(day),
                        description="Added to Paytm from HDFC Bank",
                        ref=self._ref(),
                        seq=self._next_seq(),
                    )
                )
                reloads.append(
                    Txn(
                        txn_date=day,
                        account_id=cfg.funding_account,
                        amount_paise=to_paise(cfg.reload_amount),
                        direction="out",
                        category="Transfers",
                        merchant="Own Account Transfer",
                        method="netbanking",
                        txn_type="transfer",
                        is_transfer=True,
                        ref=self._ref(),
                        seq=self._next_seq(),
                    )
                )
                balance += to_paise(cfg.reload_amount)
            balance += delta
        return reloads

    # -------------------------------------------------------------- dirt phase
    # CSV-format accounts always carry visible dirt so demos/tests stay reliable.
    _CSV_ACCOUNTS = ("hdfc_savings", "icici_savings")

    def _apply_dirt(self, txns: list[Txn], start: date, end: date) -> list[Txn]:
        cfg = self.profile.dirt
        out = list(txns)
        originals = [t for t in out if not t.is_duplicate_row]

        def with_csv_guarantee(pool: list[Txn], chosen: list[Txn]) -> list[Txn]:
            """Ensure at least one selected row per CSV-format account."""
            result = list(chosen)
            for aid in self._CSV_ACCOUNTS:
                if any(t.account_id == aid for t in result):
                    continue
                candidates = [t for t in pool if t.account_id == aid and t not in result]
                if candidates:
                    result.append(self.rng.choice(candidates))
            return result

        # 1. in-file duplicated prints (balance-neutral reprints)
        dup_count = max(1, int(len(out) * cfg.duplicate_row_rate))
        dups = with_csv_guarantee(originals, self.rng.sample(originals, min(dup_count, len(originals))))
        out.extend(replace(t, is_duplicate_row=True) for t in dups)

        # 2. blank descriptions (never on duplicate copies or transfer rows —
        #    transfers are structural and must keep their identity for matching)
        blank_pool = [t for t in out if not t.is_duplicate_row and not t.is_transfer]
        n_blanks = min(max(1, int(len(out) * cfg.blank_description_rate)), len(blank_pool))
        blank_targets = with_csv_guarantee(blank_pool, self.rng.sample(blank_pool, n_blanks))
        for t in blank_targets:
            t.description, t.merchant, t.category = "", None, "Uncategorized"

        # 3. unknown merchants (same exclusions as blanks)
        unknown_pool = [t for t in blank_pool if t not in blank_targets and not t.is_transfer]
        n_unknown = min(max(1, int(len(out) * cfg.unknown_merchant_rate)), len(unknown_pool))
        unknown_targets = with_csv_guarantee(unknown_pool, self.rng.sample(unknown_pool, n_unknown))
        for t in unknown_targets:
            t.description = f"UPI/{self._ref()}/UNKNOWN-MCH-{self.rng.randint(1000, 9999)}"
            t.merchant, t.category = None, "Uncategorized"

        # 4. zero-amount rows (impossible records, pinned accounts)
        for account in ("hdfc_savings", "paytm_wallet"):
            day = start + timedelta(days=self.rng.randint(1, max(1, (end - start).days)))
            out.append(self._dirt_txn(account, day, 0, f"UPI/{self._ref()}/MERCHANT"))

        # 5. future-dated rows (impossible records, pinned accounts)
        for account in ("hdfc_savings", "axis_credit_card"):
            day = end + timedelta(days=cfg.future_date_offset_days)
            out.append(self._dirt_txn(account, day, self.rng.randint(200, 1500) * 100, f"UPI/{self._ref()}/FUTURE-TXN"))
        return out

    def _dirt_txn(self, account: str, day: date, amount_paise: int, description: str) -> Txn:
        return Txn(
            txn_date=day,
            account_id=account,
            amount_paise=amount_paise,
            direction="out",
            category="Uncategorized",
            merchant=None,
            method="upi",
            txn_type="purchase",
            ts=self._ts(day) if account == "paytm_wallet" else None,
            description=description,
            ref=self._ref(),
            seq=self._next_seq(),
        )

    # ------------------------------------------------------------- write phase
    def _write_files(
        self, txns: list[Txn], period: tuple[date, list[date], date], out_dir: Path, scenario: str
    ) -> list[dict[str, Any]]:
        _start, month_firsts, _end = period

        by_account_month: dict[str, dict[date, list[Txn]]] = defaultdict(lambda: defaultdict(list))
        for t in txns:
            by_account_month[t.account_id][date(t.txn_date.year, t.txn_date.month, 1)].append(t)

        months_to_write = sorted({m for per_account in by_account_month.values() for m in per_account})
        if scenario == "incoming":
            months_to_write = [max(month_firsts)]

        balances = {aid: to_paise(float(meta.get("opening_balance", 0))) for aid, meta in self.profile.accounts.items()}

        writers = {
            "hdfc_savings": lambda path, rows, month: write_hdfc_csv(path, rows, balances["hdfc_savings"], self._describe),
            "icici_savings": lambda path, rows, month: write_icici_csv(path, rows, self._describe),
            "paytm_wallet": lambda path, rows, month: write_paytm_xlsx(path, rows, balances["paytm_wallet"], self._describe),
            "axis_credit_card": lambda path, rows, month: write_axis_pdf(path, rows, f"{month:%B %Y}", self._describe),
        }

        files: list[dict[str, Any]] = []
        for account in self.sources.accounts:
            aid = account.account_id
            for month in [m for m in months_to_write if m in by_account_month.get(aid, {})]:
                rows = sorted(by_account_month[aid][month], key=lambda t: (t.txn_date, t.seq))
                ext = account.format.file_type
                path = out_dir / aid / f"{aid}_{month:%Y-%m}.{ext}"
                path.parent.mkdir(parents=True, exist_ok=True)

                rows_n, closing = writers[aid](path, rows, month)
                if closing is not None:
                    balances[aid] = closing
                files.append(
                    {
                        "path": str(path.relative_to(out_dir)),
                        "account": aid,
                        "month": f"{month:%Y-%m}",
                        "rows": rows_n,
                        "sha256": sha256_file(path),
                    }
                )
        return files

    # ---------------------------------------------------------------- manifest
    def _build_manifest(
        self, period: tuple[date, list[date], date], txns: list[Txn], files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        start, _month_firsts, end = period
        per_account: dict[str, int] = defaultdict(int)
        per_category: dict[str, int] = defaultdict(int)
        for t in txns:
            per_account[t.account_id] += 1
            per_category[t.category] += 1
        return {
            "generator": "finflow-datagen",
            "synthetic": True,
            "seed": self.seed,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "row_count": len(txns),
            "rows_per_account": dict(sorted(per_account.items())),
            "rows_per_category": dict(sorted(per_category.items())),
            "files": files,
        }

    # ----------------------------------------------------------------- helpers
    def _validate_config(self) -> None:
        for stream in self.profile.streams:
            for merchant in stream.merchants:
                self.catalog.category_of(merchant)  # raises KeyError if unknown

    def _ref(self) -> str:
        return f"{self.rng.getrandbits(36):09X}"

    def _ts(self, day: date) -> datetime:
        return datetime.combine(
            day, time(self.rng.randint(_TS_HOUR_RANGE[0], _TS_HOUR_RANGE[1]), self.rng.randint(0, 59))
        )

    def _describe(self, t: Txn) -> str:
        """Render a transaction description in the owning institution's dialect."""
        if t.description is not None:
            return t.description
        merchant = (t.merchant or "UNKNOWN").upper()
        style = str(self.profile.account_meta(t.account_id).get("descriptor_style", "hdfc"))

        if style == "hdfc":
            specials = {
                "Savings Interest": f"SAVINGS INTEREST/{t.ref}",
                "Bank Charges": f"CHRG-AMC+GST/{t.ref}",
                "Own Account Transfer": f"SELF TRANSFER/{t.ref}/ICICI",
                "Credit Card Bill": f"AXIS CREDIT CARD BILL/{t.ref}",
            }
            if t.merchant in specials:
                return specials[t.merchant]
            return {
                "upi": f"UPI/{t.ref}/{merchant}/{_PHONE}",
                "card": f"POS/{t.ref}/{merchant}",
                "netbanking": f"NEFT/{t.ref}/{merchant}",
                "autopay": f"ACH-D/{merchant}",
            }.get(t.method, f"TXN/{t.ref}/{merchant}")

        if style == "icici":
            if t.merchant == "Bank Charges":
                return f"SMM CHRG+GST/{t.ref}"
            return {
                "upi": f"UPI/{merchant}/{t.ref}",
                "card": f"{merchant}/{t.ref}",
                "netbanking": f"NEFT {merchant} {t.ref}",
                "autopay": f"SI-{merchant}",
            }.get(t.method, f"TXN {merchant} {t.ref}")

        if style == "wallet":
            if t.merchant == "Own Account Transfer":
                return "Added to Paytm from HDFC Bank"
            return f"{'Received from' if t.direction == 'in' else 'Paid to'} {t.merchant or 'Unknown'}"

        # card dialect
        if t.merchant == "Credit Card Bill":
            return "CARD PAYMENT RECEIVED"
        return merchant


def json_manifest(manifest: dict[str, Any]) -> str:
    """Serialize the manifest deterministically (stable key order)."""
    import json

    return json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
