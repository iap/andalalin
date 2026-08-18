#!/usr/bin/env python3
"""Fail if plugin Python source mutates config or the filesystem.

Hermes plugins must be read-only: observe and report, never write. This guard
scans the plugin's Python sources and exits non-zero when it finds filesystem
writes, config mutation, or mutating subprocesses — turning the read-only
contract into an enforced CI invariant rather than a convention.

Scanned: ``*.py`` under the repo root, excluding ``tools/`` (CI-time utilities;
the guard itself lives there and contains these patterns as regex literals).

Style and CI wiring mirror tools/check_self_claim.py.

Usage:
    python tools/check_no_mutation.py            # scan plugin Python sources
    python tools/check_no_mutation.py --selftest # regression-check the patterns
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
        # Builtin open(): mode is the 2nd positional arg (after a comma).
        # Write flags are w, a, x, or "+" (r+/w+/a+). Read-only "r"/"rb" pass.
        re.compile(r"open\s*\(\s*[^,]+,\s*[\"'][^\"']*(?:w|a|x|\+)[^\"']*[\"']"),
    ),
    (
        "write-mode open(..., mode=...)",
        re.compile(r"open\s*\([^)]*mode\s*=\s*[\"'][^\"']*(?:w|a|x|\+)[^\"']*[\"']"),
    ),
    (
        "Path.open() write (positional mode)",
        # pathlib.Path.open(mode, ...) takes the mode as its FIRST positional
        # argument, so a `.open("w")` method call has no comma before the mode.
        re.compile(r"\.open\s*\(\s*[\"'][^\"']*(?:w|a|x|\+)[^\"']*[\"']"),
    ),
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

# Regression table: (snippet, should_a_pattern_match). Covers both open()
# signatures and read-only negatives so a regex tweak can't silently reopen a hole.
_SELFTEST_CASES: list[tuple[str, bool]] = [
    ('open(path, "r", encoding="utf-8")', False),
    ('open(path, "w")', True),
    ('open(path, "a", encoding="utf-8")', True),
    ('open(path, "rb")', False),
    ('open(path, "wb")', True),
    ('open(path, "r+")', True),
    ('open(path, mode="w")', True),
    ('open(path, mode="r")', False),
    ('Path("out").open("w")', True),
    ('Path("out").open("r")', False),
    ('Path("out").open("wb")', True),
    ('Path("out").open(mode="a")', True),
    ("yaml.dump(data, f)", True),
    ("yaml.safe_load(text)", False),
    ('Path("x").write_text(s)', True),
    ("os.remove(p)", True),
    ("os.makedirs(p)", True),
    ("shutil.rmtree(p)", True),
    ('subprocess.run(["hermes", "config", "path"])', False),
    ('subprocess.run(["pip", "install", "x"])', True),
]


def scan(path: Path) -> list[str]:
    """Return "path:lineno: line" strings for every offending line in `path`."""
    hits: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        for label, pattern in _PATTERNS:
            if pattern.search(line):
                hits.append(f"{path}:{lineno}: [{label}] {line.strip()}")
                break
    return hits


def selftest() -> int:
    """Verify the patterns against the regression table; exit non-zero on drift."""
    failures = 0
    for snippet, expect in _SELFTEST_CASES:
        matched = any(pattern.search(snippet) for _, pattern in _PATTERNS)
        if matched != expect:
            failures += 1
            print(
                f"SELFTEST FAIL: expected match={expect} got={matched} for: {snippet}",
                file=sys.stderr,
            )
    if failures:
        print(f"{failures} selftest case(s) failed", file=sys.stderr)
        return 1
    print(f"selftest OK: {len(_SELFTEST_CASES)} cases")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()

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
