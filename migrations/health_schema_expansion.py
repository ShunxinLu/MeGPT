"""
Comprehensive Health Database Migration - Stores ALL Garmin data

Run this to expand the health database schema and re-sync all data.
Creates automatic backup before any schema changes.
"""

import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

# Add project root to path
import sys
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from integrations.garmin_client import get_garmin_client
from config import Config
from services.backup_service import create_backup


def get_db_path():
    """Get database path."""
    return Config().db_path


def migrate_health_schema():
    """Expand health database schema to store ALL Garmin data."""
    # Create backup before schema changes
    print("Creating backup before schema migration...")
    backup_path = create_backup("before_schema_migration")
    print(f"Backup created: {backup_path.name}")
    print()

    db_path = get_db_path()
    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    # 1. Expand health_daily table with ALL daily metrics
    print("\n[1/5] Expanding health_daily table...")
    try:
        # Add new columns if they don't exist
        new_columns = [
            ("steps_goal", "INTEGER DEFAULT 10000"),
            ("distance_km", "REAL DEFAULT 0"),
            ("calories_bmr", "INTEGER DEFAULT 0"),
            ("calories_goal", "INTEGER DEFAULT 2000"),
            ("floors_goal", "INTEGER DEFAULT 10"),
            ("min_heart_rate", "INTEGER DEFAULT 0"),
            ("stress_max", "INTEGER DEFAULT 0"),
            ("stress_min", "INTEGER DEFAULT 0"),
            ("body_battery_current", "INTEGER DEFAULT 0"),
            ("sleep_score", "INTEGER DEFAULT 0"),
            ("sleep_seconds", "INTEGER DEFAULT 0"),
            ("deep_sleep_seconds", "INTEGER DEFAULT 0"),
            ("light_sleep_seconds", "INTEGER DEFAULT 0"),
            ("rem_sleep_seconds", "INTEGER DEFAULT 0"),
            ("awake_seconds", "INTEGER DEFAULT 0"),
            ("spo2_avg", "REAL DEFAULT 0"),
            ("spo2_max", "REAL DEFAULT 0"),
            ("spo2_min", "REAL DEFAULT 0"),
            ("respiration_avg", "REAL DEFAULT 0"),
            ("respiration_max", "REAL DEFAULT 0"),
            ("respiration_min", "REAL DEFAULT 0"),
            ("intensity_minutes_moderate", "INTEGER DEFAULT 0"),
            ("intensity_minutes_vigorous", "INTEGER DEFAULT 0"),
            ("hydration_ml", "INTEGER DEFAULT 0"),
        ]

        for col_name, col_def in new_columns:
            try:
                conn.execute(f"ALTER TABLE health_daily ADD COLUMN {col_name} {col_def}")
                print(f"  Added column: {col_name}")
            except sqlite3.OperationalError:
                pass  # Column already exists
    except Exception as e:
        print(f"  Error: {e}")

    # 2. Expand health_activities table with ALL activity data
    print("\n[2/5] Expanding health_activities table...")
    try:
        new_activity_columns = [
            ("start_time_gmt", "TEXT"),
            ("duration_min", "REAL DEFAULT 0"),
            ("distance_km", "REAL DEFAULT 0"),
            ("avg_speed_m_s", "REAL DEFAULT 0"),
            ("max_speed_m_s", "REAL DEFAULT 0"),
            ("avg_pace_min_km", "REAL DEFAULT 0"),
            ("steps", "INTEGER DEFAULT 0"),
            ("avg_cadence", "INTEGER DEFAULT 0"),
            ("max_cadence", "INTEGER DEFAULT 0"),
            ("avg_power", "REAL DEFAULT 0"),
            ("max_power", "REAL DEFAULT 0"),
            ("elevation_gain_m", "REAL DEFAULT 0"),
            ("elevation_loss_m", "REAL DEFAULT 0"),
            ("min_elevation_m", "REAL DEFAULT 0"),
            ("max_elevation_m", "REAL DEFAULT 0"),
            ("aerobic_effect", "REAL DEFAULT 0"),
            ("anaerobic_effect", "REAL DEFAULT 0"),
            ("training_effect_label", "TEXT"),
            ("activity_type_id", "INTEGER"),
            ("description", "TEXT"),
            ("device_name", "TEXT"),
            ("summary_json", "TEXT"),  # Store full JSON for splits/HR zones
        ]

        for col_name, col_def in new_activity_columns:
            try:
                conn.execute(f"ALTER TABLE health_activities ADD COLUMN {col_name} {col_def}")
                print(f"  Added column: {col_name}")
            except sqlite3.OperationalError:
                pass
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Create health_training_metrics table
    print("\n[3/5] Creating health_training_metrics table...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_training_metrics (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL UNIQUE,
            vo2_max REAL DEFAULT 0,
            vo2_max_precise REAL DEFAULT 0,
            fitness_age INTEGER DEFAULT 0,
            training_status TEXT,
            training_status_code INTEGER DEFAULT 0,
            acute_training_load REAL DEFAULT 0,
            chronic_training_load REAL DEFAULT 0,
            training_load_balance TEXT,
            endurance_score INTEGER DEFAULT 0,
            endurance_classification INTEGER DEFAULT 0,
            hill_score INTEGER DEFAULT 0,
            hill_strength_score INTEGER DEFAULT 0,
            hill_endurance_score INTEGER DEFAULT 0,
            training_readiness TEXT,
            readiness_score INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. Create health_body_composition table
    print("\n[4/5] Creating health_body_composition table...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_body_composition (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL UNIQUE,
            weight_kg REAL DEFAULT 0,
            body_fat_percent REAL DEFAULT 0,
            body_mass_index REAL DEFAULT 0,
            muscle_mass_kg REAL DEFAULT 0,
            bone_mass_kg REAL DEFAULT 0,
            body_water_percent REAL DEFAULT 0,
            visceral_fat_mass_kg REAL DEFAULT 0,
            metabolic_age INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 5. Create health_hrv table
    print("\n[5/5] Creating health_hrv table...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_hrv (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL UNIQUE,
            hrv_avg INTEGER DEFAULT 0,
            hrv_max INTEGER DEFAULT 0,
            hrv_min INTEGER DEFAULT 0,
            hrv_nightly_avg INTEGER DEFAULT 0,
            hrv_last_night_avg INTEGER DEFAULT 0,
            hrv_baseline_upper INTEGER DEFAULT 0,
            hrv_baseline_lower INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    print("\nCreating indexes...")
    indexes = [
        ("idx_training_date", "health_training_metrics", "(date)"),
        ("idx_training_vo2", "health_training_metrics", "(vo2_max DESC)"),
        ("idx_body_comp_date", "health_body_composition", "(date DESC)"),
        ("idx_hrv_date", "health_hrv", "(date DESC)"),
        ("idx_activities_distance", "health_activities", "(distance_meters DESC)"),
        ("idx_activities_duration", "health_activities", "(duration_seconds DESC)"),
    ]

    for idx_name, table, columns in indexes:
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} {columns}")
            print(f"  Created index: {idx_name}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    print("\nSchema migration complete!")


def sync_all_garmin_data(days: int = 365):
    """Sync ALL Garmin data for specified days.

    Args:
        days: Number of days to sync (default 365 - FULL YEAR)
    """
    print(f"\n{'='*60}")
    print(f"SYNCING ALL GARMIN DATA - Last {days} days")
    print(f"{'='*60}\n")

    client = get_garmin_client()

    if not client.ensure_authenticated():
        print("ERROR: Not authenticated! Run: python scripts/auth_garmin.py")
        return

    conn = sqlite3.connect(get_db_path())

    results = {
        "daily_stats": 0,
        "activities": 0,
        "training_metrics": 0,
        "body_composition": 0,
        "errors": 0,
    }

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # 1. Sync daily stats for each day
    print(f"[1/4] Syncing {days} days of daily stats...")
    for day_offset in range(days):
        sync_date = end_date - timedelta(days=day_offset)
        date_str = sync_date.isoformat()

        try:
            stats = client.get_todays_stats()
            if stats:
                # Map to expanded schema
                row_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT OR REPLACE INTO health_daily
                    (id, date, steps, steps_goal, distance_meters, distance_km,
                     calories_total, calories_active, calories_bmr, calories_goal,
                     resting_heart_rate, avg_heart_rate, max_heart_rate, min_heart_rate,
                     stress_avg, stress_max, stress_min,
                     body_battery_high, body_battery_low, body_battery_current,
                     sleep_score, sleep_seconds, deep_sleep_seconds,
                     light_sleep_seconds, rem_sleep_seconds, awake_seconds,
                     spo2_avg, spo2_max, spo2_min,
                     respiration_avg, respiration_max, respiration_min,
                     intensity_minutes_moderate, intensity_minutes_vigorous,
                     floors_climbed, floors_goal, intensity_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row_id, stats.get("date"), stats.get("steps"), stats.get("steps_goal"),
                    stats.get("distance_meters"), stats.get("distance_km"),
                    stats.get("calories_total"), stats.get("calories_active"),
                    stats.get("calories_bmr"), stats.get("calories_goal"),
                    stats.get("resting_heart_rate"), stats.get("avg_heart_rate"),
                    stats.get("max_heart_rate"), stats.get("min_heart_rate"),
                    stats.get("stress_avg"), stats.get("stress_max"), stats.get("stress_min"),
                    stats.get("body_battery_high"), stats.get("body_battery_low"),
                    stats.get("body_battery_current"),
                    stats.get("sleep_score"), stats.get("sleep_seconds"),
                    stats.get("deep_sleep_seconds"), stats.get("light_sleep_seconds"),
                    stats.get("rem_sleep_seconds"), stats.get("awake_seconds"),
                    stats.get("spo2_avg"), stats.get("spo2_max"), stats.get("spo2_min"),
                    stats.get("respiration_avg"), stats.get("respiration_max"),
                    stats.get("respiration_min"),
                    stats.get("intensity_minutes_moderate"),
                    stats.get("intensity_minutes_vigorous"),
                    stats.get("floors_climbed"), stats.get("floors_goal"),
                    stats.get("intensity_minutes_total"),
                ))
                results["daily_stats"] += 1

                if (day_offset + 1) % 30 == 0:
                    print(f"  {day_offset + 1} days synced...")
        except Exception as e:
            results["errors"] += 1

    conn.commit()
    print(f"  Daily stats: {results['daily_stats']} days")

    # 2. Sync ALL activities
    print(f"\n[2/4] Syncing ALL activities...")
    activities = client.get_activities(limit=2000)
    print(f"  Found {len(activities)} activities")

    for act in activities:
        try:
            row_id = str(uuid.uuid4())
            conn.execute("""
                INSERT OR REPLACE INTO health_activities
                (id, garmin_activity_id, activity_type, activity_type_id, name,
                 start_time, start_time_gmt, duration_seconds, duration_min,
                 distance_meters, distance_km,
                 avg_heart_rate, max_heart_rate, min_heart_rate, calories,
                 avg_speed_m_s, max_speed_m_s, avg_pace_min_km,
                 steps, avg_cadence, max_cadence,
                 avg_power, max_power,
                 elevation_gain_m, elevation_loss_m, min_elevation_m, max_elevation_m,
                 aerobic_effect, anaerobic_effect, training_effect_label,
                 description, device_name, summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row_id,
                act.get("garmin_activity_id"),
                act.get("activity_type"),
                act.get("activity_type_id"),
                act.get("name"),
                act.get("start_time"),
                act.get("start_time_gmt"),
                act.get("duration_seconds"),
                act.get("duration_min"),
                act.get("distance_meters"),
                act.get("distance_km"),
                act.get("avg_heart_rate"),
                act.get("max_heart_rate"),
                act.get("min_heart_rate"),
                act.get("calories"),
                act.get("avg_speed_m_s"),
                act.get("max_speed_m_s"),
                act.get("avg_pace_min_km"),
                act.get("steps"),
                act.get("avg_cadence"),
                act.get("max_cadence"),
                act.get("avg_power"),
                act.get("max_power"),
                act.get("elevation_gain_m"),
                act.get("elevation_loss_m"),
                act.get("min_elevation_m"),
                act.get("max_elevation_m"),
                act.get("aerobic_effect"),
                act.get("anaerobic_effect"),
                act.get("training_effect_label"),
                act.get("description"),
                act.get("device_name"),
                str(act),  # Store full dict as JSON
            ))
            results["activities"] += 1
        except Exception as e:
            results["errors"] += 1

    conn.commit()
    print(f"  Activities: {results['activities']} synced")

    # 3. Sync training metrics (VO2 Max, endurance score, hill score)
    print(f"\n[3/4] Syncing training metrics...")
    training = client.get_training_status()
    if training:
        vo2_data = training.get("mostRecentVO2Max", {}).get("generic", {})
        status_data = training.get("mostRecentTrainingStatus", {}).get("latestTrainingStatusData", {})

        if vo2_data:
            try:
                row_id = str(uuid.uuid4())
                today = date.today().isoformat()

                endurance = client.get_endurance_score()
                endurance_score = endurance.get("enduranceScoreDTO", {}).get("overallScore", 0) if endurance else 0

                hill = client.get_hill_score()
                hill_score = hill.get("periodAvgScore", {}).get(today, 0) if hill else 0

                conn.execute("""
                    INSERT OR REPLACE INTO health_training_metrics
                    (id, date, vo2_max, vo2_max_precise, fitness_age,
                     endurance_score, hill_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (row_id, today,
                      vo2_data.get("vo2MaxValue", 0),
                      vo2_data.get("vo2MaxPreciseValue", 0),
                      vo2_data.get("fitnessAge", 0),
                      endurance_score,
                      hill_score))
                results["training_metrics"] += 1
                print(f"  VO2 Max: {vo2_data.get('vo2MaxValue')}, Endurance: {endurance_score}, Hill: {hill_score}")
            except Exception as e:
                print(f"  Error: {e}")

    # 4. Sync body composition
    print(f"\n[4/4] Syncing body composition...")
    body_comp = client.get_body_composition(start_date, end_date)
    if body_comp:
        for entry in body_comp[:100]:  # Limit recent entries
            try:
                row_id = str(uuid.uuid4())
                calendar_date = entry.get("calendarDate", entry.get("date"))
                if not calendar_date:
                    continue

                conn.execute("""
                    INSERT OR REPLACE INTO health_body_composition
                    (id, date, weight_kg, body_fat_percent, body_mass_index,
                     muscle_mass_kg, bone_mass_kg, body_water_percent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row_id,
                    calendar_date,
                    entry.get("weight") or 0,
                    entry.get("bodyFat") or 0,
                    entry.get("bmi") or 0,
                    entry.get("muscleMass") or 0,
                    entry.get("boneMass") or 0,
                    entry.get("bodyWater") or 0,
                ))
                results["body_composition"] += 1
            except Exception as e:
                results["errors"] += 1

        print(f"  Body composition: {results['body_composition']} entries")

    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print("SYNC COMPLETE!")
    print(f"{'='*60}")
    print(f"Daily stats:     {results['daily_stats']} days")
    print(f"Activities:       {results['activities']} workouts")
    print(f"Training:        {results['training_metrics']} entries")
    print(f"Body composition: {results['body_composition']} entries")
    print(f"Errors:           {results['errors']}")
    print()


if __name__ == "__main__":
    print("="*60)
    print("GARMIN HEALTH DATABASE - FULL SYNC")
    print("="*60)
    print()

    # First migrate schema
    migrate_health_schema()

    # Then sync ALL data (365 days)
    sync_all_garmin_data(days=365)

    print("\nNow run the server to access all your health data!")
