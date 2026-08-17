"""Single source of truth for names/values that drift across Hermes versions.

Update THIS file (and only this file) when a `hermes` subcommand or config field
is renamed upstream. CI should diff these against live `hermes ...` output.
Do not scatter these strings across checks.py or __init__.py.
"""

# Top-level config key for MCP servers
CONFIG_MCP_SERVERS = "mcp_servers"

# Foreign keys that indicate a Claude-Code-style paste (silently NOT read by Hermes)
FOREIGN_MCP_KEYS = ("mcpServers", "mcp.servers")

# MCP server shape requirements (per entry): stdio needs `command`, http needs `url`
MCP_STDIO_KEY = "command"
MCP_HTTP_KEY = "url"

# Current MCP tool naming convention (v0.20.x: double underscore)
MCP_TOOL_NAME_PREFIX = "mcp__"
MCP_TOOL_DELIM = "__"

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
)
