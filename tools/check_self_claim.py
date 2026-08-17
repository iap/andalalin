#!/usr/bin/env python3
"""Fail if documentation asserts self-endorsing quality claims.

Scans Markdown files under the repo root and exits non-zero if it finds
self-claim phrasing. Used by CI to keep README / CONTRIBUTING / skills
describing behavior ("Skills track the Hermes source") instead of asserting
quality ("Content is verified against the Hermes source").

The assertion pattern is deliberately word-boundary-scoped to the assertion
form ("is/are/was/were/been/being verified|audited|guaranteed") so it does NOT
flag directives such as "must be verified against the source" — those are
instructions, not claims.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Assertion form: "Content is verified against ..." / "Checks are audited".
ASSERTION = re.compile(
    r"\b(?:is|are|was|were|been|being)\s+(?:fully\s+)?(?:verified|audited|guaranteed)\b",
    re.IGNORECASE,
)

# Unambiguous self-aggrandizing terms.
SELF_AGGRANDIZING = re.compile(
    r"production-ready|production-grade|bulletproof|best-in-class|"
    r"industry-leading|world-class|seamless|flawless|battle-tested|rock-solid",
    re.IGNORECASE,
)

_PATTERNS = (ASSERTION, SELF_AGGRANDIZING)


def scan(path: Path) -> list[str]:
    """Return "path:lineno: line" strings for every offending line in `path`."""
    hits: list[str] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        for pattern in _PATTERNS:
            if pattern.search(line):
                hits.append(f"{path}:{lineno}: {line.strip()}")
                break
    return hits


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    targets = sorted(root.rglob("*.md"))
    if not targets:
        print(f"No Markdown files found under {root}", file=sys.stderr)
        return 1

    hits: list[str] = []
    for path in targets:
        hits.extend(scan(path))

    if hits:
        print("Self-claim language found in docs:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        print("Describe behavior; don't assert quality.", file=sys.stderr)
        return 1

    print(f"Docs self-claim guard: clean ({len(targets)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
