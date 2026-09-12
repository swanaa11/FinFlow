"""Unit tests for shared utilities: money, hashing, logging redaction, settings."""

from __future__ import annotations

from decimal import Decimal

import pytest

from finflow.config import get_settings
from finflow.utils.hashing import canonical_row_hash, sha256_bytes
from finflow.utils.logging import sanitize
from finflow.utils.money import MoneyFormatError, format_inr, from_paise, to_paise


class TestMoney:
    def test_to_paise_exact(self) -> None:
        assert to_paise(100) == 10_000
        assert to_paise("1,234.50" .replace(",", "")) == 123_450
        assert to_paise(Decimal("99.99")) == 9_999
        assert to_paise(0.1) == 10

    def test_to_paise_rejects_sub_paise(self) -> None:
        with pytest.raises(MoneyFormatError):
            to_paise("10.555")

    def test_to_paise_rejects_garbage(self) -> None:
        with pytest.raises(MoneyFormatError):
            to_paise("abc")

    def test_round_trip(self) -> None:
        for paise in (0, 1, 99, 10_000, 123_450, 999_999_999):
            assert to_paise(from_paise(paise)) == paise

    def test_format_inr_indian_grouping(self) -> None:
        assert format_inr(0) == "₹0"
        assert format_inr(50) == "₹0.50"
        assert format_inr(123_450) == "₹1,234.50"
        assert format_inr(12_34_56_700, with_decimals=True) == "₹12,34,567.00"
        assert format_inr(-4_200) == "-₹42"

    def test_negative_paise(self) -> None:
        assert from_paise(-150) == Decimal("-1.50")


class TestHashing:
    def test_sha256_bytes_stable(self) -> None:
        assert sha256_bytes(b"finflow") == sha256_bytes(b"finflow")
        assert sha256_bytes(b"a") != sha256_bytes(b"b")

    def test_canonical_row_hash_order_independent(self) -> None:
        h1 = canonical_row_hash({"a": 1, "b": "x"})
        h2 = canonical_row_hash({"b": "x", "a": 1})
        assert h1 == h2

    def test_canonical_row_hash_value_sensitive(self) -> None:
        assert canonical_row_hash({"a": 1}) != canonical_row_hash({"a": 2})


class TestLogSanitizer:
    def test_redacts_telegram_token_shape(self) -> None:
        msg = "failed for bot 1234567890:AAEhBOweik6ad9r_QXMENQjcrGbqCr4K-4s"
        assert "AAEhBOweik" not in sanitize(msg)
        assert "***REDACTED***" in sanitize(msg)

    def test_redacts_key_value_secrets(self) -> None:
        msg = "using password=hunter2 now"
        assert "hunter2" not in sanitize(msg)

    def test_redacts_caller_supplied_secrets(self) -> None:
        assert "s3cret" not in sanitize("token is s3cret", extra_secrets=["s3cret"])

    def test_plain_messages_untouched(self) -> None:
        assert sanitize("processed 42 rows") == "processed 42 rows"


class TestSettings:
    def test_defaults_resolve(self) -> None:
        from finflow.config import get_settings

        settings = get_settings()
        assert settings.root.exists()
        assert settings.incoming_dir == settings.data_path / "incoming"
        assert settings.active_db_file.name == "finflow.duckdb"

    def test_demo_mode_switches_database(self) -> None:
        from finflow.config.settings import Settings

        settings = Settings(demo_mode=True, root=get_settings().root)
        assert settings.active_db_file == settings.root / "data/demo/finflow_demo.duckdb"
