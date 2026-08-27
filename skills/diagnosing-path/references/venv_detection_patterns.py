"""Virtual environment detection patterns for Hermes Agent.

Copy-paste-ready functions for scripts and plugins that need to detect
which venv is active, or whether a venv exists in a project.
"""

import os
import sys
from pathlib import Path
from typing import Optional


def is_venv_active() -> bool:
    """Return True if the current Python is running inside a virtual environment."""
    return (
        hasattr(sys, "real_prefix")  # virtualenv
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)  # venv
    )


def active_venv_path() -> Optional[Path]:
    """Return the path to the active venv, or None if not in a venv."""
    if not is_venv_active():
        return None
    prefix = Path(sys.prefix)
    if prefix.is_dir() and (prefix / "pyvenv.cfg").exists():
        return prefix
    return None


def find_venv_dirs(project_root: Path) -> list[Path]:
    """Return existing venv directories in canonical resolution order.
    
    Checks `.venv` (uv default, canonical) first, then `venv` (legacy).
    """
    candidates = [project_root / ".venv", project_root / "venv"]
    return [c for c in candidates if c.is_dir() and (c / "pyvenv.cfg").exists()]


def resolve_venv(project_root: Optional[Path] = None) -> Optional[Path]:
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
    if is_venv_active():
        prefix = active_venv_path()
        if prefix is not None:
            return prefix

    # 3 & 4. Check project root candidates
    root = project_root or Path.cwd()
    for name in (".venv", "venv"):
        candidate = root / name
        if candidate.is_dir() and (candidate / "pyvenv.cfg").exists():
            return candidate

    # 5. No venv found
    return None


def venv_bin_dir(venv_path: Path) -> Path:
    """Return the binary directory for a venv.
    
    Windows uses Scripts/, POSIX uses bin/.
    """
    return venv_path / ("Scripts" if sys.platform == "win32" else "bin")


def venv_python_path(venv_path: Path) -> Path:
    """Return the path to the Python executable inside a venv."""
    bin_dir = venv_bin_dir(venv_path)
    exe = "python.exe" if sys.platform == "win32" else "python"
    return bin_dir / exe


def activate_venv_command(venv_path: Path) -> str:
    """Return the shell command to activate a venv (for scripts/docs)."""
    if sys.platform == "win32":
        return f"{venv_path / 'Scripts' / 'activate.bat'}"
    else:
        # Quote the path to handle spaces and shell metacharacters safely
        import shlex
        activate = venv_path / "bin" / "activate"
        return f"source {shlex.quote(str(activate))}"


def probe_shell() -> Optional[Path]:
    """Detect the active venv from shell environment (when not inside Python).
    
    Returns None if no venv is active.
    """
    env_venv = os.environ.get("VIRTUAL_ENV")
    if env_venv:
        p = Path(env_venv)
        if p.is_dir() and (p / "pyvenv.cfg").exists():
            return p
    return None


if __name__ == "__main__":
    print(f"Python: {sys.executable}")
    print(f"In venv: {is_venv_active()}")
    print(f"Active venv: {active_venv_path()}")
    
    root = Path("/Users/iap/.hermes/hermes-agent")
    print(f"\nProject root: {root}")
    print(f"Venv dirs found: {find_venv_dirs(root)}")
    print(f"Resolved venv: {resolve_venv(root)}")
    
    venv = resolve_venv(root)
    if venv:
        print(f"Bin dir: {venv_bin_dir(venv)}")
        print(f"Python: {venv_python_path(venv)}")
        print(f"Activate: {activate_venv_command(venv)}")
    
    # Verify quoting works for paths with spaces
    test_venv = Path("/tmp/test path/venv")
    print(f"\nQuoted activate (space in path): {activate_venv_command(test_venv)}")
