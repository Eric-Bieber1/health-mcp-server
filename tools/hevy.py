"""Hevy workout tools — 6 DB-only tools for strength training data."""

import json
from mcp_instance import mcp
from db import query_all, query_one


@mcp.tool()
def get_recent_workouts(limit: int = 10) -> str:
    """Get recent workouts from Hevy.

    Args:
        limit: Maximum number of workouts to return (1-50, default 10).

    Returns a formatted list of workouts with title, date, duration, and volume.
    """
    limit = max(1, min(50, limit))
    rows = query_all(
        "SELECT id, title, start_time, duration_min, total_volume_lbs, total_sets "
        "FROM hevy_workouts ORDER BY start_time DESC LIMIT ?",
        (limit,),
    )

    if not rows:
        return "No workouts found in the database."

    lines = [
        f"Recent Workouts (showing {len(rows)})",
        "=" * 55,
    ]

    for w in rows:
        date_str = w["start_time"][:10] if w.get("start_time") else "Unknown"
        duration = f"{w['duration_min']:.0f} min" if w.get("duration_min") else "N/A"
        volume = f"{w['total_volume_lbs']:,.0f} lbs" if w.get("total_volume_lbs") else "N/A"
        sets = w.get("total_sets", "N/A")

        lines.append("")
        lines.append(f"  [{w['id']}] {w.get('title', 'Workout')}")
        lines.append(f"  Date: {date_str}  |  Duration: {duration}")
        lines.append(f"  Volume: {volume}  |  Sets: {sets}")

    return "\n".join(lines)


@mcp.tool()
def get_workout(workout_id: str) -> str:
    """Get detailed information about a single workout.

    Args:
        workout_id: The Hevy workout ID.

    Returns workout details including each exercise with sets, weight, and reps.
    """
    row = query_one("SELECT * FROM hevy_workouts WHERE id = ?", (workout_id,))

    if not row:
        return f"No workout found with ID {workout_id}."

    date_str = row["start_time"][:10] if row.get("start_time") else "Unknown"
    duration = f"{row['duration_min']:.0f} min" if row.get("duration_min") else "N/A"
    volume = f"{row['total_volume_lbs']:,.0f} lbs" if row.get("total_volume_lbs") else "N/A"

    lines = [
        f"Workout: {row.get('title', 'Workout')}",
        "=" * 45,
        f"Date:     {date_str}",
        f"Duration: {duration}",
        f"Volume:   {volume}",
        f"Sets:     {row.get('total_sets', 'N/A')}",
    ]

    exercises_json = row.get("exercises_json")
    if exercises_json:
        try:
            exercises = json.loads(exercises_json)
            lines.append("")
            lines.append("Exercises:")
            for ex in exercises:
                name = ex.get("name", "Unknown")
                sets = ex.get("sets", 0)
                best_w = ex.get("best_weight_lbs", 0)
                best_r = ex.get("best_reps", 0)
                vol = ex.get("volume_lbs", 0)
                muscle = ex.get("muscle", "")
                lines.append(f"  {name} ({muscle})")
                lines.append(f"    {sets} sets | Best: {best_w} lbs x {best_r} | Volume: {vol:,.0f} lbs")
        except json.JSONDecodeError:
            lines.append("  (Could not parse exercise data)")

    return "\n".join(lines)


@mcp.tool()
def get_exercise_progress(exercise_name: str, limit: int = 20) -> str:
    """Get progression over time for a specific exercise.

    Args:
        exercise_name: Name of the exercise (e.g. 'Bench Press (Barbell)').
                       Use a partial match — case-insensitive search.
        limit: Maximum entries to return (default 20).

    Returns chronological list of best weight, reps, volume, and e1RM per session.
    """
    limit = max(1, min(100, limit))
    rows = query_all(
        "SELECT workout_date, exercise_name, best_weight_lbs, best_reps, volume_lbs, e1rm_lbs, primary_muscle "
        "FROM hevy_exercise_progress WHERE exercise_name LIKE ? ORDER BY workout_date DESC LIMIT ?",
        (f"%{exercise_name}%", limit),
    )

    if not rows:
        return f"No progress data found for exercise matching '{exercise_name}'."

    actual_name = rows[0]["exercise_name"]
    muscle = rows[0].get("primary_muscle", "")

    lines = [
        f"Exercise Progress: {actual_name} ({muscle})",
        "=" * 55,
        f"{'Date':<12} {'Weight':>8} {'Reps':>5} {'Volume':>10} {'e1RM':>8}",
        "-" * 55,
    ]

    for r in reversed(rows):  # chronological order
        date = r["workout_date"]
        weight = f"{r['best_weight_lbs']:.1f}" if r.get("best_weight_lbs") else "N/A"
        reps = str(r.get("best_reps", "N/A"))
        volume = f"{r['volume_lbs']:,.0f}" if r.get("volume_lbs") else "N/A"
        e1rm = f"{r['e1rm_lbs']:.1f}" if r.get("e1rm_lbs") else "N/A"
        lines.append(f"{date:<12} {weight:>8} {reps:>5} {volume:>10} {e1rm:>8}")

    return "\n".join(lines)


@mcp.tool()
def get_personal_records() -> str:
    """Get all-time personal records for every tracked exercise.

    Returns PRs sorted by estimated 1-rep max (e1RM), showing best weight,
    best volume, and best e1RM with dates for each exercise.
    """
    rows = query_all(
        "SELECT * FROM hevy_personal_records ORDER BY best_e1rm_lbs DESC",
    )

    if not rows:
        return "No personal records found in the database."

    lines = [
        "Personal Records",
        "=" * 65,
    ]

    for r in rows:
        name = r["exercise_name"]
        lines.append(f"\n  {name}")
        if r.get("best_weight_lbs"):
            lines.append(f"    Best Weight: {r['best_weight_lbs']:.1f} lbs ({r.get('best_weight_date', 'N/A')})")
        if r.get("best_e1rm_lbs"):
            lines.append(f"    Best e1RM:   {r['best_e1rm_lbs']:.1f} lbs ({r.get('best_e1rm_date', 'N/A')})")
        if r.get("best_volume_lbs"):
            lines.append(f"    Best Volume: {r['best_volume_lbs']:,.0f} lbs ({r.get('best_volume_date', 'N/A')})")

    return "\n".join(lines)


@mcp.tool()
def get_muscle_volume(days: int = 30) -> str:
    """Get training volume by muscle group over a time period.

    Args:
        days: Number of days to look back (default 30).

    Returns total volume in pounds grouped by primary muscle group.
    """
    days = max(1, min(365, days))
    rows = query_all(
        "SELECT primary_muscle, SUM(volume_lbs) as total_volume, COUNT(*) as sets_count "
        "FROM hevy_exercise_progress "
        "WHERE workout_date >= date('now', ? || ' days') "
        "GROUP BY primary_muscle ORDER BY total_volume DESC",
        (f"-{days}",),
    )

    if not rows:
        return f"No workout data found in the last {days} days."

    total_vol = sum(r["total_volume"] for r in rows if r["total_volume"])

    lines = [
        f"Volume by Muscle Group — Last {days} Days",
        "=" * 50,
        f"{'Muscle':<15} {'Volume':>12} {'Sets':>6} {'% Total':>8}",
        "-" * 50,
    ]

    for r in rows:
        muscle = r["primary_muscle"] or "other"
        vol = r["total_volume"] or 0
        sets = r["sets_count"] or 0
        pct = (vol / total_vol * 100) if total_vol > 0 else 0
        lines.append(f"{muscle:<15} {vol:>10,.0f} lbs {sets:>5} {pct:>7.1f}%")

    lines.append("-" * 50)
    lines.append(f"{'TOTAL':<15} {total_vol:>10,.0f} lbs")

    return "\n".join(lines)


@mcp.tool()
def get_weekly_summary(weeks: int = 4) -> str:
    """Get weekly workout count and volume summary.

    Args:
        weeks: Number of weeks to show (default 4).

    Returns a week-by-week breakdown of workout count, total volume,
    and average duration.
    """
    weeks = max(1, min(52, weeks))
    rows = query_all(
        "SELECT "
        "  strftime('%Y-W%W', start_time) as week, "
        "  COUNT(*) as workout_count, "
        "  SUM(total_volume_lbs) as total_volume, "
        "  AVG(duration_min) as avg_duration, "
        "  SUM(total_sets) as total_sets "
        "FROM hevy_workouts "
        "WHERE start_time >= date('now', ? || ' days') "
        "GROUP BY week ORDER BY week DESC",
        (f"-{weeks * 7}",),
    )

    if not rows:
        return f"No workout data found in the last {weeks} weeks."

    lines = [
        f"Weekly Summary — Last {weeks} Weeks",
        "=" * 60,
        f"{'Week':<10} {'Workouts':>9} {'Volume':>12} {'Avg Dur':>9} {'Sets':>6}",
        "-" * 60,
    ]

    for r in rows:
        week = r["week"]
        count = r["workout_count"]
        vol = f"{r['total_volume']:,.0f}" if r.get("total_volume") else "0"
        dur = f"{r['avg_duration']:.0f} min" if r.get("avg_duration") else "N/A"
        sets = r.get("total_sets", 0)
        lines.append(f"{week:<10} {count:>9} {vol:>10} lbs {dur:>9} {sets:>6}")

    return "\n".join(lines)
