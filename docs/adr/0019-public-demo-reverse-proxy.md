# 19. Public demo reverse proxy on port 8007

Status: accepted for the explicitly requested `sfuai.ca:8007` deployment.
Date: 2026-09-23.

## Context

ADR-0010 permits only a bounded trusted-LAN publication and explicitly excludes
internet exposure. The user has now authorized an external endpoint in addition
to the loopback candidate. The standard-library demo has no authentication or TLS
and accepts a strict Host allowlist. Publishing its container directly would
either reject `sfuai.ca` or widen backend identity and operations unnecessarily.

This ADR narrowly supersedes ADR-0010's public-internet prohibition only for the
read-only candidate at `sfuai.ca:8007` under the controls and limitations below.
ADR-0010 remains authoritative for every other deployment and capability.

## Decision

Keep the application container and its `127.0.0.1:18007` publication unchanged.
Add a dedicated nginx edge service to the same candidate Compose project. Publish
only that edge on `0.0.0.0:8007`. It accepts `Host: sfuai.ca`, rejects other Host
values, forwards a fixed `Host: demo` over the private candidate network, and does
not pass client-controlled forwarding identity headers.

The proxy image is pinned by digest, runs as an unprivileged user with a read-only
root filesystem and bounded Docker logs, and writes temporary state only to tmpfs.
Its access log records remote address, time, method, normalized URI, status, byte
count and duration; it omits query strings, bodies and headers. The backend's
existing concurrency, request size, method/path allowlists, security headers and
rate limits remain authoritative. Because the backend sees the proxy address,
external users share its rate-limit bucket; this is an intentional protective
limit for this small read-only demo.

This endpoint is plain HTTP and has no authentication. It must not carry accounts,
credentials, private source data or mutations. DNS plus upstream firewall/NAT
forwarding remain environmental prerequisites. A future persistent or sensitive
service must move behind the established TLS ingress with explicit authentication,
proxy trust and monitoring rather than extending this exception.

## Rollback

Stop/remove the external proxy service or bind it to loopback, then recreate the
candidate project. Port 18007, the graph, GeoPackage and client remain unchanged.
