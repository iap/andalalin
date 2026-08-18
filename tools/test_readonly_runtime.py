#!/usr/bin/env python3
"""Runtime smoke test: verify the plugin is read-only at runtime.

Snapshots the active Hermes config file, runs the full check suite, and asserts
the file's existence and content are unchanged. This tests the read-only
guarantee at runtime — the plugin must not create, modify, or delete config —
complementing the static no-mutation guard (which only inspects source).

Requires the `hermes` CLI on PATH (installed in CI).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _hermes_config_path() -> str | None:
    proc = subprocess.run(
        ["hermes", "config", "path"], capture_output=True, text=True
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return lines[-1] if proc.returncode == 0 and lines else None


def _snapshot(path: str | None) -> tuple[bool, str | None]:
    """Return (exists, sha256_or_None) for the config file at `path`."""
    if not path:
        return False, None
    p = Path(path)
    if not p.exists():
        return False, None
    return True, hashlib.sha256(p.read_bytes()).hexdigest()


def main(argv: list[str]) -> int:
    cfg = _hermes_config_path()
    if not cfg:
        print("FAIL: `hermes config path` did not resolve a config path", file=sys.stderr)
        return 1

    # The repo dir is hyphenated ("hermes-guide") so it can't be imported as a
    # package directly; copy the sources into a valid package name first.
    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "hermes_guide"
        pkg.mkdir()
        for name in ("__init__.py", "checks.py", "constants.py"):
            shutil.copy(REPO / name, pkg / name)
        sys.path.insert(0, td)

        import hermes_guide.checks as checks  # noqa: E402

        before_exists, before_hash = _snapshot(cfg)
        results = checks.run_all()
        after_exists, after_hash = _snapshot(cfg)

    if before_exists != after_exists:
        print(
            f"FAIL: config file existence changed ({before_exists} -> {after_exists}): {cfg}",
            file=sys.stderr,
        )
        return 1
    if before_exists and before_hash != after_hash:
        print(f"FAIL: config file content changed during run: {cfg}", file=sys.stderr)
        return 1
    if not results:
        print("FAIL: no checks ran", file=sys.stderr)
        return 1

    print(f"OK: {len(results)} check(s) ran, config file unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
