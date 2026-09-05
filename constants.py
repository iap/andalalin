"""Single source of truth for names/values that drift across Hermes versions.

Update THIS file (and only this file) when a `hermes` subcommand or config field
is renamed upstream. CI should diff these against live `hermes ...` output.
Do not scatter these strings across checks.py or __init__.py.
"""

# Top-level config key for MCP servers
CONFIG_MCP_SERVERS = "mcp_servers"

# Top-level config key for the built-in memory section (memory.provider,
# memory.memory_char_limit, ...). Also a plugin sub-category dir name — the F3
# guard forbids it as a literal in checks.py, so it lives here.
CONFIG_MEMORY_SECTION = "memory"

# Foreign keys that indicate a Claude-Code-style paste (silently NOT read by Hermes)
# Top-level foreign key from a Claude-Code-style paste that Hermes silently ignores.
# (Dropped the dead `"mcp.servers"` entry: `key in data` only matches top-level
# keys, so a dotted name never matched the nested `mcp.servers` it was meant for.)
FOREIGN_MCP_KEYS = ("mcpServers",)

# MCP server shape requirements (per entry): stdio needs `command`, http needs `url`
MCP_STDIO_KEY = "command"
MCP_HTTP_KEY = "url"

# MCP facts that drift across Hermes versions. Verified 2026-09 against Hermes
# v0.21.0 (commit 63279301). Upstream sources: tools/mcp_tool.py through
# v2026.8.31; after the 2026-09 refactor, tools/mcp_tool_schema.py (prefix) and
# tools/mcp_tool_common.py (tool-call timeout). These are checked against
# upstream main by tools/check_upstream_drift.py (DRIFT_FACTS) — update them
# here and in skills/diagnosing-mcp/SKILL.md together when they change upstream.
MCP_TOOL_NAME_PREFIX = "mcp__"       # native MCP tool-name prefix: mcp__<server>__<tool>
MCP_TIMEOUT_DEFAULT = 300            # per-tool-call timeout default, seconds
MCP_CONNECT_TIMEOUT_DEFAULT = 60     # initial connection timeout default, seconds

# Upstream project_venv_dir() candidate order (hermes_constants.py) — its
# docstring: "``venv`` wins when both exist, matching what the installers
# write." skills/diagnosing-path/SKILL.md and references/venv_detection_patterns.py
# mirror this order; tools/check_upstream_drift.py asserts it against upstream.
PROJECT_VENV_ORDER = '"venv", ".venv"'

# Built-in memory stores (tools/memory_tool.py: get_memory_dir() -> $HERMES_HOME/memories/).
# Entry delimiter and default char limits drift upstream — verified 2026-09
# against hermes-agent commit 8d3745a99b (defaults in cli-config.yaml.example /
# hermes_cli/config_defaults.py). check_memory_hygiene() in checks.py consumes
# these; tools/check_upstream_drift.py (DRIFT_FACTS) asserts the delimiter and
# limits against upstream main, where the delimiter lives in
# tools/memory_tool_store.py (moved there by the 2026-09 refactor).
BUILTIN_MEMORY_STORES = ("MEMORY.md", "USER.md")
MEMORY_ENTRY_DELIMITER = "§"
MEMORY_CHAR_LIMIT_DEFAULT = 2200
USER_CHAR_LIMIT_DEFAULT = 1375

# Plugin sub-category directories that use their own discovery/selection keys
# (memory.provider / context.engine / image_gen.provider / --provider) — NOT plugins.enabled.
PLUGIN_SUBCATEGORY_DIRS = (
    "platforms",
    "memory",
    "context_engine",
    "model-providers",
    "image_gen",
    "video_gen",
    "web",
    "browser",
    "cron_providers",
    # NOT "observability" — observability plugins are `standalone` and gated by
    # plugins.enabled (namespaced keys like `observability/langfuse`), not an
    # own provider key.
)
