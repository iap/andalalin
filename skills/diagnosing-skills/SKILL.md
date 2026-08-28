---
name: diagnosing-skills
description: Diagnose Hermes skills that are not discovered, not loading, shadowed, hidden by platform or toolset conditions, or stuck as user-modified after edits.
version: 1.0.1
metadata:
  hermes:
    tags: [hermes, skills, troubleshooting]
    related_skills: [hermes-configuration-guide]
---

# Diagnosing Skill Configuration

Goal: reduce any skill problem to one concrete fix. Distinguish **discovered** (appears in the index / as a `/command`) from **loading** (frontmatter parses) from **triggering** (the model chooses to use it) — they fail differently.

## 1. Where skills come from

- **Local (source of truth)**: `$HERMES_HOME/skills/<category>/<name>/SKILL.md`. Bundled skills are seeded here on install and on every `hermes update` (a `.no-bundled-skills` marker opts a profile out). Agent-created and hub-installed skills land here too.
- **External dirs**: `skills.external_dirs` in `config.yaml` (supports `~` and `${VAR}`). Non-existent paths are **silently skipped**. On a name collision, **local wins**. External dirs are not write-protected — the agent can edit skills found there.
- **Hub/taps**: `hermes skills install` (official / skills-sh / well-known / github / url / clawhub / lobehub / browse-sh), each recorded in `skills/.hub/lock.json` with provenance for `hermes skills check`/`update`.
- **Plugin-bundled**: `ctx.register_skill(name, path)` — namespaced `plugin:skill`; only available while that plugin is enabled.

## 2. SKILL.md format

`---` frontmatter requires `name` and `description` (house style: ≤60-char description, front-load trigger wording — the index shows name + description and that is what the model matches on). Optional: `version`, `platforms: [macos, linux, windows]`, `required_environment_variables`, and `metadata.hermes` — `tags`, `category`, and conditional activation `fallback_for_toolsets` / `requires_toolsets` / `fallback_for_tools` / `requires_tools`, plus `config` declarations (stored under `skills.config`, surfaced via `hermes config migrate`).

## 3. How to inspect

- `hermes skills list` / in chat `/skills list` — everything discovered, including source.
- `skills_list` / `skill_view(name)` agent tools — exactly what the model sees.
- `/reload-skills` — re-scan after adding/removing files on disk.

## 4. Pitfalls (symptom → cause → fix)

1. **Not discovered** — directory not under a real skills root, or the file is not named exactly `SKILL.md`. → Move to `$HERMES_HOME/skills/<category>/<name>/SKILL.md`; `/reload-skills`.
2. **Discovered as `/name` but name surprises you** — the slash command comes from the frontmatter `name`, not the directory name. → Align them or reference the frontmatter name.
3. **Edits to a shared/external copy never apply** — a same-named **local** skill shadows every external dir. → Edit the local copy, rename one, or delete the local shadow.
4. **Bundled skill stuck as "user-modified"** — you hand-restored a bundled skill by copy-paste; the `.bundled_manifest` origin hash no longer matches, so updates skip it forever. → `hermes skills reset <name>` (keep current) or `--restore` (pristine bundled copy). Per-profile.
5. **Skill hidden on this machine** — `platforms:` excludes the current OS, or conditional activation applies (`fallback_for_*` hides it when a toolset/tool IS available; `requires_*` hides it when one is NOT). → Check frontmatter; this hiding is intentional.
6. **Skill present but prompts for setup / fails at runtime** — `required_environment_variables` unset (local CLI prompts once; messaging surfaces never prompt). → Set the value in `$HERMES_HOME/.env` or run `hermes setup`.
7. **Agent's skill writes never land** — `skills.write_approval: true` stages every write under `$HERMES_HOME/pending/skills/`. → Review with `/skills pending`, `/skills diff <id>`, `/skills approve|reject <id>`; toggle the gate with `/skills approval off`.
8. **Hub skill drifted from upstream** — upstream changed after install. → `hermes skills check` then `hermes skills update [name]`.
9. **New bundled skills never appear** — profile has a `.no-bundled-skills` marker. → `hermes skills opt-in --sync`.
10. **Plugin skill gone** — the providing plugin was disabled. → `hermes plugins enable <name>`.

## 5. Localization workflow

1. `/reload-skills`, then `hermes skills list` — absent? → pitfalls 1, 5, 10, 9.
2. Present but wrong content? → check shadowing (3) and provenance (`hermes skills list --source hub`).
3. Present, correct, but the model ignores it? → description quality (2 §2): make the first ~60 characters state when to use it.
4. Agent-side write issues? → gate (7).
5. Apply the fix and verify with `skill_view(name)` or by invoking `/<name>`.
