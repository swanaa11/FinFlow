# ADR-0001: Record architecture decisions

Date: 2026-09-12 · Status: Accepted

## Context

FinFlow is a portfolio-grade project that will be reviewed by senior engineers.
Design rationale that lives only in chat history is lost to reviewers and to
future maintainers.

## Decision

We record every significant architectural decision as a short ADR in
`docs/adr/`, numbered sequentially and immutable once accepted (superseded
ADRs point to their replacement).

## Consequences

Trade-offs are visible to reviewers — which is precisely the signal a DE
interviewer looks for. Cost: a small amount of documentation discipline.
