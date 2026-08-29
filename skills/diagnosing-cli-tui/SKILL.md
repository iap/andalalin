---
name: diagnosing-cli-tui
description: "Diagnose and fix Hermes Agent CLI/TUI issues on native Windows (PowerShell/conhost, Git Bash backend): rendering artifacts, themes/skins, busy indicators, mouse modes, encoding, and launch/resume."
version: 1.0.5
metadata:
  hermes:
    tags: [hermes, tui, cli, windows, themes, troubleshooting, diagnosing]
    related_skills: [hermes-cli-tui-output-artifacts, hermes-configuration-guide]
---

# Diagnose Hermes CLI/TUI (Windows)

Playbook for running and fixing the Hermes Agent CLI/TUI on this machine.
Use when the TUI misrenders, truncates, shows unreadable indicators, fails
to launch, or when asked how to theme/skin Hermes on Windows.

## 0. Environment baseline (origin machine: one Windows box, verified 2026-08-24)

> [!CAUTION]
> This baseline records **one specific Windows machine** — the box this skill was written on. It is **not** a description of your machine. Before applying anything below, confirm the local environment with `hermes config path`, `hermes --version`, and `hermes doctor`; paths, `HERMES_HOME`, shell, and OS differ per machine (on macOS/Linux the **default** home is `~/.hermes` — overridable via `HERMES_HOME` or a named profile; `hermes config path` always prints the active one).

- Hermes Agent v0.20.4, git install: `%LOCALAPPDATA%\hermes\hermes-agent` (venv inside)
- `HERMES_HOME = %LOCALAPPDATA%\hermes` (native Windows; `~/.hermes` is NOT the active home)
- OS: Windows 10 Home 22H2 (build 19045.7663)
- Shell: Windows PowerShell 5.1; console host: conhost (classic window) or Windows Terminal 1.24 (installed)
- Tool shell backend: PortableGit (MinGit, msys2) bash - resolved via `HERMES_GIT_BASH_PATH` or `%LOCALAPPDATA%\hermes\git\usr\bin\bash.exe` (non-busybox variant)
- TUI frontend: Node app `hermes-tui` (React 19 + custom Ink fork), launched as a subprocess of the Python CLI; Node >= 20 required
- Ground truth commands: `hermes config path`, `hermes config show`, `hermes --version`, `hermes doctor`

## 1. Launch and resume

```powershell
hermes              # classic CLI by default; launches TUI when display.interface: tui
hermes --tui        # force TUI
hermes --tui -c     # resume latest TUI session (or HERMES_TUI_RESUME=1 / display.tui_auto_resume_recent: true)
hermes --cli        # force classic REPL for one invocation
```

Applied on the origin machine (config.yaml, backup: `config.yaml.bak-20260824-0457`):

```yaml
display:
  interface: tui
  tui_status_indicator: ascii
  mouse_tracking: wheel
  details_mode: collapsed
```

`display.tui_auto_resume_recent` is **false** (fresh session per launch). If `hermes` ever opens a previous chat instead of a fresh session, check that key or `HERMES_TUI_RESUME=1`; resume on demand with `hermes --tui -c` (`--resume <id>` for a specific session).

User env vars: `EDITOR=code --wait`, `HERMES_TUI_THEME=dark`.

## 2. In-TUI slash commands that fix rendering

| Command | Effect |
|---|---|
| `/indicator ascii` | Readable busy indicator (default is `kaomoji`, can be hard to read on conhost). Styles: kaomoji, emoji, unicode (braille), ascii. Persist: `display.tui_status_indicator` |
| `/skin <name>` | Live theme preview. Built-ins: default, ares, mono, slate, daylight, warm-lightmode, poseidon, sisyphus, charizard. Persist: `display.skin` |
| `/mouse wheel` | Mouse preset 1000+1006 (scroll + click, no hover). `all` includes 1003 hover - unsupported on conhost. Persist: `display.mouse_tracking` |
| `/details collapsed` | Quiet feed: fold thinking/tools under chevrons. Persist: `display.details_mode` or `display.sections.<section>: collapsed` |
| `/usage` | Token/cost panel. If silent in TUI, see upstream #37637 |
| `/exit` | Quit; conhost should restore a clean prompt (no residual frame) |

## 3. Skins & themes (style system)

- Skins live at `$HERMES_HOME/skins/<name>.yaml`; user skins inherit missing keys from `default`
- Keys: `colors` (banner_*, ui_*, prompt, input_rule, response_border, session_*, status_bar_bg, voice_status_bg, selection_bg, completion_menu_*), `spinner` (waiting_faces, thinking_faces, thinking_verbs, wings), `branding` (agent_name, response_label, prompt_symbol, help_header...), `tool_prefix`, `tool_emojis`, `banner_logo` / `banner_hero` (Rich markup ASCII art)
- Built-in skins load from `hermes_cli/skin_engine.py`; unknown skins fall back to `default`
- Consoles with poor glyph coverage: prefer ASCII-ish faces (e.g. `(>_<)`, `(^_^)`, `(o_o)`) and box-drawing `tool_prefix` like `|`
- Save skin YAML as UTF-8 WITHOUT BOM (a BOM inside a folded YAML scalar silently breaks parsing)
- Visual editor: `npx -y hermes-mod` (community tool; honors HERMES_HOME)
- Light-terminal detection: `HERMES_TUI_THEME` (light|dark|6-hex) > `COLORFGBG` > OSC 11 probe (OSC 11 not supported on conhost - set the env var explicitly)

## 4. Windows-specific troubleshooting

1. **Mojibake / garbled output**: Hermes forces UTF-8 via `hermes_cli/stdio.py::configure_windows_stdio()` (sets CP_UTF8, PYTHONUTF8=1, PYTHONIOENCODING=utf-8). Do NOT set `HERMES_DISABLE_WINDOWS_UTF8`. If tool output from the Git Bash backend is garbled, set `LANG=C.UTF-8` / `LC_ALL=C.UTF-8` for that bash (msys2 reads Windows env). PS 5.1 pipes: `$OutputEncoding = [Text.UTF8Encoding]::new()`.
2. **Missing glyphs / tofu faces**: conhost has no font fallback. Fixes: Windows Terminal + Cascadia Mono, or `/indicator ascii`.
3. **Editor silent (`/edit`, Ctrl-X Ctrl-E)**: Hermes defaults `EDITOR=notepad`. Set `EDITOR=code --wait` (Cursor/VS Code shim works). Never point at an editor that returns immediately without `--wait`.
4. **WinError 193 (%1 is not a valid Win32 application)**: invoking an extensionless shebang script. Always use the `.cmd` shim (`npx.cmd`, not `npx`).
5. **Process liveness**: never `os.kill(pid, 0)` on Windows (maps to CTRL_C_EVENT, bpo-14484). Use `psutil.pid_exists()` / `gateway.status._pid_exists()`.
6. **Gateway at login**: `hermes gateway install` uses schtasks (ONLOGON, no admin), spawns via pythonw.exe with DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW.
7. **Antivirus flags uv.exe**: false positive; whitelist the `%LOCALAPPDATA%\hermes\bin` folder (hash changes each upgrade). Verify authenticity via `gh attestation verify` (see README).
8. **Installer BOM**: `iex (irm ...)` strips BOM; `[scriptblock]::Create((irm ...))` does not.
9. **Config schema drift**: `hermes config set` flags `display.mouse_tracking` and `display.details_mode` as unrecognized - they ARE valid TUI keys (documented); values save and are read anyway. Do not delete them.

## 5. Known upstream issues (check before re-reporting)

- #25418 / #19216 - terminal resize corrupts TUI layout / infinite render loop
- #12130 - TUI v2 parity gaps vs classic CLI (~23/48 slash commands, overlays, @ refs)
- #53301 - TUI pet colors washed out on WSL/Windows (Kitty-graphics fallback)
- #37637 - /usage silent in CLI/TUI (works on Telegram)
- #19214 - `terminal.cwd` controls cwd for CLI/TUI/gateway/cron/delegation (one key, easy foot-gun)
- #14638 / #20782 - Windows Git Bash backend: exit 126, terminal/write_file tool failures
- #83938 - test_profiles.py fails on Windows with non-UTF-8 codepages

## 6. Cross-platform guardrails

- Prefer config/env fixes (work identically on POSIX); keep path logic runtime-resolved via `HERMES_HOME`
- Never hardcode `C:\...` paths in skills/plugins - use `%LOCALAPPDATA%\hermes` on Windows, `~/.hermes` elsewhere
- Shell commands issued by the agent keep POSIX syntax (the Windows backend is Git Bash); mind MSYS2 path translation and `core.autocrlf`
- Skins degrade to `default`; unknown indicator styles fall back; TUI falls back to classic CLI when Node/TTY is missing - preserve these fallbacks

## 7. Verification checklist

```powershell
hermes --version; hermes doctor      # Node >= 20, bash, deps
hermes config get display            # confirm keys above
hermes skills list                   # this skill should appear (hub or local, enabled)
# in TUI: /indicator ascii; /skin slate; /mouse wheel; /usage; /exit
```

Deep-dive reference: the original investigation with screenshot forensics,
redundancy analysis, and full source evidence lives at
`references/hermes-cli-tui-windows-investigation.md` in this skill's directory.
