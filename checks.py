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

import importlib
import json
import os
import re
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


def frontmatter(path):
    """Extract the frontmatter mapping from a SKILL.md, or None if absent/invalid.

    Single source of truth for frontmatter parsing, shared by the skills and
    commands checks here and by the plugin's skill registry in __init__.py.
    Returns None (not {}) for malformed or non-mapping frontmatter so callers
    never call .get() on a list/scalar.
    """
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
        fm = yaml.safe_load(parts[1])
    except Exception:
        return None
    return fm if isinstance(fm, dict) else None


def _iter_skills():
    """Yield (skill_dir_path, frontmatter_or_None) for every SKILL.md, cached.

    Skips hidden/archive directories (``.archive``, ``.curator_backups``,
    ``.hub``) that Hermes uses for internal bookkeeping but does not load as
    skills — mirroring the loader so archived/backup copies never produce
    false positives.
    """
    if "skills" not in _cache:
        home = _hermes_home()
        out = []
        if home:
            skills_root = os.path.join(home, "skills")
            if os.path.isdir(skills_root):
                for dirpath, dirnames, filenames in os.walk(skills_root):
                    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                    if "SKILL.md" in filenames:
                        out.append((dirpath, frontmatter(os.path.join(dirpath, "SKILL.md"))))
        _cache["skills"] = out
    return _cache["skills"]


def _bundled_skill_names():
    """Return the set of Hermes-bundled skill names from ``.bundled_manifest``.

    The manifest is Hermes' authoritative ``name:hash`` record of skills it
    ships and updates. Skills in this set are Hermes-managed, so their issues
    are not user-fixable (an update overwrites them) and are labelled
    distinctly instead of prompting the user to edit them.
    """
    if "bundled_names" not in _cache:
        home = _hermes_home()
        names = set()
        if home:
            manifest = os.path.join(home, "skills", ".bundled_manifest")
            if os.path.isfile(manifest):
                try:
                    with open(manifest, "r", encoding="utf-8") as f:
                        for line in f:
                            name = line.split(":", 1)[0].strip()
                            if name:
                                names.add(name)
                except Exception:
                    # Unreadable/malformed manifest — treat as empty (best-effort;
                    # fail open toward user-actionable labels).
                    names = set()
        _cache["bundled_names"] = names
    return _cache["bundled_names"]


def _as_name_set(value):
    """Normalize a config value (list or scalar string) into a set of names.

    Guards against a scalar ``plugins.enabled: my-plugin`` — ``set("my-plugin")``
    would explode into single characters and produce bogus findings. Non-list,
    non-string values (bool/int/float/dict) are ignored, mirroring Hermes's
    list-only ``plugins.enabled`` handling instead of crashing on ``set(True)``.
    """
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, (list, tuple, set, frozenset)):
        # Keep only string names: malformed entries (dicts, ints, ...) must not
        # reach set()/sorted() and crash the diagnostic.
        return {v for v in value if isinstance(v, str)}
    # bool/int/float/dict/… are ignored (Hermes requires a list for `enabled`).
    return set()


# Slug normalization — identical to Hermes agent/skill_bundles.py::_slugify and
# agent/skill_commands.py::scan_skill_commands (same patterns + steps).
_BUNDLE_INVALID_CHARS = re.compile(r"[^a-z0-9-]")
_BUNDLE_MULTI_HYPHEN = re.compile(r"-{2,}")


def _bundle_slug(name):
    """Normalize a skill/bundle name to the hyphenated slash-command slug."""
    if not isinstance(name, str):
        return ""
    cmd = name.lower().replace(" ", "-").replace("_", "-")
    cmd = _BUNDLE_INVALID_CHARS.sub("", cmd)
    return _BUNDLE_MULTI_HYPHEN.sub("-", cmd).strip("-")


def _rel_path(path, base):
    """Return `path` relative to `base` for compact, unambiguous diagnostics."""
    try:
        return os.path.relpath(path, base)
    except ValueError:  # different drives (Windows)
        return path


# --- config ---------------------------------------------------------------

def check_config_parses():
    path, data = _read_config()
    if not path:
        return {"status": "unknown", "reason": "`hermes config path` failed", "detail": None}
    if not os.path.exists(path):
        return {"status": "broken", "reason": "config file missing", "detail": path}
    if data is None:
        return {
            "status": "broken",
            "reason": "config.yaml does not parse (or root is not a mapping)",
            "detail": path,
        }
    return {"status": "healthy", "reason": "config.yaml parses", "detail": path}


# --- MCP ------------------------------------------------------------------

def _parse_enabled(value, default=True):
    """Mirror Hermes hermes_cli/tools_config.py::_parse_enabled_flag.

    Hermes treats ``enabled: false``, ``"false"``, ``"no"``, ``"off"``, and ``0``
    as disabled; matching this avoids flagging disabled servers as broken.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


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

    servers = data.get(constants.CONFIG_MCP_SERVERS)
    if servers is None:
        servers = {}
    if isinstance(servers, dict):
        for name, entry in servers.items():
            if not isinstance(entry, dict):
                broken.append(f"`{constants.CONFIG_MCP_SERVERS}.{name}` is not a mapping")
                continue
            if "disabled" in entry:
                notes.append(
                    f"`{constants.CONFIG_MCP_SERVERS}.{name}` uses `disabled:` "
                    f"(not read by Hermes; server stays enabled) — set `enabled: false` to disable"
                )
            if not _parse_enabled(entry.get("enabled")):
                notes.append(f"`{constants.CONFIG_MCP_SERVERS}.{name}` is disabled (skipped)")
                continue
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
    bundled = _bundled_skill_names()
    for dirpath, fm in _iter_skills():
        seen += 1
        # Label [bundled] only from the skill's declared name (what Hermes
        # keys the manifest on). The directory basename is not reliable
        # ownership evidence — two skills at different depths can share a
        # basename — so an unreadable/nameless skill is never inferred to be
        # bundled.
        name = fm.get("name") if fm else None
        tag = " [bundled]" if name in bundled else ""
        if fm is None:
            findings.append(f"{dirpath}: SKILL.md has no valid frontmatter{tag}")
            continue
        for req in ("name", "description"):
            if not fm.get(req):
                findings.append(f"{dirpath}: frontmatter missing `{req}`{tag}")

    if findings:
        return {"status": "broken", "reason": f"{len(findings)} skill issue(s)", "detail": findings}
    return {"status": "healthy", "reason": f"{seen} skill(s) present with valid frontmatter", "detail": skills_root}


# --- commands -------------------------------------------------------------

def _builtin_command_names():
    """Return the set of built-in slash-command names and aliases from Hermes core.

    Best-effort: returns an empty set if the import fails (e.g. running outside
    a live Hermes environment), in which case the builtin-collision check is
    silently skipped rather than false-positives.
    """
    try:
        from hermes_cli.commands import COMMAND_REGISTRY  # type: ignore[import-not-found]

        names = set()
        for cmd in COMMAND_REGISTRY:
            names.add(cmd.name)
            for alias in cmd.aliases or ():
                names.add(alias)
        return names
    except Exception:
        return set()


def check_commands():
    """Detect skill-bundle slug collisions, malformed bundle files, and builtin shadowing."""
    home = _hermes_home()
    if not home:
        return {"status": "unknown", "reason": "cannot resolve $HERMES_HOME", "detail": None}

    skill_slugs = set()
    skill_slug_owners: dict[str, str] = {}  # slug -> first skill dir (first-wins, mirrors Hermes)
    skill_slug_versions: dict[str, str] = {}  # slug -> version string of first owner
    collisions = []
    for dirpath, fm in _iter_skills():
        if fm and fm.get("name"):
            s = _bundle_slug(fm.get("name"))
            if s:
                skill_slugs.add(s)
                if s in skill_slug_owners:
                    first_v = skill_slug_versions.get(s) or "unversioned"
                    this_v = str(fm.get("version") or "").strip() or "unversioned"
                    collisions.append(
                        f"skill `{_rel_path(skill_slug_owners[s], home)}` (v{first_v}) and "
                        f"`{_rel_path(dirpath, home)}` (v{this_v}) both normalize to "
                        f"`/{s}` (first wins)"
                    )
                else:
                    skill_slug_owners[s] = dirpath
                    skill_slug_versions[s] = str(fm.get("version") or "").strip()

    # Skill-vs-builtin collisions: a skill whose slug matches a built-in command
    # name is silently shadowed (built-in wins). Surface this so the user can
    # rename the skill before wondering why `/<name>` behaves unexpectedly.
    builtin_names = _builtin_command_names()
    if builtin_names:
        for dirpath, fm in _iter_skills():
            if fm and fm.get("name"):
                s = _bundle_slug(fm.get("name"))
                if s and s in builtin_names:
                    collisions.append(
                        f"skill `{_rel_path(dirpath, home)}` (/{s}) shadows a built-in command "
                        f"(builtin wins — rename the skill or expect the builtin behavior)"
                    )

    malformed = []
    bundle_slugs: dict[str, str] = {}  # slug -> first bundle stem (bundle-vs-bundle first-wins)
    bundles_root = os.path.join(home, "skill-bundles")
    if os.path.isdir(bundles_root):
        for fn in sorted(os.listdir(bundles_root)):
            if not fn.endswith((".yaml", ".yml")):
                continue
            stem = fn.rsplit(".", 1)[0]
            bundle_path = os.path.join(bundles_root, fn)
            try:
                with open(bundle_path, "r", encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
            except Exception as exc:
                malformed.append(f"bundle `{stem}` failed to parse: {exc}")
                continue

            # Mirror Hermes agent/skill_bundles.py::_load_bundle_file: a bundle
            # must be a mapping with a non-empty `skills` list and a resolvable
            # name/slug, otherwise Hermes skips it during slash-command discovery.
            if not isinstance(loaded, dict):
                malformed.append(f"bundle `{stem}` is not a mapping (skipped by Hermes)")
                continue

            skills = loaded.get("skills") or []
            if not isinstance(skills, list):
                malformed.append(f"bundle `{stem}`: `skills` is not a list (skipped by Hermes)")
            elif not [s for s in skills if str(s).strip()]:
                malformed.append(f"bundle `{stem}` has an empty `skills` list (skipped by Hermes)")

            name = str(loaded.get("name") or stem).strip()
            if not name:
                malformed.append(f"bundle `{stem}` has no usable name (skipped by Hermes)")
                continue
            slug = _bundle_slug(name)
            if not slug:
                malformed.append(f"bundle `{stem}` yields an empty slug (skipped by Hermes)")
                continue

            if slug in bundle_slugs:
                collisions.append(
                    f"bundle `{stem}` (/{slug}) shadows bundle "
                    f"`{bundle_slugs[slug]}` (/{slug}) (first wins)"
                )
            else:
                bundle_slugs[slug] = stem

            if slug in skill_slugs:
                collisions.append(f"bundle `{stem}` (/{slug}) shadows skill `/{slug}` (bundle wins)")

    if malformed:
        return {"status": "broken", "reason": f"{len(malformed)} malformed bundle(s)", "detail": malformed + collisions}
    if collisions:
        return {"status": "informational", "reason": f"{len(collisions)} slug collision(s)", "detail": collisions}
    return {"status": "healthy", "reason": "no slug collisions or malformed bundles", "detail": None}


# --- hooks ----------------------------------------------------------------

def check_hooks():
    # `hermes hooks doctor` exits 0 even with problems, so we parse its output
    # (rc is not a reliable signal — it is 0 in all cases). Count the ✗/⚠ markers
    # emitted per hook rather than matching the summary line's exact wording.
    rc, stdout, _ = _run(["hermes", "hooks", "doctor"], timeout=30)
    if rc != 0 or not stdout.strip():
        return {
            "status": "unknown",
            "reason": f"`hermes hooks doctor` unavailable or failed (rc={rc})",
            "detail": None,
        }
    if "No shell hooks configured" in stdout:
        return {"status": "healthy", "reason": "no shell hooks configured", "detail": None}
    # Count per-hook findings — ✗ and ⚠ are the only stable markers in the output.
    import re as _re

    markers = _re.findall(r"\s+[✗⚠]", stdout)
    if markers:
        return {
            "status": "broken",
            "reason": f"`hermes hooks doctor` reported {len(markers)} finding(s)",
            "detail": stdout.strip()[:2000],
        }
    if "All shell hooks look healthy" in stdout:
        return {"status": "healthy", "reason": "hooks doctor passed", "detail": None}
    # Output ran but matched no known summary pattern — treat as unknown rather
    # than falsely healthy in case Hermes changed its wording.
    return {
        "status": "unknown",
        "reason": "`hermes hooks doctor` output matched no known summary pattern",
        "detail": stdout.strip()[:2000],
    }
    # Verify the allowlist file is structurally sound, if present.
    home = _hermes_home()
    allowlist = os.path.join(home, "shell-hooks-allowlist.json") if home else None
    if allowlist and os.path.exists(allowlist):
        try:
            with open(allowlist, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception:
            return {
                "status": "broken",
                "reason": "shell-hooks-allowlist.json is not valid JSON",
                "detail": allowlist,
            }
    return {"status": "healthy", "reason": "hooks doctor passed", "detail": None}


# --- plugins --------------------------------------------------------------

def _bundled_plugins_dir():
    """Resolve the bundled plugins directory the loader scans, or None.

    Uses Hermes' own resolver so nested category layouts (browser/, image_gen/,
    model-providers/, platforms/, ...) resolve exactly as the loader does. The
    import is dynamic (importlib) so it stays mypy-clean and the check still
    runs when imported outside a live Hermes process (e.g. in a unit test).
    """
    try:
        resolver = getattr(importlib.import_module("hermes_cli.plugins"), "get_bundled_plugins_dir")
        return str(resolver())
    except Exception:
        return None


def _read_plugin_manifest(d):
    """Return a directory plugin's manifest ``name``, or None if none exists.

    Accepts ``plugin.yaml`` then ``plugin.yml``, mirroring
    ``plugins_cmd._read_manifest_info``. Portable Agent Plugins v1 packages
    (``plugin.json``) install disabled by default and are out of scope here.
    """
    manifest_file = os.path.join(d, "plugin.yaml")
    if not os.path.isfile(manifest_file):
        manifest_file = os.path.join(d, "plugin.yml")
    if not os.path.isfile(manifest_file):
        return None
    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f) or {}
        name = manifest.get("name")
    except Exception:
        name = None
    if name is None:
        name = os.path.basename(d)
    return name


def _collect_plugin_ids(root, prefix, depth, skip_names, seen):
    """Recursively collect discoverable plugin identifiers, mirroring
    ``plugins_cmd._scan_level``: a plugin resolves by its manifest ``name`` or
    its path-derived ``key`` (``<category>/<dirname>``). Both are added to
    *seen* so ``plugins.enabled`` matches by name or key alike."""
    if not root or not os.path.isdir(root):
        return
    for d in sorted(os.listdir(root)):
        dpath = os.path.join(root, d)
        if not os.path.isdir(dpath):
            continue
        if depth == 0 and skip_names and d in skip_names:
            continue
        name = _read_plugin_manifest(dpath)
        if name is not None:
            key = f"{prefix}/{d}" if prefix else name
            seen.add(name)
            seen.add(key)
            continue
        if depth >= 1:
            continue
        sub_prefix = f"{prefix}/{d}" if prefix else d
        _collect_plugin_ids(dpath, sub_prefix, depth + 1, set(), seen)


def check_plugins():
    path, data = _read_config()
    home = _hermes_home()
    if not path or data is None or not home:
        return {"status": "unknown", "reason": "cannot read config", "detail": path}

    plugins_cfg = data.get("plugins")
    plugins_cfg = plugins_cfg if isinstance(plugins_cfg, dict) else {}
    enabled = _as_name_set(plugins_cfg.get("enabled"))
    disabled = _as_name_set(plugins_cfg.get("disabled"))

    plugins_root = os.path.join(home, "plugins")
    skip = set(constants.PLUGIN_SUBCATEGORY_DIRS)

    # Collect every plugin the loader can see — the user dir *and* the bundled
    # dir (with its category sub-layouts) — by both manifest name and key. This
    # is what makes enabled bundled plugins (e.g. `disk-cleanup`,
    # `kilocode-provider`) resolvable instead of being falsely flagged missing.
    known: set[str] = set()
    _collect_plugin_ids(plugins_root, "", 0, set(), known)
    _collect_plugin_ids(_bundled_plugins_dir(), "", 0, {"memory", "context_engine", "model-providers"}, known)

    broken = []
    for name in sorted(enabled):
        if name in skip:
            continue  # sub-category dirs use their own selection keys, not plugins.enabled
        if name not in known:
            broken.append(f"`{name}` is enabled but no matching plugin manifest was found")

    notes = []
    if os.path.isdir(plugins_root):
        for name in sorted(os.listdir(plugins_root)):
            if name in skip or name.startswith(".") or name == "__pycache__":
                continue
            if not os.path.isdir(os.path.join(plugins_root, name)):
                continue
            if name not in enabled and name not in disabled:
                notes.append(f"`{name}` discovered but not enabled (opt-in)")

    if broken:
        return {"status": "broken", "reason": f"{len(broken)} enabled plugin(s) missing or broken", "detail": broken + notes}
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
