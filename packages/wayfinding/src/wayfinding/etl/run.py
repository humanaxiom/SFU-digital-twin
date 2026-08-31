"""ETL entry point — invoked by `make etl` or `make etl-extract`."""

from pathlib import Path


def main(command: str | None = None) -> int:
    """Execute the ETL pipeline.

    Supports commands:
    - extract: Extract layers from GDB to GeoPackage
    - (future): normalize, build-graph, index, etc.
    """
    if command is None:
        print("ETL infrastructure ready. No data processing yet (DT-003+).")
        print("Usage: python -m wayfinding.etl.run <command>")
        print("Commands:")
        print("  extract    Extract layers from GDB to GeoPackage")
        return 0

    if command == "extract":
        return run_extract()

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


if __name__ == "__main__":
    import sys

    cli_command = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(cli_command))
