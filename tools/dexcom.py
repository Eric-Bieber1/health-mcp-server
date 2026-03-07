"""Dexcom G7 tools — 4 tools with DB-first strategy for readings/stats."""

import logging
import os
import statistics
from datetime import datetime, timedelta, timezone

from mcp_instance import mcp
from db import query_all, query_one
from clients.dexcom_client import get_dexcom_client, with_retry
from auth import require_auth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Live-API-only tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_current_glucose(api_key: str) -> str:
    """Get the current glucose reading from Dexcom G7.

    Args:
        api_key: API key for authentication.

    Returns glucose value in mg/dL, trend arrow, and trend description.
    The reading must be within the last 10 minutes to be considered current.
    Always uses live API for real-time data.
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        def _fetch():
            dexcom = get_dexcom_client()
            return dexcom.get_current_glucose_reading()

        reading = with_retry(_fetch)

        if reading is None:
            return "No current glucose reading available. The sensor may not have a reading within the last 10 minutes."

        age = datetime.now(timezone.utc) - reading.datetime.replace(tzinfo=timezone.utc)
        if age > timedelta(minutes=10):
            return (
                f"No current reading (latest is {int(age.total_seconds() // 60)} minutes old).\n"
                f"Last value: {reading.value} mg/dL | Trend: {reading.trend_arrow} ({reading.trend_description})\n"
                f"Time: {reading.datetime.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        return (
            f"Current Glucose: {reading.value} mg/dL\n"
            f"Trend: {reading.trend_arrow} ({reading.trend_description})\n"
            f"Time: {reading.datetime.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"Error fetching current glucose: {e}")
        return "Failed to fetch current glucose data. Please try again later."


@mcp.tool()
def get_latest_glucose(api_key: str) -> str:
    """Get the latest available glucose reading, looking back up to 24 hours.

    Args:
        api_key: API key for authentication.

    Unlike get_current_glucose, this searches further back if no recent reading exists.
    Always uses live API for freshest reading.
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        def _fetch():
            dexcom = get_dexcom_client()
            current = dexcom.get_current_glucose_reading()
            if current is not None:
                return current, False
            readings = dexcom.get_glucose_readings(minutes=1440, max_count=1)
            if readings:
                return readings[0], True
            return None, True

        reading, is_old = with_retry(_fetch)

        if reading is None:
            return "No glucose readings found in the last 24 hours."

        age = datetime.now(timezone.utc) - reading.datetime.replace(tzinfo=timezone.utc)
        age_min = int(age.total_seconds() // 60)

        if age_min < 60:
            age_str = f"{age_min} minutes ago"
        else:
            hours = age_min // 60
            mins = age_min % 60
            age_str = f"{hours}h {mins}m ago"

        return (
            f"Latest Glucose: {reading.value} mg/dL\n"
            f"Trend: {reading.trend_arrow} ({reading.trend_description})\n"
            f"Time: {reading.datetime.strftime('%Y-%m-%d %H:%M:%S')} ({age_str})"
        )
    except Exception as e:
        logger.error(f"Error fetching latest glucose: {e}")
        return "Failed to fetch latest glucose data. Please try again later."


# ---------------------------------------------------------------------------
# DB-first tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_glucose_readings(api_key: str, minutes: int = 60, max_count: int = 12) -> str:
    """Get glucose readings for a specified time window.

    Args:
        api_key: API key for authentication.
        minutes: Number of minutes to look back (1-1440, default 60).
                 Common values: 60=1hr, 120=2hr, 180=3hr, 360=6hr, 720=12hr, 1440=24hr.
        max_count: Maximum readings to return (1-288, default 12).
                   Dexcom reads every 5 min, so 12 readings = 1 hour.
    """
    err = require_auth(api_key)
    if err:
        return err
    minutes = max(1, min(1440, minutes))
    max_count = max(1, min(288, max_count))

    # Try DB first
    cutoff = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    rows = query_all(
        "SELECT timestamp, glucose_mg_dl, trend_arrow, trend_description FROM glucose_readings "
        "WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
        (cutoff, max_count),
    )
    if rows:
        lines = [f"Glucose Readings — last {minutes} minutes (showing {len(rows)} readings)\n"]
        lines.append(f"{'Time':<22} {'mg/dL':>6}  Trend")
        lines.append("-" * 50)

        values = []
        for r in rows:
            ts = r["timestamp"][:19]
            val = r["glucose_mg_dl"]
            arrow = r.get("trend_arrow", "")
            desc = r.get("trend_description", "")
            lines.append(f"{ts:<22} {val:>6}  {arrow} {desc}")
            values.append(val)

        lines.append("-" * 50)
        lines.append(f"Range: {min(values)}-{max(values)} mg/dL | Avg: {sum(values) / len(values):.0f} mg/dL")
        lines.append("")
        lines.append("(Source: database)")
        return "\n".join(lines)

    # Fallback to live API
    try:
        def _fetch():
            dexcom = get_dexcom_client()
            return dexcom.get_glucose_readings(minutes=minutes, max_count=max_count)

        readings = with_retry(_fetch)

        if not readings:
            return f"No glucose readings found in the last {minutes} minutes."

        lines = [f"Glucose Readings — last {minutes} minutes (showing {len(readings)} readings)\n"]
        lines.append(f"{'Time':<22} {'mg/dL':>6}  Trend")
        lines.append("-" * 50)

        for r in readings:
            ts = r.datetime.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"{ts:<22} {r.value:>6}  {r.trend_arrow} {r.trend_description}")

        values = [r.value for r in readings]
        lines.append("-" * 50)
        lines.append(f"Range: {min(values)}-{max(values)} mg/dL | Avg: {sum(values) / len(values):.0f} mg/dL")
        lines.append("")
        lines.append("(Source: live API)")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error fetching glucose readings: {e}")
        return "Failed to fetch glucose readings. Please try again later."


@mcp.tool()
def get_glucose_stats(api_key: str, hours: int = 24) -> str:
    """Get glucose statistics for a time period.

    Args:
        api_key: API key for authentication.
        hours: Number of hours to analyse (1-24, default 24).

    Returns summary statistics including average, min, max, time in range,
    and estimated A1C.
    """
    err = require_auth(api_key)
    if err:
        return err
    hours = max(1, min(24, hours))
    glucose_low = int(os.environ.get("GLUCOSE_LOW", "70"))
    glucose_high = int(os.environ.get("GLUCOSE_HIGH", "180"))

    # Try DB first — check glucose_daily_stats for full-day queries
    if hours == 24:
        today = datetime.now().strftime("%Y-%m-%d")
        row = query_one("SELECT * FROM glucose_daily_stats WHERE date = ?", (today,))
        if row and row.get("readings_count", 0) > 0:
            avg = row["average"]
            estimated_a1c = (avg + 46.7) / 28.7
            return (
                f"Glucose Statistics — {today} ({row['readings_count']} readings)\n"
                f"{'=' * 45}\n"
                f"Average:        {avg:.0f} mg/dL\n"
                f"Min:            {row['min']} mg/dL\n"
                f"Max:            {row['max']} mg/dL\n"
                f"Std Deviation:  {row.get('std_dev', 0):.1f} mg/dL\n"
                f"Estimated A1C:  {estimated_a1c:.1f}%\n"
                f"\n"
                f"Time in Range ({glucose_low}-{glucose_high}): {row.get('time_in_range', 0):.1f}%\n"
                f"Time Above {glucose_high}:        {row.get('time_above', 0):.1f}%\n"
                f"Time Below {glucose_low}:         {row.get('time_below', 0):.1f}%\n"
                f"\n"
                f"(Source: database)"
            )

    # Fallback to live API
    try:
        def _fetch():
            dexcom = get_dexcom_client()
            return dexcom.get_glucose_readings(minutes=hours * 60, max_count=hours * 12)

        readings = with_retry(_fetch)

        if not readings:
            return f"No glucose readings found in the last {hours} hours."

        values = [r.value for r in readings]
        total = len(values)
        avg = sum(values) / total
        std = statistics.stdev(values) if total > 1 else 0.0
        mn, mx = min(values), max(values)

        in_range = sum(1 for v in values if glucose_low <= v <= glucose_high)
        above = sum(1 for v in values if v > glucose_high)
        below = sum(1 for v in values if v < glucose_low)
        very_high = sum(1 for v in values if v > 250)
        very_low = sum(1 for v in values if v < 54)

        pct = lambda n: f"{n / total * 100:.1f}%"
        estimated_a1c = (avg + 46.7) / 28.7

        return (
            f"Glucose Statistics — last {hours} hours ({total} readings)\n"
            f"{'=' * 45}\n"
            f"Average:        {avg:.0f} mg/dL\n"
            f"Min:            {mn} mg/dL\n"
            f"Max:            {mx} mg/dL\n"
            f"Std Deviation:  {std:.1f} mg/dL\n"
            f"Estimated A1C:  {estimated_a1c:.1f}%\n"
            f"\n"
            f"Time in Range ({glucose_low}-{glucose_high}): {pct(in_range)}  ({in_range}/{total})\n"
            f"Time Above {glucose_high}:        {pct(above)}  ({above}/{total})\n"
            f"Time Below {glucose_low}:         {pct(below)}  ({below}/{total})\n"
            f"Very High (>250):      {pct(very_high)}  ({very_high}/{total})\n"
            f"Very Low  (<54):       {pct(very_low)}  ({very_low}/{total})\n"
            f"\n"
            f"(Source: live API)"
        )
    except Exception as e:
        logger.error(f"Error calculating glucose stats: {e}")
        return "Failed to fetch glucose stats. Please try again later."
