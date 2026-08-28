---
name: diagnosing-mcp
description: Diagnose Hermes MCP servers that will not connect, expose no tools, fail OAuth, or ignore config — with the exact config.yaml fields and hermes mcp commands to fix each.
version: 1.0.1
metadata:
  hermes:
    tags: [hermes, mcp, troubleshooting]
    related_skills: [hermes-configuration-guide]
---

# Diagnosing MCP Configuration

Goal: reduce any MCP problem to one concrete fix — a `mcp_servers:` entry in `$HERMES_HOME/config.yaml` (resolve with `hermes config path`) or a `hermes mcp` subcommand. Hermes registers server tools as `mcp__<server>__<tool>` and one runtime toolset per contributing server (`mcp-<server>`).

## 1. Configuration shape

```yaml
mcp_servers:
  filesystem:                      # stdio server
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  linear:                          # OAuth 2.1 HTTP server
    url: "https://mcp.linear.app/mcp"
    auth: oauth
```

Key fields: stdio → `command`, `args`, `env` (only these plus a safe baseline reach the subprocess); http → `url`, `headers`; mTLS → `client_cert` (PEM path or `[cert, key(, password)]`), `client_key`; timing → `timeout` (tool call, default 300s), `connect_timeout` (default 60s), `keepalive_interval`; recycling → `idle_timeout_seconds`, `max_lifetime_seconds`; `enabled` (default true); `supports_parallel_tool_calls`; `sampling`, `elicitation` (both default on). `${VAR}` in command/args/url/headers is expanded at connect time from the environment including `$HERMES_HOME/.env`.

Per-server tool filtering: `tools.include` (whitelist) / `tools.exclude` (blacklist, fnmatch globs allowed) — **`include` wins when both are set**; `tools.prompts: false` / `tools.resources: false` disable utility wrappers. If everything callable and all utilities are filtered out, Hermes creates no toolset for that server — by design.

## 2. How to inspect

- `hermes mcp` — interactive picker showing each server's status (available / enabled / installed (disabled)).
- `hermes mcp configure <name>` — re-probe the server and re-pick its tools.
- `hermes mcp login <name>` — run the OAuth flow with a full 5-minute wait.
- In chat: `/reload-mcp` reloads from config; `/context` shows the MCP token share.
- Edit config from a **fresh terminal** while a session is running: the in-session auto-reload only waits 30s.

## 3. Pitfalls (symptom → cause → fix)

1. **Server not listed at all** — YAML syntax error in `config.yaml` drops servers (or the whole file), or `enabled: false` skips the server entirely. → Validate YAML; set `enabled: true` or remove the field.
2. **`command not found` / spawn ENOENT** — `command` is not on PATH. On Windows point at the `.cmd`/`.exe` or use an absolute path; verify with `node --version` / `npx --version` in the same shell Hermes uses.
3. **Tools missing** — a `tools.include`/`exclude` filter removed them (include wins), or the server session lacks the capability (resource/prompt wrappers only register when the server supports them), or the server failed to connect so nothing registered. → Run `hermes mcp configure <name>`; check status in `hermes mcp`.
4. **OAuth never completes** — (a) config edited inside a running session: the 30s auto-reload kills the browser flow → run `hermes mcp login <name>` from a fresh terminal; (b) headless/remote host → use paste-back of the redirect URL, SSH port-forward, or `oauth.redirect_uri`; (c) WAF 403s loopback redirects → set `oauth.redirect_host: localhost`.
5. **OAuth login "works" but tool calls time out** — the provider rejects dynamic client registration (Google Drive, Atlassian): `tools/list` succeeds unauthenticated, so login looks fine but no token lands. → Create an OAuth client in the provider console and set `oauth.client_id` / `oauth.client_secret`, then `hermes mcp login <name>`.
6. **Tool call times out** — slow server startup. → Raise `timeout` / `connect_timeout` on that entry.
7. **Catalog entry stale after Hermes update** — catalog MCPs never auto-update. → Re-run `hermes mcp install <name>`.
8. **Claude-Code-style config pasted in** — `mcpServers` JSON or nested `mcp.servers` is not read. → Use top-level `mcp_servers:` in YAML (or `hermes import-agent claude-code`).

## 4. Localization workflow

1. `hermes config path` → open the file, confirm the entry exists under `mcp_servers:` and YAML parses.
2. `hermes mcp` → read the entry's status: absent → pitfall 1; disabled → enable it; present-but-failing → step 3.
3. Match the failure: ENOENT → 2; timeout → 6; OAuth → 4/5.
4. Check filters (pitfall 3) before blaming the connection.
5. Apply the fix, then `/reload-mcp` (or restart), and confirm the `mcp__<server>__*` tools appear (`/context`).
