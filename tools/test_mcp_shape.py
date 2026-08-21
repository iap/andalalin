#!/usr/bin/env python3
"""Regression test: the MCP shape check must flag only genuinely malformed
servers — never valid stdio (`command`) / http (`url`) entries.

Guards against the constants.py placeholder regression where MCP_STDIO_KEY /
MCP_HTTP_KEY were `"***"` instead of `"command"` / `"url"`, which made every
enabled MCP server report as broken.

Follows the same source-copy import trick as tools/test_readonly_runtime.py:
the repo dir is hyphenated ("hermes-guide") so it cannot be imported as a
package directly; copy the sources into a valid package name first.

Usage:
    python tools/test_mcp_shape.py
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

        import hermes_guide.checks as checks
        import hermes_guide.constants as constants

        # 1. Direct guard: the constant values must be the real field names.
        if constants.MCP_STDIO_KEY != "command":
            failures.append(
                f"MCP_STDIO_KEY is {constants.MCP_STDIO_KEY!r}, expected 'command'"
            )
        if constants.MCP_HTTP_KEY != "url":
            failures.append(
                f"MCP_HTTP_KEY is {constants.MCP_HTTP_KEY!r}, expected 'url'"
            )

        # 2. Behavioral: a valid stdio + http config must be healthy.
        healthy_config = {
            "mcp_servers": {
                "filesystem": {"command": "npx", "args": ["-y", "x"]},
                "linear": {"url": "https://mcp.linear.app/mcp"},
            }
        }
        checks._read_config = lambda: ("/fake/config.yaml", healthy_config)
        r = checks.check_mcp_servers_shape()
        if r["status"] != "healthy":
            failures.append(f"valid config reported {r['status']!r}: {r}")

        # 3. A server with neither key must still be flagged, and the message
        #    must name command/url (not the old placeholder).
        broken_config = {
            "mcp_servers": {
                "filesystem": {"command": "npx"},
                "bad": {"args": ["x"]},
            }
        }
        checks._read_config = lambda: ("/fake/config.yaml", broken_config)
        r = checks.check_mcp_servers_shape()
        detail = " ".join(r.get("detail") or [])
        if r["status"] != "broken":
            failures.append(f"malformed config reported {r['status']!r}, expected 'broken': {r}")
        if "mcp_servers.bad" not in detail:
            failures.append(f"malformed detail missing 'mcp_servers.bad': {detail}")
        if "filesystem" in detail:
            failures.append(f"valid server 'filesystem' wrongly flagged: {detail}")
        if "`command`" not in detail or "`url`" not in detail:
            failures.append(f"malformed detail missing command/url field names: {detail}")
        if "***" in detail:
            failures.append(f"placeholder '***' leaked into detail: {detail}")

        # 4. Disabled servers must be skipped, not flagged.
        disabled_config = {
            "mcp_servers": {
                "off": {"enabled": False, "args": ["x"]},
            }
        }
        checks._read_config = lambda: ("/fake/config.yaml", disabled_config)
        r = checks.check_mcp_servers_shape()
        if r["status"] not in ("healthy", "informational"):
            failures.append(f"disabled-only config reported {r['status']!r}: {r}")

    if failures:
        print("MCP shape regression FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("MCP shape regression OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
