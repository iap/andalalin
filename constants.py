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
    "observability",
)
