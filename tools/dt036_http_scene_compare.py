#!/usr/bin/env python3
"""Compare complete baseline and optimized scene HTTP bodies in Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from urllib.parse import quote, urlsplit
from urllib.request import urlopen


def origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"baseline", "demo", "localhost", "127.0.0.1"}
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise argparse.ArgumentTypeError("Use an isolated local demo origin.")
    return value.rstrip("/")


def fetch(base: str, path: str) -> tuple[bytes, float]:
    began = perf_counter()
    with urlopen(base + path, timeout=30) as response:
        if response.status != 200:
            raise AssertionError(f"Unexpected HTTP status {response.status}")
        body = response.read()
    return body, perf_counter() - began


def main() -> None:
    if not Path("/.dockerenv").exists():
        raise SystemExit("Run this comparison inside Docker.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=origin, default="http://baseline:8080")
    parser.add_argument("--candidate", type=origin, default="http://demo:8080")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to replace existing evidence.")
    result = {"status": "running", "container": os.environ.get("HOSTNAME"), "scenes": []}
    try:
        baseline_levels, _ = fetch(args.baseline, "/demo/v1/levels")
        candidate_levels, _ = fetch(args.candidate, "/demo/v1/levels")
        assert baseline_levels == candidate_levels, "Level catalog changed"
        for level in json.loads(baseline_levels)["levels"]:
            level_id = level["level_id"]
            path = f"/demo/v1/levels/{quote(level_id, safe='')}/scene"
            baseline, baseline_seconds = fetch(args.baseline, path)
            candidate, candidate_seconds = fetch(args.candidate, path)
            assert baseline == candidate, f"Complete HTTP scene changed: {level_id}"
            scene = json.loads(candidate)
            record = {
                "level_id": level_id,
                "response_sha256": hashlib.sha256(candidate).hexdigest(),
                "response_bytes": len(candidate),
                "baseline_seconds": baseline_seconds,
                "candidate_seconds": candidate_seconds,
                "counts": {key: len(scene[key]) for key in ("units", "details", "landmarks")},
            }
            result["scenes"].append(record)
            print(json.dumps(record), flush=True)
        result["status"] = "passed"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")


if __name__ == "__main__":
    main()
