# 20. Router-matched public demo publication

Status: accepted for the user's requested external demo restoration
Date: 2026-10-08

The user confirmed router TCP public ports 8010–8020 map one-to-one to
192.168.1.80 local ports 18080–18090. Select public http://sfuai.ca:8017/ and
publish the existing nginx edge on 0.0.0.0:18087 (container port remains 8007).

This narrowly supersedes ADR-0019's external 8007 publication and private 18007
binding. The loaded developer demo retains port 18007; the already verified
exact-topology candidate is restored separately on 127.0.0.1:18107. The candidate
GeoPackage/graph/stats and their provenance remain unchanged. No new ingestion,
topology or artifact promotion is authorized.

All other ADR-0019 controls remain: only Host sfuai.ca is accepted, upstream Host
is fixed to demo, forwarding identity is cleared, nginx is digest-pinned and
unprivileged with a read-only filesystem, and logs are bounded. This is the same
read-only plain-HTTP demonstration with no authentication. ADR-0010's other
publication restrictions remain in force.

Record both ports explicitly: Docker binds the local NAT target 18087, while
users open public 8017. A host-gateway browser verifies the proxy but does not
prove router/firewall traversal. Independent outside-network HTTP is required
before claiming external accessibility.

Rollback stops only the candidate external service. Both private candidate 18107
and existing developer 18007 remain available; source and artifacts are unchanged.
