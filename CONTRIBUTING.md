# Contributing

Thank you for your interest in contributing to hermes-guide!

## What this project is

hermes-guide is a [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin + skills tap. The plugin (`plugin.yaml` + `__init__.py`/`checks.py`/`constants.py`) ships read-only diagnostics (`/hermes-doctor` and `hermes guide`), and the `skills/` directory bundles six SKILL.md files that teach configuration and troubleshooting for MCP, skills, commands, hooks, and plugins.

## Reporting Issues

If a skill contains inaccurate guidance for a specific Hermes version, or is missing a known pitfall, please [open an issue](https://github.com/iap/hermes-guide/issues).

## Branch Naming

Short-lived branches, prefixed by type. Branch → merge to `master` → delete; never keep long-lived category buckets.

| Prefix | Use for |
|---|---|
| `fix/` | Defects (wrong behavior), e.g. `fix/mcp-key-constants` |
| `feat/` | Enhancements and refactors, e.g. `feat/plugin-hardening` |

Add a new prefix only when you actually need it (`docs/`, `chore/`, …).

## Skill naming convention

- `diagnosing-<surface>` for diagnostic skills (e.g. `diagnosing-mcp`, `diagnosing-path`).
- `hermes-` prefix reserved for the configuration map skill (`hermes-configuration-guide`).
- Kebab-case, lowercase, ≤20 characters.

## Pull Requests

1. Fork the repository.
2. Create a feature branch (`git checkout -b fix/diagnosing-mcp-oauth`).
3. Edit or add SKILL.md files under `skills/<name>/`, and/or the plugin files (`plugin.yaml`, `__init__.py`, `checks.py`, `constants.py`).
4. Verify frontmatter parses (valid YAML between `---` fences, `name`, `description`, `version`).
5. Run `python -m py_compile __init__.py checks.py constants.py` and `hermes plugins doctor . --ci`.
6. Cross-check every `hermes <subcommand>` reference against the installed Hermes docs or `--help` output.
7. Commit with a descriptive message and open a pull request.

## Content Guidelines

- Every diagnosis must resolve to a concrete action: a `hermes <subcommand>` or a specific file + field edit, then `/reload-*` or restart.
- Hermes configuration is YAML (`config.yaml`), never JSON.
- `$HERMES_HOME` is `~/.hermes` on POSIX, `%LOCALAPPDATA%\hermes` on native Windows. Teach `hermes config path` as ground truth.
- When Hermes changes behavior, update the affected skill(s) and bump their `version`.
- See [AGENTS.md](AGENTS.md) for the full set of agent instructions and false-positive hazards to avoid.

## Writing style

Describe behavior — don't assert quality. Docs should say what the plugin and skills *do*, not how good they are.

- ✅ "Skills track the Hermes source"
- ✅ "Checks report malformed bundles, missing plugins, and slug collisions"
- ❌ "The most reliable, fully accurate guide to Hermes"

CI enforces this with a self-claim guard over all Markdown files (`tools/check_self_claim.py`). The deny-list lives in that script. If it trips, reword the line to a factual description of behavior.

## Questions?

Open an issue and we'll help.
