"""
Health Tools for MeGPT Domain Integration

This module provides health data retrieval functionality from Garmin Connect.
Uses the database layer to fetch cached health metrics for fast responses.
"""

from langchain_core.tools import tool
from typing import Optional
from datetime import date, datetime, timedelta
from database import get_connection


def _format_time(seconds: int) -> str:
    """Format seconds to readable time string."""
    if seconds <= 0:
        return "0m"
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    if hrs > 0:
        return f"{hrs}h {mins}m"
    return f"{mins}m"


def _format_distance(meters: float) -> str:
    """Format meters to readable distance string."""
    if meters >= 1000:
        return f"{meters / 1000:.1f} km"
    return f"{int(meters)} m"


def _get_date_string(date_input: str) -> str:
    """Convert date string like 'today', 'yesterday' to ISO format."""
    today = date.today()
    if date_input.lower() in ("today", "now"):
        return today.isoformat()
    elif date_input.lower() in ("yesterday", "yesterday"):
        return (today - timedelta(days=1)).isoformat()
    else:
        # Try to parse as date
        try:
            parsed = datetime.strptime(date_input, "%Y-%m-%d").date()
            return parsed.isoformat()
        except ValueError:
            # Default to today
            return today.isoformat()


@tool
def get_health_summary(date_input: str = "today") -> str:
    """
    Get daily health summary including steps, heart rate, calories, stress, and Body Battery.

    Useful for checking daily activity levels, fitness progress, and wellness metrics.

    Args:
        date_input: Date to query - "today", "yesterday", or "YYYY-MM-DD" format (default: today)

    Returns:
        Formatted health summary with key metrics
    """
    print(f"[HEALTH] Getting daily summary for: {date_input}")

    date_str = _get_date_string(date_input)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT date, steps, distance_meters, calories_total, calories_active,
                   resting_heart_rate, avg_heart_rate, max_heart_rate,
                   stress_avg, body_battery_high, body_battery_low,
                   floors_climbed, intensity_minutes
            FROM health_daily
            WHERE date = ?
        """,
            (date_str,),
        )
        result = cursor.fetchone()

        if not result:
            return f"No health data available for {date_str}. Garmin may not be connected or data hasn't synced yet."

        # Format the response
        lines = [
            f"📊 Health Summary for {result['date']}",
            "",
            "👟 Activity:",
            f"  • Steps: {result['steps']:,}",
            f"  • Distance: {_format_distance(result['distance_meters'])}",
            f"  • Active Calories: {result['calories_active']:,}",
            f"  • Total Calories: {result['calories_total']:,}",
            f"  • Intensity Minutes: {result['intensity_minutes']}",
            f"  • Floors Climbed: {result['floors_climbed']}",
            "",
            "❤️ Heart Rate:",
            f"  • Resting: {result['resting_heart_rate']} bpm",
            f"  • Average: {result['avg_heart_rate']} bpm",
            f"  • Max: {result['max_heart_rate']} bpm",
            "",
            "⚡ Wellness:",
            f"  • Body Battery: {result['body_battery_low']}-{result['body_battery_high']}",
            f"  • Stress Average: {result['stress_avg']}/100",
        ]

        return "\n".join(lines)


@tool
def get_recent_workouts(limit: int = 5) -> str:
    """
    Get recent workout activities with distance, duration, heart rate, and pace.

    Useful for reviewing training history, workout patterns, and fitness progress.

    Args:
        limit: Maximum number of workouts to return (default: 5)

    Returns:
        Formatted list of recent workouts
    """
    print(f"[HEALTH] Getting recent workouts (limit: {limit})")

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT activity_type, name, start_time, duration_seconds,
                   distance_meters, avg_heart_rate, max_heart_rate,
                   calories, avg_pace
            FROM health_activities
            ORDER BY start_time DESC
            LIMIT ?
        """,
            (limit,),
        )
        results = cursor.fetchall()

        if not results:
            return "No workout activities found. Garmin may not be connected or no activities recorded yet."

        lines = [f"🏃 Recent Workouts ({len(results)} activities)", ""]

        for idx, workout in enumerate(results, 1):
            lines.append(
                f"{idx}. {workout['activity_type'].upper()}: {workout['name']}\n"
                f"   Date: {workout['start_time']}\n"
                f"   Duration: {_format_time(workout['duration_seconds'])} | "
                f"Distance: {_format_distance(workout['distance_meters'])}\n"
                f"   Heart Rate: {workout['avg_heart_rate']} bpm avg, "
                f"{workout['max_heart_rate']} bpm max\n"
                f"   Calories: {workout['calories']:,} | Pace: {workout['avg_pace']}\n"
            )

        return "\n".join(lines)


@tool
def get_sleep_data(date_input: str = "last_night") -> str:
    """
    Get sleep analysis including sleep stages, duration, and sleep score.

    Useful for tracking sleep quality, identifying patterns, and monitoring rest.

    Args:
        date_input: Date to query - "last_night", "today", "yesterday", or "YYYY-MM-DD" (default: last_night)

    Returns:
        Formatted sleep data with stages and quality metrics
    """
    print(f"[HEALTH] Getting sleep data for: {date_input}")

    # Handle "last_night" default
    if date_input == "last_night":
        today = date.today()
        # If it's before noon, last night is yesterday's date
        # If after noon, last night is today's date (night of yesterday to today morning)
        date_str = today.isoformat()
    else:
        date_str = _get_date_string(date_input)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT date, sleep_start, sleep_end, duration_seconds,
                   deep_sleep_seconds, light_sleep_seconds,
                   rem_sleep_seconds, awake_seconds, sleep_score
            FROM health_sleep
            WHERE date = ?
        """,
            (date_str,),
        )
        result = cursor.fetchone()

        if not result:
            return f"No sleep data available for {date_str}. Garmin may not be connected or sleep tracking disabled."

        total = result['duration_seconds']
        lines = [
            f"😴 Sleep Analysis for {result['date']}",
            "",
            f"Sleep Score: {result['sleep_score']}/100",
            f"Total Sleep: {_format_time(total)}",
            f"Time in Bed: {result['sleep_start']} → {result['sleep_end']}",
            "",
            "Sleep Stages:",
            f"  • Deep Sleep: {_format_time(result['deep_sleep_seconds'])} "
            f"({result['deep_sleep_seconds'] / total * 100:.1f}%)" if total > 0 else "  • Deep Sleep: 0m",
            f"  • Light Sleep: {_format_time(result['light_sleep_seconds'])} "
            f"({result['light_sleep_seconds'] / total * 100:.1f}%)" if total > 0 else "  • Light Sleep: 0m",
            f"  • REM Sleep: {_format_time(result['rem_sleep_seconds'])} "
            f"({result['rem_sleep_seconds'] / total * 100:.1f}%)" if total > 0 else "  • REM Sleep: 0m",
            f"  • Awake: {_format_time(result['awake_seconds'])} "
            f"({result['awake_seconds'] / total * 100:.1f}%)" if total > 0 else "  • Awake: 0m",
        ]

        return "\n".join(lines)


@tool
def get_health_trends(days: int = 7) -> str:
    """
    Get health trends over multiple days including averages and patterns.

    Useful for identifying fitness trends, tracking progress toward goals,
    and spotting patterns in health metrics.

    Args:
        days: Number of days to analyze (default: 7, max: 30)

    Returns:
        Formatted trend analysis with averages and patterns
    """
    print(f"[HEALTH] Getting health trends over {days} days")

    # Limit days to prevent excessive queries
    days = min(max(1, days), 30)

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT date, steps, distance_meters, calories_active,
                   resting_heart_rate, stress_avg, intensity_minutes
            FROM health_daily
            ORDER BY date DESC
            LIMIT ?
        """,
            (days,),
        )
        results = cursor.fetchall()

        if not results:
            return "No health trend data available. Garmin may not be connected or insufficient data."

        # Calculate averages
        total_steps = sum(r['steps'] for r in results)
        total_distance = sum(r['distance_meters'] for r in results)
        total_calories = sum(r['calories_active'] for r in results)
        total_intensity = sum(r['intensity_minutes'] for r in results)
        avg_hr = sum(r['resting_heart_rate'] for r in results if r['resting_heart_rate'] > 0) / len([r for r in results if r['resting_heart_rate'] > 0]) if any(r['resting_heart_rate'] > 0 for r in results) else 0
        avg_stress = sum(r['stress_avg'] for r in results if r['stress_avg'] > 0) / len([r for r in results if r['stress_avg'] > 0]) if any(r['stress_avg'] > 0 for r in results) else 0

        count = len(results)
        lines = [
            f"📈 Health Trends - Past {count} Days",
            "",
            "Averages:",
            f"  • Daily Steps: {total_steps // count:,}",
            f"  • Daily Distance: {_format_distance(total_distance / count)}",
            f"  • Active Calories: {total_calories // count:,}/day",
            f"  • Intensity Minutes: {total_intensity // count}/day",
            f"  • Resting Heart Rate: {int(avg_hr)} bpm",
            f"  • Stress Level: {int(avg_stress)}/100",
            "",
            "Daily Breakdown:",
        ]

        for r in reversed(results[-7:]):  # Show last 7 days in chronological order
            lines.append(
                f"  {r['date']}: {r['steps']:,} steps, "
                f"{_format_time(r['intensity_minutes'])} intensity, "
                f"{r['stress_avg']} stress"
            )

        return "\n".join(lines)


# Export health tools list for use in agent_graph.py
HEALTH_TOOLS = [
    get_health_summary,
    get_recent_workouts,
    get_sleep_data,
    get_health_trends,
]
