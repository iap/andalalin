#!/usr/bin/env python3
"""F4 regression: a scope filter must match a check label exactly.

``run_all(scope=...)`` filtered with ``scope not in label``, a substring test.
Two consequences, both verified against the pre-fix code:

- ``hermes guide s`` silently ran skills+commands+hooks+plugins, because "s"
  is a substring of four labels.
- ``hermes guide bogus`` produced no checks and exited 0 — a typo reported
  success from a diagnostic tool, the one failure mode that matters here.

Guards:

1. An exact label runs exactly that check.
2. A substring of a label (``s``, ``o``, ``mc``) is rejected, not expanded.
3. An unknown scope raises ``ValueError`` naming the valid scopes.
4. ``scope=None`` runs every check.
5. The CLI handler exits non-zero on an unknown scope; the slash-command
   handler returns the error as text (slash commands have no exit contract).

Run: python3 tools/test_scope_validation.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "hermes_guide"
        pkg.mkdir()
        for name in ("__init__.py", "checks.py", "constants.py"):
            shutil.copy(REPO / name, pkg / name)
        sys.path.insert(0, td)

        import hermes_guide as guide  # noqa: E402
        import hermes_guide.checks as checks  # noqa: E402

        labels = [label for label, _ in checks._CHECKS]

        # Stub every check so nothing touches the real environment.
        checks._CHECKS = [
            (label, lambda _l=label: {"status": "healthy", "reason": _l, "detail": None})
            for label in labels
        ]

        # (1) an exact label runs exactly that check
        for label in labels:
            got = sorted(checks.run_all(scope=label).keys())
            if got != [label]:
                failures.append(f"scope={label!r} ran {got}, expected [{label!r}]")

        # (2) a substring of a label must be rejected, not expanded
        for substring in ("s", "o", "mc", "plug", "config "):
            try:
                got = sorted(checks.run_all(scope=substring).keys())
            except ValueError:
                continue
            failures.append(
                f"substring scope {substring!r} was accepted and ran {got}"
            )

        # (3) an unknown scope raises ValueError naming the valid scopes
        try:
            checks.run_all(scope="bogus")
            failures.append("unknown scope 'bogus' did not raise ValueError")
        except ValueError as exc:
            for label in labels:
                if label not in str(exc):
                    failures.append(f"ValueError text omits valid scope {label!r}: {exc}")
                    break

        # (4) scope=None runs everything
        got = sorted(checks.run_all().keys())
        if got != sorted(labels):
            failures.append(f"scope=None ran {got}, expected {sorted(labels)}")

        # (5) handler contracts
        class Args:
            scope = "bogus"

        try:
            guide._run_cli(Args())
            failures.append("_run_cli did not exit on an unknown scope")
        except SystemExit as exc:
            if exc.code in (0, None):
                failures.append(f"_run_cli exited {exc.code!r} on an unknown scope")

        text = guide._handle_doctor("bogus")
        if not text or "bogus" not in text:
            failures.append(f"_handle_doctor did not surface the bad scope: {text!r}")
        if "unknown scope" not in text.lower():
            failures.append(f"_handle_doctor text is not an error message: {text!r}")

        # a valid scope still works through the slash-command handler
        ok = guide._handle_doctor("mcp")
        if "mcp" not in ok:
            failures.append(f"_handle_doctor('mcp') lost its result: {ok!r}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: scope filters match check labels exactly (F4)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
