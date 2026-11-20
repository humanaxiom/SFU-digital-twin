# 21. Integrated public startup and recovery

Status: accepted for the user's explicit persistent-startup request
Date: 2026-10-08

ADR-0022 supersedes the public HTTP transport below with HTTPS in normal startup,
using an additional TLS overlay; this record's recovery/ownership controls remain.

The normal PowerShell and POSIX launchers also reconcile the fixed
sfudt-sh-navigation-candidate project using infra/wayfinding-public.env.
They print http://sfuai.ca:8017/ and wait for demo and external health. The existing
developer stack remains distinct and retains its project and ports on repeat
startup. A foreign process/project collision must not cause an existing stack to
be overwritten or duplicated. NoPublicDemo / --no-public-demo skips public
startup without stopping a running public service; dry-run mutates neither stack.

Use restart: unless-stopped for the candidate demo and external proxy. This
narrowly supersedes temporary-stop lifecycle assumptions in ADR-0010/0019:
the explicitly authorized public demo now recovers when Docker starts after a
reboot. Deliberate Compose stop/down continues to withdraw public access.
Docker Desktop itself must start at sign-in; container policies do not start it.
Do not combine container restart policies with a second host process supervisor.

ADR-0020's public 8017 → local 18087 and private 18107 ports, strict proxy Host
controls, readonly sources/artifacts and image selection remain unchanged.
Launcher failures are nonzero and never silently certify public availability.

Verification inspects live restart settings and exercises isolated process exit
recovery, repeat startup, browser/API and outside HTTP. This does not imply a
real host reboot was performed. See the official
[Docker restart policy contract](https://docs.docker.com/engine/containers/start-containers-automatically/).
