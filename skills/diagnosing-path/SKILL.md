---
name: diagnosing-path
description: "Diagnose Hermes Agent path issues — the dual-venv layout (.venv/venv), how to detect which venv is active, the canonical resolution order, and best practices for code, scripts, and documentation that reference paths."
version: 1.0.0
metadata:
  hermes:
    tags: [hermes, path, venv, python, troubleshooting, guide]
    category: guide
---

# Hermes Agent Path Diagnostics

This guide explains the dual-venv layout in Hermes Agent, how to detect which virtual environment is active, and the canonical resolution order. It applies to any code, script, or documentation that needs to reference paths in a Hermes Agent checkout.

## The Situation

Hermes Agent has a **dual-venv layout**: two directories can exist at the project root, both valid, with no single resolver in the core codebase.

| Directory | Origin | Python | Tool |
|---|---|---|---|
| `.venv/` | `uv venv` (uv's default) | 3.12.x | Current canonical |
| `venv/` | `python -m venv venv` or legacy install | 3.11.x | Legacy fallback |

Both can coexist. When they do, `.venv` wins (it's newer, managed by uv, and Python 3.12+).

**Why this happened:** Older installs and some documentation used `python -m venv venv`. When uv became the default package manager, `uv venv` created `.venv`. Migration scripts didn't remove the old `venv/`, so both persist.

**Current state upstream:** 15+ code sites in `hermes_cli/` hardcode `PROJECT_ROOT / "venv"`. There is no single `project_venv_dir()` resolver in `hermes_constants.py` (only `venv_bin_dir(venv_dir)` which requires you to already know the path). This is a known gap.

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
    candidates = [project_root / ".venv", project_root / "venv"]
    return [c for c in candidates if c.is_dir() and (c / "pyvenv.cfg").exists()]
```

## Canonical Resolution Order

When resolving the venv path (for scripts, subprocess invocation, or path construction):

1. **`VIRTUAL_ENV` env var** — if set, this is the active venv. Trust it.
2. **`sys.prefix`** — if running inside a venv, this is the venv path.
3. **`.venv/`** — uv's default. Check first.
4. **`venv/`** — Legacy fallback. Only if `.venv/` doesn't exist.
5. **None** — No venv found. The system Python is in use.

```python
import os
import sys
from pathlib import Path

def resolve_venv(project_root: Path | None = None) -> Path | None:
    """Resolve the active or canonical venv for a Hermes Agent checkout.
    
    Resolution order:
    1. VIRTUAL_ENV environment variable (if set and valid)
    2. sys.prefix (if running inside a venv inside the project)
    3. .venv/ (uv default, canonical)
    4. venv/ (legacy fallback)
    5. None (system Python, no venv)
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

    # 3 & 4. Check project root candidates
    root = project_root or Path.cwd()
    for name in (".venv", "venv"):
        candidate = root / name
        if candidate.is_dir() and (candidate / "pyvenv.cfg").exists():
            return candidate

    # 5. No venv found
    return None
```

## Cross-platform path construction

**Never hardcode `venv/bin/` or `venv/Scripts/`.** Use `venv_bin_dir()` from `hermes_constants.py`:

```python
from hermes_constants import venv_bin_dir

venv = resolve_venv(Path("/path/to/hermes-agent"))
if venv:
    python_path = venv_bin_dir(venv) / "python"
    # POSIX: /path/to/hermes-agent/.venv/bin/python
    # Windows: C:\path\to\hermes-agent\.venv\Scripts\python.exe
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
| macOS / Linux | `.venv/` | `bin/` | `python` |
| Windows | `.venv/` | `Scripts/` | `python.exe` |

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
python = project_root / "venv" / "bin" / "python"  # Breaks on Windows, breaks if .venv is canonical
```

### For documentation

- **Do:** Reference `hermes config path` as the ground-truth command.
- **Do:** Use `.venv/` as the canonical example (uv default).
- **Do:** Mention `venv/` as the legacy fallback.
- **Don't:** Write `source venv/bin/activate` without noting `.venv/` first.

```bash
# GOOD: probe order in documentation
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || echo "No venv found"

# BAD: hardcoded legacy only
source venv/bin/activate
```

### For CI and automation

```yaml
# GOOD: check both
- name: Activate venv
  run: |
    if [ -d .venv ]; then source .venv/bin/activate; fi
    if [ -d venv ] && [ ! -d .venv ]; then source venv/bin/activate; fi
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

`.venv` is canonical. Delete `venv/` if it's stale, or keep both — `.venv` wins by resolution order.

### Windows: "python" not found

Windows venvs use `Scripts\python.exe`, not `bin/python`. Use `venv_bin_dir()` or `sys.executable`.

## See Also

- `references/venv_detection_patterns.py` — copy-paste-ready detection functions
- Hermes core `hermes_constants.py` — `venv_bin_dir()`, `venv_python_path()`
- Hermes core `tools/skills_guard.py` — where the split causes false positives (issue #92376)
