# 1. Record architecture decisions

Status: accepted
Date: 2026-08-29

## Context

Decisions about schema, API surface, and component boundaries need a durable record that survives
past the chat session that made them, and that `architect`/`judge` can cite by number. Both
reference implementations examined for this harness
([docs/03-harness-design.md §1](../03-harness-design.md#1-why-a-harness-at-all)) use the same
lightweight ADR convention (Nygard-style: Status, Date, Context, Decision, Consequences).

## Decision

We will keep architecture decisions in `docs/adr/`, one file per decision, numbered sequentially,
named `docs/adr/<NNNN>-<slug>.md`. Each ADR states its status (`proposed` / `accepted` /
`superseded`), the date, what forces the decision, what was decided, and the consequences —
including anything it supersedes or is independent of.

`architect` is the only role that writes ADRs, and only when a plan from `planner` touches schema,
an API contract, or a component boundary (see
[.github/agents/architect.agent.md](../../.github/agents/architect.agent.md)).

## Consequences

- Every schema/API/boundary change is traceable to a written rationale, not just a diff.
- `judge` can check plan conformance against a numbered ADR instead of re-litigating the decision.
- ADRs are never edited after acceptance to change the decision — a changed decision gets a new ADR
  that supersedes the old one, same as a database migration is never edited after being applied.
