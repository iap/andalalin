#!/usr/bin/env python3
"""Detect upstream schema drift for the hermes-guide plugin (baseline-anchored).

`checks.py` / `constants.py` encode knowledge of the Hermes schema that upstream owns:
plugin subcategory dirs, skill frontmatter fields, MCP server fields, and hook event
names. When `NousResearch/hermes-agent` changes the files that define that schema, this
plugin can silently go stale.

This script diffs the watched schema files between a stored baseline commit
(`.github/upstream-drift.baseline`) and upstream HEAD, and files one GitHub issue on this
repo listing the drift. It deduplicates (skips) if a drift issue is already open, and
tells the reviewer to bump the baseline afterward. Runs in CI via
`.github/workflows/upstream-drift.yml` (weekly + manual).

Requires `git` + the `gh` CLI (both preinstalled on GitHub-hosted runners).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

UPSTREAM_REPO = os.environ.get("UPSTREAM_REPO", "NousResearch/hermes-agent")
WATCH_FILES = os.environ.get(
    "WATCH_FILES",
    "hermes_cli/plugins.py tools/skills_tool.py agent/skill_utils.py",
).split()
BASELINE_FILE = Path(".github/upstream-drift.baseline")
ISSUE_TITLE = "Upstream schema drift detected — review checks.py"
CLONE_DIR = "/tmp/hermes-agent-upstream"


def read_baseline() -> str:
    return BASELINE_FILE.read_text(encoding="utf-8").strip()


def clone_upstream() -> str:
    """Blobless partial clone of upstream `main` (fetches history, not file contents)."""
    subprocess.run(["rm", "-rf", CLONE_DIR], check=False)
    subprocess.run(
        [
            "git", "clone", "--filter=blob:none", "--no-checkout",
            "--single-branch", "--branch", "main",
            f"https://github.com/{UPSTREAM_REPO}.git", CLONE_DIR,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return CLONE_DIR


def git(repo_dir: str, *args: str) -> tuple[str, str, int]:
    proc = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)
    return proc.stdout.strip(), proc.stderr.strip(), proc.returncode


def main() -> int:
    base = read_baseline()
    repo_dir = clone_upstream()
    head, _, _ = git(repo_dir, "rev-parse", "HEAD")

    log, err, code = git(repo_dir, "log", "--format=%h %ci %s", f"{base}..HEAD", "--", *WATCH_FILES)
    if code != 0:
        if "unknown revision" in err:
            msg = f"baseline {base[:7]} not found upstream — please re-baseline `.github/upstream-drift.baseline`."
        else:
            msg = f"git log failed: {err or 'unknown error'}"
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    if not log:
        print(f"No drift: watched files unchanged since baseline {base[:7]} (HEAD {head[:7]}).")
        return 0

    body = (
        "## Upstream schema drift\n\n"
        f"Watched files changed since baseline `{base[:7]}`:\n\n"
        f"```\n{log}\n```\n\n"
        f"Compare: https://github.com/{UPSTREAM_REPO}/compare/{base[:7]}...{head[:7]}\n\n"
        "Review the changes and update `checks.py` / `constants.py` if needed. Then bump "
        f"the baseline: edit `.github/upstream-drift.baseline` to `{head}`."
    )

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo or os.environ.get("DRIFT_DRY_RUN") == "1":
        print("DRIFT DETECTED (dry-run, no issue opened):")
        print(body)
        return 0

    # Dedup: skip if an open drift issue already exists.
    proc = subprocess.run(
        [
            "gh", "issue", "list", "--repo", repo, "--state", "open",
            "--search", "Upstream schema drift", "--json", "number",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(
            f"ERROR: gh issue list failed: {proc.stderr.strip() or 'unknown error'}",
            file=sys.stderr,
        )
        return 1
    try:
        if json.loads(proc.stdout):
            print("Drift issue already open; skipping duplicate.")
            return 0
    except json.JSONDecodeError:
        print("ERROR: gh issue list returned invalid JSON.", file=sys.stderr)
        return 1

    subprocess.run(
        ["gh", "issue", "create", "--repo", repo, "--title", ISSUE_TITLE, "--body", body],
        check=True,
    )
    print("Opened drift issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
