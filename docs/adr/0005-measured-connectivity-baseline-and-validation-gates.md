# 5. Measured connectivity baseline and validation gates

Status: Accepted  
Date: 2026-08-31  
Supersedes: ADR-0004 §12 (Connectivity gate timing)

## Context

ADR-0004 §12 specified connectivity gates for DT-006 (Add Transition Edges):
- **Default profile** (pathways + stairs + elevators): exactly 1 connected component (hard gate)
- **Accessible profile** (pathways + elevators only): ≤11 connected components (informational, with reachability matrix)

This design assumed the pathway network (`graph_raw.pkl` from DT-005) would form a connected or near-connected graph on its own, with transitions bridging any small gaps. DT-006 would then validate that adding transitions produces the expected connectivity.

### Measured reality from DT-005 artifacts

Containerized execution of DT-005 (commit 14652a9) with verified read-only access to `build/wayfinding.gpkg` produced these measurements:

**Pathway-only baseline** (`build/graph_raw.pkl`):
- 15,582 nodes
- 44,826 directed pathway arcs (mode='pathway' only)
- **855 undirected connected components**
- Largest component: 2,957 nodes (AQ 3000 level)
- Smallest components: small clusters (DT-005 has no degree-zero graph nodes)

**Transition endpoint coverage** (`build/node_map.pkl`):
- 85 unique transition endpoint nodes across 63 transition features
- 80 endpoints already exist in pathway graph (degree ≥1 from pathway edges)
- 5 endpoints are transition-only (no pathway edges, would be isolated without transitions)

**Augmented graph statistics** (dry-run measurements, not yet committed):
- Adding all 5 transition-only nodes: **15,587 total nodes**
- Adding all 63 transition links (42 stairs, 21 elevators; 126 directed arcs):
  - **816 undirected components** (down from 855)
  - Largest component: 7,436 nodes
- Adding only 21 elevator links (42 directed arcs):
  - **840 undirected components** (down from 855)
  - Largest component: 7,060 nodes

### Mathematical constraints

A graph with **N** components can be reduced to at most **N - k** components by adding **k** edges (each edge can reduce component count by at most 1, and only if it bridges two previously disconnected components). Given 855 pathway-only components and 63 total transition links:

- **Minimum achievable components**: 855 - 63 = **792**
- **Measured 816 components** means 39 transitions bridged components; 24 connected within already-connected components (refinement but not bridging)

The original expectation of **1 component** for default profile is **mathematically impossible** given the measured pathway fragmentation.

### Root cause

The AIIM pathway network at SFU Burnaby exhibits severe fragmentation. Possible explanations:
1. **Data collection gaps**: Pathways not digitized for some areas (utility rooms, back corridors, isolated wings)
2. **Intentional exclusion**: Non-public or restricted areas omitted from the routable network
3. **Topology errors**: Missing pathway segments at critical junctions, producing artificial islands
4. **Door barriers**: Pathways on opposite sides of a locked door stored as separate components (the dataset lacks door-as-edge features)

Data findings §5 noted the extreme over-noding (22,426 segments, mean 0.94 m) but did not include a full connectivity audit pre-DT-005. The fragmentation was not discovered until graph construction completed.

### ADR-0004 §12 assumed connectivity

The original decision stated:
> "DT-006 will add the cross-level connectivity gate: after adding transition edges, the graph filtered to `mode in ['pathway', 'stairs', 'elevator']` must have exactly 1 connected component (PHASE-1-ETL AC4)."

This was reasonable given:
- AIIM spec implies a routable network (not just basemap geometry)
- Three buildings are physically connected at multiple levels
- 22,426 pathway segments suggested dense coverage

But the assumption was **not validated** against the actual DT-005 output before writing ADR-0004. We now have measurements that falsify it.

### Consequences of strict enforcement

If DT-006 enforced "exactly 1 component" as a hard gate:
- **Build fails immediately** on real data
- **Cannot proceed to DT-007** (contraction) or beyond
- **Blocks Phase 1 delivery** until topology is repaired

Topology repair options:
1. **Manual data correction**: Identify and add missing pathway segments in source GDB (requires geodatabase write access, violates read-only boundary, out of scope)
2. **ETL inference**: Algorithmically add connector edges across small gaps (e.g., <2 m between components on the same level) — risky, may create incorrect routes
3. **Accept fragmentation**: Document as a data-quality limitation, surface in UI ("no route available between X and Y"), defer repair to future GDB updates

Option 3 is the only feasible approach for Phase 1 that respects the read-only source boundary.

### Implications for accessible routing claims

The original design specified elevator-only accessible routing with the expectation of thin but viable connectivity (≤11 components, acknowledging possible disconnections across some level pairs).

With **840 components** in the elevator-only graph:
- Most individual rooms or small room clusters are isolated
- Elevator-only reachability is **far more limited** than implied by "≤11 components"
- Reporting vertical_order-pair reachability is insufficient; need component-level or unit-pair analysis

The elevator-only honesty principle (system design §4.2, accessibility-claims instruction) still holds — we never claim wheelchair certification or guaranteed step-free paths — but the **degree of fragmentation** must be explicitly surfaced, not buried in a reachability matrix.

### DT-006 implementation without a global-connectivity gate

If DT-006 proceeds with informational connectivity only:
- Adds all 63 transition edges
- Adds/populates 5 transition-only nodes
- Records component metrics for both profiles
- Fails only on connectivity regression, a no-op transition mode, or drift from the measured pinned
   fixture; it does not require global connectivity
- Produces `build/graph_with_transitions.pkl` with measured statistics

Then:
- **DT-007 (contraction)** proceeds on the fragmented graph (contraction is component-local, does not require global connectivity)
- **DT-008 (unit connectors)** proceeds (connects units to nearest pathway node on same level, independent of cross-component connectivity)
- **DT-009 (validation)** is where topology decisions must be made:
  - Option A: Hard gate requiring 1 component (blocks delivery until topology repair)
  - Option B: Soft gate with explicit component catalog (allows delivery, documents limitations)

The measured baseline strongly favors **Option B** — document the fragmentation, allow routing within connected regions, surface "no route available" errors at query time for disconnected pairs.

## Decision

**Supersede ADR-0004 §12** with the following revised connectivity validation contract:

### DT-006: Add transitions, record baseline, validate non-regression

**Acceptance criteria:**
1. Add all 63 transition features as 126 bidirectional directed edges (42 stairs, 21 elevators)
2. Add/populate 5 transition-only nodes (endpoints not referenced by pathway edges)
3. Record component metrics in `build/graph_with_transitions_stats.json`:
   - **Pathway-only baseline**: 855 components (from DT-005 `graph_raw_stats.json`)
   - **Default profile** (pathway + stairs + elevators): 816 components
   - **Accessible profile** (pathway + elevators only): 840 components
   - For each profile: largest component size, component size distribution (histogram or summary stats)
4. **Non-regression validation** (hard gate):
   - Default profile components ≤ pathway-only baseline (816 ≤ 855 ✓)
   - Accessible profile components ≤ pathway-only baseline (840 ≤ 855 ✓)
   - Each transition mode must bridge at least one previously disconnected component, preventing a
     no-op edge implementation from satisfying non-regression vacuously
   - *Rationale*: Adding edges should reduce or maintain component count, never increase it (increasing would indicate a node-identity or snapping bug)
5. **Pinned-fixture and transition bridging validation** (hard gate for the current source fixture):
   - Default profile must reproduce 816 components, largest component 7,436, and 39 bridged
     components
   - Elevator-only profile must reproduce 840 components, largest component 7,060, and 15 bridged
     components
   - Report how many transitions bridged components (connected two previously disconnected components) vs. refined within a component
6. **No global-connectivity gate**: DT-006 succeeds with documented fragmentation; it does not
   require one component or an arbitrary per-level component bound

**Rationale:**
- DT-006 cannot fix pathway topology; it can only add vertical transitions
- Measured baseline (855 components) makes "exactly 1 component" impossible without topology repair
- Non-regression validation catches implementation bugs (e.g., incorrect node lookups creating duplicate nodes)
- Informational metrics provide audit trail for future topology decisions

### DT-009: Validate routes, disposition topology

**Deferred decisions** (recorded here for continuity, implemented in DT-009 plan):
1. **Topology repair disposition**: Before DT-009, decide whether to:
   - Accept fragmentation and document limitations (soft gate, allows delivery)
   - Require topology repair as a prerequisite (hard gate, blocks delivery until data fixed)
   - Implement ETL inference to bridge small gaps (medium gate, requires careful validation)
2. **Component catalog**: DT-009 must produce a **connected-component catalog** mapping every `unit_id` to its component ID for both profiles, enabling query-time "no route available" detection
3. **Reachability claims**: Update routing API and UI copy to reflect measured connectivity:
   - Do not claim "campus-wide routing" without qualifying which components are connected
   - Surface component boundaries in UI (e.g., "AQ 3150 and SH 227 are not connected by indoor pathways")
   - For accessible profile, do not claim step-free access between arbitrary units; report per-query
4. **Vertical-order reachability**: Given 840 accessible-profile components:
   - Vertical_order-pair reachability matrix (e.g., "can reach vertical_order 2 from vertical_order 0 via elevators") is **insufficient** — many units on the same vertical_order are in different components
   - Must report **unit-pair reachability** or **component membership** instead
   - Example: "Elevator access from AQ 3150 to AQ 5120: unavailable (different connected components)"

### Spatial-data-invariants update

Revise [.github/instructions/spatial-data-invariants.instructions.md](../../.github/instructions/spatial-data-invariants.instructions.md):

**Old wording:**
> "A disconnected graph for the `default` routing profile is a hard build failure. A disconnected graph for the `accessible` profile is a warning plus an explicit reachability matrix — it is not an error, because 21 elevator transitions across 11 levels is genuinely thin coverage."

**New wording:**
> "The measured pathway network has 855 connected components (DT-005 baseline). Adding transitions reduces this to 816 (default profile) and 840 (accessible profile). DT-006 validates non-regression (component count does not increase) but does not enforce global connectivity. DT-009 validation produces a connected-component catalog mapping every unit to its component, enabling query-time "no route available" detection for disconnected pairs. A fully connected graph is aspirational pending topology repair; fragmentation is documented as a known data-quality limitation."

## Consequences

### Positive

- **DT-006 deliverable**: Can complete implementation against measured data without blocking on topology repair
- **Honest baseline**: Component counts and fragmentation are explicitly documented, not hidden
- **Audit trail**: Transition-bridging statistics show which edges meaningfully improved connectivity
- **Query-time failures**: Routing engine can detect and explain disconnected pairs ("no route available") rather than silently failing or computing nonsensical paths
- **Defers global-connectivity choices**: Topology repair decisions move to DT-009 after the full
   pipeline is implemented, with better context for cost/benefit analysis

### Negative

- **Fragmentation is real**: 816 components means most rooms are in isolated clusters; routing is severely limited
- **Accessible routing nearly unusable**: 840 components in elevator-only profile means step-free access is available only within tiny connected regions
- **UI/UX complexity**: Must surface "no route available" gracefully; cannot promise universal indoor routing
- **Topology repair still required**: Deferred to post-Phase-1, requires either source GDB edits (out of scope, read-only boundary) or ETL inference (risky)
- **Stakeholder expectations**: Must communicate that "indoor wayfinding" means "routing within connected regions" not "routing to any room from any room"

### Superseded decisions

- **ADR-0004 §12**: "Cross-level connectivity deferred to DT-006" remains accurate, but the hard gates specified there are replaced by the non-regression + informational metrics above
- The rest of ADR-0004 (node identity, edge keys, serialization, multipart geometry, reverse-edge convention) **remains valid and unchanged**

### Documentation updates required

1. **docs/adr/0004-graph-construction-and-node-identity.md**: Add a note at the start of §12 referencing ADR-0005 supersession
2. **docs/plans/DT-006.md**: Update AC6 (default profile connectivity) and AC7 (accessible profile connectivity) to match the non-regression semantics
3. **docs/plans/PHASE-1-ETL.md**: Remove stale "exactly 1 component" and "≤11 components" expectations from DT-006 section; add measured baseline
4. **docs/02-system-design.md**: Add a subsection under §3.3 (Graph construction) documenting the measured fragmentation and its implications for routing coverage
5. **.github/instructions/spatial-data-invariants.instructions.md**: Replace the connectivity gate wording as specified above
6. **docs/DOD.md**: No change needed (already requires passing all tests and acceptance criteria, which will reflect the updated semantics)
7. **docs/HANDOFF.md**: Update DT-006 status once implemented, referencing this ADR

### DT-007, DT-008 impacts

- **DT-007 (contraction)**: Operates component-locally (contracts degree-2 chains within each connected component independently); global connectivity not required
- **DT-008 (unit connectors)**: Projects each unit centroid to nearest pathway node **on same level_id**; does not require cross-component connectivity

Both tickets can proceed on the fragmented graph without modification.

### DT-009 validation checklist

When planning DT-009, must address:
1. ☐ Topology repair disposition decision (accept fragmentation / require repair / implement inference)
2. ☐ Connected-component catalog schema (mapping `unit_id` → `component_id` for both profiles)
3. ☐ Query-time "no route available" error detection and messaging
4. ☐ Component-boundary surfacing in UI (map visualization or routing panel)
5. ☐ Reachability API contract: unit-pair reachability, not just vertical_order-pair
6. ☐ Stakeholder communication: scope and limitations of v1 routing given fragmentation

### Accessibility claims and provenance

The elevator-only honesty principle (accessibility-claims.instructions.md) is **strengthened** by this ADR:
- Never claim "accessible routing throughout the campus" — the measured 840 components make this false
- Report per-query reachability: "Accessible route from AQ 3150 to AQ 5120: not available (different connected components)"
- Document provenance: "Connectivity based on 21 elevator transitions in the source geodatabase; isolated regions exist due to pathway topology gaps"
- No wheelchair certification: Unchanged; elevator-only != wheelchair-accessible (doors, thresholds, surface conditions unknown)

### Risk: stakeholder surprise

**Risk**: Facilities or IT stakeholders expected "indoor wayfinding" to mean universal campus routing, not fragmented routing within connected regions.

**Mitigation**:
1. Surface the measured baseline (855 → 816 components) in the DT-006 delivery summary
2. Provide a sample query demonstrating "no route available" before deploying to stakeholders
3. Offer topology repair as a **Phase 2 or 3 work item** (requires either GDB write access or ETL inference algorithm)
4. Position fragmentation as a **data-quality finding**, not a system design flaw — the AIIM pathway network is incomplete

### Risk: contraction or unit connectors worsen fragmentation

**Risk**: DT-007 contraction removes a critical junction node, splitting a component. DT-008 adds a zero-cost connector that creates a graph anomaly.

**Mitigation**:
- **DT-007**: Protected nodes include all junctions (degree ≥3), transition endpoints, and unit-connector attachment points; contraction is topology-preserving by design
- **DT-008**: Unit connectors are zero-cost and unidirectional (unit → pathway, not pathway → unit); cannot split components
- **DT-009**: Recompute component count after each stage; fail if component count increases (regression check)

### Risk: vertical-order reachability misinterpreted

**Risk**: A vertical_order-pair reachability matrix (e.g., "vertical_order 0 and vertical_order 2 are connected via elevators") may be misread as "all units on level 0 can reach all units on level 2 via elevators."

**Mitigation**:
- Do **not** emit a vertical_order-pair reachability matrix in DT-006 stats JSON
- Instead, emit **component-aware metrics**: largest connected component per vertical_order, cross-vertical_order component bridging count
- DT-009 produces the definitive **unit-pair reachability** or **component catalog**
- Documentation and UI must never claim level-to-level reachability without qualifying component boundaries

## Summary

The measured DT-005 baseline reveals the pathway network has **855 connected components**, making
the original ADR-0004 §12 expectation of one default-profile component mathematically impossible.
This ADR supersedes that section. DT-006 reproduces the measured 816 default and 840 elevator-only
component baselines, rejects connectivity regressions and no-op transition modes, but does not
require global connectivity. DT-009 owns topology disposition and the component catalog used for
query-time no-route results. Elevator-only routing remains stairs-excluded and is not wheelchair
certification.
