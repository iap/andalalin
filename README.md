# Hermes Guide

> **Package / slug:** `hermes-guide`

Hermes usage and self-diagnosis guide for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It ships two things:

1. **A plugin** — `/hermes-doctor` (in-session) and `hermes guide` (terminal): read-only diagnostics across config, MCP servers, skills, commands, hooks, and plugins.
2. **Six troubleshooting skills** — teach an agent how to locate and fix each surface.

## Install the plugin

```bash
hermes plugins install iap/hermes-guide --enable
```

This clones the repo from GitHub and enables it. To pin an immutable commit:

```bash
hermes plugins install iap/hermes-guide --ref <40-char-SHA> --enable
```

### Manual install

Alternatively, copy this repo into your Hermes plugins directory:

```bash
# POSIX / WSL: $HERMES_HOME is ~/.hermes
cp -r . ~/.hermes/plugins/hermes-guide/
hermes plugins enable hermes-guide
```

On native Windows `$HERMES_HOME` is `%LOCALAPPDATA%\hermes` (not `~/.hermes`); run `hermes config path` to confirm.

## Usage

- In a session: `/hermes-doctor` (all surfaces) or `/hermes-doctor mcp` (one surface).
- In a terminal: `hermes guide` — exits `1` if any surface is broken.

### Proactive mode (opt-in)

Add to `config.yaml`:

```yaml
plugins:
  entries:
    hermes-guide:
      settings:
        proactive: true
```

Drift findings are then logged at session start/end — watch `hermes logs --follow`.

## Install the skills (tap)

Installing the plugin (above) does **not** list or install the skills — they ship
as separate, opt-in reference material. To make them appear under `hermes skills`,
add this repo as a skills tap, then install what you want:

```bash
hermes skills tap add iap/hermes-guide
hermes skills install iap/hermes-guide/skills/hermes-configuration-guide
```

The other five skills use the same `iap/hermes-guide/skills/<name>` form:
`diagnosing-mcp`, `diagnosing-skills`, `diagnosing-commands`, `diagnosing-hooks`, `diagnosing-plugins`.

> **Note:** the identifier must include the `skills/` prefix (it is the repo-relative
> path to the skill's `SKILL.md`). The shorter `iap/hermes-guide/<name>` form does not resolve.

Each installed skill is also available as a slash command (e.g. `/hermes-configuration-guide`).

## What's included

| Skill | Purpose |
|---|---|
| `hermes-configuration-guide` | The map: resolving `$HERMES_HOME`, where each surface is configured, instruction files, and routing to the diagnostic skills |
| `diagnosing-mcp` | MCP servers that won't connect, expose no tools, fail OAuth, or ignore `mcp_servers:` config |
| `diagnosing-skills` | Skills not discovered, shadowed, hidden by platform/toolset conditions, or stuck "user-modified" |
| `diagnosing-commands` | Missing or overridden slash commands — skills-as-commands, bundles, plugin commands, per-platform permissions |
| `diagnosing-hooks` | Hooks that don't fire — the four hook systems, shell-hook consent, `hermes hooks doctor` |
| `diagnosing-plugins` | Plugins that don't load — the `plugins.enabled` gate, capability consent, discovery locations |

## Design principle

Every diagnosis resolves to a concrete action: a `hermes <subcommand>` command or a specific file + field edit, then a `/reload-*` or restart to apply.

## Contributing

Skills track the Hermes Agent source and its shipped documentation (`website/docs/` in `hermes-agent`). When Hermes changes behavior, update the affected skill and bump its `version`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
