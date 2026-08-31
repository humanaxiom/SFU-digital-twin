"""ETL entry point — invoked by `make etl` or `make etl-extract`."""

import logging
from pathlib import Path

# Configure logging for ETL operations
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main(command: str | None = None) -> int:
    """Execute the ETL pipeline.

    Supports commands:
    - extract: Extract layers from GDB to GeoPackage
    - normalise: Normalise extracted layers into production tables
    - graph-raw: Snap nodes and build raw pathway graph
    - graph-transitions: Add transition edges to pathway graph
    """
    if command is None:
        print("ETL infrastructure ready. No data processing yet (DT-003+).")
        print("Usage: python -m wayfinding.etl.run <command>")
        print("Commands:")
        print("  extract            Extract layers from GDB to GeoPackage")
        print("  normalise          Normalise extracted layers into production tables")
        print("  graph-raw          Snap nodes and build raw pathway graph")
        print("  graph-transitions  Add transition edges to pathway graph")
        return 0

    if command == "extract":
        return run_extract()

    if command == "normalise":
        return run_normalise()

    if command == "graph-raw":
        return run_graph_raw()

    if command == "graph-transitions":
        return run_graph_transitions()

    print(f"Unknown command: {command}")
    return 1


def run_extract() -> int:
    """Run the extraction step."""
    from wayfinding.etl.extract import extract_to_gpkg

    gdb_path = Path("/data/IndoorWayfinding.gdb")
    gpkg_path = Path("/workspace/build/wayfinding.gpkg")

    print(f"Extracting layers from {gdb_path}...")
    print(f"Output: {gpkg_path}")

    try:
        feature_counts = extract_to_gpkg(
            gdb_path=gdb_path,
            gpkg_path=gpkg_path,
            overwrite=True,
        )

        print("\nExtraction complete!")
        print("\nFeature counts by layer:")
        for layer_name, count in sorted(feature_counts.items()):
            print(f"  {layer_name:30s} {count:6d} features")

        total_features = sum(feature_counts.values())
        print(f"\nTotal: {total_features} features across {len(feature_counts)} layers")

        return 0
    except Exception as error:
        import traceback

        print(f"\nERROR: Extraction failed: {error}")
        traceback.print_exc()
        return 1


def run_normalise() -> int:
    """Run the normalisation step."""
    import yaml

    from wayfinding.etl.normalise import (
        normalise_details,
        normalise_facilities,
        normalise_landmarks,
        normalise_levels,
        normalise_units,
    )

    gpkg_path = Path("/workspace/build/wayfinding.gpkg")
    category_yaml_path = Path(
        "/workspace/packages/wayfinding/src/wayfinding/etl/category_mapping.yaml"
    )

    print(f"Normalising layers in {gpkg_path}...")
    print(f"Category mapping: {category_yaml_path}")

    if not gpkg_path.exists():
        print(f"\nERROR: GeoPackage not found: {gpkg_path}")
        print("Run 'make etl-extract' first to create the working GeoPackage.")
        return 1

    if not category_yaml_path.exists():
        print(f"\nERROR: Category mapping not found: {category_yaml_path}")
        return 1

    try:
        # Load category mapping
        with open(category_yaml_path) as f:
            category_mapping = yaml.safe_load(f)

        print("\nStep 1/5: Normalising facilities...")
        facility_count = normalise_facilities(gpkg_path)
        print(f"  Created {facility_count} facilities")

        print("\nStep 2/5: Normalising levels...")
        level_count = normalise_levels(gpkg_path)
        print(f"  Created {level_count} levels")

        print("\nStep 3/5: Normalising units...")
        unit_count = normalise_units(gpkg_path, category_mapping)
        print(f"  Created {unit_count} searchable units")

        print("\nStep 4/5: Normalising landmarks...")
        landmark_count = normalise_landmarks(gpkg_path)
        print(f"  Created {landmark_count} landmarks (deduplicated)")

        print("\nStep 5/5: Normalising details and doors...")
        detail_door_counts = normalise_details(gpkg_path)
        print(f"  Created {detail_door_counts['detail']} detail features")
        print(f"  Created {detail_door_counts['door']} door features")

        print("\nNormalisation complete!")
        print("\nTable counts:")
        print(f"  facility:  {facility_count:6d}")
        print(f"  level:     {level_count:6d}")
        print(f"  unit:      {unit_count:6d}")
        print(f"  landmark:  {landmark_count:6d}")
        print(f"  detail:    {detail_door_counts['detail']:6d}")
        print(f"  door:      {detail_door_counts['door']:6d}")

        total_normalised = (
            facility_count + level_count + unit_count + landmark_count +
            detail_door_counts['detail'] + detail_door_counts['door']
        )
        print(f"\nTotal normalised records: {total_normalised}")
        print("Total layers in GeoPackage: 26 (14 raw + 12 normalised dual-CRS)")

        return 0
    except Exception as error:
        import traceback

        print(f"\nERROR: Normalisation failed: {error}")
        traceback.print_exc()
        return 1


def run_graph_raw() -> int:
    """Run the graph-raw step: snap nodes and build raw pathway graph."""
    from wayfinding.etl.graph import run_graph_raw

    output_dir = Path("/workspace/build")

    print("=== DT-005: Graph Node Snapping and Raw Graph Construction ===")
    print(f"Output directory: {output_dir}")

    try:
        return run_graph_raw(output_dir)
    except Exception as error:
        import traceback

        print(f"\nERROR: Graph construction failed: {error}")
        traceback.print_exc()
        return 1


def run_graph_transitions() -> int:
    """Run the graph-transitions step: add transition edges to pathway graph."""
    from wayfinding.etl.graph import run_graph_transitions

    output_dir = Path("/workspace/build")

    print("=== DT-006: Add Transition Edges to Graph ===")
    print(f"Output directory: {output_dir}")

    try:
        return run_graph_transitions(output_dir)
    except Exception as error:
        import traceback

        print(f"\nERROR: Adding transitions failed: {error}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    cli_command = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(cli_command))
