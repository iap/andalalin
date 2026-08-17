---
name: diagnosing-plugins
description: Diagnose Hermes plugins that do not load or run — the plugins.enabled opt-in gate, capability consent, discovery locations, and provider sub-categories.
version: 1.0.0
metadata:
  hermes:
    tags: [hermes, plugins, troubleshooting]
    category: guide
---

# Diagnosing Plugins

A Hermes plugin is a **Python package**: a directory with a `plugin.yaml` manifest and a `register(ctx)` function. The single most common failure: **the plugin is discovered but not enabled** — Hermes deliberately loads nothing from third-party code until you add it to `plugins.enabled`.

## 1. Discovery locations (later sources override same-name earlier ones)

| Source | Path | Gate |
|---|---|---|
| Bundled | `<install>/plugins/` | Platform/backend sub-plugins auto-load; bundled standalone plugins still need opt-in |
| User | `$HERMES_HOME/plugins/<name>/` | `plugins.enabled` allow-list |
| Project | `<repo>/.hermes/plugins/` | Requires `HERMES_ENABLE_PROJECT_PLUGINS=true` at startup |
| pip | `hermes_agent.plugins` entry points | `plugins.enabled` |
| Nix | `services.hermes-agent.extraPlugins` | Nix config |

`hermes plugins install owner/repo [--ref <40-char SHA>] [--enable|--no-enable]` installs from Git (pinned commits only); `hermes plugins update` refuses to move a pinned plugin. Sub-category directories have their **own loaders and selection keys** — they do not obey `plugins.enabled`: `platforms/<name>/` (channels, gated per-platform in config), `memory/<name>/` (one active, `memory.provider`), `context_engine/<name>/` (`context.engine`), `model-providers/<name>/` (picked via `--provider`/config), `image_gen/<name>/` (`image_gen.provider`).

## 2. The enable gate and capabilities

```yaml
plugins:
  enabled: [my-plugin]
  disabled: [noisy-plugin]   # deny-list always wins over enabled
```

Three ways to flip: `hermes plugins` (interactive), `hermes plugins enable <name>`, `hermes plugins disable <name>`. Declared capabilities (`tools.override`, `llm.model_override`, `gateway.platform_actions`, …) require a separate one-time consent recorded under `plugins.entries.<id>.granted_capabilities`; **non-interactive installs/enables grant nothing** — a plugin then runs with capabilities off and must degrade gracefully (`ctx.has_capability()`).

## 3. How to inspect

- `hermes plugins` — interactive UI (SPACE toggles enabled).
- `hermes plugins list` — enabled / disabled / not-enabled per plugin.
- `hermes plugins capabilities [name]` — declared vs granted.
- `/plugins` in chat — status listing.
- `hermes logs --follow` — a plugin whose `register()` raises is skipped with a logged error (never crashes Hermes), so read the log for load failures.

## 4. Pitfalls (symptom → cause → fix)

1. **Installed but tools/hooks/commands absent** — not in `plugins.enabled` (install defaults to disabled; `--enable` or the post-install prompt is opt-in). → `hermes plugins enable <name>` and restart. Bundled standalone plugins are opt-in too — only platform/backend sub-plugins auto-load.
2. **Plugin works but a privileged feature is off** — capability declared but never granted (non-TTY install, or declined). → `hermes plugins capabilities <name>`; re-consent via interactive `hermes plugins enable <name>`.
3. **Project plugin ignored** — `.hermes/plugins/` is disabled by default. → Set `HERMES_ENABLE_PROJECT_PLUGINS=true` before starting Hermes, and only for trusted repos.
4. **Plugin in `list` but nothing loads at all** — `register()` raised (bad code, missing dependency). → Check `hermes logs` for the load error; fix the plugin or its requirements.
5. **Edits to a bundled plugin don't apply** — a same-name user plugin at `$HERMES_HOME/plugins/<name>/` overrides the bundled copy. → Edit the user copy (the one that actually wins) or remove it.
6. **`hermes plugins update` refuses** — the install is pinned to an exact commit SHA. → Choose a new commit explicitly: `hermes plugins install <source> --force --ref <new-sha>`.
7. **Plugin edits after install lost on update** — updates autostash and re-apply local edits, but conflicts can drop them. → Keep plugin customizations in your own fork/repo and install from that.
8. **It's not really a plugin** — TTS/STT command providers are config-driven (`tts.providers.<name>` / `stt.providers.<name>` with `type: command`); MCP integrations are `mcp_servers:` entries; gateway hooks are directories. → Route to the right surface: **`diagnosing-mcp`**, **`diagnosing-hooks`**, or the config docs.

## 5. Localization workflow

1. `hermes plugins list` — is it discovered? No → wrong location / not installed (§1 table; project plugins → pitfall 3).
2. Discovered but "not enabled" → pitfall 1 (`hermes plugins enable`).
3. Enabled but broken → `hermes logs` for a `register()` failure (pitfall 4) or a capability gap (pitfall 2).
4. Sub-category plugin (memory/context/model-provider/platform) → check its selection key in config, not `plugins.enabled`.
5. Restart the session/gateway and verify: tools appear in `/tools list`, commands in `/` autocomplete, hooks via `hermes hooks list`.
