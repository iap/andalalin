"""Single source of truth for names/values that drift across Hermes versions.

Update THIS file (and only this file) when a `hermes` subcommand or config field
is renamed upstream. CI should diff these against live `hermes ...` output.
Do not scatter these strings across checks.py or __init__.py.
"""

# Top-level config key for MCP servers
CONFIG_MCP_SERVERS = "mcp_servers"

# Foreign keys that indicate a Claude-Code-style paste (silently NOT read by Hermes)
# Top-level foreign key from a Claude-Code-style paste that Hermes silently ignores.
# (Dropped the dead `"mcp.servers"` entry: `key in data` only matches top-level
# keys, so a dotted name never matched the nested `mcp.servers` it was meant for.)
FOREIGN_MCP_KEYS = ("mcpServers",)

# MCP server shape requirements (per entry): stdio needs `command`, http needs `url`
MCP_STDIO_KEY = "command"
MCP_HTTP_KEY = "url"

# MCP facts that drift across Hermes versions (source: tools/mcp_tool.py).
# Verified 2026-08 against Hermes v0.20.4 (commit 13ce0c5). These are checked
# against upstream by tools/check_upstream_drift.py (DRIFT_FACTS) — update them
# here and in skills/diagnosing-mcp/SKILL.md together when they change upstream.
MCP_TOOL_NAME_PREFIX = "mcp__"       # native MCP tool-name prefix: mcp__<server>__<tool>
MCP_TIMEOUT_DEFAULT = 300            # per-tool-call timeout default, seconds
MCP_CONNECT_TIMEOUT_DEFAULT = 60     # initial connection timeout default, seconds

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
