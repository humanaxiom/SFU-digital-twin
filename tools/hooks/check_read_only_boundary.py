#!/usr/bin/env python3
"""Docker-only PostToolUse diagnostic; never a write-prevention mechanism.

Only direct path fields are checked, lexically. No filesystem/source inspection,
shell-command interpretation, or symlink/junction resolution is performed.
Exit 0: direct paths outside known roots; 1: not assessed; 2: protected path found.
Neither exit 0 nor a hook runner's handling of these statuses certifies a safe write.
Runtime permissions and read-only mounts remain the actual boundary.
"""

import json
import ntpath
import posixpath
import sys

WINDOWS_ROOTS = (
    r"C:\repos\sfudt\claude\dtwin-harness",
    r"C:\repos\sfudt\dtwin-harness",
)
POSIX_ROOTS = ("/data/IndoorWayfinding.gdb",)
LIMITATIONS = (
    "PostToolUse cannot prevent or undo writes. This lexical diagnostic does not inspect "
    "shell commands or establish symlink/junction safety; use runtime permissions and "
    "read-only mounts."
)


def normalize_path(target: str, cwd: object) -> tuple[str, tuple[str, ...], str]:
    """Normalize Windows paths on Linux without touching the host filesystem."""
    if "\0" in target or target.startswith(("\\\\?\\", "\\\\.\\")):
        raise ValueError("unsupported path syntax")
    windows = bool(ntpath.splitdrive(target)[0] or "\\" in target)
    if not target.startswith("/") and isinstance(cwd, str) and ntpath.splitdrive(cwd)[0]:
        windows = True
    if windows:
        drive, tail = ntpath.splitdrive(target)
        if drive and not tail.startswith(("/", "\\")):
            raise ValueError("drive-relative path is ambiguous")
        if not drive:
            if not isinstance(cwd, str) or not ntpath.splitdrive(cwd)[0] or not ntpath.isabs(cwd):
                raise ValueError("relative Windows path requires an absolute Windows cwd")
            target = ntpath.join(cwd, target)
        return (
            ntpath.normcase(ntpath.normpath(target)),
            tuple(ntpath.normcase(ntpath.normpath(root)) for root in WINDOWS_ROOTS),
            "\\",
        )
    if not posixpath.isabs(target):
        if not isinstance(cwd, str) or not posixpath.isabs(cwd):
            raise ValueError("relative path requires an absolute cwd")
        target = posixpath.join(cwd, target)
    return posixpath.normpath(target), POSIX_ROOTS, "/"


def diagnostic(message: str, code: int) -> int:
    print(json.dumps({"systemMessage": f"{message} {LIMITATIONS}"}))
    return code


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return diagnostic("Paths not assessed: missing or malformed JSON payload.", 1)
    if not isinstance(event, dict) or not isinstance(event.get("tool_input"), dict):
        return diagnostic("Paths not assessed: expected a tool_input object.", 1)
    direct_paths = [
        event["tool_input"][key]
        for key in ("filePath", "path", "file_path")
        if key in event["tool_input"]
    ]
    if not direct_paths:
        return diagnostic("Paths not assessed: no supported direct path field.", 1)
    errors = []
    for target in direct_paths:
        if not isinstance(target, str) or not target.strip():
            errors.append("direct path must be a nonempty string")
            continue
        try:
            normalized, roots, separator = normalize_path(target, event.get("cwd"))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for root in roots:
            if normalized == root or normalized.startswith(root + separator):
                return diagnostic(f"Detected protected direct path: {target!r} (root {root!r}).", 2)
    if errors:
        return diagnostic(f"Paths not assessed: {'; '.join(errors)}.", 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
