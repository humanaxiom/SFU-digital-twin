#!/usr/bin/env python3
"""Write a snapshot-specific exclusion ledger for DT-017's unmapped revised pathways."""

import argparse
import csv
import json
from pathlib import Path


def write_exclusions(review: Path, output: Path) -> None:
    audit = json.loads(review.read_text(encoding="utf-8"))
    pathways = audit["layers"]["Pathways"]
    layer = pathways["source_layers"]["revised"]
    source_hash = audit["sources"]["revised"]["sha256"]
    added = pathways["changes"]["added"]
    missing = {
        row["fid"]: row
        for row in audit["diagnostics"]
        if row["snapshot"] == "revised" and row["layer"] == layer
    }
    if [row["fid"] for row in added] != list(range(22427, 22568)):
        raise ValueError("Added pathway inventory differs from the DT-017 reviewed snapshot")
    rows = []
    for feature in added:
        finding = missing.get(feature["fid"])
        required = {"missing_facility_id", "missing_level_id"}
        if (not finding or finding["fingerprint"] != feature["fingerprint"]
                or not required.issubset(finding["reasons"])):
            raise ValueError(f"Review the changed assignment evidence for FID {feature['fid']}")
        rows.append((source_hash, layer, feature["fid"], feature["fingerprint"],
                     "excluded", "", "", "|".join(finding["reasons"])))
    with output.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("source_sha256", "layer", "fid", "feature_sha256", "decision",
                         "assigned_facility_id", "assigned_level_id", "reasons"))
        writer.writerows(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_exclusions(args.review, args.output)
