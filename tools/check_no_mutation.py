#!/usr/bin/env python3
"""Fail if plugin Python source mutates config or the filesystem.

Hermes plugins must be read-only: observe and report, never write. This guard
scans the plugin's Python sources and exits non-zero when it finds filesystem
writes, config mutation, or mutating subprocesses — turning the read-only
contract into an enforced CI invariant rather than a convention.

Scanned: ``*.py`` under the repo root, excluding ``tools/`` (CI-time utilities;
the guard itself lives there and contains these patterns as regex literals).

Style and CI wiring mirror tools/check_self_claim.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Each entry is (label, regex). Deliberately conservative: a false positive
# costs a quick look at one line, while a false negative silently allows a
# write that a diagnostic plugin should never make.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "write-mode open()",
        # Mode string (2nd positional arg) containing a write flag: w, a, x,
        # or "+" (r+/w+/a+). Read-only "r"/"rb" do not match.
        re.compile(r"open\s*\(\s*[^,]+,\s*[\"'][^\"']*(?:w|a|x|\+)[^\"']*[\"']"),
    ),
    ("write-mode open(..., mode=...)", re.compile(r"open\s*\([^)]*mode\s*=\s*[\"'][^\"']*(?:w|a|x|\+)[^\"']*[\"']")),
    ("yaml.dump", re.compile(r"\byaml\.(?:safe_)?dump\b")),
    ("json.dump", re.compile(r"\bjson\.dump\b")),
    ("Path.write_text", re.compile(r"\.write_text\s*\(")),
    ("Path.write_bytes", re.compile(r"\.write_bytes\s*\(")),
    ("os.remove/unlink/rename/replace", re.compile(r"\bos\.(?:remove|unlink|rename|replace)\s*\(")),
    ("os.mkdir/makedirs", re.compile(r"\bos\.m(?:kdir|akedirs)\s*\(")),
    ("shutil mutation", re.compile(r"\bshutil\.(?:rmtree|move|copy2?|copyfile|copytree)\s*\(")),
    (
        "mutating subprocess (pip/install/uninstall)",
        re.compile(r"subprocess\.[a-z_]+\s*\([^)]*\b(?:pip|install|uninstall)\b", re.IGNORECASE),
    ),
]

# CI-time utilities excluded from the scan (not plugin runtime code).
_EXCLUDE_DIRS = {"tools"}


def scan(path: Path) -> list[str]:
    """Return "path:lineno: line" strings for every offending line in `path`."""
    hits: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        for label, pattern in _PATTERNS:
            if pattern.search(line):
                hits.append(f"{path}:{lineno}: [{label}] {line.strip()}")
                break
    return hits


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    targets = [
        p
        for p in sorted(root.rglob("*.py"))
        if not any(part in _EXCLUDE_DIRS for part in p.relative_to(root).parts)
    ]
    if not targets:
        print("No Python files found to scan", file=sys.stderr)
        return 1

    hits: list[str] = []
    for path in targets:
        hits.extend(scan(path))

    if hits:
        print("Mutation found in plugin Python source:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print(
            f"\n{len(hits)} mutation(s). Plugins must be read-only — remove the write or document an explicit exception.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(targets)} Python file(s) scanned, no mutation detected")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
