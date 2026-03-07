"""Dexcom G7 client management — auth, caching, and retry logic."""

import os
from pydexcom import Dexcom

_dexcom_client: Dexcom | None = None


def get_dexcom_client() -> Dexcom:
    """Return a cached Dexcom client, creating one if needed."""
    global _dexcom_client
    if _dexcom_client is None:
        username = os.environ.get("DEXCOM_USERNAME")
        password = os.environ.get("DEXCOM_PASSWORD")
        region = os.environ.get("DEXCOM_REGION", "us").lower()
        if not username or not password:
            raise ValueError("Dexcom credentials not configured.")
        _dexcom_client = Dexcom(username, password, ous=(region == "ous"))
    return _dexcom_client


def reset_dexcom_client() -> None:
    """Clear the cached client so next call creates a fresh one."""
    global _dexcom_client
    _dexcom_client = None


def with_retry(fn):
    """Call fn, retry once with a fresh client on auth errors."""
    try:
        return fn()
    except Exception:
        reset_dexcom_client()
        return fn()
