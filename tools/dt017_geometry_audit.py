#!/usr/bin/env python3
"""Compare DT-033 and DT-017 geometry from verified Docker build artifacts."""

import argparse
import json
import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path

from osgeo import ogr
from shapely import wkt
from wayfinding.etl import rebuild
from wayfinding.etl.build_semantics import compare_snapshots

BASELINE = "dt033-final-20261119"
BASELINE_SEAL = "43927257561497a4d3473b63ebb42a64fe7fe325cfb8e1c1f7ead160069fc274"
FIDS = {"9321", "9328", "9332", "9333", "9346", "9347", "9348", "9352", "9353", "9354", "9356"}
RETAINED = {"9332", "9333", "9346", "9347"}
AQ3000 = "SFU_BURNABY_QUAD_3000"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pathway_records(path, layer_name, selected=None, *, legacy_wkt=False):
    source = ogr.Open(str(path), 0)
    layer = source.GetLayerByName(layer_name)
    features = layer if selected is None else (layer.GetFeature(int(fid)) for fid in selected)
    records = {}
    for feature in features:
        geometry = feature.GetGeometryRef()
        parts = (
            [geometry.GetGeometryRef(index) for index in range(geometry.GetGeometryCount())]
            if geometry.GetGeometryName() == "MULTILINESTRING" else [geometry]
        )
        fid = str(feature.GetFID())
        records[fid] = {
            "level_id": (feature.GetField("LEVEL_ID")
                         if feature.GetFieldIndex("LEVEL_ID") >= 0 else None),
            "facility_id": feature.GetField("FACILITY_ID"),
            "length_3d": feature.GetField("LENGTH_3D"),
            "parts": [tuple(part.GetPoints()) for part in parts],
        }
        if legacy_wkt:
            rounded = wkt.loads(geometry.ExportToWkt())
            rounded_parts = rounded.geoms if rounded.geom_type == "MultiLineString" else [rounded]
            records[fid]["legacy_wkt"] = [tuple(part.coords) for part in rounded_parts]
    return records


def load_graph(path, name):
    # Called only after checking the retained DT-033 digest or current run ledger.
    with (path / name).open("rb") as stream:
        return pickle.load(stream)


def segments(points):
    return list(zip(points, points[1:], strict=False))


def undirected(segment):
    return tuple(sorted(segment))


def source_segments(record):
    return Counter(undirected(segment) for part in record["parts"] for segment in segments(part))


def historical_segments(record):
    parts = {**record, "parts": record["legacy_wkt"]}
    return source_segments(parts)


def metric(points):
    return math.fsum(math.dist(*segment) for segment in segments(points))


def edge_record(u, v, key, data):
    points = list(data["geometry"].coords)
    return {
        "edge_id": key,
        "from": u,
        "to": v,
        "length_3d": data["length_3d"],
        "geometry_length_3d": metric(points),
        "geometry": points,
        "source_spans": data.get("source_spans", []),
    }


def relevant_edges(graph, *, contracted):
    by_fid = defaultdict(list)
    for u, v, key, data in graph.edges(keys=True, data=True):
        if data["mode"] != "pathway" or key.endswith("_R"):
            continue
        ids = (
            data["original_feature_ids"] if contracted
            else [str(data.get("source_feature_id", data["feature_id"]))]
        )
        for fid in FIDS.intersection(ids):
            by_fid[fid].append(edge_record(u, v, key, data))
    return dict(sorted(by_fid.items()))


def audit_raw(graph, source, candidate):
    by_fid = relevant_edges(graph, contracted=False)
    if candidate:
        require(set(by_fid) == FIDS, "Candidate does not restore all 11 source FIDs")
    else:
        require(set(by_fid) == RETAINED, "DT-033 raw pathway inclusion unexpectedly differs")
    for fid, edges in by_fid.items():
        expected = source_segments(source[fid])
        observed = Counter(
            undirected(segment) for edge in edges for segment in segments(edge["geometry"])
        )
        calculated = math.fsum(edge["geometry_length_3d"] for edge in edges)
        cost = math.fsum(edge["length_3d"] for edge in edges)
        if candidate:
            require(observed == expected, f"Raw candidate segment multiset differs for FID {fid}")
            require(math.isclose(cost, calculated, rel_tol=1e-9, abs_tol=1e-6),
                    f"Raw candidate route weight differs from 3D geometry for FID {fid}")
            require(math.isclose(cost, source[fid]["length_3d"], rel_tol=0.005, abs_tol=0.05),
                    f"Raw candidate route weight differs materially from source for FID {fid}")
            for edge in edges:
                reverse = graph.edges[edge["to"], edge["from"], edge["edge_id"] + "_R"]
                require(list(reverse["geometry"].coords) == edge["geometry"][::-1]
                        and reverse["length_3d"] == edge["length_3d"],
                        f"Reverse pathway arc differs for FID {fid}")
        foreign = observed - (expected if candidate else historical_segments(source[fid]))
        by_fid[fid] = {
            "edges": edges,
            "unsupported_segments": [segment for segment, count in foreign.items()
                                     for _ in range(count)],
            "unsupported_segment_count": foreign.total(),
            "weight_minus_geometry_m": cost - calculated,
        }
    return by_fid


def points_for_span(span, source):
    fid = str(span["feature_id"])
    part = source[fid]["parts"][span["part_index"]]
    start, end = span["start_vertex"], span["end_vertex"]
    require(0 <= start < len(part) and 0 <= end < len(part) and start != end,
            f"Invalid source span for FID {fid}: {span}")
    return part[start:end + 1] if start < end else part[end:start + 1][::-1]


def audit_contracted(graph, source, transitions, candidate):
    forward_pathways = 0
    unsupported = Counter()
    missing_spans = []
    weight_disagreements = []
    transition_disagreements = []
    transition_unsupported = Counter()
    retained_affected = defaultdict(Counter)
    for _u, _v, key, data in graph.edges(keys=True, data=True):
        if key.endswith("_R"):
            continue
        points = list(data["geometry"].coords)
        calculated = metric(points)
        error = data["length_3d"] - calculated
        if data["mode"] != "pathway":
            if abs(error) > 0.05:
                transition_disagreements.append({"edge_id": key, "weight_minus_geometry_m": error})
            transition = transitions[str(data["feature_id"])]
            actual = Counter(undirected(segment) for segment in segments(points))
            extra = actual - historical_segments(transition)
            if extra:
                transition_unsupported[key] = extra.total()
            continue
        forward_pathways += 1
        if abs(error) > 0.05:
            weight_disagreements.append({"edge_id": key, "weight_minus_geometry_m": error})
        actual = segments(points)
        if candidate:
            if not data.get("source_spans_complete"):
                missing_spans.append(key)
                continue
            expected = []
            for span in data["source_spans"]:
                source_segments_in_span = segments(points_for_span(span, source))
                expected.extend(source_segments_in_span)
                if span["feature_id"] in FIDS:
                    retained_affected[span["feature_id"]].update(
                        undirected(segment) for segment in source_segments_in_span
                    )
            require(actual == expected, f"Contracted candidate has non-source geometry in {key}")
            if FIDS.intersection(data["original_feature_ids"]):
                require(math.isclose(data["length_3d"], calculated, rel_tol=1e-9, abs_tol=1e-6),
                        f"Affected contracted pathway weight differs from geometry in {key}")
        else:
            available = set().union(*(
                source_segments(source[fid]).keys() | historical_segments(source[fid]).keys()
                for fid in data["original_feature_ids"]
            ))
            for segment in actual:
                if undirected(segment) not in available:
                    unsupported[key] += 1
    require(not missing_spans, f"Missing candidate pathway spans: {missing_spans}")
    if candidate:
        require(not transition_unsupported,
                f"Candidate has unsupported transition segments: {transition_unsupported}")
        for fid, actual in retained_affected.items():
            require(actual == source_segments(source[fid]),
                    f"Contracted candidate segment multiset differs for FID {fid}")
        require(set(retained_affected) == FIDS, "Candidate contraction lost affected FIDs")
    return {
        "forward_pathway_edges": forward_pathways,
        "unsupported_pathway_segments": unsupported.total(),
        "unsupported_pathway_edges": dict(sorted(unsupported.items())),
        "pathway_weight_disagreements_over_0_05m": weight_disagreements,
        "transition_weight_disagreements_over_0_05m": transition_disagreements,
        "unsupported_transition_segments": dict(sorted(transition_unsupported.items())),
        "verified_affected_source_segment_counts": {
            fid: counts.total() for fid, counts in sorted(retained_affected.items())
        },
        "affected": relevant_edges(graph, contracted=True),
    }


def stats(snapshot):
    return {
        **{key: snapshot[key] for key in ("graph_sha256", "units_sha256", "anchors_sha256",
                                         "node_count", "edge_count", "unit_count",
                                         "eligible_unit_count")},
        "profiles": {profile: {key: value for key, value in metrics.items() if key != "groups"}
                     for profile, metrics in snapshot["profiles"].items()},
    }


def main():
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run this audit in a Docker source-build container")
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    baseline_path, baseline_manifest = rebuild._load_historical(BASELINE)
    require(baseline_manifest["manifest_sha256"] == BASELINE_SEAL,
            "Historical run must match the reviewed DT-033 manifest seal")
    candidate_path, candidate_manifest = rebuild._load(args.candidate, "complete")
    require(candidate_manifest["source"] == baseline_manifest["source"],
            "Baseline and candidate source metadata differ")
    require(rebuild.hash_directory(rebuild.SOURCE_PATH)["sha256"] == rebuild.LEGACY_SHA256,
            "Mounted immutable source differs from the reviewed input")
    source = pathway_records(rebuild.SOURCE_PATH, "Pathways_AQ_SH_ECC", FIDS)
    pairs = (("baseline", baseline_path, baseline_manifest),
             ("candidate", candidate_path, candidate_manifest))
    report = {
        "version": "dt017-geometry-audit-v1",
        "crs": "EPSG:26910",
        "source": source,
        "scope": "Segment membership and graph routing from the immutable legacy source",
    }
    require(all(row["level_id"] == AQ3000 for row in source.values()),
            "Affected source FIDs must have recorded AQ3000 level identity")
    snapshots = []
    for name, path, manifest in pairs:
        for relative in (rebuild.RAW, rebuild.GPKG):
            require(pathway_records(path / relative, "Pathways_26910", FIDS) == source,
                    f"{name} extraction or normalization changed source FIDs or XYZ in {relative}")
        all_pathways = pathway_records(path / rebuild.RAW, "Pathways_26910",
                                       legacy_wkt=(name == "baseline"))
        transitions = pathway_records(path / rebuild.RAW, "Transitions_26910", legacy_wkt=True)
        raw = load_graph(path, rebuild.RAW_GRAPH)
        contracted = load_graph(path, rebuild.CONTRACTED)
        snapshot = json.loads((path / rebuild.SEMANTICS).read_text())
        snapshots.append(snapshot)
        report[name] = {
            "run_id": manifest["run_id"],
            "manifest_sha256": manifest["manifest_sha256"],
            "code_sha256": manifest["runtime"]["code_sha256"],
            "image_id": manifest["runtime"]["image_id"],
            "source": manifest["source"],
            "artifacts": manifest["artifacts"],
            "raw_graph_size": {"nodes": raw.number_of_nodes(), "edges": raw.number_of_edges()},
            "run_json_sha256": rebuild._sha(path / "run.json"),
            "raw": audit_raw(raw, all_pathways, candidate=(name == "candidate")),
            "contracted": audit_contracted(
                contracted, all_pathways, transitions, candidate=(name == "candidate")
            ),
            "semantics": stats(snapshot),
        }
    report["comparison"] = compare_snapshots(*snapshots)
    changed_anchors = {}
    for uid in report["comparison"]["changed_anchor_unit_ids"]:
        before, after = (snapshot["anchors"][uid] for snapshot in snapshots)
        fields = ("anchor_node", "attachment_distance_m", "eligible", "level_id")
        if any(before.get(key) != after.get(key) for key in fields):
            changed_anchors[uid] = [{key: current.get(key) for key in fields}
                                    for current in (before, after)]
    report["anchor_attachment_changes"] = changed_anchors
    output = rebuild.EXPERIMENTS_ROOT / "reviews" / f"{args.candidate}-geometry.json"
    rebuild._no_symlinks(output)
    output.parent.mkdir(exist_ok=True)
    rebuild._write_json(output, report)
    print(json.dumps({
        "output": str(output),
        "historical_raw_extra_segments": sum(item["unsupported_segment_count"]
                                              for item in report["baseline"]["raw"].values()),
        "baseline_contracted_extra_segments": report["baseline"]["contracted"][
            "unsupported_pathway_segments"],
        "candidate_contracted_pathways_checked": report["candidate"]["contracted"][
            "forward_pathway_edges"],
        "anchor_attachment_changes": len(changed_anchors),
        "profiles": report["comparison"]["profiles"],
    }, indent=2))


if __name__ == "__main__":
    main()
