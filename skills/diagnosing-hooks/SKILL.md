---
name: diagnosing-hooks
description: Diagnose Hermes hooks that do not fire — gateway HOOK.yaml hooks, plugin hooks, shell hooks stuck on consent, and outbound webhooks — using hermes hooks doctor.
version: 1.0.3
metadata:
  hermes:
    tags: [hermes, hooks, troubleshooting]
    related_skills: [hermes-configuration-guide]
---

# Diagnosing Hooks

Hermes has **four separate hook systems**. Most "my hook doesn't run" reports are a system/surface mismatch or a consent issue, not code. Identify the system first:

| System | Declared in | Runs in | Can block/inject |
|---|---|---|---|
| **Gateway hooks** | `$HERMES_HOME/hooks/<name>/HOOK.yaml` + `handler.py` (async `handle(event_type, context)`) | **Gateway only** — never fires in the CLI | Mostly observer — `command:*` can deny/rewrite/handle |
| **Plugin hooks** | `ctx.register_hook(<event>, cb)` in a plugin's `register()` | CLI + gateway | Yes (`pre_tool_call` block, `pre_llm_call` context, `pre_verify` continue) |
| **Shell hooks** | `hooks:` block in `config.yaml`, pointing at a script (convention: `$HERMES_HOME/agent-hooks/`) | CLI + gateway | Yes (same events as plugin hooks) |
| **Outbound webhooks** | `hooks.outbound:` list in `config.yaml` | CLI + gateway | No — HTTP push only, response ignored |

Valid hook-event names are the `VALID_HOOKS` set in `hermes_cli/plugins.py` (the count grows across releases — verify against the installed source rather than a hardcoded number). Gateway hooks use a **different** event vocabulary (`gateway:startup`, `session:start`, `session:end`, `session:reset`, `agent:start|step|end`, `command:*`, `reaction:*`).

## 1. Shell-hook essentials (the most common breakage)

```yaml
hooks:
  pre_tool_call:
    - matcher: "terminal"                  # regex; pre/post_tool_call only
      command: "~/.hermes/agent-hooks/scan.sh"
      timeout: 10                          # default 60, capped at 300
      fail_closed: true                    # pre_tool_call only; blocks on failure
```

Protocol: JSON payload on stdin, optional JSON response on stdout. Exit code **2** blocks the tool call (Claude-Code compatible). Block shapes: `{"decision": "block", "reason": ...}` or `{"action": "block", "message": ...}`; context injection: `{"context": "..."}` for `pre_llm_call`.

### Plugin-hook callback timeouts (how they fail)

Python plugin callbacks (`ctx.register_hook(cb)`) get a default **30s** wall-clock timeout
(`plugins.hook_callback_timeout` overrides it; hard cap 600s). How a timeout resolves depends
on the hook class:

| Hook class | On timeout |
|---|---|
| Policy hooks — `pre_tool_call` | **fail closed**: the tool is blocked (`pre_tool_call plugin callback timed out or is still running`) |
| Bounded hooks | **fail open**: the callback is abandoned, the agent continues |
| Low-frequency lifecycle hooks | intentionally unbounded |

After a timeout the same callback is suppressed for 60s, so a hung plugin cannot re-fire immediately.

**Consent gate**: each unique `(event, command)` pair prompts once, then persists to `$HERMES_HOME/shell-hooks-allowlist.json`. On non-TTY runs (gateway, cron, CI) an unapproved hook **silently stays unregistered** — bypass with `--accept-hooks`, `HERMES_ACCEPT_HOOKS=1`, or `hooks_auto_accept: true`, or hand-edit the allowlist (`approvals` array with exact `event` + `command` strings — a sha256-keyed object is the wrong format).

## 2. How to inspect

- `hermes hooks list` — configured shell + outbound hooks, consent status, signed/unsigned.
- `hermes hooks test <event> [--for-tool X] [--payload-file F]` — fire matching hooks against a synthetic payload; an invalid event name prints the valid set.
- `hermes hooks doctor` — per hook: exec bit, allowlist state, script mtime drift, JSON validity, rough runtime. Run this first for any shell-hook report.
- `hermes hooks revoke <command>` — remove allowlist entries.
- `hermes logs --follow` — hook errors are logged and isolated; a broken hook never crashes the agent (which also means it fails quietly).

## 3. Pitfalls (symptom → cause → fix)

1. **Hook never fires** — (a) gateway hook used in a CLI session (gateway-only); (b) shell hook not on the consent allowlist after a non-TTY start; (c) event name typo (config parse prints "Did you mean X?" and skips); (d) plugin providing it is disabled. → Match system to surface; `hermes hooks doctor`; `hermes plugins list`.
2. **Hook ran once, then edits do nothing** — consent keys on the exact command string; script edits are silently trusted, but if you changed the command in config it's a **new** pair needing fresh consent. → `hermes hooks list`; re-approve.
3. **Block not blocking** — exit code 2 or block JSON only works on `pre_tool_call`; a plugin-registered `pre_tool_call` may have blocked first (plugins register before shell hooks; first valid block wins); `fail_closed` on other events is ignored with a warning; a *timed-out* plugin `pre_tool_call` callback also blocks (policy hooks fail closed on timeout). → Scope the hook correctly.
4. **Hook times out** — timeouts over 300s are clamped; a slow script needs to be async. → Lower the work or raise `timeout` within the cap.
5. **Stdout produces nothing / agent warns about bad JSON** — print responses as single-line JSON (`printf '{"context": ...}'`); stack traces on stdout are unparseable. With `fail_closed: true` on `pre_tool_call`, non-JSON stdout **blocks** the call — intended.
6. **Outbound webhook not delivering** — endpoints are fire-and-forget with one retry on 5xx/connection errors, no redirects followed, bounded queue. → Check `hermes hooks list` (is it listed/signed?), receiver logs; use `secret_env` + verify `X-Hermes-Signature-256` (HMAC-SHA256) on the receiver.
7. **Gateway hook fires but handler errors** — handler must be named `handle`, take `(event_type, context)`, errors are caught and logged. → `hermes logs` and fix the handler.

## 4. Localization workflow

1. Which system? (directory hook → gateway; `hooks:` in config → shell; `hooks.outbound:` → webhook; plugin code → plugin hooks.)
2. Right surface? Gateway hooks need the gateway running (`hermes gateway status`).
3. `hermes hooks doctor` / `hermes hooks list` → consent, exec bit, drift (pitfalls 1, 2).
4. `hermes hooks test <event>` → behavior under a synthetic payload (3, 5).
5. Apply the fix, restart the session/gateway, re-test.
