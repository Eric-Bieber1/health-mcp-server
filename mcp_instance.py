"""Shared FastMCP instance — import from here to avoid circular imports."""

import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "health-mcp-server",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "3000")),
)
