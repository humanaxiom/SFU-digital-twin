# 22. TLS for integrated public startup

Status: accepted for the user's HTTPS troubleshooting and confirmed sfuai.ca
Date: 2026-10-08

Normal public startup uses candidate Compose plus docker-compose.public-tls.yml.
The TLS overlay mounts existing C:/repos/web/certs read-only into the dedicated
demo proxy. No files or services in the sibling web repository are modified.
The certificate and key remain outside Git and outside the application container.
Deployment settings select the directory; launchers protect it from ambient
overrides just like the fixed NAT settings. Missing/invalid credentials fail
startup rather than silently serve an uncertified HTTPS endpoint.

Public https://sfuai.ca:8017/ uses the same local18087/container8007 forwarding
as ADR-0020. nginx negotiates TLS1.2/1.3 and proxies fixed Host demo to its readonly
candidate. Arbitrary Host requests remain rejected. Plain HTTP sent to the TLS
listener redirects to fixed https://sfuai.ca:8017 preserving the request path.
Query strings remain excluded from bounded access logs. The base HTTP candidate
Compose/config remains available for isolated investigation.

This supersedes ADR-0019/0020's plain-HTTP public transport for normal startup;
all other security, NAT, artifact and ADR-0021 recovery controls remain intact.
No authentication or sensitive operations are introduced. Certificate renewal
is owned by the existing external certificate setup; this project does not
claim renewal automation. Reload/restart nginx after certificate replacement.
TLS does not establish or repair NAT loopback on this router.
