# ADR-0002: DuckDB as the analytical warehouse (no cloud warehouse)

Date: 2026-09-12 · Status: Accepted

## Context

The platform needs a SQL analytical layer. Candidate free options: BigQuery
sandbox, Snowflake trial, PostgreSQL, DuckDB. Hard constraint: ₹0 recurring,
no credit card, no expiring infrastructure.

## Decision

**DuckDB** (embedded, MIT) is the primary warehouse. Local filesystem + Parquet
is the Bronze layer.

## Rationale

- BigQuery sandbox deletes **all** tables after 60 days and the permanent free
  tier requires a billing account (verified 2026-09). Snowflake is a 14-day
  trial. Both fail "free forever" — unacceptable for daily personal use.
- Personal-scale data (10^4–10^6 rows) is DuckDB's sweet spot: columnar,
  parallel, zero-ops, single file, read-only-safe for concurrent dashboard use.
- PostgreSQL is kept for exactly one role: Airflow's metadata database — where
  it is required, not chosen.

## Consequences

- Trade-off: no "BigQuery/Snowflake on my resume" signal from running it.
  Mitigation: `docs/scaling.md` maps each component to its cloud equivalent
  and the dbt models remain port-standard SQL.
- Single-writer discipline required: serving reads use read-only connections.
- Rebuildability is mandatory: nightly EXPORT backup + full rebuild from raw
  is a tested command (raw files are the true system of record).
