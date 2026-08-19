#!/usr/bin/env python3
"""Fail if a SKILL.md changed but its `version` frontmatter was not bumped.

Compares the current tree against `origin/master` (or the merge base of the
current branch). For every SKILL.md whose content changed, the `version` field
in its frontmatter must also have changed — otherwise the change is a silent
drift that won't trigger a reinstall for users who already have the skill.

Usage:
    python tools/check_skill_version_bump.py            # compare vs origin/master
    python tools/check_skill_version_bump.py <ref>      # compare vs <ref>
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _git(args: list[str]) -> str:
    proc = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.stdout or ""


def _merge_base(ref: str) -> str | None:
    out = _git(["merge-base", "HEAD", ref]).strip()
    return out or None


def _changed_files(ref: str) -> list[str]:
    out = _git(["diff", "--name-only", ref, "--"])
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _frontmatter_at(path: str, ref: str) -> dict | None:
    """Read the YAML frontmatter of `path` as it exists at `ref`, or None."""
    try:
        blob = _git(["show", f"{ref}:{path}"])
    except Exception:
        return None
    if not blob.startswith("---"):
        return None
    parts = blob.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        import yaml

        fm = yaml.safe_load(parts[1])
    except Exception:
        return None
    return fm if isinstance(fm, dict) else None


def _frontmatter_here(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        import yaml

        fm = yaml.safe_load(parts[1])
    except Exception:
        return None
    return fm if isinstance(fm, dict) else None


def main(argv: list[str]) -> int:
    ref = argv[1] if len(argv) > 1 else "origin/master"
    base = _merge_base(ref) if not argv[1:2] else ref
    if not base:
        print(f"Could not resolve merge base against {ref}; skipping version-bump check.", file=sys.stderr)
        return 0

    changed = _changed_files(base)
    skill_files = [f for f in changed if f.endswith("SKILL.md")]
    if not skill_files:
        print("No SKILL.md files changed; version-bump check skipped.")
        return 0

    failures = []
    for path in skill_files:
        before = _frontmatter_at(path, base)
        after = _frontmatter_here(path)
        if before is None or after is None:
            # New or deleted file — no bump required (new installs get it fresh).
            continue
        before_ver = before.get("version")
        after_ver = after.get("version")
        if before_ver == after_ver:
            failures.append((path, before_ver))

    if failures:
        print("SKILL.md changed but `version` was not bumped:", file=sys.stderr)
        for path, ver in failures:
            print(f"  {path} (version still {ver!r})", file=sys.stderr)
        print("Bump the `version` field in each changed SKILL.md.", file=sys.stderr)
        return 1

    print(f"OK: {len(skill_files)} SKILL.md change(s) all have a version bump.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
