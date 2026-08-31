"""Extract AIIM layers from FileGDB to GeoPackage with dual CRS.

This module handles the extraction of all seven AIIM layers (Facilities, Levels,
Units, Pathways, Transitions, Landmarks, Details) from the read-only source
File Geodatabase into a working GeoPackage.

Each layer is extracted twice:
- *_26910: Native EPSG:26910 (NAD83 / UTM zone 10N) with 3D geometry preserved
  for all metric computations (distance, snapping, routing costs)
- *_wgs84: Reprojected to EPSG:4326 (WGS84) with 2D geometry for web client display

The EPSG:26910 layers are the source of truth for all routing and spatial operations.
"""

import subprocess
from pathlib import Path
from typing import Literal

# Source layers from the AIIM geodatabase
SOURCE_LAYERS = [
    "Facilities_AQ_SH_ECC",
    "Levels_AQ_SH_ECC",
    "Units_AQ_SH_ECC",
    "Pathways_AQ_SH_ECC",
    "Transitions_AQ_SH_ECC",
    "Landmarks_AQ_SH_ECC",
    "Details_AQ_SH_ECC",
]

# Output layer names (without suffix)
BASE_LAYER_NAMES = [
    "Facilities",
    "Levels",
    "Units",
    "Pathways",
    "Transitions",
    "Landmarks",
    "Details",
]


def extract_to_gpkg(
    gdb_path: Path,
    gpkg_path: Path,
    overwrite: bool = False,
) -> dict[str, int]:
    """Extract all AIIM layers from FileGDB to GeoPackage with dual CRS.

    Creates 14 layers in the output GeoPackage:
    - 7 layers with _26910 suffix: native EPSG:26910, 3D geometry preserved
    - 7 layers with _wgs84 suffix: reprojected to EPSG:4326, 2D geometry

    Args:
        gdb_path: Path to source IndoorWayfinding.gdb (must exist, read-only)
        gpkg_path: Output GeoPackage path (will be created/overwritten)
        overwrite: If True, delete existing gpkg_path before extraction

    Returns:
        Dictionary mapping layer name to feature count for verification

    Raises:
        FileNotFoundError: If gdb_path does not exist
        RuntimeError: If ogr2ogr extraction fails for any layer
        PermissionError: If gdb_path is not readable or gpkg_path not writable
        FileExistsError: If gpkg_path exists and overwrite=False
    """
    if gpkg_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Output GeoPackage already exists: {gpkg_path}. "
                f"Use overwrite=True to replace it."
            )
        gpkg_path.unlink()

    if not gdb_path.exists():
        raise FileNotFoundError(f"Source GDB not found: {gdb_path}")
    if not gdb_path.is_dir():
        raise ValueError(f"GDB path must be a directory: {gdb_path}")

    gpkg_path.parent.mkdir(parents=True, exist_ok=True)

    feature_counts: dict[str, int] = {}

    for source_layer, base_name in zip(SOURCE_LAYERS, BASE_LAYER_NAMES, strict=True):
        # Extract to EPSG:26910 (native, 3D preserved)
        layer_26910 = f"{base_name}_26910"
        count_26910 = _extract_layer(
            gdb_path=gdb_path,
            gpkg_path=gpkg_path,
            source_layer=source_layer,
            target_layer=layer_26910,
            target_srs="EPSG:26910",
            dim="XYZ",
        )
        feature_counts[layer_26910] = count_26910

        # Extract to EPSG:4326 (reprojected, 2D)
        layer_wgs84 = f"{base_name}_wgs84"
        count_wgs84 = _extract_layer(
            gdb_path=gdb_path,
            gpkg_path=gpkg_path,
            source_layer=source_layer,
            target_layer=layer_wgs84,
            target_srs="EPSG:4326",
            dim="XY",
        )
        feature_counts[layer_wgs84] = count_wgs84

    return feature_counts


def _extract_layer(
    gdb_path: Path,
    gpkg_path: Path,
    source_layer: str,
    target_layer: str,
    target_srs: str,
    dim: Literal["XY", "XYZ"],
) -> int:
    """Extract a single layer using ogr2ogr.

    Args:
        gdb_path: Source FileGDB path
        gpkg_path: Target GeoPackage path
        source_layer: Name of layer in source GDB
        target_layer: Name of layer in target GPKG
        target_srs: Target spatial reference (e.g., "EPSG:26910", "EPSG:4326")
        dim: Coordinate dimension ("XY" for 2D, "XYZ" for 3D)

    Returns:
        Number of features in the extracted layer

    Raises:
        RuntimeError: If ogr2ogr command fails
    """
    # Build ogr2ogr command
    cmd = ["ogr2ogr", "-f", "GPKG"]

    # If GPKG exists, update it; otherwise create new
    if gpkg_path.exists():
        cmd.extend(["-update", "-append"])

    cmd.extend(
        [
            "-nln",
            target_layer,
            "-t_srs",
            target_srs,
            "-dim",
            dim,
            str(gpkg_path),
            str(gdb_path),
            source_layer,
        ]
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ogr2ogr failed for layer {source_layer} -> {target_layer}:\n"
            f"Command: {' '.join(cmd)}\n"
            f"Exit code: {result.returncode}\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )

    return _count_features(gpkg_path, target_layer)


def _count_features(gpkg_path: Path, layer_name: str) -> int:
    """Count features in a GeoPackage layer using ogrinfo.

    Args:
        gpkg_path: Path to GeoPackage
        layer_name: Name of layer to count

    Returns:
        Number of features in the layer

    Raises:
        RuntimeError: If ogrinfo command fails
    """
    cmd = ["ogrinfo", "-so", str(gpkg_path), layer_name]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ogrinfo failed to count features in {layer_name}:\n"
            f"stderr: {result.stderr}"
        )

    # Parse feature count from output
    # Expected line: "Feature Count: 1210"
    # Combine stdout and stderr since ogrinfo may output to either
    output = result.stdout + result.stderr
    for line in output.splitlines():
        if "Feature Count:" in line:
            count_str = line.split(":")[-1].strip()
            return int(count_str)

    raise RuntimeError(
        f"Could not parse feature count from ogrinfo output for {layer_name}:\n"
        f"{output}"
    )
