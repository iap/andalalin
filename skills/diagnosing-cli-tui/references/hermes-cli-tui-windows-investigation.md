# Hermes Agent CLI/TUI — Windows (PowerShell 5.1 + Git Bash/mingw64) Investigation

**Date:** 2026-08-24 · **Scope:** Hermes Agent CLI/TUI on native Windows (Windows PowerShell 5.1 / conhost, PortableGit bash backend), cross-platform compatibility preserved
**Method:** Screenshot forensics (AutoGLM OCR + zoomed-crop re-verification), local install/source inspection, official docs review, upstream issue-tracker research

---

## 1. Verified baseline

| Item | Value | Evidence |
|---|---|---|
| Install | `C:\Users\iap\AppData\Local\hermes\hermes-agent` (git install, venv inside) | `hermes --version` |
| Version | **Hermes Agent v0.20.4 (2026.8.18)**, Python 3.12.13, OpenAI SDK 2.24.0 | `hermes --version` |
| Repo | origin `iap/hermes-agent` (fork), upstream `NousResearch/hermes-agent`, HEAD `13ce0c5c67` | `git remote -v`, `git log` |
| TUI frontend | `hermes-tui` — React 19 + custom Ink fork (`@hermes/ink`), esbuild bundle, `ui-tui/dist/entry.js`; launched as a Node subprocess from the Python CLI | `ui-tui/package.json`, TUI docs |
| TUI gateway | Python `tui_gateway/`; in-process gateway; optionally `HERMES_TUI_GATEWAY_URL` for the web dashboard's embedded chat | TUI docs |
| Shell | Windows PowerShell **5.1.19041.7663**, Windows 10 22H2 (build 19045), classic console host (conhost) window | screenshot title bar, `$PSVersionTable` |
| bash backend | PortableGit (MinGit, msys2-based) at `%LOCALAPPDATA%\hermes\git`, resolved via `HERMES_GIT_BASH_PATH`; fallback chain documented | Windows-native guide |
| Model in screenshot | `stealth/ox-alpha` via Nous inference API (1M context) — matches `config.yaml` `model.default` | config + screenshot rows |
| Config overrides | `display`: only `compact/personality/resume_display` set — skin, interface, indicator, mouse tracking all **defaults** | `%LOCALAPPDATA%\hermes\config.yaml` |
| Screenshot | 683×1009 px — narrow terminal window | image dims |

The screenshot shows the **TUI activity feed** (live per-event rows: checkbox/state glyph, kaomoji busy face, verb + per-row timer, `→ ox-alpha` model tag, `271K/1M` context tokens, progress bar, `26%`, `12m`), with a status line below.

---

## 2. Findings from your screenshot (forensics, per issue)

> Method note: the first full-image OCR reported "mojibake/tofu" glyphs. I re-verified with 3 zoomed crops. **The kaomoji are real rendered glyphs, not tofu boxes** — the earlier "Γûí/ΓÜí/><B<D" readings were OCR artifacts (the stylized faces are genuinely hard to read at 8–9 pt, which is itself a finding).

| # | Finding | Evidence | Severity |
|---|---|---|---|
| S1 | **Busy-indicator kaomoji faces are illegible/ambiguous.** Default indicator is `kaomoji`. Faces like `(>_<B)`-style render as real glyphs but read as gibberish at console font sizes; on conhost, any face glyph missing from Consolas degrades to an empty box. | crop OCR: every row `(>_<B)`-type face; `config_defaults.py`: `tui_status_indicator: kaomoji` | Medium (visual UX) |
| S2 | **Severe truncation from wide rows in a narrow window (683 px ≈ 88 cols).** Action text clipped (`musing...`), row tail `...`, status-line badge clipped mid-word (`Review hermes-llama Re...`). No minimum-width guard or graceful column collapse — instead it truncates **all** columns simultaneously. | crop row OCR; full-image status bar | Medium |
| S3 | **Per-row redundancy of session-level metrics.** `271K/1M` (context tokens), `26%`, `12m` are identical on **every** row — they're session state, not row state. Only the timer differs. ~45 sequential "musing…" rows with the same verb = a wall of near-identical lines; state changes are hard to spot. | full-image OCR (all rows identical tails) | Medium (information design) |
| S4 | **Overloaded color semantics.** Green is used for `✔` (done), the model tag, **and** the `26%`; cyan for the action text **and** the progress fill; no legend. On 16-color/lower-fidelity consoles these collapse together. | crop OCR color report | Low/Medium |
| S5 | **Leftmost column mixes meanings.** `[ ]`-style checkbox + state glyph + (crop shows `[✔XK@]`) — ambiguous semantics (selection? done? task icon?), truncated into each other. | crop OCR | Low |
| S6 | **Feed updates repaint the whole list at timer granularity.** ~45 rows × per-second timers = constant full-list diffs. On conhost (slower VT diff engine than Windows Terminal) this costs CPU and can feel jittery; the codebase already solves this class of problem for the shimmer clock (single shared interval, one batched render — see `loaders.tsx` comment referencing #20379), but row timers are per-row state. | source inspection | Low/Medium (perf) |
| S7 | **`PS >` prompt read by full-image OCR at bottom-left, below the TUI frame.** If the TUI had exited, the alt-screen should have been restored (no residue). Either the OCR misread the status/composer row, or conhost left a stale frame on exit. Worth one manual check (see §9). | full-image OCR | Unverified / Low |

**Net:** no broken rendering, but the feed is *noisy, truncated, and redundant* — the core UX issues are legibility (faces), horizontal budget, and per-row duplication of global state.

---

## 3. Platform issues — Windows PowerShell 5.1 / conhost

| # | Issue | Verified status | Optimal fix (no cross-platform break) |
|---|---|---|---|
| P1 | **conhost has no font fallback**: glyphs absent from Consolas render as boxes; emoji/kaomoji quality is poor. Your window is the classic conhost ("Windows PowerShell" title). | upstream docs confirm WT recommended; known issue #53301 (washed-out pet colors on Windows) | Install **Windows Terminal** (`winget install Microsoft.WindowsTerminal`) and a Nerd Font / Cascadia Code; OR switch indicator to ASCII (below). Terminal choice is outside Hermes — zero compat impact on other platforms. |
| P2 | **Code page churn**: Hermes sets CP_UTF8 (65001) for its own process (`hermes_cli/stdio.py::configure_windows_stdio`), but PS 5.1 itself and child Git Bash inherit different defaults; output piped/subprocess-captured can be mangled. | docs describe the shim; live: my own tooling hit cp1252 `UnicodeEncodeError` on this machine this session | Ensure `HERMES_DISABLE_WINDOWS_UTF8` is **not** set; in `~/.bashrc` of the Git Bash backend export `LANG=C.UTF-8 LC_ALL=C.UTF-8`; in PS 5.1 use `$OutputEncoding = [Text.UTF8Encoding]::new()` if you pipe `hermes` output. Prefer pwsh 7 + WT. |
| P3 | **PS 5.1 ANSI-internal encoding** for redirection/pipes breaks captured logs; also `irm | iex` BOM issue if you ever re-install via `[scriptblock]::Create`. | docs; upstream #27397 | Use `iex (irm …)` form; consider pwsh 7. |
| P4 | **Mouse tracking**: TUI default `display.mouse_tracking: all` enables SGR 1003 hover mode — conhost does not implement 1003 (partial 1000/1002 only) and conhost QuickEdit fights SGR mouse. | docs list presets & tmux caveats | `/mouse wheel` (1000+1006) on conhost, or `all` inside Windows Terminal. Persists to config. |
| P5 | **Light-theme auto-detection fails on conhost**: no `COLORFGBG`, and the OSC 11 background probe is unsupported in conhost (works on Ghostty/Warp/iTerm2/WezTerm/Kitty). A dark-background conhost may not be detected → wrong theme guess. | docs | Set `HERMES_TUI_THEME=dark` (or `light`) explicitly; or a raw 6-hex background. |
| P6 | **Clipboard/OSC52 + image paste** degrade on conhost; `Ctrl+V` works but clipboard-image fallback can't paste images into conhost; Kitty-graphics pet renders as placeholder grid (colors washed — upstream #53301). | docs describe 3-layer paste fallback; upstream issue | Run TUI in Windows Terminal; pet is decorative — ignore or set `/indicator ascii`. |
| P7 | **Node version ambiguity**: installer provisions Node 26 at `%LOCALAPPDATA%\hermes\node`, but a system Node on PATH can be older (TUI needs ≥20; `hermes doctor` checks). | docs pitfalls section | Keep Hermes's node dir first on PATH for Hermes sessions, or let Hermes manage it; use `HERMES_TUI_DIR` for prebuilt bundles (Nix/system packages) — already cross-platform. |
| P8 | **`/edit` / `Ctrl-X Ctrl-E`** defaults to `notepad` (blocking editor works, but is bare). | docs (pre-#21561 fix, `EDITOR=notepad`) | Set `EDITOR`/`VISUAL` to `code --wait` (or nvim/hx) at User scope. |
| P9 | **Git Bash (mingw64) backend quirks**: MSYS2 path translation (`/c/...`), `core.autocrlf` CRLF rewriting, and the known "exit 126 with empty output" class of failures (#14638, #20782 terminal/write_file). | upstream issues | Keep `HERMES_GIT_BASH_PATH` pointing at the **non-busybox** MinGit (`usr/bin/bash.exe`); if commands return 126/empty, run `hermes doctor` and check `git config core.autocrlf`; prefer the bundled bash over system Git for the agent. |
| P10 | **Antivirus false positives** on `uv.exe` (Bitdefender/Defender quarantine), documented by upstream with attestation verification steps. | README troubleshooting | Whitelist `%LOCALAPPDATA%\hermes\bin` folder (not file hash — uv updates). |

---

## 4. Upstream issues relevant to CLI/TUI (verified this session)

| Issue | Title / relevance |
|---|---|
| [#25418](https://github.com/NousResearch/hermes-agent/issues/25418) | Terminal resize → layout corruption (CLI/TUI) |
| [#19216](https://github.com/NousResearch/hermes-agent/issues/19216) | TUI resize → infinite render/scroll loop |
| [#12130](https://github.com/NousResearch/hermes-agent/issues/12130) | TUI v2 vs classic CLI parity: ~23/48 slash commands missing locally (overlays, @ refs, curses commands) |
| [#53301](https://github.com/NousResearch/hermes-agent/issues/53301) | TUI pet colors washed out on WSL/Windows |
| [#37637](https://github.com/NousResearch/hermes-agent/issues/37637) | `/usage` works via Telegram gateway, silent in CLI/TUI |
| [#19214](https://github.com/NousResearch/hermes-agent/issues/19214) | `terminal.cwd` is a foot-gun — one key controls cwd for CLI/TUI/gateway/cron/delegation. **Your config has `terminal.cwd: .`** — if you run the TUI from different directories this bites; pin it per-invocation or set it deliberately. |
| [#14638](https://github.com/NousResearch/hermes-agent/issues/14638) | Terminal tool exits 126 with empty output on Windows (Git Bash backend) |
| [#20782](https://github.com/NousResearch/hermes-agent/issues/20782) | `terminal` / `write_file` tools fail inside agent on Windows |
| [#83938](https://github.com/NousResearch/hermes-agent/issues/83938) | 8 test failures on Windows with non-UTF-8 ANSI codepage (cp949) — encoding-dependent test suite |
| [#18637](https://github.com/NousResearch/hermes-agent/issues/18637) | Windows 11 install: terminal execution fails exit 126 |
| [#27397](https://github.com/NousResearch/hermes-agent/issues/27397) | One-line install broken by UTF-8 BOM (fixed by stripping BOM) |
| [#25808](https://github.com/NousResearch/hermes-agent/issues/25808) | Feature: remote human-input bridge for in-flight CLI/TUI runs |
| [#18308](https://github.com/NousResearch/hermes-agent/issues/18308) | Copy/paste broken on GNOME (reference: paste path is terminal-dependent) |

Already-fixed upstream (do not re-report): `os.kill(pid,0)` → `CTRL_C_EVENT` footguns (14 sites, `_pid_exists()` + CI check `scripts/check-windows-footguns.py`), UTF-8 stdio shim, gateway `pythonw.exe` detached spawn, BOM-stripped installer.

---

## 5. Redundancy analysis (information design)

1. **Session metrics on every row** — context tokens (`271K/1M`), progress (`26%`), elapsed (`12m`) are global; render once (status line) and show *deltas* per row.
2. **Model tag per row** (`→ ox-alpha`) — session-level identity, repeated ~45×.
3. **Same-state rows** — ~45 consecutive `musing…` rows differ only in timer. Collapse to one row + `×N` counter (or group by phase), expand on state change. This is the single biggest readability win and costs nothing on other platforms.
4. **Status line duplicates the rows** — same tokens/time already on every row also appears in the status bar → three sources of the same data.
5. **Double truncation signals** — action `musing...` + tail `...` + clipped status badge: three places clip simultaneously instead of prioritizing.

---

## 6. Optimization opportunities (quick wins first)

1. **`/indicator ascii`** (or `unicode` = braille spinner) — instantly readable on conhost; persists via `display.tui_status_indicator` (default is `kaomoji`). Zero impact on other platforms.
2. **`HERMES_TUI_THEME=dark`** — bypass broken auto-detection on conhost (P5).
3. **`display.mouse_tracking: wheel`** (or `/mouse wheel`) — avoids 1003-hover conflicts in conhost/tmux and the "No image in clipboard" prompt-row spam documented in the TUI guide.
4. **Set a skin** — built-ins: `default`, `ares`, `mono`, `slate`, `daylight`, `warm-lightmode`, `poseidon`, `sisyphus`, `charizard`. For consoles: **`mono`** (clean grayscale, screen-recording safe) or **`slate`**. Live-preview with `/skin`. Persist via `display.skin`.
5. **Custom skin for Windows conhost** — `%LOCALAPPDATA%\hermes\skins\mytheme.yaml`: keep `spinner.thinking_faces`/`waiting_faces` within ASCII + common box-drawing (e.g. `(>_<)`, `(•_•)`, `(^_^)`), set `spinner.wings`, `tool_prefix: "│"`, and adjust `status_bar_bg` for your console palette. Missing keys inherit `default`. Save as **UTF-8 without BOM** (BOM inside folded YAML scalars silently breaks parsing — documented pitfall).
6. **`display.interface: tui`** + `HERMES_TUI_RESUME=1` — make bare `hermes` open the TUI and auto-reattach after dropped SSH/terminal sessions; `hermes --cli` still drops to classic REPL per-invocation (back-compat preserved).
7. **`/details collapsed`** / `display.sections.*` — the TUI streams thinking+tools expanded by default; for a calmer feed set `display.sections.thinking: collapsed` etc. This directly reduces the 45-row wall (S3).
8. **Editor**: `EDITOR=code --wait` (User env var) for `/edit` and `Ctrl-X Ctrl-E`.
9. **Terminal**: Windows Terminal + Nerd Font (or Cascadia Code) + pwsh 7; set a light/dark profile to match `HERMES_TUI_THEME`. This is the single largest *visual* improvement for the S1/S4/S6 class of issues.
10. **Perf**: use `HERMES_TUI_DIR` if a prebuilt bundle is shipped (skips prebuild); keep `ui-tui/node_modules` shared across git worktrees (documented); the shimmer-clock single-interval pattern (#20379) is the model for batching row timers if you patch the feed.
11. **Hermes Mod** (`npx -y hermes-mod`, community tool) — visual skin editor with logo/image→ASCII art conversion, writes to `~/.hermes/skins/` (honors `HERMES_HOME`).

### Recommended config delta for this machine (`%LOCALAPPDATA%\hermes\config.yaml`)

```yaml
display:
  interface: tui            # bare `hermes` opens the TUI
  skin: slate               # or mono; live-preview with /skin first
  tui_status_indicator: ascii   # readable on conhost; swap to kaomoji in WT
  mouse_tracking: wheel     # 1000+1006; `all` only inside Windows Terminal
  sections:
    thinking: collapsed     # quiet feed (matches "/details collapsed")
    tools: expanded
  details_mode: collapsed
terminal:
  cwd: "C:\\Users\\iap"     # be explicit; see upstream #19214
```

plus environment (User scope): `HERMES_TUI_THEME=dark`, `HERMES_TUI_RESUME=1`, `EDITOR=code --wait`; and in the Git-Bash backend `~/.bashrc`: `export LANG=C.UTF-8 LC_ALL=C.UTF-8`.

---

## 7. Cross-platform compatibility guardrails

- All fixes above are **config/env/terminal-side** — nothing changes code, so Linux/macOS/WSL behavior is untouched. Where code changes are proposed (row-timer batching, per-row metric dedup), they are pure rendering-layer changes in `ui-tui/` (Node) shared across OSes; keep PowerShell/conhost-specific behavior behind terminal capability detection (they already do this for OSC 11 / `COLORFGBG`).
- Windows-only paths must stay runtime-resolved: `HERMES_HOME` (`%LOCALAPPDATA%\hermes`) vs `~/.hermes` — never hardcode (your `hermes-llama` plugin's B3 finding is exactly this class of bug).
- Process liveness: use `psutil.pid_exists()` / `gateway.status._pid_exists()` — never `os.kill(pid, 0)` on Windows (`CTRL_C_EVENT` collision, bpo-14484; upstream CI blocks it).
- Invoke Node/npm shims as `.cmd` (`npx.cmd`, not `npx`) — `CreateProcessW` can't run extensionless shebangs (WinError 193).
- Shell tools must keep POSIX syntax — the agent's shell is Git Bash on Windows; MSYS2 path translation and `core.autocrlf` are the usual culprits for "works on Linux, fails here".
- Save any YAML/skin/config as UTF-8 **without BOM**.
- Terminal-independent fallbacks already exist: `/indicator unicode|ascii`, skins degrade to `default`, TUI falls back to classic CLI when Node/TTY is missing — preserve these paths.

---

## 8. Themes & styles quick reference (verified)

- **Skins** (`display.skin`, `/skin <name>`): colors (banner/UI/prompt/status/selection/completion), `spinner` (`waiting_faces`, `thinking_faces`, `thinking_verbs`, `wings`), `branding` (agent_name, prompt_symbol, help_header…), `tool_prefix`, `tool_emojis`, `banner_logo`/`banner_hero` (Rich markup ASCII art). Custom skins: `~/.hermes/skins/<name>.yaml`, inherit from `default`; user skins shadow built-ins. `display.py`/`skin_engine.py` hold defaults.
- **Busy indicator**: `display.tui_status_indicator` = `kaomoji` (default) | `emoji` | `unicode` (braille) | `ascii`; `/indicator <style>` live. Styles have matched glyph widths to avoid status-bar jitter.
- **Light detection**: `HERMES_TUI_THEME` (light|dark|6-hex) > `COLORFGBG` > OSC 11 probe.
- **TUI layout knobs**: `display.sections.{thinking,tools,subagents,activity}`, `details_mode`, `/details`, `display.mouse_tracking`, `display.compact` (yours is `false`).
- **Status line**: live/queued states, cwd+git branch (mtime-cached), `⏱/⏲` elapsed, 🗜 auto-compress count, ▶ background tasks, ⚠ YOLO badge.

---

## 9. Verification steps for you (2 minutes)

```powershell
# 1. confirm the console situation
$PSVersionTable.PSVersion        # 5.1 → consider pwsh 7
[Console]::OutputEncoding        # should be UTF-8 (65001) inside hermes
Get-Command hermes | Select Source

# 2. confirm TUI basics + apply fixes
hermes --version
hermes doctor                    # Node ≥20, git bash, deps
hermes --tui --dev               # run with visible diagnostics if launch oddness
# inside the TUI:
/indicator ascii                 # fix S1 immediately
/skin slate                      # live preview; pick your favorite
/mouse wheel                     # conhost-safe mouse
/details collapsed               # quiet the feed (S3)
/usage                           # if this is silent, you hit upstream #37637

# 3. window-resize sanity (upstream #25418/#19216)
# shrink → enlarge the window; if layout corrupts or render spins, note the
# reproduction and file/upvote the upstream issue.

# 4. exit-cleanliness check (S7)
# quit the TUI (Ctrl+D or /exit) — conhost should restore a CLEAN prompt with
# no residual TUI frame. If you see leftover rows, that's an alt-screen
# restore bug on conhost worth reporting with your exact terminal host.
```

---

## 10. Sources (all accessed this session)

- Docs (hermes-agent.nousresearch.com): [TUI](/docs/user-guide/tui), [CLI](/docs/user-guide/cli), [Windows Native](/docs/user-guide/windows-native), [Configuration](/docs/user-guide/configuration), [Skins & Themes](/docs/user-guide/features/skins), [FAQ](/docs/reference/faq) — saved as extracted text under `tmp-doc-*.txt` during the session
- Repo README (NousResearch/hermes-agent, fetched)
- Local source: `ui-tui/` (`package.json`, `src/content/verbs.ts`, `src/components/loaders.tsx`, `src/theme.ts`, `src/app/usePet.ts`), `hermes_cli/config_defaults.py`, `hermes_cli/skin_engine.py`, `tui_gateway/`
- Upstream issues: #25418, #19216, #12130, #53301, #37637, #19214, #14638, #20782, #83938, #18637, #27397, #25808, #18308
- Local config: `%LOCALAPPDATA%\hermes\config.yaml` (display/model/terminal keys only)
- Screenshot forensics: full-image OCR + 3 zoomed crops (`crops/*.png` + JSON results)