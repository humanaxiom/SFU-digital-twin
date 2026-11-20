#!/usr/bin/env python3
"""Prepare fixed DT-017 route replays for the real Docker browser/API gate."""

import argparse
import json
import math
from pathlib import Path

from dt017_geometry_audit import AQ3000, BASELINE, BASELINE_SEAL, FIDS, require
from wayfinding.demo.routing import RoutingService
from wayfinding.etl import rebuild

ARTIFACTS = (rebuild.GPKG, rebuild.CONTRACTED, rebuild.STATS)


def signature(result):
    if result["status"] != 200:
        return {"status": result["status"], "code": result["code"]}
    return {
        "status": result["status"],
        "distance_m": result["network_distance_m"],
        "levels": [visit["level_id"] for visit in result["guidance"]["visits"]],
        "transitions": [[edge["edge_id"], edge["mode"]] for edge in result["edges"]
                        if edge["mode"] != "pathway"],
        "affected_fids": sorted(FIDS.intersection(
            fid for edge in result["edges"] for fid in edge["original_feature_ids"]
        )),
    }


def browser_fixture(response):
    result = {key: response[key] for key in (
        "profile", "network_distance_m", "edge_ids", "edges", "steps", "provenance",
        "warnings", "geometries",
    )}
    for name in ("origin", "destination"):
        endpoint = dict(response[name])
        endpoint["node_id"] = endpoint.pop("anchor_node")
        result[name] = endpoint
    result["reachability"] = {
        "algorithm": response["reachability_algorithm"],
        "component_semantics": response["component_semantics"],
    }
    return result


def verify_affected(name, before, after, expected):
    before_status, before_distance, after_distance, fids = expected
    require(before["status"] == before_status and after["status"] == 200,
            f"Affected fixture {name} changed expected statuses: {before} -> {after}")
    if before_distance is not None:
        require(math.isclose(before["distance_m"], before_distance, abs_tol=1e-6),
                f"Affected fixture {name} changed historical distance: {before}")
    require(after["levels"] == [AQ3000] and not after["transitions"],
            f"Affected fixture {name} must stay on AQ3000")
    require(after["affected_fids"] == fids and math.isclose(
        after["distance_m"], after_distance, abs_tol=1e-6
    ), f"Affected fixture {name} changed pathway lineage or corrected distance: {after}")


def main():
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run this replay preparation in a Docker artifact-build container")
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    baseline_path, baseline_manifest = rebuild._load_historical(BASELINE)
    require(baseline_manifest["manifest_sha256"] == BASELINE_SEAL,
            "Historical run must match the reviewed DT-033 manifest seal")
    candidate_path, candidate_manifest = rebuild._load(args.candidate, "complete")
    require(candidate_manifest["source"] == baseline_manifest["source"], "Source identities differ")
    baseline, candidate = (RoutingService.from_artifacts(*(path / name for name in ARTIFACTS))
                           for path in (baseline_path, candidate_path))
    canonical = json.loads(
        (rebuild.REPO_ROOT / "docs/reports/DT-015-demo-routes.json").read_text(encoding="utf-8")
    )["fixtures"]
    requests = {
        name: (fixture["origin"]["unit_id"], fixture["destination"]["unit_id"], fixture["profile"])
        for name, fixture in canonical.items()
    }
    requests["strand_crossfloor"] = (
        "SFU_BURNABY_STRAND_1000_1036", "SFU_BURNABY_STRAND_3000_3050.1", "default",
    )
    affected = {}
    for profile in ("default", "elevator_only"):
        name = f"aq_multipart_gained_{profile}"
        requests[name] = (f"{AQ3000}_3012", f"{AQ3000}_305", profile)
        affected[name] = (409, None, 59.504457670781775, ["9332", "9333", "9356"])
    requests["aq_multipart_shorter"] = (f"{AQ3000}_306", f"{AQ3000}_3110", "default")
    affected["aq_multipart_shorter"] = (
        200, 95.83393715933627, 64.4825259749847, ["9346", "9353"],
    )
    report = {
        "version": "dt017-browser-fixtures-v1",
        "baseline_manifest_sha256": BASELINE_SEAL,
        "candidate_manifest_sha256": candidate_manifest["manifest_sha256"],
        "artifact_hashes": {Path(name).name: candidate_manifest["artifacts"][name]
                            for name in ARTIFACTS},
        "fixtures": {},
        "comparisons": {},
    }
    for name, request in requests.items():
        previous = baseline.route(*request)
        current = candidate.route(*request)
        before, after = signature(previous), signature(current)
        if name in affected:
            verify_affected(name, before, after, affected[name])
        else:
            require(current["status"] == 200 and previous["status"] == 200,
                    f"Established route {name} must be routable in both builds")
            require(
                before["levels"] == after["levels"]
                and before["transitions"] == after["transitions"],
                f"Established route {name} changed floor visits or transition modes",
            )
            require(math.isclose(before["distance_m"], after["distance_m"], abs_tol=1e-6),
                    f"Established route {name} changed distance: {before} -> {after}")
        origin, destination, profile = request
        options = candidate.route_options(origin, profile)
        require(any(item["unit_id"] == destination and item["availability"] == "connected"
                    for item in options["destinations"]),
                f"Established route {name} is absent in candidate route options")
        report["comparisons"][name] = {"baseline": before, "candidate": after}
        report["fixtures"][name] = browser_fixture(current)
    origin, destination, _profile = requests["strand_crossfloor"]
    request = {"origin": {"unit_id": origin}, "destination": {"unit_id": destination},
               "profile": "elevator_only"}
    rejection = candidate.route(origin, destination, request["profile"])
    require(signature(rejection) == {"status": 409, "code": "no_elevator_only_route"},
            "The Strand stairs route must fail in the elevator-only profile")
    report["rejected_route"] = {"request": request, "response": rejection}

    output = rebuild.EXPERIMENTS_ROOT / "reviews" / f"{args.candidate}-routes.json"
    rebuild._no_symlinks(output)
    output.parent.mkdir(exist_ok=True)
    rebuild._write_json(output, report)
    print(json.dumps({"output": str(output), "comparisons": report["comparisons"]}, indent=2))


if __name__ == "__main__":
    main()
