---
description: "Decompose the backlog across the delivery phases in docs/02-system-design.md §11 into ticket-sized plans"
argument-hint: "<phase or milestone to plan>"
agent: agent
---
Plan the backlog for: ${input:scope:Which phase or milestone to decompose}

1. Invoke `planner` to break the target phase from
   [docs/02-system-design.md §11](../../docs/02-system-design.md#11-delivery-phases) into
   ticket-sized units (each independently plannable via `/tdd-feature`), respecting dependency order
   (e.g. ETL before routing, routing before instruction generation, per §11).
2. For each ticket, confirm the acceptance criteria are testable and the ticket does not silently
   assume infrastructure (containers, migrations) that a prior ticket must deliver first.
3. Flag any ticket that clearly needs an ADR before work starts (schema/API/component-boundary
   change) so `architect` is scheduled ahead of `implementer`.
4. Report the ticket list in dependency order with a one-line scope for each; do not write the
   individual `docs/plans/<ticket-id>.md` files here — that happens per-ticket in `/tdd-feature`.
