"""hermes-guide plugin — executable, read-only Hermes configuration diagnostics.

Exposes:
  - `/hermes-doctor`  slash command  (CLI + gateway sessions)
  - `hermes guide <scope>`  CLI subcommand  (terminal; exit 1 on broken)

Also bundles the six troubleshooting skills under the `hermes-guide:` namespace
(read-only reference; opt-in explicit loads, not in the system prompt index).

Checks: config, mcp, skills, commands, hooks, plugins. The full ~30-check catalog
layers on top of `checks.py`.

Opt-in `proactive: true` runs drift checks on session start/end and logs
findings (observer-only; nothing is injected or modified).
"""

import logging
import pathlib
import sys

import yaml

from . import checks

logger = logging.getLogger(__name__)

_BASE = pathlib.Path(__file__).resolve().parent


def _format_result(results):
    """Render check envelopes as a compact, human-readable report."""
    lines = []
    exit_ok = True
    for label, r in results.items():
        status = r.get("status", "unknown")
        if status == "healthy":
            mark = "+"
        elif status == "broken":
            mark = "x"
            exit_ok = False
        elif status == "informational":
            mark = "~"
        else:
            mark = "?"
            exit_ok = False
        lines.append(f"{mark} {label}: {r.get('reason', '')}")
        detail = r.get("detail")
        if detail:
            if isinstance(detail, list):
                for d in detail:
                    lines.append(f"    - {d}")
            elif status != "healthy":
                lines.append(f"    - {detail}")
    return exit_ok, "\n".join(lines) if lines else "(no checks)"


def _skill_meta(skill_md):
    """Return (name, description) from a SKILL.md frontmatter, or (None, "")."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except Exception:
        return None, ""
    if not text.startswith("---"):
        return None, ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, ""
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except Exception:
        return None, ""
    if not isinstance(fm, dict):
        return None, ""
    return fm.get("name"), fm.get("description", "")


def _register_skills(ctx):
    """Bundle the reference skills under the `hermes-guide:` namespace."""
    skills_root = _BASE / "skills"
    if not skills_root.is_dir():
        return
    for skill_dir in sorted(skills_root.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        name, description = _skill_meta(skill_md)
        if not name:
            name = skill_dir.name
        try:
            ctx.register_skill(name, skill_md, description=description)
        except Exception as exc:  # a broken skill must not kill the plugin
            logger.warning("hermes-guide: skip skill %r: %s", name, exc)


def _handle_doctor(raw_args):
    """`/hermes-doctor` handler — optional scope, e.g. `/hermes-doctor mcp`."""
    scope = raw_args.strip() or None
    _, text = _format_result(checks.run_all(scope=scope))
    return text


def _run_cli(args):
    """`hermes guide <scope>` handler."""
    scope = getattr(args, "scope", None)
    exit_ok, text = _format_result(checks.run_all(scope=scope))
    print(text)
    sys.exit(0 if exit_ok else 1)


def _setup_cli(subparser):
    subparser.add_argument(
        "scope", nargs="?", help="optional filter: config|mcp|skills|commands|hooks|plugins"
    )


def _proactive_check(**_kwargs):
    """Run drift checks at a session boundary; log findings (observer-only)."""
    for label, r in checks.run_all().items():
        status = r.get("status")
        if status == "broken":
            logger.warning("hermes-guide [%s] broken: %s", label, r.get("reason"))
            detail = r.get("detail")
            if isinstance(detail, list):
                for d in detail:
                    logger.warning("    - %s", d)
        elif status == "informational":
            logger.info("hermes-guide [%s] note: %s", label, r.get("reason"))


def register(ctx):
    _register_skills(ctx)
    ctx.register_command(
        "hermes-doctor",
        handler=_handle_doctor,
        description="Run read-only Hermes configuration health checks",
    )
    ctx.register_cli_command(
        name="guide",
        help="Run read-only Hermes configuration diagnostics",
        setup_fn=_setup_cli,
        handler_fn=_run_cli,
    )

    if ctx.get_config("proactive", False):
        ctx.register_hook("on_session_start", _proactive_check)
        ctx.register_hook("on_session_end", _proactive_check)
