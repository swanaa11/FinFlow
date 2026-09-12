# ADR-0007: Synthetic-only data in anything public

Date: 2026-09-12 · Status: Accepted

## Context

FinFlow processes real financial statements locally, but the repository, any
hosted demo, screenshots, and README examples are public. Real financial data
must never leak.

## Decision

Every public artifact contains **only generated synthetic data**:

- `data/` is gitignored except `data/sample/` (generator output).
- The hosted Streamlit demo runs with `FINFLOW_DEMO_MODE=true`, which forces
  the synthetic demo database at the code level — real databases are
  unreachable, not merely hidden.
- Screenshots for README/LinkedIn are produced exclusively from the demo dataset.
- Real statements stay in local, gitignored directories (`data/incoming/`,
  `data/raw/`, `data/quarantine/`).

## Consequences

- CI includes a guard test asserting the sample dataset exists and carries the
  synthetic manifest (seed, date range) so "demo data" cannot rot silently.
- The generator is a first-class milestone, not an afterthought — its realism
  is what makes demos convincing.
