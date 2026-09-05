---
name: hermes-configuration-guide
description: Map of Hermes Agent configuration — where MCP servers, skills, commands, hooks, and plugins live, and which diagnostic skill to load when something does not work.
version: 1.0.5
metadata:
  hermes:
    tags: [hermes, configuration, troubleshooting]
    related_skills: [diagnosing-mcp, diagnosing-skills, diagnosing-commands, diagnosing-hooks, diagnosing-plugins, diagnosing-path, diagnosing-cli-tui, diagnosing-memory, hermes-agent]
---

# Hermes Configuration Guide

This skill is the **map**: where each Hermes extension surface is configured, how conflicts resolve, and which `diagnosing-*` skill to load when something breaks. Hermes is configured in **YAML** (`config.yaml`), not JSON — if you are migrating from Claude Code or Cursor, `mcpServers` becomes `mcp_servers:` and `hermes import-agent claude-code` migrates servers, skills, and instructions automatically.

## Step 0 — Resolve $HERMES_HOME first

Never guess where Hermes reads its files. The home directory differs by platform and profile:

- **POSIX / WSL**: `~/.hermes`
- **Native Windows**: `%LOCALAPPDATA%\hermes` (e.g. `C:\Users\<you>\AppData\Local\hermes`) — `~/.hermes` may also exist there and is NOT the active home
- **Named profiles**: each profile has its own home; `hermes -p <profile> ...` and `HERMES_HOME=<dir>` override it
- **Two different things are called "platform" in this guide set**: the **operating system** (POSIX vs Windows — as above, and the `platforms:` frontmatter field in skills) and the **chat/messaging platform** (Telegram, Discord, Slack — in slash-command permissions and plugin `platforms/` sub-categories). Check which one a sentence means before acting.
- **Ground truth**: run `hermes config path` — it prints the active config file's full path. `hermes config show` dumps the merged config; `hermes config set <section.key> <value>` edits it safely.

## The five surfaces at a glance

| Surface | Configured in | Inspect with |
|---|---|---|
| **MCP servers** | `$HERMES_HOME/config.yaml` → `mcp_servers:` (stdio: `command`/`args`/`env`; http: `url`/`headers`) | `hermes mcp`, `/reload-mcp` |
| **Skills** | `$HERMES_HOME/skills/<category>/<name>/SKILL.md` (source of truth); extra dirs via `skills.external_dirs`; hub installs via `hermes skills` | `hermes skills list`, `/skills list`, `/reload-skills` |
| **Slash commands** | No standalone command files. Built-in registry + every installed skill (`/<skill-name>`) + skill bundles (`$HERMES_HOME/skill-bundles/*.yaml`) + plugin commands | Type `/` for autocomplete, `hermes bundles list` |
| **Hooks** | Four systems: gateway hooks (`$HERMES_HOME/hooks/<name>/HOOK.yaml` + `handler.py`, gateway-only); plugin hooks (`ctx.register_hook()`); shell hooks (`hooks:` block in config.yaml); outbound webhooks (`hooks.outbound:`) | `hermes hooks list / test / doctor` |
| **Plugins** | `$HERMES_HOME/plugins/<name>/` with `plugin.yaml` + `register(ctx)`; **opt-in** via `plugins.enabled` | `hermes plugins`, `/plugins` |

## Instruction files (a separate system)

- `SOUL.md` (`$HERMES_HOME/SOUL.md`) — agent persona, always loaded as prompt slot #1. You edit it.
- `USER.md` / `MEMORY.md` (`$HERMES_HOME/memories/`) — agent-written memory, injected as a **frozen snapshot at session start**; mid-session saves appear only next session. This is the usual cause of "it forgot what I just told it."
- Project context — exactly **one** per session, first match wins: `.hermes.md` → `AGENTS.md` → `CLAUDE.md` → `.cursorrules`, discovered from the working directory upward.

## Key $HERMES_HOME inventory

`config.yaml` (main config + `platforms:`/`gateway:` messaging settings) · `.env` (secrets; documented vars override config) · `gateway.json` (legacy gateway fallback) · `skills/` · `skill-bundles/` · `hooks/` (gateway hooks) · `agent-hooks/` (shell-hook script convention) · `plugins/` · `shell-hooks-allowlist.json` (shell-hook consent) · `mcp-tokens/` (OAuth caches) · `logs/` · `state.db` (sessions).

## Routing — when something is wrong

- MCP server not connecting, tools missing, OAuth failing → **`diagnosing-mcp`**
- A skill not discovered, not triggering, shadowed, or stuck "user-modified" → **`diagnosing-skills`**
- A `/command` missing, wrong, or overridden → **`diagnosing-commands`**
- A hook not firing, blocked consent, or behaving unexpectedly → **`diagnosing-hooks`**
- A plugin not loading, not enabled, or missing capabilities → **`diagnosing-plugins`**
- Auth/API failures on hub installs (`Could not fetch from any source`, GitHub 401, rate-limit 403) → **`diagnosing-auth`**
- Memory not persisting ("it forgot"), an external memory provider silently unavailable, or `MEMORY.md`/`USER.md` errors → **`diagnosing-memory`**
- Script/path/venv problems (wrong interpreter, `venv/bin/python` missing, the dual `.venv`/`venv` layout) → **`diagnosing-path`**
- Terminal/TUI issues on **native Windows** (misrendering, themes, indicators, launch failures) → **`diagnosing-cli-tui`**; on POSIX/WSL there is no dedicated skill yet — start with `hermes doctor` and the `display:` block of `config.yaml`

Every diagnosis should end in a concrete action: a `hermes <subcommand>` command or a specific file + field edit, then a restart or `/reload-*` to apply.
