#!/usr/bin/env python3
"""Measure trusted artifact scenes without changing source/artifact content."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from wayfinding.demo.artifact import ArtifactRepository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", default="/data/wayfinding.gpkg")
    parser.add_argument("--output", required=True)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        raise SystemExit("Run this benchmark inside Docker.")
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f"Refusing to replace evidence: {output}")
    started = perf_counter()
    repository = ArtifactRepository(args.artifact)
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "container": os.environ.get("HOSTNAME"),
        "artifact_sha256": repository.artifact_sha256,
        "repository_init_seconds": perf_counter() - started,
        "records": [],
    }
    levels = repository.levels()
    result["level_count"] = len(levels)
    for pass_number in range(1, args.passes + 1):
        for level in levels:
            began = perf_counter()
            scene = repository.scene(level["level_id"])
            scene_seconds = perf_counter() - began
            began = perf_counter()
            body = json.dumps(scene, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            serialization_seconds = perf_counter() - began
            canonical = json.dumps(scene, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True, allow_nan=False).encode("utf-8")
            record = {
                "pass": pass_number,
                "level_id": level["level_id"],
                "scene_seconds": scene_seconds,
                "serialization_seconds": serialization_seconds,
                "canonical_scene_sha256": hashlib.sha256(canonical).hexdigest(),
                "response_sha256": hashlib.sha256(body).hexdigest(),
                "response_bytes": len(body),
                "counts": {name: len(scene[name]) for name in ("units", "details", "landmarks")},
            }
            result["records"].append(record)
            print(json.dumps(record), flush=True)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
