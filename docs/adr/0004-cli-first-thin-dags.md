# ADR-0004: CLI-first pipeline; Airflow DAGs are thin wrappers

Date: 2026-09-12 · Status: Accepted

## Context

The owner machine has <8 GB RAM. Apache Airflow comfortably needs 2.5–4 GB in
Docker. Cron would run this pipeline in ~50 MB. But Airflow is the most
recognized orchestrator in Data Engineering job descriptions, and the owner
explicitly chose it.

## Decision

Every pipeline capability is a **CLI command** (`finflow ingest|process|build|
notify|run-all`) with its own tested library function underneath. Airflow DAGs
contain **no business logic** — they shell into these commands with retries and
scheduling. A `lite` deployment profile (scheduler loop / host cron, ~0.5 GB)
runs the identical commands without Airflow.

## Rationale

- The core pipeline is testable in CI without orchestrator overhead.
- The orchestrator becomes a replaceable scheduling policy, not a framework
  the codebase is married to — a genuinely good production pattern, not just a
  RAM workaround.
- Honest trade-off documented rather than hidden: Airflow is chosen for
  retries/backfill/UI *and* recruiter relevance; the design keeps that choice
  reversible in minutes.

## Consequences

- DAG import errors can never break business logic; they only break scheduling.
- On the owner's machine the `lite` profile is the recommended daily mode and
  `full` (Airflow) the demo/interview mode — measured-RSS acceptance test in
  M14 records the real numbers.
