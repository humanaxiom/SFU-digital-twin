# Copilot adapter

Read [AGENTS.md](../AGENTS.md) for shared repository instructions, then
[docs/HANDOFF.md](../docs/HANDOFF.md) and the relevant ticket plan and accepted ADRs.
These are the shared sources of truth for Copilot and Codex.

The roles and prompts under `.github/` remain Copilot-specific helpers. Select
roles appropriate to the task. Completion requires actual gate evidence and a
final diff review including documentation, not merely a historical judge verdict.
The post-tool hook is diagnostic only: it cannot prevent a completed write.
Read-only mounts and runtime permissions provide the source protection boundary.
