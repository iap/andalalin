#!/usr/bin/env python3
"""F1 regression: the shell-hooks-allowlist.json check must be reachable.

``check_hooks()`` once returned unconditionally before the allowlist
validation, leaving that block unreachable — a corrupt allowlist was never
reported. Two guards here:

1. Static: no statement in ``check_hooks()`` may follow an unconditional
   return (AST-level unreachability, which is how the original bug surfaced).
2. Behavioral: with a malformed allowlist on disk, ``check_hooks()`` must
   return a ``broken`` envelope naming the allowlist on every
   ``hermes hooks doctor`` outcome (no-hooks / healthy / unrecognized wording),
   and a well-formed allowlist must leave doctor's own verdict untouched.

Loads the modules as a real ``hermes_guide`` package in a temp dir (the
relative ``from . import constants`` needs a parent package) and monkeypatches
``_run``/``_hermes_home`` so the ``hermes`` CLI is never invoked.

Run: python3 tools/test_reachable_allowlist_check.py
"""

from __future__ import annotations

import ast
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _unreachable(func_name: str) -> list[tuple[int, int]]:
    """Return [(return_line, first_dead_line)] for statements after a return."""
    tree = ast.parse((REPO / "checks.py").read_text(encoding="utf-8"))
    dead: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for i, stmt in enumerate(node.body):
                if isinstance(stmt, (ast.Return, ast.Raise)) and i < len(node.body) - 1:
                    dead.append((stmt.lineno, node.body[i + 1].lineno))
    return dead


def main(argv: list[str]) -> int:
    failures: list[str] = []

    # (1) static reachability
    for ret_line, dead_line in _unreachable("check_hooks"):
        failures.append(
            f"check_hooks() unreachable code: return at line {ret_line} makes "
            f"line {dead_line} onward dead"
        )

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "hermes_guide"
        pkg.mkdir()
        for name in ("__init__.py", "checks.py", "constants.py"):
            shutil.copy(REPO / name, pkg / name)
        sys.path.insert(0, td)

        import hermes_guide.checks as checks  # noqa: E402

        home = Path(td) / "home"
        home.mkdir()
        allowlist = home / "shell-hooks-allowlist.json"
        checks._hermes_home = lambda: str(home)

        doctor_outputs = {
            "no-hooks": (0, "No shell hooks configured — nothing to check.\n", ""),
            "healthy": (0, "All shell hooks look healthy\n", ""),
            "unknown-wording": (0, "some future summary line\n", ""),
        }

        # (2) a malformed allowlist is broken on every doctor outcome
        allowlist.write_text("{ this is not json", encoding="utf-8")
        for label, response in doctor_outputs.items():
            checks._cache.clear()
            checks._run = lambda cmd, timeout=20, _r=response: _r
            result = checks.check_hooks()
            if result.get("status") != "broken":
                failures.append(
                    f"malformed allowlist not reported with doctor={label}: "
                    f"status={result.get('status')!r} reason={result.get('reason')!r}"
                )
            elif "allowlist" not in str(result.get("detail", "")):
                failures.append(
                    f"broken envelope omits the allowlist path with doctor={label}: "
                    f"detail={result.get('detail')!r}"
                )

        # (3) a valid allowlist preserves doctor's own verdict
        allowlist.write_text('{"hooks": []}', encoding="utf-8")
        for label, expected in (("no-hooks", "healthy"), ("healthy", "healthy"),
                                ("unknown-wording", "unknown")):
            checks._cache.clear()
            checks._run = lambda cmd, timeout=20, _r=doctor_outputs[label]: _r
            result = checks.check_hooks()
            if result.get("status") != expected:
                failures.append(
                    f"valid allowlist altered the {label} verdict: "
                    f"expected {expected}, got {result.get('status')!r}"
                )

        # (4) an absent allowlist is not a finding
        allowlist.unlink()
        checks._cache.clear()
        checks._run = lambda cmd, timeout=20: doctor_outputs["no-hooks"]
        if checks.check_hooks().get("status") != "healthy":
            failures.append("absent allowlist wrongly produced a finding")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: allowlist JSON check is reachable and enforced (F1)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
