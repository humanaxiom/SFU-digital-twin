"""Isolated, staged rebuild of the reviewed legacy source; never promotes outputs."""

import argparse
import hashlib
import json
import os
import pickle
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import rfc8785
import yaml
from osgeo import gdal

from wayfinding.demo.routing import _units_from_gpkg
from wayfinding.etl import graph, normalise
from wayfinding.etl.build_semantics import compare_snapshots, semantic_snapshot
from wayfinding.etl.extract import extract_to_gpkg
from wayfinding.etl.source_review import hash_directory
from wayfinding.etl.topology import DEFAULT_MODE, ENDPOINT_MODE, EXACT_MODE, TOPOLOGY_MODES

REPO_ROOT = Path(__file__).resolve().parents[5]
EXPERIMENTS_ROOT = REPO_ROOT / "build/experiments"
SOURCE_PATH = Path("/source/IndoorWayfinding.gdb")
LEGACY_SHA256 = "8710ab93e5c66c8a442f8db2baa4e7efb2c77ea46006e5d301c63796c332f07e"
RAW = "raw/wayfinding.gpkg"
GPKG = "derived/wayfinding.gpkg"
RAW_GRAPH = "derived/graph_raw.pkl"
NODE_MAP = "derived/node_map.pkl"
TRANSITIONS = "derived/graph_with_transitions.pkl"
CONTRACTED = "derived/graph_contracted.pkl"
STATS = "derived/graph_contracted_stats.json"
SEMANTICS = "semantic-snapshot.json"
STAGES = [
    ("extract", ["@source"], [RAW]),
    ("normalise", [RAW], [GPKG]),
    ("graph-raw", [GPKG], [RAW_GRAPH, NODE_MAP, "derived/graph_raw_stats.json"]),
    ("graph-transitions", [GPKG, RAW_GRAPH, NODE_MAP],
     [TRANSITIONS, "derived/graph_with_transitions_stats.json"]),
    ("graph-contract", [GPKG, TRANSITIONS], [CONTRACTED, STATS]),
    ("semantics", [GPKG, CONTRACTED, STATS], [SEMANTICS]),
]


def _stages(manifest: dict[str, Any]) -> list[Any]:
    stages = list(STAGES)
    if manifest.get("build_config", {}).get("topology_mode", ENDPOINT_MODE) == EXACT_MODE:
        name, inputs, outputs = stages[2]
        stages[2] = (name, inputs, [*outputs, "derived/topology_audit.json"])
    return stages


def _digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _no_symlinks(path: Path) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError(f"symlink path is forbidden: {path}")


def _run_path(run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id, flags=re.ASCII):
        raise ValueError("Invalid run ID; use 1–64 ASCII letters, digits, underscores or hyphens")
    # Reserve utility directories and case-insensitive aliases on Windows bind mounts.
    if run_id.casefold() in {"reviews", "comparisons"}:
        raise ValueError("Reserved run ID")
    root = EXPERIMENTS_ROOT
    _no_symlinks(root)
    path = root / run_id
    _no_symlinks(path)
    if path.resolve().parent != root.resolve():
        raise ValueError("Run path escapes experiments root")
    return path


def _file(run: Path, relative: str) -> Path:
    if "\\" in relative or Path(relative).is_absolute():
        raise ValueError("Invalid artifact path")
    path = run / relative
    _no_symlinks(path)
    if not path.resolve().is_relative_to(run.resolve()) or path.resolve() == run.resolve():
        raise ValueError("Artifact path escapes run")
    return path


def _sha(path: Path) -> str:
    _no_symlinks(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def runtime_identity() -> dict[str, Any]:
    """Record launcher-inspected image identity and exact relevant code bytes."""
    image_id = os.environ.get("WAYFINDING_BUILD_IMAGE_ID", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Use the Docker rebuild launcher to supply the inspected image ID")
    code_paths = sorted((REPO_ROOT / "packages/wayfinding/src/wayfinding").rglob("*.py"))
    code_paths.extend([
        Path(__file__).parent / "category_mapping.yaml",
        REPO_ROOT / "infra/requirements.lock",
    ])
    code = {path.relative_to(REPO_ROOT).as_posix(): _sha(path) for path in code_paths}
    return {
        "image_id": image_id,
        "image_reference": os.environ.get("WAYFINDING_BUILD_IMAGE_REFERENCE", "unreported"),
        "python": sys.version.split()[0],
        "gdal": gdal.VersionInfo("--version"),
        "code_sha256": _digest(code),
        "code_files": code,
    }


def _write_json(path: Path, value: dict[str, Any], *, replace: bool = False) -> None:
    _no_symlinks(path)
    content = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        return
    temporary = path.with_name(path.name + ".tmp")
    _no_symlinks(temporary)
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(content)
    temporary.replace(path)


def _checkpoint(run: Path, manifest: dict[str, Any]) -> None:
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _digest(manifest)
    _write_json(run / "run.json", manifest, replace=(run / "run.json").exists())


def _verify_chain(run: Path, manifest: dict[str, Any]) -> None:
    ledger = {"@source": manifest["source"]["sha256"]}
    stages = manifest["stages"]
    if len(stages) > len(STAGES):
        raise ValueError("Unexpected stage ledger")
    for stage, (name, inputs, outputs) in zip(stages, _stages(manifest), strict=False):
        if stage["name"] != name or stage["inputs"] != {key: ledger[key] for key in inputs}:
            raise ValueError("Stage input lineage mismatch")
        if set(stage["outputs"]) != set(outputs):
            raise ValueError("Stage output lineage mismatch")
        for key, digest in stage["outputs"].items():
            if _sha(_file(run, key)) != digest:
                raise ValueError(f"Artifact hash mismatch: {key}")
            ledger[key] = digest
    ledger.pop("@source")
    if ledger != manifest["artifacts"]:
        raise ValueError("Artifact ledger mismatch")


def _load(run_id: str, state: str) -> tuple[Path, dict[str, Any]]:
    run = _run_path(run_id)
    manifest = json.loads(_file(run, "run.json").read_text(encoding="utf-8"))
    seal = manifest.pop("manifest_sha256", None)
    if seal != _digest(manifest):
        raise ValueError("Manifest hash mismatch")
    manifest["manifest_sha256"] = seal
    if (manifest.get("schema_version") != 1 or manifest.get("run_id") != run_id
            or manifest.get("path_base") != "run_directory"):
        raise ValueError("Manifest identity mismatch")
    if manifest.get("state") != state:
        raise ValueError(f"Expected state {state}, got {manifest.get('state')}")
    config = manifest.get("build_config", {"topology_mode": ENDPOINT_MODE})
    if set(config) != {"topology_mode"} or config["topology_mode"] not in TOPOLOGY_MODES:
        raise ValueError("Invalid sealed build configuration")
    if state == "complete" and manifest.get("source_reverified") is not True:
        raise ValueError("Complete state requires final source verification")
    if manifest.get("runtime") != runtime_identity():
        raise ValueError("Build code or toolchain changed between stages")
    if manifest["source"]["sha256"] != LEGACY_SHA256:
        raise ValueError("Unreviewed source snapshot")
    expected_count = 1 if state == "extracted" else len(STAGES)
    if len(manifest["stages"]) != expected_count:
        raise ValueError("Incomplete stage ledger")
    _verify_chain(run, manifest)
    return run, manifest


def _stage(run: Path, manifest: dict[str, Any], operation: Callable[[], None]) -> None:
    if runtime_identity() != manifest["runtime"]:
        raise ValueError("Build code or toolchain changed before stage")
    name, inputs, outputs = _stages(manifest)[len(manifest["stages"])]
    ledger = {"@source": manifest["source"]["sha256"], **manifest["artifacts"]}
    consumed = {key: ledger[key] for key in inputs}
    for key, digest in consumed.items():
        if key != "@source" and _sha(_file(run, key)) != digest:
            raise ValueError(f"Input hash mismatch before {name}: {key}")
    for key in outputs:
        if _file(run, key).exists():
            raise FileExistsError(f"Stage output already exists: {key}")
    operation()
    if runtime_identity() != manifest["runtime"]:
        raise ValueError("Build code or toolchain changed during stage")
    for key, digest in consumed.items():
        if key != "@source" and _sha(_file(run, key)) != digest:
            raise ValueError(f"Input changed during {name}: {key}")
    produced = {key: _sha(_file(run, key)) for key in outputs}
    manifest["stages"].append({"name": name, "inputs": consumed, "outputs": produced})
    manifest["artifacts"].update(produced)
    _checkpoint(run, manifest)


def _failed(run: Path, manifest: dict[str, Any], error: Exception) -> None:
    manifest["state"] = "failed"
    manifest["failure"] = {"type": type(error).__name__, "message": str(error)}
    _checkpoint(run, manifest)


def extract_run(run_id: str, topology_mode: str = DEFAULT_MODE) -> Path:
    if topology_mode not in TOPOLOGY_MODES:
        raise ValueError("Unsupported topology mode")
    run = _run_path(run_id)
    if run.exists():
        raise FileExistsError(f"Run already exists: {run}")
    runtime = runtime_identity()
    source = hash_directory(SOURCE_PATH)
    if source["sha256"] != LEGACY_SHA256:
        raise ValueError("Unreviewed source snapshot; builder accepts the verified legacy only")
    run.parent.mkdir(parents=True, exist_ok=True)
    run.mkdir(exist_ok=False)
    manifest: dict[str, Any] = {
        "schema_version": 1, "path_base": "run_directory", "run_id": run_id,
        "state": "extracting", "source": source, "runtime": runtime,
        "source_selection": "verified_legacy", "promotion": "not_promoted",
        "source_quality": "not_certified",
        "build_config": {"topology_mode": topology_mode},
        "stages": [], "artifacts": {},
    }
    _checkpoint(run, manifest)
    try:
        (run / "raw").mkdir()

        def extract() -> None:
            manifest["extracted_counts"] = extract_to_gpkg(
                gdb_path=SOURCE_PATH, gpkg_path=run / RAW, overwrite=False
            )

        _stage(run, manifest, extract)
        if hash_directory(SOURCE_PATH) != source:
            raise ValueError("Source changed during extraction")
        manifest["state"] = "extracted"
        _checkpoint(run, manifest)
    except Exception as error:
        _failed(run, manifest, error)
        raise
    return run


def _normalise(run: Path, manifest: dict[str, Any]) -> None:
    target = run / GPKG
    shutil.copyfile(run / RAW, target)
    mapping = yaml.safe_load((Path(__file__).parent / "category_mapping.yaml").read_text())
    counts = {
        "facility": normalise.normalise_facilities(target),
        "level": normalise.normalise_levels(target),
        "unit": normalise.normalise_units(target, mapping),
        "landmark": normalise.normalise_landmarks(target),
    }
    counts.update(normalise.normalise_details(target))
    manifest["normalized_counts"] = counts


def _graph_stage(function: Callable[[Path], int], run: Path) -> None:
    code = function(run / "derived")
    if code != 0:
        raise RuntimeError(f"Graph stage {function.__name__} failed with exit {code}")


def _semantic_stage(run: Path) -> None:
    # The stage ledger has just verified these internally produced trusted artifacts.
    with (run / CONTRACTED).open("rb") as stream:
        candidate_graph = pickle.load(stream)
    stats = json.loads((run / STATS).read_text())
    expected = {
        "inputs": sorted([
            {"path": "derived/graph_with_transitions.pkl", "sha256": _sha(run / TRANSITIONS)},
            {"path": "derived/wayfinding.gpkg", "sha256": _sha(run / GPKG)},
        ], key=lambda item: item["path"]),
        "outputs": [{"path": "derived/graph_contracted.pkl", "sha256": _sha(run / CONTRACTED)}],
    }
    if stats.get("lineage") != expected:
        raise ValueError("Contraction sidecar lineage mismatch")
    snapshot = semantic_snapshot(candidate_graph, _units_from_gpkg(run / GPKG))
    _write_json(run / SEMANTICS, snapshot)


def derive_run(run_id: str) -> Path:
    run, manifest = _load(run_id, "extracted")
    manifest["state"] = "deriving"
    _checkpoint(run, manifest)
    try:
        (run / "derived").mkdir()
        _stage(run, manifest, lambda: _normalise(run, manifest))
        topology_mode = manifest.get("build_config", {}).get("topology_mode", ENDPOINT_MODE)
        if topology_mode == ENDPOINT_MODE:
            # Legacy manifests may omit build_config. Pin their historical graph
            # behavior explicitly because run_graph_raw defaults to exact noding
            # for new standalone builds.
            _stage(
                run,
                manifest,
                lambda: _graph_stage(
                    lambda path: graph.run_graph_raw(path, topology_mode=ENDPOINT_MODE),
                    run,
                ),
            )
        else:
            def raw_graph() -> None:
                code = graph.run_graph_raw(run / "derived", topology_mode=topology_mode)
                if code != 0:
                    raise RuntimeError(f"Graph raw stage failed with exit {code}")
            _stage(run, manifest, raw_graph)
        _stage(run, manifest, lambda: _graph_stage(graph.run_graph_transitions, run))
        _stage(run, manifest, lambda: _graph_stage(graph.run_graph_contract, run))
        _stage(run, manifest, lambda: _semantic_stage(run))
        manifest["state"] = "derived"
        _checkpoint(run, manifest)
    except Exception as error:
        _failed(run, manifest, error)
        raise
    return run


def finalize_run(run_id: str) -> Path:
    run, manifest = _load(run_id, "derived")
    try:
        if hash_directory(SOURCE_PATH) != manifest["source"]:
            raise ValueError("Source changed before finalization")
        manifest["state"] = "complete"
        manifest["source_reverified"] = True
        manifest["limitations"] = [
            "Experimental legacy rebuild; no artifact promotion",
            "Completion verifies reconstruction and lineage, not source-data quality",
            "Approximate room anchors do not establish room-to-path traversability",
            "Elevator-only excludes stairs; accessibility remains unverified",
            "Revised pathways and supplemental survey data are not ingested",
        ]
        _checkpoint(run, manifest)
    except Exception as error:
        _failed(run, manifest, error)
        raise
    return run


def compare_runs(left: str, right: str) -> dict[str, Any]:
    if left.casefold() == right.casefold():
        raise ValueError("Comparison requires two distinct runs")
    left_path, left_manifest = _load(left, "complete")
    right_path, right_manifest = _load(right, "complete")
    left_snapshot = json.loads((left_path / SEMANTICS).read_text())
    right_snapshot = json.loads((right_path / SEMANTICS).read_text())
    comparison = compare_snapshots(left_snapshot, right_snapshot)
    comparison.update({
        "schema_version": 1, "left_run": left, "right_run": right,
        "left_manifest_sha256": left_manifest["manifest_sha256"],
        "right_manifest_sha256": right_manifest["manifest_sha256"],
        "source_equal": left_manifest["source"] == right_manifest["source"],
        "build_config_equal": (
            left_manifest.get("build_config") == right_manifest.get("build_config")
        ),
        "artifact_bytes_equal": left_manifest["artifacts"] == right_manifest["artifacts"],
        "promotion": "not_promoted",
    })
    folder = EXPERIMENTS_ROOT / "comparisons"
    _no_symlinks(folder)
    folder.mkdir(exist_ok=True)
    _write_json(folder / f"{left}--{right}.json", comparison)
    return comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("extract", "derive", "finalize"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--run-id", required=True)
        if command == "extract":
            subparser.add_argument("--topology", choices=TOPOLOGY_MODES, default=DEFAULT_MODE)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--left", required=True)
    compare.add_argument("--right", required=True)
    args = parser.parse_args(argv)
    try:
        if not Path("/.dockerenv").exists():
            raise ValueError("Build commands must run in Docker")
        if args.command == "compare":
            result = compare_runs(args.left, args.right)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["equivalent"] and result["source_equal"] else 1
        action = {"extract": extract_run, "derive": derive_run, "finalize": finalize_run}
        if args.command == "extract":
            print(extract_run(args.run_id, args.topology))
        else:
            print(action[args.command](args.run_id))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(f"Rebuild failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
