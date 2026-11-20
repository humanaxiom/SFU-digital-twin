# 25. Exact multipart pathway reconstruction

Status: Accepted
Date: 2026-11-19

DT-017 supersedes ADR-0004's stored-part concatenation and ADR-0015's
multipart exclusion for pathways only.
Source files and transitions remain unchanged. A multipart pathway is admitted only
when exact native XYZ endpoints form one connected open chain, each part is simple,
and the resulting line is simple. Branches, cycles, duplicates, disjoint parts,
near joins and unsupported travel direction are explicitly excluded. Multipart
admission requires TRAVEL_DIRECTION=1 (bidirectional). Orient the unique chain so
its first stored part retains its source direction; this preserves direction where
supported without claiming the old false endpoints are authoritative. Single-part
endpoint identity retains the existing WKT rounding contract; multipart assembly
uses native WKB doubles. No snapping is used to establish part connectivity.

Remove only the repeated join coordinate. Every emitted segment retains its
original part index and vertex indices; exact noding slices these segment spans,
and reversal reverses span traversal. LENGTH_3D remains the recorded cost and
exact splits allocate that cost proportionally, with existing mismatch diagnostics.
Both endpoint and exact pipelines use the same reconstructed chain. Raw statistics
and topology audit disclose reconstructed and excluded feature identities. Existing
artifacts remain readable and are never rewritten. Historical component counts
are not acceptance targets for corrected candidates; DT-017 requires fresh source,
geometry, profile reachability and application evidence before promotion.

Contraction also retains a boundary whenever incident native pathway XYZ endpoints
differ, even if they share a centimetre node. Such edges retain their existing
graph connectivity and costs but remain separate geometries; contraction never
replaces a native segment by dropping a nonidentical coordinate. This supersedes
any older assumption that snapped identity proves coordinate equality.

Endpoint mode also carries complete original part/vertex spans for reconstructed
multipart edges, including reverse traversal. Contracted edges retain those spans;
completeness is false when mixed with older endpoint edges without source spans.
