---
description: "Bring up the current phase's runnable slice for a stakeholder walkthrough and report exactly what can and cannot be demonstrated yet"
agent: agent
model: 'Claude Opus 4.5 (copilot)'
---
Prepare a demo of the current delivery phase
(see [docs/02-system-design.md §11](../../docs/02-system-design.md#11-delivery-phases) and
[docs/HANDOFF.md](../../docs/HANDOFF.md) for phase status).

1. Determine what is actually runnable today — do not promise capability from a later phase.
2. If nothing is runnable yet (pre-Phase-1), demo the reproducible data-findings path instead:
   `tools/dump_gdb_schema.ps1`, `tools/dump_gdb_domains.ps1`, `tools/run_profile.ps1`, and walk
   through [docs/01-data-findings.md](../../docs/01-data-findings.md).
3. Once services exist, bring them up via the checked-in bootstrap path only (never ad hoc commands)
   and invoke `test-runner` first to confirm the gate is green before demoing.
4. Report a script: what you'll show, in what order, and the one or two data gaps
   (`docs/01-data-findings.md §8`) worth calling out so the accessible-mode limitation is never
   overstated to stakeholders.
