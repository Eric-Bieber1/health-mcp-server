"""Garmin Connect client management — auth, caching, and retry logic."""

import os
from garminconnect import Garmin

_garmin_client: Garmin | None = None


def get_garmin_client() -> Garmin:
    """Return a cached Garmin client, logging in if necessary."""
    global _garmin_client
    if _garmin_client is None:
        email = os.environ.get("GARMIN_EMAIL")
        password = os.environ.get("GARMIN_PASSWORD")
        if not email or not password:
            raise ValueError("GARMIN_EMAIL and GARMIN_PASSWORD must be set")

        tokenstore = os.environ.get("GARMIN_TOKENSTORE")
        _garmin_client = Garmin(email, password)
        if tokenstore:
            _garmin_client.garth.configure(domain="garmin.com")
            try:
                _garmin_client.login(tokenstore)
            except Exception:
                _garmin_client.login()
                _garmin_client.garth.dump(tokenstore)
        else:
            _garmin_client.login()
    return _garmin_client


def reset_garmin_client() -> None:
    """Clear the cached client so next call re-logs in."""
    global _garmin_client
    _garmin_client = None


def call_garmin(func: str, *args, **kwargs):
    """Call a Garmin API method with automatic retry on auth failure."""
    try:
        client = get_garmin_client()
        return getattr(client, func)(*args, **kwargs)
    except Exception as first_err:
        err_msg = str(first_err).lower()
        if any(t in err_msg for t in ("unauthorized", "session", "login", "403", "401", "token")):
            reset_garmin_client()
            client = get_garmin_client()
            return getattr(client, func)(*args, **kwargs)
        raise first_err
