#!/usr/bin/env python3
"""Detect upstream schema drift for the hermes-guide plugin.

`checks.py` / `constants.py` encode knowledge of the Hermes schema that upstream
owns: plugin subcategory dirs, skill frontmatter fields, MCP server fields, and hook
event names. When `NousResearch/hermes-agent` changes the files that define that
schema, this plugin can silently go stale.

This script flags upstream commits (within the last N days) that touched the watched
schema files, and files a GitHub issue on this repo so a human reviews the drift.
Runs in CI via `.github/workflows/upstream-drift.yml` (weekly + manual).

Requires the `gh` CLI (preinstalled on GitHub-hosted runners) with a token that can
read the public upstream repo and create issues on this repo.
"""

import datetime
import os
import subprocess
import sys
from urllib.parse import urlencode

UPSTREAM_REPO = os.environ.get("UPSTREAM_REPO", "NousResearch/hermes-agent")
WATCH_FILES = os.environ.get(
    "WATCH_FILES",
    "hermes_cli/plugins.py tools/skills_tool.py agent/skill_utils.py",
).split()
WINDOW_DAYS = int(os.environ.get("DRIFT_WINDOW_DAYS", "7"))


def recent_commits(path: str, since: str) -> list[str]:
    """Return SHAs of upstream commits touching `path` since `since` (ISO-8601)."""
    query = urlencode({"path": path, "since": since}, safe="/")
    proc = subprocess.run(
        ["gh", "api", f"repos/{UPSTREAM_REPO}/commits?{query}", "--jq", ".[].sha"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"WARN: could not query {path}: {proc.stderr.strip()}", file=sys.stderr)
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    since = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=WINDOW_DAYS)
    ).isoformat()

    touched: dict[str, list[str]] = {}
    for path in WATCH_FILES:
        shas = recent_commits(path, since)
        if shas:
            touched[path] = shas

    if not touched:
        print(f"No upstream schema changes in the last {WINDOW_DAYS} days.")
        return 0

    lines = [f"## Upstream schema drift (last {WINDOW_DAYS} days)", ""]
    for path, shas in touched.items():
        lines.append(f"### `{path}`")
        for sha in shas[:20]:
            lines.append(f"- [`{sha[:7]}`](https://github.com/{UPSTREAM_REPO}/commit/{sha})")
        lines.append("")
    lines.append(
        "These files define schema the `hermes-guide` plugin depends on (plugin "
        "subcategory dirs, skill frontmatter, MCP server fields, hook event names). "
        "Review the changes and update `checks.py` / `constants.py` if needed."
    )
    body = "\n".join(lines)

    issue_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not issue_repo or os.environ.get("DRIFT_DRY_RUN") == "1":
        print("DRIFT DETECTED (dry-run, no issue opened):")
        print(body)
        return 0

    subprocess.run(
        [
            "gh", "issue", "create",
            "--repo", issue_repo,
            "--title", "Upstream schema drift detected — review checks.py",
            "--body", body,
        ],
        check=True,
    )
    print("Opened drift issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
