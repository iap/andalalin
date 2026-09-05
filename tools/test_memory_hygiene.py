#!/usr/bin/env python3
"""Regression coverage for checks.check_memory_hygiene() (the `memories` scope).

Greptile review of PR #42 flagged four diagnostic gaps that ad-hoc testing
missed; each case below pins one of them plus the core paths:

  F1  mixed dated/undated entries must report the undated count (not stay
      silent because *some* entry is dated)
  F2  a fresh install with no store files must be `healthy` ("nothing to
      audit"), not noisy `informational`
  F3  non-profile agent notes that merely *start* with "User" (e.g. "User
      authentication uses OAuth") must NOT be flagged as mis-targeted
  F4  this file — the check had no committed regression coverage at all

Also covers: over-limit via a *configured* limit, near-duplicate detection,
mis-target detection for genuine profile facts, and the one-store-missing case.

Run: python3 tools/test_memory_hygiene.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _make_env(td: Path, config: str):
    """Isolated Hermes home + importable package copy; returns (home, checks)."""
    home = td / "home"
    (home / "memories").mkdir(parents=True)
    (home / "config.yaml").write_text(config, encoding="utf-8")
    root = td / "libs"
    pkg = root / "hermes_guide"
    pkg.mkdir(parents=True)
    for name in ("__init__.py", "checks.py", "constants.py"):
        shutil.copy(REPO / name, pkg / name)
    sys.path.insert(0, str(root))
    import hermes_guide.checks as checks  # noqa: E402

    checks._hermes_config_path = lambda: str(home / "config.yaml")
    return home, checks


def _store(home: Path, name: str, entries: list[str]) -> None:
    path = home / "memories" / name
    if entries:
        path.write_text("\n§\n".join(entries), encoding="utf-8")


def _run(checks, scope="memories"):
    return checks.run_all(scope)["memories"]


def case_fresh_install(td: Path) -> None:
    """F2: no store files -> healthy, nothing to audit (no notes)."""
    home, checks = _make_env(td, "memory: {}\n")
    r = _run(checks)
    assert r["status"] == "healthy" and "nothing to audit" in r["reason"], r


def case_over_limit(td: Path) -> None:
    """Configured limit is honored; over-limit store -> broken."""
    home, checks = _make_env(td, "memory:\n  memory_char_limit: 100\n")
    _store(home, "MEMORY.md", ["x" * 150])
    _store(home, "USER.md", ["ok entry"])
    r = _run(checks)
    assert r["status"] == "broken" and any("over limit" in d for d in r["detail"]), r


def case_near_dupe(td: Path) -> None:
    """Near-duplicate pair -> informational merge note."""
    home, checks = _make_env(td, "memory: {}\n")
    _store(home, "MEMORY.md", [
        "Foundry local tests run with FOUNDRY_PROFILE=default forge test --optimize false for speed.",
        "Foundry local tests run with FOUNDRY_PROFILE=default forge test --optimize false for velocity.",
    ])
    _store(home, "USER.md", ["User prefers concise responses."])
    r = _run(checks)
    assert r["status"] == "informational" and any("near-duplicate" in d for d in r["detail"]), r


def case_mixed_dates(td: Path) -> None:
    """F1: one dated + one undated entry must report the undated count."""
    home, checks = _make_env(td, "memory: {}\n")
    _store(home, "MEMORY.md", [
        "[2026-09-05] Dated convention entry about the fork CI runners.",
        "Undated convention entry about the dashboard port bridging.",
    ])
    _store(home, "USER.md", ["User prefers concise responses."])
    r = _run(checks)
    assert r["status"] == "informational", r
    assert any("1 of 2 entries lack" in d for d in r["detail"]), r


def case_all_dated_clean(td: Path) -> None:
    """All entries dated, no dupes, under limit -> healthy with no notes."""
    home, checks = _make_env(td, "memory: {}\n")
    _store(home, "MEMORY.md", [
        "[2026-09-05] Dated convention entry about the fork CI runners.",
        "[2026-09-04] Another dated convention entry, distinct in content.",
    ])
    _store(home, "USER.md", ["User prefers concise responses."])
    r = _run(checks)
    assert r["status"] == "healthy", r


def case_user_prefix_not_profile(td: Path) -> None:
    """F3: agent note starting with 'User' but not a profile fact -> no finding."""
    home, checks = _make_env(td, "memory: {}\n")
    _store(home, "MEMORY.md", ["User authentication uses OAuth against the gateway."])
    _store(home, "USER.md", ["User prefers concise responses."])
    r = _run(checks)
    assert not any("reads like a user-profile fact" in d for d in (r["detail"] or [])), r


def case_mis_target(td: Path) -> None:
    """Genuine profile fact in MEMORY.md -> flagged with retarget advice."""
    home, checks = _make_env(td, "memory: {}\n")
    _store(home, "MEMORY.md", ["User prefers concise, direct responses."])
    _store(home, "USER.md", ["User prefers concise responses."])
    r = _run(checks)
    assert any("belongs in USER.md" in d for d in (r["detail"] or [])), r


def case_one_store_missing(td: Path) -> None:
    """One store present, one missing -> informational with the missing note."""
    home, checks = _make_env(td, "memory: {}\n")
    _store(home, "USER.md", ["User prefers concise responses."])
    r = _run(checks)
    assert r["status"] == "informational", r
    assert any("MEMORY.md: not created yet" in d for d in r["detail"]), r


def main() -> int:
    cases = [
        case_fresh_install,
        case_over_limit,
        case_near_dupe,
        case_mixed_dates,
        case_all_dated_clean,
        case_user_prefix_not_profile,
        case_mis_target,
        case_one_store_missing,
    ]
    failed = 0
    for case in cases:
        with tempfile.TemporaryDirectory() as raw:
            try:
                case(Path(raw))
                print(f"OK: {case.__name__}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL: {case.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(cases)} case(s) failed", file=sys.stderr)
        return 1
    print(f"OK: {len(cases)} memory-hygiene case(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
