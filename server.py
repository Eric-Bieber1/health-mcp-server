"""Health MCP Server — Unified Garmin, Dexcom, and Hevy tools.

Reads from the fitness dashboard's SQLite DB first to avoid redundant
API calls, with live API fallback when data isn't in the DB.

Supports streamable-http (default, port 3000) and stdio (--stdio flag) transports.
"""

import sys
import os

from dotenv import load_dotenv

load_dotenv()

# Update DB_PATH from environment before importing tools
import db
db.DB_PATH = os.environ.get("DB_PATH", db.DB_PATH)

from mcp_instance import mcp  # noqa: E402

# Import tool modules — side-effect registers all tools with mcp
import tools.garmin   # noqa: E402, F401  — 12 tools
import tools.dexcom   # noqa: E402, F401  — 4 tools
import tools.hevy     # noqa: E402, F401  — 6 tools
import tools.nutrition  # noqa: E402, F401  — 6 tools

from starlette.requests import Request    # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "health-mcp-server"})


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
