#!/usr/bin/env python3
"""F2 regression: only real plugins may be reported as "not enabled".

The notes loop in ``check_plugins`` tested nothing but ``os.path.isdir``, while
``_collect_plugin_ids`` requires a ``plugin.yaml``/``plugin.yml`` manifest. Any
stray directory under ``$HERMES_HOME/plugins`` was therefore announced as an
opt-in plugin — on the reference install that meant a state-file directory and
a vendored Node checkout were reported on every run.

Guards:

1. A manifest-less directory produces no note (core does not treat it as a
   plugin either).
2. A directory with a manifest, not listed in enabled/disabled, still produces
   a note (the real feature keeps working).
3. The note is keyed on the manifest ``name``, not the directory basename, so a
   plugin whose manifest name differs from its directory is reported once and
   under the identifier ``plugins.enabled`` actually matches.
4. An enabled plugin whose manifest name differs from its directory is not
   reported as missing.

Uses a synthetic ``$HERMES_HOME`` and never invokes the ``hermes`` CLI.

Run: python3 tools/test_plugins_notes.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: list[str]) -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "hermes_guide"
        pkg.mkdir()
        for name in ("__init__.py", "checks.py", "constants.py"):
            shutil.copy(REPO / name, pkg / name)
        sys.path.insert(0, td)

        import hermes_guide.checks as checks  # noqa: E402

        home = Path(td) / "home"
        plugins = home / "plugins"

        # stray dirs with NO manifest — must never be reported
        _write(plugins / "state-only/state.json", '{"a": 1}')
        _write(plugins / "vendored-node/package.json", '{"name": "x"}')
        (plugins / "empty-dir").mkdir(parents=True, exist_ok=True)

        # a real plugin, not enabled — must be reported
        _write(plugins / "real-plugin/plugin.yaml", "name: real-plugin\nversion: 0.1.0\n")

        # a real plugin whose manifest name differs from its directory
        _write(plugins / "dir-name-differs/plugin.yaml", "name: manifest-name\nversion: 0.1.0\n")

        # an enabled plugin whose manifest name differs from its directory
        _write(plugins / "enabled-dir/plugin.yaml", "name: enabled-manifest\nversion: 0.1.0\n")

        config = home / "config.yaml"
        _write(config, "plugins:\n  enabled:\n    - enabled-manifest\n  disabled: []\n")

        checks._cache.clear()
        checks._hermes_config_path = lambda: str(config)
        checks._hermes_home = lambda: str(home)
        checks._bundled_plugins_dir = lambda: None

        result = checks.check_plugins()
        detail = result.get("detail") or []
        notes = [str(d) for d in detail] if isinstance(detail, list) else [str(detail)]
        joined = " | ".join(notes)

        # (1) no manifest-less directory may appear
        for stray in ("state-only", "vendored-node", "empty-dir"):
            if stray in joined:
                failures.append(
                    f"manifest-less dir {stray!r} was reported as a plugin: {joined}"
                )

        # (2) a real un-enabled plugin is still reported
        if "real-plugin" not in joined:
            failures.append(f"real un-enabled plugin was not reported: {joined}")

        # (3) the note is keyed on the manifest name, not the directory
        if "manifest-name" not in joined:
            failures.append(f"note not keyed on manifest name: {joined}")
        if "dir-name-differs" in joined:
            failures.append(f"note used the directory basename instead of the manifest name: {joined}")

        # (4) an enabled plugin resolved by manifest name is not "missing"
        if result.get("status") == "broken":
            failures.append(f"enabled plugin wrongly reported missing: {result!r}")
        if "enabled-manifest" in joined or "enabled-dir" in joined:
            failures.append(f"enabled plugin should not appear in notes: {joined}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OK: only manifest-bearing plugin dirs are reported (F2)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
