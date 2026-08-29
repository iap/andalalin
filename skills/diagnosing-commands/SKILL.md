---
name: diagnosing-commands
description: Diagnose missing or overridden Hermes slash commands — skills as commands, skill bundles, plugin-registered commands, and per-platform admin/user permissions.
version: 1.0.2
metadata:
  hermes:
    tags: [hermes, commands, troubleshooting]
    related_skills: [hermes-configuration-guide]
---

# Diagnosing Slash Commands

Hermes has **no standalone custom-command files** (no `commands/*.md` directory like Claude Code). Every `/command` comes from exactly four sources, dispatched through one central registry (`hermes_cli/commands.py`) on two surfaces: the interactive CLI/TUI and the messaging gateway. Diagnose by identifying which source the command should come from.

## 1. The four sources

| Source | How it's created | Notes |
|---|---|---|
| **Built-in registry** | Ships with Hermes (`/model`, `/skills`, `/reload-mcp`, …) | Case-insensitive; see `/help` |
| **Skills** | Every installed skill is automatically `/<skill-name>` | The name comes from SKILL.md frontmatter, not the directory |
| **Skill bundles** | `hermes bundles create <name> --skill a --skill b` → `$HERMES_HOME/skill-bundles/<slug>.yaml` | Loads several skills at once; **a bundle wins a slug collision with a skill** |
| **Plugin commands** | `ctx.register_command(name, handler, description)` in a plugin | Only while that plugin is enabled |

Multiple leading `/skill` tokens stack (up to 5) in one message; parsing stops at the first token that isn't an installed skill, so argument paths like `/tmp/scan.pdf` are safe.

## 2. Pitfalls (symptom → cause → fix)

1. **`/my-skill` not found** — skill not discovered at all (wrong directory, missing/misnamed `SKILL.md`, shadowed by a local copy). → Follow **`diagnosing-skills`**; the command appears when discovery does (`/reload-skills`).
2. **Command name differs from the folder name** — the slash command uses the frontmatter `name`. → Reference the frontmatter name or rename it.
3. **`/name` loads the wrong thing** — a bundle with the same slug shadows the skill (intentional), or a local skill shadows an external one. → `hermes bundles list`; rename one of them.
4. **A plugin's command is missing** — the plugin is installed but not in `plugins.enabled`. → `hermes plugins enable <name>`; restart. Follow **`diagnosing-plugins`**.
5. **Command works in the CLI but not on Telegram/Discord/Slack** — each messaging platform can gate slash commands by role, **scoped separately for DMs and groups**: when `allow_admin_from` (or `group_allow_admin_from`) lists user IDs, admins get every command and non-admins get only `user_allowed_commands` (plus `/help`, `/whoami`); if **no** admin list is set for a scope, gating is **off** for that scope and every allowed user can run everything. → Set the keys in the platform's `extra:` block in `~/.hermes/config.yaml`, restart the gateway.
6. **Command exists but arguments vanish** — stacking parsing consumed what looked like a flag, or the command takes no args (e.g. `/plan` treats trailing text as its request). → Check the command's entry in `/help`; avoid leading `/` in arguments you want passed through.
7. **Aliases behave oddly** — many commands have aliases (`/reset`→`/new`, `/ctx`→`/context`); both dispatch identically. → Not a bug; check the canonical name in the reference.

## 3. Localization workflow

1. Type `/` and search the autocomplete — found? It's a dispatch/args issue (6/7). Not found? → step 2.
2. Which source should provide it? skill → **`diagnosing-skills`** (pitfall 1/2); bundle → `hermes bundles show <name>` (3); plugin → **`diagnosing-plugins`** (4); expected built-in → check `/help` and your Hermes version (`hermes version`; built-ins gain commands over releases).
3. Surface-specific failure (CLI works, gateway doesn't) → pitfall 5.
4. Apply the fix, `/reload-skills` or restart as appropriate, confirm via autocomplete or invocation.
