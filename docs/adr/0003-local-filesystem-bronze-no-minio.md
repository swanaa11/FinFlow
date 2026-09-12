# ADR-0003: Local filesystem + Parquet for Bronze — no MinIO, no S3

Date: 2026-09-12 · Status: Accepted

## Context

The candidate architecture sketch assumed an object store (S3 or MinIO) between
ingestion and processing, with event-driven triggers.

## Decision

Bronze is **immutable local files**: original statements in `data/raw/` plus
Parquet datasets partitioned by `(source, year, month)`. No object store, no
event triggers; a scheduled/on-demand scan of `data/incoming/` is the trigger.

## Rationale

- MinIO Community Edition is effectively end-of-life: admin console stripped
  (mid-2025), official binaries discontinued (Oct 2025), repository archived,
  no security fixes (verified 2026-09). Adopting it would add unmaintained
  infrastructure for zero functional gain on a single machine.
- All data lives on one host by design (privacy). Object storage solves
  multi-machine/multi-tenant problems this platform does not have.
- S3+Lambda event triggers would require a card-carrying cloud account —
  rejected in ADR-0002's cost framing.

## Consequences

- Adding object storage later is a writer-interface change, not a redesign
  (the Parquet layout is already partitioned for pruned reads).
- Files are the unit of idempotency: sha256 content-hash registry, not bucket
  notifications.
