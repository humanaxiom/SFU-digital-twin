# Plans

[DT-024](DT-024.md) is the next client implementation plan: coherent building/floor navigation, searchable endpoints, explicit route commitment and synchronized journeys. Architecture is accepted for implementation; runtime work has not started. DT-017/DT-023 data scope remains independent.

[DT-021](DT-021.md) fixes initial route framing and adds explicit map zoom controls.

[DT-020](DT-020.md) addresses route availability choices and visible route failures.

[DT-019](DT-019.md) records the verified rebuild-launcher image-diagnostic fix.

Per-ticket implementation plans, written by `planner` before any code exists — see
[docs/03-harness-design.md §3](../03-harness-design.md#3-subagent-pipeline) and
[.github/agents/planner.agent.md](../../.github/agents/planner.agent.md).

Naming: `<ticket-id>.md`, e.g. `DT-016.md`. Current build work is
[DT-016](DT-016.md), followed by [DT-017](DT-017.md). The
[takeover plan](CODEX-TAKEOVER.md) records inherited findings and migration work;
[HANDOFF](../HANDOFF.md) is authoritative for current execution and gate status.

[DT-018](DT-018.md) implements clearer floor transitions, ordinary-language guidance
and selected-segment highlighting. Client presentation uses the accepted artifacts;
DT-017 corrected geometry and candidate-backed E2E remain required for final
navigation-quality acceptance. Follow the handoff for actual verification status.
