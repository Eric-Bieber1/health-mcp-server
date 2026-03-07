"""API key authentication for Health MCP Server.

Format of AUTH_KEYS env var:
    name:key:permission,name:key:permission

Example:
    AUTH_KEYS=claude-desktop:health-key-claude-2026:read-only
"""

import os
import logging

logger = logging.getLogger(__name__)

_agents: dict[str, dict] = {}


def _load_agents():
    global _agents
    raw = os.environ.get("AUTH_KEYS", "")
    if not raw:
        logger.warning("No AUTH_KEYS configured — all requests will be rejected")
        return

    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            name, key, permission = parts
            _agents[key.strip()] = {
                "name": name.strip(),
                "key": key.strip(),
                "permission": permission.strip(),
            }
        else:
            logger.warning(f"Invalid AUTH_KEYS entry (expected name:key:permission): {entry}")


_load_agents()


def authenticate(api_key: str) -> dict | None:
    """Look up an agent by API key. Returns agent dict or None."""
    return _agents.get(api_key)


def require_auth(api_key: str) -> str | None:
    """Validate API key. Returns error string or None if valid."""
    if not api_key:
        return "Auth error: api_key is required."
    agent = authenticate(api_key)
    if not agent:
        return "Auth error: Invalid API key."
    return None
