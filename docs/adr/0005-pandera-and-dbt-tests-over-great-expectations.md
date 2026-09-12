# ADR-0005: Pandera at the boundary + dbt tests in the warehouse (no Great Expectations)

Date: 2026-09-12 · Status: Accepted

## Context

Data quality is a first-class requirement. Candidates: Great Expectations,
Pandera, dbt tests, custom validation.

## Decision

Two independent, complementary quality nets:

1. **Pandera dataframe schemas** at the ingestion boundary (per source format
   and for the canonical schema). Failures go to quarantine with machine-readable
   error codes — never silent drops.
2. **dbt tests** inside the warehouse: uniqueness, not_null, accepted_values,
   relationships — gating every `dbt build`, so bad data is structurally unable
   to reach marts or notifications.

## Rationale

Great Expectations is powerful for large orgs (expectation suites, data docs,
checkpoint ecosystems) but heavyweight for a one-developer personal platform.
Pandera gives contract-level validation inline with pandas/polars flows, and
dbt tests give warehouse-level gates with lineage-aware docs — covering 95% of
the GE value at a fraction of the operational cost.

## Consequences

- Error-code vocabulary (Q01–Qnn) defined in one module; quarantine rows carry
  codes + raw payloads for reprocessing.
- If validation needs grow (cross-table expectations at scale), the two nets
  can be extended — or GE introduced behind the same quarantine interface.
