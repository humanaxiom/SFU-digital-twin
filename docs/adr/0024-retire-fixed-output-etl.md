# 24. Retire fixed-output ETL commands

Status: Accepted for DT-033
Date: 2026-11-19

ADR-0011 introduced isolated builds and verified stage lineage. The older Make
and Python stage commands still target accepted artifact paths. An operator can
therefore change only one member of the artifact set, or lose the GeoPackage
when an extraction fails.

Use the existing rebuild launcher and a fresh run ID for all operator builds.
Reject legacy stage invocations before any data operation and direct callers to
the supported command. Candidates remain under build/experiments and retain
their own manifest. An existing run ID cannot authorize replacement.

This supersedes the individual stage invocation instructions in ADR-0006 and
earlier ETL tickets. The read-only source mount, separate source and artifact
capabilities, published image policy and topology contracts still apply.

For explicit library extraction, a caller supplies the output path. Preserve
an existing output until a complete replacement is available on the same
filesystem. Default extraction refuses to overwrite an existing file. The
isolated builder additionally reserves its own unused run directory before
invoking extraction.