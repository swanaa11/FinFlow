# FinFlow — Implementation Log

Honest, milestone-by-milestone record of what was built, validated, and what
remains. Each entry is committed only after its acceptance checks pass.

---

## Milestone 1 — Repository & Environment ✅

**Delivered**
- `src/` package layout (`finflow` installable, console script `finflow`)
- Typed configuration: `FINFLOW_*` env vars / `.env`, pydantic-validated,
  repo-root-relative paths, `DEMO_MODE` fail-safe switch (ADR-0007)
- `utils.money`: integer-paise engine + Indian-grouped `format_inr` (ADR-0006)
- `utils.hashing`: streaming sha256 (file identity), canonical row hashes
- `utils.logging`: JSON logs, secret redaction (token shapes + caller-supplied)
- CLI skeleton (`finflow version|info|datagen`), Makefile, `.env.example`,
  MIT license, CI workflow (authored; push pending token scope), 7 ADRs,
  approved architecture plan (`docs/PLAN.md`)

**Validated**: lint clean · settings/money/hash/logging unit tests pass ·
`finflow info` renders resolved config.

## Milestone 2 — Synthetic Data Generator ✅

**Delivered**
- Config-driven "digital twin" (`config/datagen.yaml` + `config/sources.yaml` +
  `config/categories.yaml` — all pydantic-validated, cross-checked at init)
- Realistic financial behaviour: monthly salary, rent, autopays, subscriptions,
  quarter-end interest, probabilistic daily spend with per-merchant price
  ranges, wallet auto-reload when low, credit-card bill = previous month's
  actual card spend, own-account transfers
- 4 accounts in 4 distinct export formats: HDFC CSV (two-column, running
  balance), ICICI CSV (debit/credit + signed net), Paytm XLSX (signed, with
  timestamps), Axis card PDF (multi-page reportlab statement)
- **Dirt injection (stratified, guaranteed per CSV account):** duplicated
  statement reprints (balance-neutral), blank descriptions, unknown merchants,
  zero-amount rows, future-dated rows
- **Planted signals:** 4 statistical outliers (e.g. ₹42,500 Croma), 3
  same-merchant consecutive-day near-duplicate pairs
- Deterministic: same seed + period ⇒ byte-identical corpus (verified by test)
- `manifest.json` with period, per-account/category counts, file sha256s

**Validated (28 tests, all passing)**
- Determinism (byte-level), seed sensitivity, manifest/file agreement
- Per-format golden checks (columns, conventions, PDF text extraction)
- Running-balance walk across HDFC files (opening + Σrows = printed balance)
- Dirt presence, future-dated rows beyond period end, planted anomalies present
- Income booked as deposits; transfer rows excluded from description dirt

**Known follow-ups (M3+):** dirt rows are currently labelled `Uncategorized`
in the generator's internal view; the ingestion quarantine (not the generator)
is what must detect and isolate them at parse time.

**Demo dataset (committed):** `data/sample/` — 12 complete months
(2025-09 → 2026-08), 1,709 rows, 50 files, 4 accounts, 289 KB.

---

## Upcoming

- M3 Ingestion — hash registry, adapters, raw archiving
- M4 Validation — Pandera contracts + quarantine
- M5–M8 — normalize → dedupe → DuckDB → dbt (MVP gate)
- M11–M17 — Airflow (lite/full profiles), dashboard, Telegram, Docker, CI,
  docs, Streamlit Cloud demo
