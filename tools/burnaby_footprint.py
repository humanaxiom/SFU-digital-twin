#!/usr/bin/env python3
"""Screen the public SFU RoomFinder footprint for Burnaby building 038 (ASB)."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from wayfinding.overview_footprint import (
    FEATURE_QUERY,
    IDS_QUERY,
    MAX_BYTES,
    SOURCE,
    screen,
)


def _fetch(parameters):
    url = f"{SOURCE}?{urlencode(parameters)}"
    with urlopen(url, timeout=20) as reply:
        if reply.geturl() != url:
            raise ValueError("RoomFinder redirected the query")
        body = reply.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("RoomFinder response exceeded the size limit")
    result = json.loads(body)
    if not isinstance(result, dict) or "error" in result:
        raise ValueError("RoomFinder returned a query error")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="Fresh evidence file stem under /evidence")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.run_id):
        parser.error("run ID must be 1–64 lowercase ASCII letters, digits or hyphens")
    path = Path("/evidence") / f"{args.run_id}.json"
    if path.exists():
        parser.error(f"evidence already exists at {path}")
    try:
        ids_response = _fetch(IDS_QUERY)
        if ids_response.get("objectIdFieldName") != "OBJECTID":
            raise ValueError("RoomFinder returned an unexpected object ID field")
        if ids_response.get("exceededTransferLimit", False) is not False:
            raise ValueError("RoomFinder returned an incomplete object ID set")
        evidence = screen(_fetch(FEATURE_QUERY), ids_response.get("objectIds"))
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    except (RuntimeError, ValueError, OSError) as exc:
        parser.exit(1, f"Footprint screen failed: {exc}\n")
    print(json.dumps({"output": str(path), "screen_sha256": evidence["screen_sha256"]}))


if __name__ == "__main__":
    main()
