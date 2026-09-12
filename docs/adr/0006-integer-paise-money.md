# ADR-0006: Money is integer paise end-to-end

Date: 2026-09-12 · Status: Accepted

## Context

Statement files carry money as decimal strings ("1,234.50"). Floats silently
accumulate error; decimal rounding mistakes in a finance platform destroy trust
and are a classic interview red flag.

## Decision

All storage, transformation, and aggregation uses **integer paise**
(`amount_paise INT`). Conversion happens at two boundaries only: parsing
(statement string → paise, via `Decimal`, exact) and presentation (paise →
Indian-grouped ₹ string). A strict converter rejects sub-paise precision
instead of rounding silently.

## Consequences

- Sums, comparisons and joins are exact; hash-based idempotency is stable.
- Trade-off: marts expose a `signed_amount DECIMAL(18,2)` view column for human
  ergonomics — derived, never authoritative.
- Indian digit grouping (₹12,34,567.89) implemented once in `format_inr`.
