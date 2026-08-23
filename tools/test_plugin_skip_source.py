#!/usr/bin/env python3
"""F3 regression: subcategory-dir names must come from constants.py.

``constants.py`` is the declared single source of truth for names that drift
across Hermes versions (see AGENTS.md). ``check_plugins`` nonetheless passed a
hardcoded ``{"memory", "context_engine", "model-providers"}`` literal to
``_collect_plugin_ids`` for the bundled directory, duplicating 3 of the 9
entries in ``constants.PLUGIN_SUBCATEGORY_DIRS`` and free to drift from it.

Guards:

1. Static: no subcategory-dir name literal appears in ``checks.py`` outside a
   comment — the set must be referenced via ``constants``.
2. Static: ``checks.py`` references ``constants.PLUGIN_SUBCATEGORY_DIRS``.
3. Behavioral: every name in ``constants.PLUGIN_SUBCATEGORY_DIRS`` is excluded
   from the bundled-directory scan, so a bundled plugin inside a subcategory
   dir (which resolves by its own provider key, not ``plugins.enabled``) is
   never collected as a discoverable id.

Run: python3 tools/test_plugin_skip_source.py
"""

from __future__ import annotations

import ast
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _string_literals(source: str) -> set[str]:
    """Every string constant in the module (comments are not constants)."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


def main(argv: list[str]) -> int:
    failures: list[str] = []

    sys.path.insert(0, str(REPO))
    import constants  # noqa: E402

    subcategories = set(constants.PLUGIN_SUBCATEGORY_DIRS)
    checks_source = (REPO / "checks.py").read_text(encoding="utf-8")

    # (1) no subcategory name may be hardcoded in checks.py
    literals = _string_literals(checks_source)
    leaked = sorted(subcategories & literals)
    if leaked:
        failures.append(
            "checks.py hardcodes subcategory dir name(s) "
            f"{leaked} — reference constants.PLUGIN_SUBCATEGORY_DIRS instead"
        )

    # (2) the constant is actually referenced
    if "constants.PLUGIN_SUBCATEGORY_DIRS" not in checks_source:
        failures.append("checks.py does not reference constants.PLUGIN_SUBCATEGORY_DIRS")

    # (3) behavioral: subcategory dirs are excluded from the bundled scan
    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "hermes_guide"
        pkg.mkdir()
        for name in ("__init__.py", "checks.py", "constants.py"):
            shutil.copy(REPO / name, pkg / name)
        sys.path.insert(0, td)

        import hermes_guide.checks as checks  # noqa: E402

        home = Path(td) / "home"
        bundled = Path(td) / "bundled"

        # one bundled plugin per subcategory dir, plus a top-level one
        for sub in sorted(subcategories):
            _write(bundled / sub / f"{sub}-plugin/plugin.yaml", f"name: {sub}-plugin\n")
        _write(bundled / "top-level/plugin.yaml", "name: top-level\n")

        config = home / "config.yaml"
        _write(config, "plugins:\n  enabled: []\n  disabled: []\n")
        (home / "plugins").mkdir(parents=True, exist_ok=True)

        checks._cache.clear()
        checks._hermes_config_path = lambda: str(config)
        checks._hermes_home = lambda: str(home)
        checks._bundled_plugins_dir = lambda: str(bundled)

        known: set[str] = set()
        checks._collect_plugin_ids(
            str(bundled), "", 0, set(constants.PLUGIN_SUBCATEGORY_DIRS), known
        )

        for sub in sorted(subcategories):
            if f"{sub}-plugin" in known or f"{sub}/{sub}-plugin" in known:
                failures.append(
                    f"subcategory dir {sub!r} was scanned; its plugins must be "
                    "excluded (they resolve by their own provider key)"
                )
        if "top-level" not in known:
            failures.append("a top-level bundled plugin was not collected")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: subcategory dirs come from constants.PLUGIN_SUBCATEGORY_DIRS (F3)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
