"""Deterministic, read-only health checks.

Every check returns an envelope:

    {"status": "healthy" | "informational" | "broken" | "unknown",
     "reason": str, "detail": ...}

- `healthy`       — nothing to act on.
- `informational` — intentional/expected state worth a glance (e.g. a plugin
  discovered but not opted in). Not a failure.
- `broken`        — something that will cause real breakage.
- `unknown`       — could not determine (path/env unavailable).

Checks are read-only by design: they resolve paths, read files, parse them, and
shell out to `hermes ... doctor`-style read-only commands. They never mutate
config, enable/disable anything, or auto-fix.
"""

import json
import os
import subprocess

import yaml

from . import constants


def _run(cmd, timeout=20):
    """Run a subprocess; return (returncode, stdout, stderr) as separate strings."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        return out.returncode, out.stdout or "", out.stderr or ""
    except FileNotFoundError:
        return -127, "", f"{cmd[0]}: command not found on PATH"
    except Exception:
        return -1, "", ""


# Per-run memoization (cleared at the start of every run_all() so each
# invocation re-resolves fresh, but within one run the expensive resolutions —
# the `hermes config path` subprocess, the config.yaml read, and the skills
# walk — happen exactly once instead of once per check).
_cache: dict = {}


def _hermes_config_path():
    if "config_path" not in _cache:
        rc, stdout, _ = _run(["hermes", "config", "path"], timeout=15)
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        # Use stdout only (never stderr) — the path is printed to stdout.
        _cache["config_path"] = lines[-1] if rc == 0 and lines else None
    return _cache["config_path"]


def _hermes_home():
    """Resolve $HERMES_HOME as the parent directory of the active config file."""
    path = _hermes_config_path()
    return os.path.dirname(path) if path else None


def _read_config():
    """Return (path, data) for the active config; data is None on parse failure."""
    path = _hermes_config_path()
    if not path:
        return None, None
    if "config_data" not in _cache:
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
            # A non-mapping root (list/scalar) is malformed for our purposes.
            _cache["config_data"] = loaded if isinstance(loaded, dict) else None
        except Exception:
            _cache["config_data"] = None
    return path, _cache["config_data"]


def _frontmatter(path):
    """Extract frontmatter dict from a SKILL.md (or None)."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except Exception:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def _iter_skills():
    """Yield (skill_dir_path, frontmatter_or_None) for every SKILL.md, cached."""
    if "skills" not in _cache:
        home = _hermes_home()
        out = []
        if home:
            skills_root = os.path.join(home, "skills")
            if os.path.isdir(skills_root):
                for dirpath, _dirnames, filenames in os.walk(skills_root):
                    if "SKILL.md" in filenames:
                        out.append((dirpath, _frontmatter(os.path.join(dirpath, "SKILL.md"))))
        _cache["skills"] = out
    return _cache["skills"]


# --- config ---------------------------------------------------------------

def check_config_parses():
    path, data = _read_config()
    if not path:
        return {"status": "unknown", "reason": "`hermes config path` failed", "detail": None}
    if not os.path.exists(path):
        return {"status": "broken", "reason": "config file missing", "detail": path}
    if data is None:
        return {"status": "broken", "reason": "config.yaml does not parse (or root is not a mapping)", "detail": None}
    return {"status": "healthy", "reason": "config.yaml parses", "detail": path}


# --- MCP ------------------------------------------------------------------

def check_mcp_servers_shape():
    path, data = _read_config()
    if not path or data is None:
        return {"status": "unknown", "reason": "cannot read config", "detail": path}

    broken = []
    notes = []
    # Check parsed top-level keys (not raw text) so comments/strings don't
    # trigger false "foreign key" findings.
    for key in constants.FOREIGN_MCP_KEYS:
        if key in data:
            broken.append(
                f"foreign key `{key}` present (silently not read; use `{constants.CONFIG_MCP_SERVERS}`)"
            )

    servers = data.get(constants.CONFIG_MCP_SERVERS) or {}
    if isinstance(servers, dict):
        for name, entry in servers.items():
            if not isinstance(entry, dict):
                broken.append(f"`{constants.CONFIG_MCP_SERVERS}.{name}` is not a mapping")
                continue
            if entry.get("enabled") is False:
                notes.append(f"`{constants.CONFIG_MCP_SERVERS}.{name}` is `enabled: false` (skipped)")
            if not entry.get(constants.MCP_STDIO_KEY) and not entry.get(constants.MCP_HTTP_KEY):
                broken.append(
                    f"`{constants.CONFIG_MCP_SERVERS}.{name}` has neither "
                    f"`{constants.MCP_STDIO_KEY}` nor `{constants.MCP_HTTP_KEY}`"
                )
    else:
        broken.append(
            f"`{constants.CONFIG_MCP_SERVERS}` must be a mapping, got {type(servers).__name__}"
        )

    if broken:
        return {"status": "broken", "reason": f"{len(broken)} MCP issue(s)", "detail": broken + notes}
    if notes:
        return {"status": "informational", "reason": f"{len(notes)} note(s)", "detail": notes}
    return {"status": "healthy", "reason": "MCP servers well-formed", "detail": list(servers.keys()) if isinstance(servers, dict) else []}


# --- skills ---------------------------------------------------------------

def check_skills():
    home = _hermes_home()
    if not home:
        return {"status": "unknown", "reason": "cannot resolve $HERMES_HOME", "detail": None}
    skills_root = os.path.join(home, "skills")
    if not os.path.isdir(skills_root):
        return {"status": "healthy", "reason": "no skills directory", "detail": skills_root}

    findings = []
    seen = 0
    for dirpath, fm in _iter_skills():
        seen += 1
        if fm is None:
            findings.append(f"{dirpath}: SKILL.md has no valid frontmatter")
            continue
        for req in ("name", "description"):
            if not fm.get(req):
                findings.append(f"{dirpath}: frontmatter missing `{req}`")

    if findings:
        return {"status": "broken", "reason": f"{len(findings)} skill issue(s)", "detail": findings}
    return {"status": "healthy", "reason": f"{seen} skill(s) present with valid frontmatter", "detail": skills_root}


# --- commands -------------------------------------------------------------

def check_commands():
    """Detect skill-bundle slug collisions (a bundle shadows a skill of the same name)."""
    home = _hermes_home()
    if not home:
        return {"status": "unknown", "reason": "cannot resolve $HERMES_HOME", "detail": None}

    skill_names = {fm.get("name") for _dirpath, fm in _iter_skills() if fm and fm.get("name")}

    collisions = []
    bundles_root = os.path.join(home, "skill-bundles")
    if os.path.isdir(bundles_root):
        for fn in sorted(os.listdir(bundles_root)):
            if not fn.endswith((".yaml", ".yml")):
                continue
            slug = fn.rsplit(".", 1)[0]
            if slug in skill_names:
                collisions.append(f"bundle `{slug}` shadows skill `{slug}` (bundle wins)")

    if collisions:
        return {"status": "informational", "reason": f"{len(collisions)} bundle/skill slug collision(s)", "detail": collisions}
    return {"status": "healthy", "reason": "no bundle/skill slug collisions", "detail": None}


# --- hooks ----------------------------------------------------------------

def check_hooks():
    # `hermes hooks doctor` exits 0 even with problems, so we parse its output.
    # But if the subprocess itself never ran (hermes missing, timeout), we must
    # not report "healthy".
    rc, stdout, _ = _run(["hermes", "hooks", "doctor"], timeout=30)
    if rc != 0 or not stdout.strip():
        return {"status": "unknown", "reason": f"`hermes hooks doctor` unavailable or failed (rc={rc})", "detail": None}
    if "issue(s) found" in stdout:
        return {"status": "broken", "reason": "`hermes hooks doctor` reported issues", "detail": stdout.strip()[:2000]}
    # Verify the allowlist file is structurally sound, if present.
    home = _hermes_home()
    allowlist = os.path.join(home, "shell-hooks-allowlist.json") if home else None
    if allowlist and os.path.exists(allowlist):
        try:
            with open(allowlist, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception:
            return {"status": "broken", "reason": "shell-hooks-allowlist.json is not valid JSON", "detail": allowlist}
    return {"status": "healthy", "reason": "hooks doctor passed", "detail": None}


# --- plugins --------------------------------------------------------------

def check_plugins():
    path, data = _read_config()
    home = _hermes_home()
    if not path or data is None or not home:
        return {"status": "unknown", "reason": "cannot read config", "detail": path}

    plugins_cfg = data.get("plugins")
    plugins_cfg = plugins_cfg if isinstance(plugins_cfg, dict) else {}
    enabled = set(plugins_cfg.get("enabled") or [])
    disabled = set(plugins_cfg.get("disabled") or [])

    plugins_root = os.path.join(home, "plugins")
    if not os.path.isdir(plugins_root):
        return {"status": "healthy", "reason": "no plugins directory", "detail": plugins_root}

    # Skip sub-category dirs that use their own discovery/selection (not plugins.enabled).
    skip = set(constants.PLUGIN_SUBCATEGORY_DIRS)
    notes = []
    for name in sorted(os.listdir(plugins_root)):
        if name in skip or name.startswith("."):
            continue
        if not os.path.isdir(os.path.join(plugins_root, name)):
            continue
        if name not in enabled and name not in disabled:
            notes.append(f"`{name}` discovered but not enabled (opt-in)")

    if notes:
        return {"status": "informational", "reason": f"{len(notes)} plugin(s) not enabled", "detail": notes}
    return {"status": "healthy", "reason": "plugins consistent with enable list", "detail": sorted(enabled)}


# --- runner ---------------------------------------------------------------

_CHECKS = [
    ("config", check_config_parses),
    ("mcp", check_mcp_servers_shape),
    ("skills", check_skills),
    ("commands", check_commands),
    ("hooks", check_hooks),
    ("plugins", check_plugins),
]


def run_all(scope=None):
    """Run every check; optionally filter by a scope substring (e.g. 'mcp').

    Each check is isolated: a crash in one check surfaces as a `broken`
    envelope instead of aborting the whole report (a diagnostic tool must
    survive the broken inputs it exists to diagnose).
    """
    _cache.clear()
    results = {}
    for label, fn in _CHECKS:
        if scope and scope not in label:
            continue
        try:
            results[label] = fn()
        except Exception as exc:
            results[label] = {
                "status": "broken",
                "reason": f"check crashed ({type(exc).__name__}: {exc})",
                "detail": None,
            }
    return results
