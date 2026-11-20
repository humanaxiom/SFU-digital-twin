"""Retirement notice for the fixed-output ETL command."""

import sys


def main(command: str | None = None) -> int:
    """Direct legacy callers to a fresh isolated rebuild."""
    entry_point = f"wayfinding.etl.run {command}" if command else "wayfinding.etl.run"
    print(
        f"{entry_point!r} is retired. "
        "Use 'make etl RUN_ID=<unused-id>' for an isolated rebuild.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
