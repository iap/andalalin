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
import re
import subprocess
import sys
from pathlib import Path

UPSTREAM_REPO = os.environ.get("UPSTREAM_REPO", "NousResearch/hermes-agent")
WATCH_FILES = os.environ.get(
    "WATCH_FILES",
    "hermes_cli/plugins.py tools/skills_tool.py agent/skill_utils.py "
    "skills/autonomous-ai-agents/hermes-agent",
).split()
BASELINE_FILE = Path(".github/upstream-drift.baseline")
ISSUE_TITLE = "Upstream schema drift detected — review checks.py"
CLONE_DIR = "/tmp/hermes-agent-upstream"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import constants  # noqa: E402  (repo-root single source of truth)

# Facts that drift across Hermes versions. Each tuple: (label, upstream path,
# extraction regex with one capture group, the hermes-guide constant asserting
# ground truth). The watched files above cover *schema* drift; this covers *fact*
# drift in files we intentionally do not watch whole (mcp_tool.py, config.py).
DRIFT_FACTS = [
    ("MCP tool-name prefix", "tools/mcp_tool.py",
     r'MCP_TOOL_NAME_PREFIX\s*=\s*"([^"]+)"', constants.MCP_TOOL_NAME_PREFIX),
    ("MCP per-tool-call timeout default (s)", "tools/mcp_tool.py",
     r'per-tool-call timeout in seconds \(default:\s*(\d+)\)', str(constants.MCP_TIMEOUT_DEFAULT)),
    ("MCP connect_timeout default (s)", "tools/mcp_tool.py",
     r'_DEFAULT_CONNECT_TIMEOUT\s*=\s*(\d+)', str(constants.MCP_CONNECT_TIMEOUT_DEFAULT)),
    ("MCP config key", "hermes_cli/config.py",
     r'"(mcp_servers)"', constants.CONFIG_MCP_SERVERS),
]


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


def verify_facts(repo_dir: str, head: str) -> list[str]:
    """Extract each watched fact from upstream HEAD and flag any mismatch."""
    mismatches = []
    for label, path, pattern, expected in DRIFT_FACTS:
        content, err, code = git(repo_dir, "show", f"{head}:{path}")
        if code != 0:
            mismatches.append(
                f"{label}: could not read upstream {path} ({err or 'unknown error'})"
            )
            continue
        m = re.search(pattern, content)
        if not m:
            mismatches.append(f"{label}: pattern not found in upstream {path}")
            continue
        actual = m.group(1)
        if actual != expected:
            mismatches.append(
                f"{label}: upstream now `{actual}`, hermes-guide asserts `{expected}` "
                "(update constants.py and the matching SKILL.md)"
            )
    return mismatches


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

    fact_mismatches = verify_facts(repo_dir, head)

    if not log and not fact_mismatches:
        print(
            f"No drift: watched files unchanged and facts verified since baseline "
            f"{base[:7]} (HEAD {head[:7]})."
        )
        return 0

    sections = []
    if log:
        sections.append(
            "## Schema drift\n\n"
            f"Watched files changed since baseline `{base[:7]}`:\n\n"
            f"```\n{log}\n```"
        )
    if fact_mismatches:
        sections.append(
            "## Fact drift\n\n" + "\n".join(f"- {m}" for m in fact_mismatches)
        )
    sections.append(
        f"Compare: https://github.com/{UPSTREAM_REPO}/compare/{base[:7]}...{head[:7]}\n\n"
        "Review the changes and update `checks.py` / `constants.py` / the SKILL.md files "
        f"as needed. Then bump the baseline: edit `.github/upstream-drift.baseline` to `{head}`."
    )
    body = "\n\n".join(sections)

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo or os.environ.get("DRIFT_DRY_RUN") == "1":
        print("DRIFT DETECTED (dry-run, no issue opened):")
        print(body)
        return 0

    # Dedup: skip only if the canonical drift issue (exact title) is open. A
    # broad substring match could otherwise let an unrelated issue suppress a
    # real drift alert.
    proc = subprocess.run(
        [
            "gh", "issue", "list", "--repo", repo, "--state", "open",
            "--search", "Upstream schema drift", "--json", "number,title",
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
        issues = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("ERROR: gh issue list returned invalid JSON.", file=sys.stderr)
        return 1

    if any(i.get("title") == ISSUE_TITLE for i in issues):
        print("Drift issue already open; skipping duplicate.")
        return 0

    subprocess.run(
        ["gh", "issue", "create", "--repo", repo, "--title", ISSUE_TITLE, "--body", body],
        check=True,
    )
    print("Opened drift issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
