---
name: diagnosing-path
description: "Diagnose Hermes Agent path issues — the dual-venv layout (.venv/venv), how to detect which venv is active, the canonical resolution order, and best practices for code, scripts, and documentation that reference paths."
version: 1.1.0
metadata:
  hermes:
    tags: [hermes, path, venv, python, troubleshooting, guide]
    related_skills: [hermes-configuration-guide, diagnosing-cli-tui]
---

# Hermes Agent Path Diagnostics

This guide explains the dual-venv layout in Hermes Agent, how to detect which virtual environment is active, and the canonical resolution order. It applies to any code, script, or documentation that needs to reference paths in a Hermes Agent checkout.

## The Situation

Hermes Agent has a **dual-venv layout**: two directories can exist at the project root, both valid, with no single resolver in the core codebase.

| Directory | Origin | Python | Tool |
|---|---|---|---|
| `.venv/` | `uv venv` (uv's default) | 3.12.x | Current canonical |
| `venv/` | `python -m venv venv` or legacy install | 3.11.x | Legacy fallback |

Both can coexist. When they do, **`venv` wins**: upstream's own resolver picks it first, "matching what the installers write." A script that scans `.venv` first can therefore resolve a different interpreter than Hermes core does on the same checkout.

**Why this happened:** Older installs and some documentation used `python -m venv venv`. When uv became the default package manager, `uv venv` created `.venv`. Migration scripts didn't remove the old `venv/`, so both persist.

**Current state upstream:** `hermes_constants.py` ships `project_venv_dir(project_root)` (added 2026-08-19, commit `7a94b1f`), which resolves `venv` **before** `.venv` — its docstring: *"``venv`` wins when both exist, matching what the installers write."* It checks only `is_dir()` (no `pyvenv.cfg` validation), and callers decide whether a missing venv is an error. Before that commit, ~11 code sites in `hermes_cli/` hardcoded `PROJECT_ROOT / "venv"`, so `venv`-first matches both the new resolver and legacy behavior.

## Detection — Is a venv active?

When Python is running inside a virtual environment:

```python
import sys

def is_venv():
    """Return True if running inside a virtual environment."""
    return (
        hasattr(sys, "real_prefix")  # virtualenv
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)  # venv
    )

def active_venv_path():
    """Return the path to the active venv, or None if not in a venv."""
    if not is_venv():
        return None
    return sys.prefix
```

Shell detection:

```bash
# POSIX
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Active venv: $VIRTUAL_ENV"
else
    echo "No active venv"
fi

# Windows PowerShell
if ($env:VIRTUAL_ENV) {
    Write-Output "Active venv: $env:VIRTUAL_ENV"
} else {
    Write-Output "No active venv"
}
```

## Detection — Which venv directories exist?

```python
from pathlib import Path

def find_venv_dirs(project_root: Path) -> list[Path]:
    """Return existing venv directories in resolution order."""
    candidates = [project_root / "venv", project_root / ".venv"]
    return [c for c in candidates if c.is_dir() and (c / "pyvenv.cfg").exists()]
```

## Canonical Resolution Order

When resolving the venv path (for scripts, subprocess invocation, or path construction):

1. **`VIRTUAL_ENV` env var** — if set, this is the active venv. Trust it.
2. **`sys.prefix`** — if running inside a venv, this is the venv path.
3. **`project_venv_dir()`** — preferred: import it from `hermes_constants.py` rather than re-implementing the scan.
4. **`venv/`** — installer default; `project_venv_dir()` checks this first.
5. **`.venv/`** — uv default; only if `venv/` doesn't exist.
6. **None** — No venv found. The system Python is in use.

```python
import os
import sys
from pathlib import Path

def resolve_venv(project_root: Path | None = None) -> Path | None:
    """Resolve the active or canonical venv for a Hermes Agent checkout.

    Resolution order:
    1. VIRTUAL_ENV environment variable (if set and valid)
    2. sys.prefix (if running inside a venv inside the project)
    3. venv/ (installer default — project_venv_dir() resolves this first)
    4. .venv/ (uv default)
    5. None (system Python, no venv)

    Mirrors hermes_constants.py::project_venv_dir: candidates resolve on
    is_dir() alone, so a stray empty directory wins the same way it does
    upstream. Prefer importing project_venv_dir() when Hermes core is
    importable; use this replica outside the checkout.
    """
    # 1. Explicit override
    env_venv = os.environ.get("VIRTUAL_ENV")
    if env_venv:
        p = Path(env_venv)
        if p.is_dir() and (p / "pyvenv.cfg").exists():
            return p

    # 2. Running inside a venv
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        prefix = Path(sys.prefix)
        if prefix.is_dir() and (prefix / "pyvenv.cfg").exists():
            return prefix

    # 3 & 4. Check project root candidates — venv first, matching upstream
    root = project_root or Path.cwd()
    for name in ("venv", ".venv"):
        candidate = root / name
        if candidate.is_dir():
            return candidate

    # 5. No venv found
    return None
```

## Cross-platform path construction

**Never hardcode `venv/bin/` or `venv/Scripts/`.** Use `venv_bin_dir()` from `hermes_constants.py`:

```python
from hermes_constants import venv_bin_dir, project_venv_dir

venv = project_venv_dir(Path("/path/to/hermes-agent"))
if venv:
    python_path = venv_bin_dir(venv) / "python"
    # POSIX: /path/to/hermes-agent/venv/bin/python    (installer layout)
    #         /path/to/hermes-agent/.venv/bin/python  (uv layout, when venv/ absent)
    # Windows: C:\path\to\hermes-agent\venv\Scripts\python.exe
```

If `venv_bin_dir` is not available (outside Hermes core), replicate the logic:

```python
from pathlib import Path
import sys

def venv_bin_dir(venv_path: Path) -> Path:
    """Return the binary directory for a venv (Scripts/ on Windows, bin/ elsewhere)."""
    return venv_path / ("Scripts" if sys.platform == "win32" else "bin")
```

## Platform Reference

| Platform | Venv directory | Binary subdirectory | Python executable |
|---|---|---|---|
| macOS / Linux | `venv/` or `.venv/` | `bin/` | `python` |
| Windows | `venv/` or `.venv/` | `Scripts/` | `python.exe` |

## Best Practices

### For scripts

```python
# GOOD: resolve dynamically
from pathlib import Path
import sys

def get_venv_python(project_root: Path) -> Path | None:
    venv = resolve_venv(project_root)
    if venv is None:
        return None
    bin_dir = venv / ("Scripts" if sys.platform == "win32" else "bin")
    return bin_dir / ("python.exe" if sys.platform == "win32" else "python")

# BAD: hardcoded path
python = project_root / "venv" / "bin" / "python"  # Breaks on Windows, breaks on .venv-only checkouts
```

### For documentation

- **Do:** Reference `hermes config path` as the ground-truth command.
- **Do:** Resolve via `project_venv_dir()` from `hermes_constants.py` (it picks `venv/` before `.venv/`).
- **Do:** Mention both layouts — `venv/` (installers) and `.venv/` (uv).
- **Don't:** Hardcode either name alone, or document an activation path without noting the other layout.

```bash
# GOOD: probe order in documentation — venv first, matching project_venv_dir()
source venv/bin/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null || echo "No venv found"

# BAD: hardcoded single layout
source venv/bin/activate
```

### For CI and automation

```yaml
# GOOD: check both, venv first (matches project_venv_dir())
- name: Activate venv
  run: |
    if [ -d venv ]; then source venv/bin/activate
    elif [ -d .venv ]; then source .venv/bin/activate; fi
```

### For plugins and skills

Plugins run inside the Hermes installation's venv. Don't assume the venv name — use `sys.prefix` or `sys.executable`:

```python
import sys

# GOOD: wherever Python is running from
python_exe = Path(sys.executable)

# BAD: assuming .venv in the CWD
python_exe = Path.cwd() / ".venv" / "bin" / "python"  # May not be the running venv
```

## Troubleshooting

### "No module installed" but the package exists

The wrong venv is active. Check:

```bash
which python        # Should point inside .venv/ or venv/
python -c "import sys; print(sys.prefix)"  # Confirms active venv
```

### Both `.venv/` and `venv/` exist

Upstream's `project_venv_dir()` resolves `venv/` first, so scripts mirroring Hermes core pick `venv/` — which may be the stale one if this checkout is uv-managed. Don't guess: find the live one (e.g. `venv/bin/pip show hermes-agent` vs `.venv/bin/pip show hermes-agent`, or `hermes doctor`), then delete the stale directory to remove the ambiguity.

### Windows: "python" not found

Windows venvs use `Scripts\python.exe`, not `bin/python`. Use `venv_bin_dir()` or `sys.executable`.

## See Also

- `references/venv_detection_patterns.py` — copy-paste-ready detection functions
- Hermes core `hermes_constants.py` — `project_venv_dir()` (the resolver), `venv_bin_dir()`, `venv_python_path()`
- Hermes core `tools/skills_guard.py` — where the split causes false positives (issue #92376)
