#!/usr/bin/env python3
"""Capture takeover evidence from paths mounted at ``/workspace``."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ARTIFACT_NAMES = (
    "wayfinding.gpkg",
    "graph_contracted.pkl",
    "graph_contracted_stats.json",
)
NOTE = "File-content identity, not approval. Consult docs/reports/CODEX-TAKEOVER.md."


def validate_workspace_path(path: str, workspace: Path) -> Path:
    """Resolve a repository-relative path and reject workspace escapes."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError(f"Path is not valid inside workspace: {path!r}")

    # Git emits POSIX separators, but reject Windows absolute/drive paths too.
    posix_path = PurePosixPath(path.replace("\\", "/"))
    windows_path = PureWindowsPath(path)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"Path escapes workspace: {path!r}")
    if ".." in posix_path.parts:
        raise ValueError(f"Path escapes workspace: {path!r}")

    root = workspace.resolve()
    candidate = (root / Path(*posix_path.parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace: {path!r}") from exc
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_entry(path_name: str, workspace: Path) -> dict[str, str | None]:
    path = validate_workspace_path(path_name, workspace)
    return {
        "path": path_name,
        "sha256": _sha256(path) if path.is_file() else None,
    }


def _artifact_entry(name: str, workspace: Path) -> dict[str, str]:
    path = validate_workspace_path(f"build/{name}", workspace)
    if not path.is_file():
        raise FileNotFoundError(f"Required artifact is unavailable: build/{name}")
    return {"name": name, "sha256": _sha256(path)}


def _manifest_bytes(files: list[dict[str, str | None]]) -> bytes:
    return json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _output_path(output: Path, workspace: Path) -> Path:
    if output.is_absolute():
        root = workspace.resolve()
        destination = output.resolve(strict=False)
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Output escapes workspace: {output!s}") from exc
        return destination
    return validate_workspace_path(str(output), workspace)


def write_manifest(
    *,
    head: str,
    statuses: Iterable[str],
    paths: Iterable[str],
    workspace: Path = Path("/workspace"),
    output: Path = Path("build/takeover-state.json"),
) -> Path:
    """Hash forwarded Git paths and accepted artifacts in the container."""
    root = workspace.resolve()
    files = [_file_entry(path, root) for path in sorted(set(paths))]
    manifest_hash = hashlib.sha256(_manifest_bytes(files)).hexdigest()
    artifacts = [_artifact_entry(name, root) for name in ARTIFACT_NAMES]
    state: dict[str, Any] = {
        "captured_at": datetime.now(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        ),
        "head": head,
        "status": list(statuses),
        "dirty_manifest_sha256": manifest_hash,
        "files": files,
        "artifacts": artifacts,
        "note": NOTE,
    }
    destination = _output_path(output, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(state, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", required=True)
    parser.add_argument("--status", action="append", default=[])
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--output", type=Path, default=Path("build/takeover-state.json"))
    args = parser.parse_args()
    try:
        destination = write_manifest(
            head=args.head,
            statuses=args.status,
            paths=args.path,
            workspace=args.workspace,
            output=args.output,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        parser.error(str(exc))
    state = json.loads(destination.read_text(encoding="utf-8"))
    print(f"Recorded {destination} ({state['dirty_manifest_sha256']})")


if __name__ == "__main__":
    main()
