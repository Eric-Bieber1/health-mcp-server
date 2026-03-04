"""Shared FastMCP instance — import from here to avoid circular imports."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("health-mcp-server")
