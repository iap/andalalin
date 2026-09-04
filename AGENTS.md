# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project Overview

**hermes-guide** is a [Hermes Agent](https://github.com/NousResearch/hermes-agent) **plugin + skills tap**. The plugin (`plugin.yaml` + `__init__.py`/`checks.py`/`constants.py`) exposes read-only diagnostics (`/hermes-doctor` and `hermes guide`), and the `skills/` directory bundles nine SKILL.md files that teach agents and users how to configure and troubleshoot MCP servers, skills, commands, hooks, plugins, hub auth, paths/venvs, and the Windows CLI/TUI.

Two install paths: the plugin (`hermes plugins install iap/hermes-guide --enable`, or a git clone into `~/.hermes/plugins/hermes-guide/` + `hermes plugins enable hermes-guide`) and the tap (`hermes skills tap add iap/hermes-guide`).

## Repository Structure

| Path | Purpose |
|---|---|
| `plugin.yaml` | Plugin manifest (name, version, config schema) |
| `__init__.py` | Plugin entrypoint — registers `/hermes-doctor` and `hermes guide` (the nine skills ship separately via the skills tap) |
| `checks.py` | The six read-only health checks (config/mcp/skills/commands/hooks/plugins) |
| `constants.py` | Single source of truth for names/values that drift across Hermes versions |
| `skills/*/SKILL.md` | The nine skills (one map + eight diagnostics) |
| `tools/` | Guard linters (no-mutation, self-claim, version bump, upstream drift) + regression tests, all run by CI |
| `README.md` | Plugin + tap overview, install instructions, skill table |
| `AGENTS.md` | This file — agent instructions for working on the repo |
| `CLAUDE.md` | `@AGENTS.md` import (Claude Code entry point) |
| `.github/workflows/ci.yml` | CI — py_compile, mypy, `hermes plugins doctor . --ci`, guard linters, regression tests, bandit |
| `.github/workflows/upstream-drift.yml` | Weekly upstream drift watch (`tools/check_upstream_drift.py`) — opens an issue when Hermes changes watched schema files or drift-prone facts |
| `CONTRIBUTING.md` | Contribution guidelines |
| `CODE_OF_CONDUCT.md` | Contributor Covenant v2.1 |
| `SECURITY.md` | Security policy |
| `LICENSE` | MIT License |

## Guidelines

### Authoring skills

- Each skill lives in its own directory under `skills/<name>/SKILL.md`.
- **Naming convention**: `diagnosing-<surface>` for diagnostic skills (e.g. `diagnosing-mcp`, `diagnosing-path`). The `hermes-` prefix is reserved for the configuration map skill. Keep names kebab-case, lowercase, ≤20 characters.
- Frontmatter requires `name` (slug), `description` (keep it short), and `version` (semver).
- Content must be **verified against the installed Hermes source** (the local checkout or install location) — specifically `website/docs/` for documentation and `hermes_cli/` / `agent/` / `hermes_constants.py` for source truth. Do not rely solely on web search; the installed copy is authoritative for the version in use.
- Hermes configuration is **YAML** (`config.yaml`), not JSON. Never reference JSON config syntax.
- `$HERMES_HOME` resolves to `~/.hermes` on POSIX but `%LOCALAPPDATA%\hermes` on native Windows. Teach `hermes config path` as the ground-truth command.
- Every diagnosis must resolve to a concrete action: a `hermes <subcommand>` command or a specific file + field edit, then a `/reload-*` or restart to apply.
- When Hermes behavior changes, update the affected skill(s) and bump their `version`.

### Authoring plugin code

- `constants.py` is the single source of truth for names/values that drift across Hermes versions; update it (not `checks.py`) when an upstream name changes.
- Checks in `checks.py` must stay **read-only** — resolve paths, read files, parse, and shell out to read-only `hermes ...` commands. Never mutate config or auto-fix.
- A new check: add the function to `checks.py` and register it in the `_CHECKS` list. It must return an envelope (`status`, `reason`, `detail`) and tolerate malformed input without crashing.
- `plugin.yaml` `capabilities:` stays empty on purpose (zero privileged capabilities); don't add capabilities without a concrete need.

### Style

- Name the exact `hermes` command (e.g. `hermes config path`), not a generic description ("run the config command").
- Tables for structured data (pitfall catalogs, system comparisons). Bullet lists for steps.
- Keep each SKILL.md focused on one surface (MCP, skills, commands, hooks, plugins, or the config map).
- Use GitHub alert callouts where they genuinely help:
  > [!NOTE] — context not to miss
  > [!TIP] — optional shortcut
  > [!IMPORTANT] — required for success
  > [!WARNING] — breakage/data loss risk
  > [!CAUTION] — irreversible action

### Common pitfalls to avoid

> [!WARNING]
> **Don't confuse Hermes with Claude Code or ZCode**. Hermes has no standalone command files (commands come from built-ins, skills-as-slash, bundles, and plugins). Hooks have four separate systems, not one. Plugins use `plugin.yaml` + `register(ctx)`, not `plugin.json`.

> [!WARNING]
> **Don't copy zcode-guide patterns blindly** — Hermes differs structurally (commands, hooks, and plugin format are all different).

> [!IMPORTANT]
> **Don't guess hook event names**. The valid set lives in `hermes_cli/plugins.py:VALID_HOOKS` and grows across releases — verify against the installed source rather than a hardcoded count.

> [!NOTE]
> **Don't hardcode venv paths**. Hermes has a dual-venv layout: `venv/` (created by installers) and `.venv/` (uv's default) can coexist. Upstream's `project_venv_dir()` in `hermes_constants.py` resolves `venv` first — when both exist, `venv` wins. Resolve via `project_venv_dir()` / `venv_bin_dir()` from `hermes_constants.py`, or mirror that order; never assume either name. See the `diagnosing-path` skill for detection patterns, canonical resolution order, and cross-platform best practices.

### Testing and validation

CI enforces a syntax check, mypy, the plugin self-check, the `tools/` guard linters, and the `tools/` regression suite. Before declaring work complete:

1. Run `python -m py_compile __init__.py checks.py constants.py`.
2. Run `hermes plugins doctor . --ci` from the repo root.
3. Run the guard linters and regression tests: `python tools/check_no_mutation.py --selftest && python tools/check_no_mutation.py && python tools/check_self_claim.py`, then every `python tools/test_*.py`.
4. If you changed a `SKILL.md`, its `version` frontmatter must be bumped (`tools/check_skill_version_bump.py` enforces this against the merge base).
5. Read each changed SKILL.md back and confirm YAML frontmatter parses cleanly (three dashes, valid keys, no tab indentation in YAML).
6. Cross-check every `hermes <subcommand>` reference against the installed Hermes docs or `--help` output.
7. Verify `$HERMES_HOME` paths are correct for both POSIX and Windows.
8. State what was checked, what passed, and what was skipped.

Beyond the CI gates, smoke-test the *model-facing* behavior with a one-shot run — this verifies discovery AND that the skill's instructions are actually followed:

```bash
hermes -z "Use the diagnosing-path skill: which interpreter should a script in the Hermes checkout use?"
```

1. Run `python -m py_compile __init__.py checks.py constants.py`.
2. Run `hermes plugins doctor . --ci` from the repo root.
3. Read each changed SKILL.md back and confirm YAML frontmatter parses cleanly (three dashes, valid keys, no tab indentation in YAML).
4. Cross-check every `hermes <subcommand>` reference against the installed Hermes docs or `--help` output.
5. Verify `$HERMES_HOME` paths are correct for both POSIX and Windows.
6. State what was checked, what passed, and what was skipped.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution workflow, branch naming, commit message format, and content guidelines.
