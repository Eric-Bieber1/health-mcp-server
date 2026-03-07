"""Garmin Connect tools — 12 tools with DB-first strategy where applicable."""

import logging
from datetime import datetime
from mcp_instance import mcp
from db import query_one, query_all
from clients.garmin_client import call_garmin
from auth import require_auth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper formatters
# ---------------------------------------------------------------------------

def _seconds_to_hm(seconds) -> str:
    if seconds is None:
        return "N/A"
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _kg_to_lbs(kg) -> float:
    if kg is None:
        return 0.0
    return round(kg * 2.20462, 1)


def _safe_get(data, *keys, default="N/A"):
    current = data
    for key in keys:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, (list, tuple)) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return default
    return current if current is not None else default


# ---------------------------------------------------------------------------
# DB-first tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_stats(api_key: str, date: str) -> str:
    """Get daily health summary for a given date.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format (e.g. '2026-02-25')

    Returns a formatted summary including steps, heart rate, body battery,
    stress, calories, floors climbed, and distance.
    """
    err = require_auth(api_key)
    if err:
        return err
    # Try DB first
    row = query_one("SELECT * FROM garmin_daily WHERE date = ?", (date,))
    if row:
        lines = [
            f"Daily Stats for {date}",
            "=" * 35,
            f"Total Steps:      {row.get('total_steps', 'N/A')}",
            f"Resting HR:       {row.get('resting_hr', 'N/A')} bpm",
            f"Body Battery:     {row.get('body_battery', 'N/A')}",
            f"Avg Stress:       {row.get('avg_stress', 'N/A')}",
            f"Sleep Score:      {row.get('sleep_score', 'N/A')}",
            f"HRV:              {row.get('hrv_ms', 'N/A')} ms",
            f"Weight:           {row.get('weight_lbs', 'N/A')} lbs",
            f"BP:               {row.get('bp_systolic', 'N/A')}/{row.get('bp_diastolic', 'N/A')} mmHg",
            "",
            "(Source: database)",
        ]
        return "\n".join(lines)

    # Fallback to live API
    try:
        data = call_garmin("get_stats", date)
    except Exception as e:
        logger.error(f"Error fetching stats for {date}: {e}")
        return "Failed to fetch stats data. Please try again later."

    if not data:
        return f"No stats data found for {date}."

    total_steps = _safe_get(data, "totalSteps")
    resting_hr = _safe_get(data, "restingHeartRate")
    bb_charged = _safe_get(data, "bodyBatteryChargedValue")
    bb_drained = _safe_get(data, "bodyBatteryDrainedValue")
    avg_stress = _safe_get(data, "averageStressLevel")
    total_cal = _safe_get(data, "totalKilocalories")
    active_cal = _safe_get(data, "activeKilocalories")
    floors = _safe_get(data, "floorsAscended")
    distance_m = _safe_get(data, "totalDistanceMeters")

    distance_str = "N/A"
    if distance_m not in (None, "N/A"):
        km = distance_m / 1000
        mi = distance_m / 1609.344
        distance_str = f"{km:.2f} km ({mi:.2f} mi)"

    lines = [
        f"Daily Stats for {date}",
        "=" * 35,
        f"Total Steps:      {total_steps}",
        f"Resting HR:       {resting_hr} bpm",
        f"Body Battery:     +{bb_charged} / -{bb_drained}",
        f"Avg Stress:       {avg_stress}",
        f"Total Calories:   {total_cal} kcal",
        f"Active Calories:  {active_cal} kcal",
        f"Floors Climbed:   {floors}",
        f"Distance:         {distance_str}",
        "",
        "(Source: live API)",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_sleep_summary(api_key: str, date: str) -> str:
    """Get sleep data summary for a given date.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format. This is the date you woke up on.

    Returns formatted sleep summary including score, duration, and stage
    breakdown (deep, light, REM, awake).
    """
    err = require_auth(api_key)
    if err:
        return err
    # Try DB first for sleep score and HRV
    row = query_one("SELECT * FROM garmin_daily WHERE date = ?", (date,))
    if row and row.get("sleep_score") is not None:
        lines = [
            f"Sleep Summary for {date}",
            "=" * 35,
            f"Sleep Score:      {row.get('sleep_score')}",
            f"HRV:              {row.get('hrv_ms', 'N/A')} ms",
            f"Resting HR:       {row.get('resting_hr', 'N/A')} bpm",
            "",
            "(Source: database — use live API for full stage breakdown)",
        ]
        return "\n".join(lines)

    # Fallback to live API for full data
    try:
        data = call_garmin("get_sleep_data", date)
    except Exception as e:
        logger.error(f"Error fetching sleep data for {date}: {e}")
        return "Failed to fetch sleep data. Please try again later."

    if not data:
        return f"No sleep data found for {date}."

    dto = _safe_get(data, "dailySleepDTO", default={})
    sleep_score = _safe_get(dto, "sleepScores", "overall", "value")
    sleep_start = _safe_get(dto, "sleepStartTimestampLocal")
    sleep_end = _safe_get(dto, "sleepEndTimestampLocal")
    sleep_time_sec = _safe_get(dto, "sleepTimeSeconds")
    deep_sec = _safe_get(dto, "deepSleepSeconds")
    light_sec = _safe_get(dto, "lightSleepSeconds")
    rem_sec = _safe_get(dto, "remSleepSeconds")
    awake_sec = _safe_get(dto, "awakeSleepSeconds")
    resting_hr = _safe_get(dto, "restingHeartRate")
    avg_spo2 = _safe_get(dto, "averageSpO2Value")
    avg_respiration = _safe_get(dto, "averageRespirationValue")
    hrv_status = _safe_get(dto, "hrvStatus")

    def _fmt_ts(ts):
        if ts in (None, "N/A"):
            return "N/A"
        try:
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts / 1000).strftime("%I:%M %p")
            return str(ts)
        except Exception:
            return str(ts)

    lines = [
        f"Sleep Summary for {date}",
        "=" * 35,
        f"Sleep Score:      {sleep_score}",
        f"Bedtime:          {_fmt_ts(sleep_start)}",
        f"Wake Time:        {_fmt_ts(sleep_end)}",
        f"Total Sleep:      {_seconds_to_hm(sleep_time_sec)}",
        f"Deep Sleep:       {_seconds_to_hm(deep_sec)}",
        f"Light Sleep:      {_seconds_to_hm(light_sec)}",
        f"REM Sleep:        {_seconds_to_hm(rem_sec)}",
        f"Awake:            {_seconds_to_hm(awake_sec)}",
        f"Resting HR:       {resting_hr} bpm",
        f"Avg SpO2:         {avg_spo2}%",
        f"Avg Respiration:  {avg_respiration} brpm",
        f"HRV Status:       {hrv_status}",
        "",
        "(Source: live API)",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_heart_rates_summary(api_key: str, date: str) -> str:
    """Get heart rate zone summary for a given date.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format.

    Returns a compact summary of resting HR, max HR, and time spent in
    each heart rate zone. Always uses live API (zones not stored in DB).
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        data = call_garmin("get_heart_rates", date)
    except Exception as e:
        logger.error(f"Error fetching heart rate data for {date}: {e}")
        return "Failed to fetch heart rate data. Please try again later."

    if not data:
        return f"No heart rate data found for {date}."

    resting_hr = _safe_get(data, "restingHeartRate")
    max_hr = _safe_get(data, "maxHeartRate")
    min_hr = _safe_get(data, "minHeartRate")

    lines = [
        f"Heart Rate Summary for {date}",
        "=" * 35,
        f"Resting HR:  {resting_hr} bpm",
        f"Max HR:      {max_hr} bpm",
        f"Min HR:      {min_hr} bpm",
    ]

    zones = _safe_get(data, "heartRateZones", default=[])
    if zones and isinstance(zones, list):
        lines.append("")
        lines.append("Heart Rate Zones:")
        zone_labels = [
            "Rest", "Zone 1 (Easy)", "Zone 2 (Moderate)",
            "Zone 3 (Hard)", "Zone 4 (Very Hard)", "Zone 5 (Max)",
        ]
        for i, zone in enumerate(zones):
            label = zone_labels[i] if i < len(zone_labels) else f"Zone {i}"
            secs = _safe_get(zone, "secsInZone", default=0)
            lines.append(f"  {label}: {_seconds_to_hm(secs)}")

    return "\n".join(lines)


@mcp.tool()
def get_body_composition(api_key: str, start_date: str, end_date: str) -> str:
    """Get body composition data for a date range.

    Args:
        api_key: API key for authentication.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns weight entries with dates, converted to pounds.
    """
    err = require_auth(api_key)
    if err:
        return err
    # Try DB first
    rows = query_all(
        "SELECT date, weight_lbs FROM garmin_daily WHERE date BETWEEN ? AND ? AND weight_lbs IS NOT NULL ORDER BY date",
        (start_date, end_date),
    )
    if rows:
        lines = [
            f"Body Composition: {start_date} to {end_date}",
            "=" * 45,
        ]
        weights = [r["weight_lbs"] for r in rows]
        avg_w = sum(weights) / len(weights)
        lines.append(f"Avg Weight:    {avg_w:.1f} lbs")
        lines.append("")
        lines.append("Weight Entries:")
        for r in rows:
            lines.append(f"  {r['date']}: {r['weight_lbs']} lbs")
        lines.append("")
        lines.append("(Source: database)")
        return "\n".join(lines)

    # Fallback to live API
    try:
        data = call_garmin("get_body_composition", start_date, end_date)
    except Exception as e:
        logger.error(f"Error fetching body composition for {start_date} to {end_date}: {e}")
        return "Failed to fetch body composition data. Please try again later."

    if not data:
        return f"No body composition data found for {start_date} to {end_date}."

    lines = [
        f"Body Composition: {start_date} to {end_date}",
        "=" * 45,
    ]

    total_avg = _safe_get(data, "totalAverage", default={})
    if isinstance(total_avg, dict):
        weight_val = _safe_get(total_avg, "weight", default=None)
        bmi = _safe_get(total_avg, "bmi", default=None)
        body_fat = _safe_get(total_avg, "bodyFat", default=None)
        muscle_mass = _safe_get(total_avg, "muscleMass", default=None)
        if weight_val not in (None, "N/A"):
            weight_kg = weight_val / 1000 if weight_val > 1000 else weight_val
            lines.append(f"Avg Weight:    {_kg_to_lbs(weight_kg)} lbs ({weight_kg:.1f} kg)")
        if bmi not in (None, "N/A"):
            lines.append(f"Avg BMI:       {bmi:.1f}")
        if body_fat not in (None, "N/A"):
            lines.append(f"Avg Body Fat:  {body_fat:.1f}%")
        if muscle_mass not in (None, "N/A"):
            mm_kg = muscle_mass / 1000 if muscle_mass > 1000 else muscle_mass
            lines.append(f"Avg Muscle:    {_kg_to_lbs(mm_kg)} lbs ({mm_kg:.1f} kg)")

    entries = _safe_get(data, "dateWeightList", default=[])
    if entries and isinstance(entries, list):
        lines.append("")
        lines.append("Weight Entries:")
        for entry in entries:
            cal_date = _safe_get(entry, "calendarDate", default="Unknown")
            weight_g = _safe_get(entry, "weight", default=None)
            if weight_g not in (None, "N/A"):
                weight_kg = weight_g / 1000 if weight_g > 1000 else weight_g
                lines.append(f"  {cal_date}: {_kg_to_lbs(weight_kg)} lbs ({weight_kg:.1f} kg)")

    lines.append("")
    lines.append("(Source: live API)")
    return "\n".join(lines)


@mcp.tool()
def get_blood_pressure(api_key: str, start_date: str, end_date: str) -> str:
    """Get blood pressure readings for a date range.

    Args:
        api_key: API key for authentication.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns systolic, diastolic, and pulse readings.
    """
    err = require_auth(api_key)
    if err:
        return err
    # Try DB first
    rows = query_all(
        "SELECT date, bp_systolic, bp_diastolic FROM garmin_daily WHERE date BETWEEN ? AND ? AND bp_systolic IS NOT NULL ORDER BY date",
        (start_date, end_date),
    )
    if rows:
        lines = [
            f"Blood Pressure: {start_date} to {end_date}",
            "=" * 45,
        ]
        for r in rows:
            lines.append(f"  {r['date']}: {r['bp_systolic']}/{r['bp_diastolic']} mmHg")
        lines.append("")
        lines.append("(Source: database)")
        return "\n".join(lines)

    # Fallback to live API
    try:
        data = call_garmin("get_blood_pressure", start_date, end_date)
    except Exception as e:
        logger.error(f"Error fetching blood pressure for {start_date} to {end_date}: {e}")
        return "Failed to fetch blood pressure data. Please try again later."

    if not data:
        return f"No blood pressure data found for {start_date} to {end_date}."

    lines = [
        f"Blood Pressure: {start_date} to {end_date}",
        "=" * 45,
    ]

    measurements = []
    if isinstance(data, dict):
        measurements = _safe_get(data, "measurementSummaries", default=[])
        if not measurements:
            measurements = _safe_get(data, "bloodPressureMeasurements", default=[])
    elif isinstance(data, list):
        measurements = data

    if not measurements:
        lines.append("No blood pressure readings found in this period.")
        return "\n".join(lines)

    for entry in measurements:
        if isinstance(entry, dict):
            date_str = _safe_get(
                entry, "measurementTimestampLocal",
                default=_safe_get(entry, "calendarDate", default="Unknown"),
            )
            systolic = _safe_get(entry, "systolic")
            diastolic = _safe_get(entry, "diastolic")
            pulse = _safe_get(entry, "pulse")
            line = f"  {date_str}: {systolic}/{diastolic} mmHg, Pulse: {pulse} bpm"
            lines.append(line)

    lines.append("")
    lines.append("(Source: live API)")
    return "\n".join(lines)


@mcp.tool()
def get_stress_summary(api_key: str, date: str) -> str:
    """Get stress level breakdown for a given date.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format.

    Returns average stress, max stress, and time spent at each stress
    level (rest, low, medium, high).
    """
    err = require_auth(api_key)
    if err:
        return err
    # Try DB first for avg stress
    row = query_one("SELECT * FROM garmin_daily WHERE date = ?", (date,))
    if row and row.get("avg_stress") is not None:
        lines = [
            f"Stress Summary for {date}",
            "=" * 35,
            f"Avg Stress Level:  {row['avg_stress']}",
            f"Body Battery:      {row.get('body_battery', 'N/A')}",
            "",
            "(Source: database — use live API for full stress breakdown)",
        ]
        return "\n".join(lines)

    # Fallback to live API
    try:
        data = call_garmin("get_stress_data", date)
    except Exception as e:
        logger.error(f"Error fetching stress data for {date}: {e}")
        return "Failed to fetch stress data. Please try again later."

    if not data:
        return f"No stress data found for {date}."

    avg_stress = _safe_get(data, "overallStressLevel")
    max_stress = _safe_get(data, "maxStressLevel")
    rest_dur = _safe_get(data, "restStressDuration")
    low_dur = _safe_get(data, "lowStressDuration")
    med_dur = _safe_get(data, "mediumStressDuration")
    high_dur = _safe_get(data, "highStressDuration")
    bb_high = _safe_get(data, "bodyBatteryHighestValue")
    bb_low = _safe_get(data, "bodyBatteryLowestValue")

    lines = [
        f"Stress Summary for {date}",
        "=" * 35,
        f"Avg Stress Level:  {avg_stress}",
        f"Max Stress Level:  {max_stress}",
        "",
        "Time at Each Level:",
        f"  Rest:    {_seconds_to_hm(rest_dur)}",
        f"  Low:     {_seconds_to_hm(low_dur)}",
        f"  Medium:  {_seconds_to_hm(med_dur)}",
        f"  High:    {_seconds_to_hm(high_dur)}",
    ]

    if bb_high not in (None, "N/A") or bb_low not in (None, "N/A"):
        lines.append("")
        lines.append(f"Body Battery Range: {bb_low} - {bb_high}")

    lines.append("")
    lines.append("(Source: live API)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Live-API-only tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_activities(api_key: str, start: int = 0, limit: int = 10) -> str:
    """Get a list of recent activities.

    Args:
        api_key: API key for authentication.
        start: Starting index (0 = most recent). Default 0.
        limit: Maximum number of activities to return. Default 10, max 50.

    Returns a formatted list of activities with name, type, date,
    duration, distance, and calories.
    """
    err = require_auth(api_key)
    if err:
        return err
    limit = max(1, min(50, limit))
    start = max(0, start)
    try:
        data = call_garmin("get_activities", start, limit)
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
        return "Failed to fetch activities data. Please try again later."

    if not data:
        return "No activities found."

    lines = [
        f"Recent Activities (showing {len(data)} results)",
        "=" * 55,
    ]

    for act in data:
        act_id = _safe_get(act, "activityId")
        name = _safe_get(act, "activityName", default="Unnamed")
        act_type = _safe_get(act, "activityType", "typeKey", default="unknown")
        start_local = _safe_get(act, "startTimeLocal", default="Unknown date")
        duration_sec = _safe_get(act, "duration", default=None)
        distance_m = _safe_get(act, "distance", default=None)
        calories = _safe_get(act, "calories", default="N/A")
        avg_hr = _safe_get(act, "averageHR", default="N/A")

        duration_str = _seconds_to_hm(duration_sec)
        distance_str = "N/A"
        if distance_m not in (None, "N/A", 0):
            km = distance_m / 1000
            mi = distance_m / 1609.344
            distance_str = f"{km:.2f} km ({mi:.2f} mi)"

        lines.append("")
        lines.append(f"  [{act_id}] {name}")
        lines.append(f"  Type: {act_type}  |  Date: {start_local}")
        lines.append(f"  Duration: {duration_str}  |  Distance: {distance_str}")
        lines.append(f"  Calories: {calories} kcal  |  Avg HR: {avg_hr} bpm")

    return "\n".join(lines)


@mcp.tool()
def get_activity(api_key: str, activity_id: int) -> str:
    """Get detailed information about a single activity.

    Args:
        api_key: API key for authentication.
        activity_id: The numeric Garmin activity ID.

    Returns formatted activity details including HR, pace, elevation,
    and performance metrics.
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        data = call_garmin("get_activity", activity_id)
    except Exception as e:
        logger.error(f"Error fetching activity {activity_id}: {e}")
        return "Failed to fetch activity data. Please try again later."

    if not data:
        return f"No data found for activity {activity_id}."

    name = _safe_get(data, "activityName", default="Unnamed")
    act_type = _safe_get(data, "activityType", "typeKey", default="unknown")
    start_local = _safe_get(data, "startTimeLocal", default="Unknown")
    duration_sec = _safe_get(data, "duration", default=None)
    distance_m = _safe_get(data, "distance", default=None)
    calories = _safe_get(data, "calories", default="N/A")
    avg_hr = _safe_get(data, "averageHR", default="N/A")
    max_hr = _safe_get(data, "maxHR", default="N/A")
    avg_speed = _safe_get(data, "averageSpeed", default=None)
    elev_gain = _safe_get(data, "elevationGain", default="N/A")
    elev_loss = _safe_get(data, "elevationLoss", default="N/A")
    avg_cadence = _safe_get(
        data, "averageRunningCadenceInStepsPerMinute",
        default=_safe_get(data, "averageBikingCadenceInRevPerMinute", default="N/A"),
    )
    te_aero = _safe_get(data, "aerobicTrainingEffect", default="N/A")
    te_anaero = _safe_get(data, "anaerobicTrainingEffect", default="N/A")
    vo2max = _safe_get(data, "vO2MaxValue", default="N/A")

    distance_str = "N/A"
    if distance_m not in (None, "N/A", 0):
        km = distance_m / 1000
        mi = distance_m / 1609.344
        distance_str = f"{km:.2f} km ({mi:.2f} mi)"

    pace_str = "N/A"
    if avg_speed not in (None, "N/A", 0) and distance_m not in (None, "N/A", 0):
        pace_min_per_km = (1000 / avg_speed) / 60
        pace_min = int(pace_min_per_km)
        pace_sec = int((pace_min_per_km - pace_min) * 60)
        pace_str = f"{pace_min}:{pace_sec:02d} /km"

    lines = [
        f"Activity Detail: {name}",
        "=" * 45,
        f"Activity ID:          {activity_id}",
        f"Type:                 {act_type}",
        f"Date:                 {start_local}",
        f"Duration:             {_seconds_to_hm(duration_sec)}",
        f"Distance:             {distance_str}",
        f"Avg Pace:             {pace_str}",
        f"Calories:             {calories} kcal",
        "",
        "Heart Rate:",
        f"  Average:            {avg_hr} bpm",
        f"  Max:                {max_hr} bpm",
        "",
        "Performance:",
        f"  Elevation Gain:     {elev_gain} m",
        f"  Elevation Loss:     {elev_loss} m",
        f"  Avg Cadence:        {avg_cadence}",
        f"  VO2 Max:            {vo2max}",
        f"  Aerobic TE:         {te_aero}",
        f"  Anaerobic TE:       {te_anaero}",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_steps_data(api_key: str, date: str) -> str:
    """Get step data summarized by time period for a given date.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format.

    Returns step totals grouped by morning, afternoon, and evening.
    Always uses live API (time-of-day breakdown not in DB).
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        data = call_garmin("get_steps_data", date)
    except Exception as e:
        logger.error(f"Error fetching steps data for {date}: {e}")
        return "Failed to fetch steps data. Please try again later."

    if not data or not isinstance(data, list):
        return f"No steps data found for {date}."

    morning_steps = 0
    afternoon_steps = 0
    evening_steps = 0
    total_steps = 0
    peak_steps = 0
    peak_time = "N/A"

    for entry in data:
        steps = _safe_get(entry, "steps", default=0)
        if steps in (None, "N/A"):
            steps = 0
        start_ts = _safe_get(entry, "startGMT", default=None)
        if start_ts is None:
            start_ts = _safe_get(entry, "startTimeLocal", default=None)

        total_steps += steps
        if steps > peak_steps:
            peak_steps = steps
            peak_time = start_ts if start_ts else "N/A"

        hour = None
        if start_ts:
            try:
                if isinstance(start_ts, str) and "T" in start_ts:
                    hour = int(start_ts.split("T")[1].split(":")[0])
                elif isinstance(start_ts, (int, float)):
                    hour = datetime.fromtimestamp(start_ts / 1000).hour
            except Exception:
                pass

        if hour is not None:
            if hour < 12:
                morning_steps += steps
            elif hour < 17:
                afternoon_steps += steps
            else:
                evening_steps += steps

    lines = [
        f"Steps Summary for {date}",
        "=" * 35,
        f"Total Steps:      {total_steps}",
        "",
        "By Time of Day:",
        f"  Morning (00-12):   {morning_steps}",
        f"  Afternoon (12-17): {afternoon_steps}",
        f"  Evening (17-24):   {evening_steps}",
        "",
        f"Peak Interval:    {peak_steps} steps at {peak_time}",
    ]
    return "\n".join(lines)


@mcp.tool()
def get_training_readiness(api_key: str, date: str) -> str:
    """Get training readiness score and contributing factors.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format.

    Returns readiness score, level, and contributing factors.
    Always uses live API (not stored in DB).
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        data = call_garmin("get_training_readiness", date)
    except Exception as e:
        logger.error(f"Error fetching training readiness for {date}: {e}")
        return "Failed to fetch training readiness data. Please try again later."

    if not data:
        return f"No training readiness data found for {date}."

    score = _safe_get(data, "score")
    level = _safe_get(data, "level")

    lines = [
        f"Training Readiness for {date}",
        "=" * 35,
        f"Score:   {score}",
        f"Level:   {level}",
        "",
        "Contributing Factors:",
    ]

    factors_to_check = [
        ("sleepScore", "Sleep Score"),
        ("sleepHistory", "Sleep History"),
        ("recoveryTime", "Recovery Time"),
        ("acuteLoad", "Acute Load"),
        ("trainingLoadBalance", "Training Load Balance"),
        ("hRV", "HRV Status"),
        ("stressHistory", "Stress History"),
        ("sleepQuality", "Sleep Quality"),
    ]

    for key, label in factors_to_check:
        val = _safe_get(data, key)
        if val not in (None, "N/A"):
            if isinstance(val, dict):
                factor_score = _safe_get(val, "score", default=_safe_get(val, "value", default=""))
                factor_level = _safe_get(val, "level", default=_safe_get(val, "status", default=""))
                lines.append(f"  {label}: {factor_score} ({factor_level})")
            else:
                lines.append(f"  {label}: {val}")

    return "\n".join(lines)


@mcp.tool()
def get_training_status(api_key: str, date: str) -> str:
    """Get training status including load, VO2 max, and recovery.

    Args:
        api_key: API key for authentication.
        date: Date in YYYY-MM-DD format.

    Returns training status, load numbers, VO2 max, and recovery time.
    Always uses live API (not stored in DB).
    """
    err = require_auth(api_key)
    if err:
        return err
    try:
        data = call_garmin("get_training_status", date)
    except Exception as e:
        logger.error(f"Error fetching training status for {date}: {e}")
        return "Failed to fetch training status data. Please try again later."

    if not data:
        return f"No training status data found for {date}."

    lines = [
        f"Training Status for {date}",
        "=" * 40,
    ]

    fields = [
        ("trainingStatusPhrase", "Status"),
        ("trainingLoad7Day", "7-Day Load"),
        ("trainingLoad28Day", "28-Day Load"),
        ("acuteTrainingLoad", "Acute Load"),
        ("chronicTrainingLoad", "Chronic Load"),
        ("trainingLoadBalance", "Load Balance"),
        ("ltTimestamp", "Lactate Threshold Date"),
        ("vo2MaxPreciseValue", "VO2 Max"),
        ("vo2MaxValue", "VO2 Max (alt)"),
        ("fitnessAge", "Fitness Age"),
        ("recoveryTimeInMinutes", "Recovery Time"),
    ]

    for key, label in fields:
        val = _safe_get(data, key)
        if val not in (None, "N/A"):
            if key == "recoveryTimeInMinutes" and isinstance(val, (int, float)):
                hours = int(val) // 60
                mins = int(val) % 60
                lines.append(f"  {label}: {hours}h {mins}m")
            elif isinstance(val, dict):
                sub_val = _safe_get(val, "value", default=_safe_get(val, "score", default=str(val)))
                lines.append(f"  {label}: {sub_val}")
            else:
                lines.append(f"  {label}: {val}")

    return "\n".join(lines)


@mcp.tool()
def get_weigh_ins(api_key: str, start_date: str, end_date: str) -> str:
    """Get weight measurements for a date range.

    Args:
        api_key: API key for authentication.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns a formatted list of weight measurements in pounds and kg.
    """
    err = require_auth(api_key)
    if err:
        return err
    # Try DB first
    rows = query_all(
        "SELECT date, weight_lbs FROM garmin_daily WHERE date BETWEEN ? AND ? AND weight_lbs IS NOT NULL ORDER BY date",
        (start_date, end_date),
    )
    if rows:
        lines = [
            f"Weight Measurements: {start_date} to {end_date}",
            "=" * 45,
        ]
        for r in rows:
            lines.append(f"  {r['date']}: {r['weight_lbs']} lbs")
        lines.append("")
        lines.append("(Source: database)")
        return "\n".join(lines)

    # Fallback to live API
    try:
        data = call_garmin("get_weigh_ins", start_date, end_date)
    except Exception as e:
        logger.error(f"Error fetching weigh-ins for {start_date} to {end_date}: {e}")
        return "Failed to fetch weigh-in data. Please try again later."

    if not data:
        return f"No weigh-in data found for {start_date} to {end_date}."

    lines = [
        f"Weight Measurements: {start_date} to {end_date}",
        "=" * 45,
    ]

    entries = []
    if isinstance(data, dict):
        entries = _safe_get(data, "dailyWeightSummaries", default=[])
        if not entries:
            entries = _safe_get(data, "dateWeightList", default=[])
    elif isinstance(data, list):
        entries = data

    if not entries:
        lines.append("No individual measurements found.")
        return "\n".join(lines)

    for entry in entries:
        if isinstance(entry, dict):
            cal_date = _safe_get(
                entry, "calendarDate",
                default=_safe_get(entry, "summaryDate", default="Unknown"),
            )
            weight_val = _safe_get(
                entry, "weight",
                default=_safe_get(entry, "maxWeight",
                default=_safe_get(entry, "avgWeight", default=None)),
            )
            if weight_val not in (None, "N/A"):
                weight_kg = weight_val / 1000 if weight_val > 1000 else weight_val
                weight_lbs = _kg_to_lbs(weight_kg)
                bmi = _safe_get(entry, "bmi", default=None)
                line = f"  {cal_date}: {weight_lbs} lbs ({weight_kg:.1f} kg)"
                if bmi not in (None, "N/A"):
                    line += f"  BMI: {bmi:.1f}"
                lines.append(line)

    lines.append("")
    lines.append("(Source: live API)")
    return "\n".join(lines)
