# 27. Restore two-room click routing with explicit inspection mode

Status: accepted and locally verified; [DT-034 evidence](../reports/DT-034.md).
Date: 2026-11-20

## Context

The user expects clicking room A then room B to create directions. ADR-0017's
Stage C inspection-only clicks removed that familiar interaction. Tests that
explicitly chose Start here, Directions here and Preview did not cover this
expectation. The reported instance is the candidate on loopback port 18107.

## Decision

Default the visible Room clicks selector to Route A to B. In this mode a map
room or room-list activation inspects the record and selects A if there is no
origin. A subsequent distinct room selects B and submits the route automatically.
Further clicks replace B while retaining A. Clear resets endpoints. Selecting A
again only inspects it. Pointer, Enter and Space use the same action.

Inspect only is an explicit alternate mode that preserves endpoints and routes.
Changing modes cancels waiting endpoint selections, without clearing a committed
route. Search, dropdown, assistant, Start here and Directions here actions retain
their draft and explicit Preview behavior. The committed route keeps its own
endpoint and profile identity until a successful replacement.

Known unsupported B selections remain inspectable and visibly explain why no
route can be drawn. They cannot replace the prior route or issue a route POST.
Pending availability belongs to the original click: newer clicks, explicit draft
edits, Clear and mode changes invalidate it. A later floor/building exploration
must not be stolen by the eventual accepted route or stale room details. Detail
loading is independent of route submission.

This supersedes ADR-0017's inspection-only room activation and sole-Preview
submission rules only for default room-click routing. Its remaining contracts,
including exploration, submitted snapshots and source/graph boundaries, remain.
No HTTP API, graph, source data, artifact or routing algorithm changes.

## Verification

[DT-034](../plans/DT-034.md) requires an untouched-default two-click browser
regression, explicit inspection coverage and Docker browser/API checks on both
accepted artifacts and the running candidate. Existing inspection tests must
select Inspect only rather than silently assume it is the default.
