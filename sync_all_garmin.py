"""
Final Garmin Sync - Store ALL data properly including RAW JSON!

Creates automatic backup before any destructive operations.
ALL database tables are protected by the backup mechanism.
"""
import json
import sqlite3
import uuid
from datetime import date, timedelta

from integrations.garmin_client import get_garmin_client
from config import Config
from services.db_protection import require_backup_bulk, protected_db

print("="*60)
print("FINAL GARMIN SYNC - ALL DATA")
print("="*60)
print()

client = get_garmin_client()

if not client.ensure_authenticated():
    print("ERROR: Not authenticated!")
    exit(1)

# Use protected connection - auto-backups before destructive operations
conn = protected_db()

results = {"daily": 0, "activities": 0, "training": 0, "errors": 0}

# Sync last 90 days combining daily + sleep data
print("\n[1/3] Syncing 90 days with FULL data (daily + sleep)...")
end_date = date.today()

for day_offset in range(90):
    sync_date = end_date - timedelta(days=day_offset)
    date_str = sync_date.isoformat()

    try:
        # Get daily stats using raw client (supports date parameter)
        stats = client.client.get_stats(date_str)

        # Get sleep data (nested format)
        sleep = client.client.get_sleep_data(date_str)

        # Get heart rates
        rhr = 0
        try:
            heart_rates = client.client.get_heart_rates(date_str)
            if heart_rates:
                rhr = heart_rates.get("restingHeartRate", 0)
        except Exception:
            pass

        # Get stress data
        stress_avg = 0
        stress_max = 0
        stress_min = 0
        try:
            stress = client.client.get_stress_data(date_str)
            if stress:
                stress_avg = stress.get("overallStressLevel", 0)
                stress_max = stress.get("maxStressLevel", 0)
                stress_min = stress.get("minStressLevel", 0)
        except Exception:
            pass

        # Get Body Battery
        bb_high = bb_low = bb_current = 0
        try:
            body_battery = client.client.get_body_battery(date_str)
            if body_battery and len(body_battery) > 0:
                bb_high = body_battery[0].get("highest", 0)
                bb_low = body_battery[0].get("lowest", 0)
                bb_current = body_battery[0].get("value", 0)
        except Exception:
            pass

        # Extract sleep score from nested structure
        sleep_score = 0
        sleep_seconds = 0
        deep_sec = 0
        light_sec = 0
        rem_sec = 0
        awake_sec = 0
        spo2_avg = 0

        if sleep and "dailySleepDTO" in sleep:
            dto = sleep["dailySleepDTO"]
            if dto:
                # Sleep score is nested under sleepScores.overall.value
                sleep_scores = dto.get("sleepScores", {})
                overall = sleep_scores.get("overall", {})
                sleep_score = int(overall.get("value", 0) or 0)

                sleep_seconds = int(dto.get("sleepTimeSeconds", 0) or 0)
                deep_sec = int(dto.get("deepSleepSeconds", 0) or 0)
                light_sec = int(dto.get("lightSleepSeconds", 0) or 0)
                rem_sec = int(dto.get("remSleepSeconds", 0) or 0)
                awake_sec = int(dto.get("awakeSleepSeconds", 0) or 0)

                # SpO2 from sleep data
                spo2_avg = float(dto.get("averageSpO2Value", 0) or 0)

        if stats:
            row_id = str(uuid.uuid4())
            # Store RAW JSON - preserves ALL Garmin data
            raw_json = json.dumps(stats, ensure_ascii=False, default=str)
            conn.execute("""
                INSERT INTO health_daily
                (id, date, steps, distance_meters, distance_km,
                 calories_total, calories_active, calories_bmr,
                 resting_heart_rate, avg_heart_rate, max_heart_rate,
                 stress_avg, stress_max, stress_min,
                 body_battery_high, body_battery_low, body_battery_current,
                 sleep_score, sleep_seconds,
                 deep_sleep_seconds, light_sleep_seconds, rem_sleep_seconds, awake_seconds,
                 spo2_avg,
                 floors_climbed, intensity_minutes, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row_id, date_str,
                int(stats.get("totalSteps", 0) or 0),
                float(stats.get("totalDistanceMeters", 0) or 0),
                float(stats.get("totalDistanceMeters", 0) or 0) / 1000,
                int(stats.get("totalKilocalories", 0) or 0),
                int(stats.get("activeKilocalories", 0) or 0),
                int(stats.get("burnedKilocalories", 0) or 0),
                int(rhr),
                int(stats.get("averageHeartRate", 0) or 0),
                int(stats.get("maxHeartRate", 0) or 0),
                int(stress_avg),
                int(stress_max),
                int(stress_min),
                int(bb_high), int(bb_low), int(bb_current),
                sleep_score,
                sleep_seconds,
                deep_sec, light_sec, rem_sec, awake_sec,
                spo2_avg,
                int(stats.get("floorsClimbed", 0) or 0),
                int(stats.get("intensityMinutes", 0) or 0),
                raw_json,  # RAW JSON from Garmin
            ))
            results["daily"] += 1

        if (day_offset + 1) % 30 == 0:
            print(f"  {day_offset + 1} days...")

    except Exception as e:
        results["errors"] += 1

conn.commit()
print(f"  Daily + Sleep: {results['daily']} days")

# Sync activities with all fields
print("\n[2/3] Syncing activities with ALL fields...")
activities = client.client.get_activities(0, 1000)
print(f"  Found {len(activities)} activities")

for act in activities:
    try:
        row_id = str(uuid.uuid4())
        activity_type = act.get("activityType", {})
        type_key = activity_type.get("typeKey", "") if isinstance(activity_type, dict) else ""
        type_id = activity_type.get("typeId", 0) if isinstance(activity_type, dict) else 0

        # Store RAW JSON - preserves ALL Garmin activity data
        act_raw_json = json.dumps(act, ensure_ascii=False, default=str)

        conn.execute("""
            INSERT OR REPLACE INTO health_activities
            (id, garmin_activity_id, activity_type, activity_type_id, name,
             start_time, duration_seconds, duration_min,
             distance_meters, distance_km,
             avg_heart_rate, max_heart_rate, min_heart_rate, calories,
             avg_speed_m_s, max_speed_m_s,
             steps, avg_cadence, max_cadence,
             avg_power, max_power,
             elevation_gain_m, elevation_loss_m, min_elevation_m, max_elevation_m,
             aerobic_effect, anaerobic_effect,
             description, device_name, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row_id,
            str(act.get("activityId", "")),
            type_key,
            type_id,
            act.get("activityName", ""),
            act.get("startTimeLocal", ""),
            float(act.get("duration", 0) or 0),
            float(act.get("duration", 0) or 0) / 60,
            float(act.get("distance", 0) or 0),
            float(act.get("distance", 0) or 0) / 1000,
            int(act.get("averageHR", 0) or 0),
            int(act.get("maxHR", 0) or 0),
            int(act.get("minHR", 0)) if act.get("minHR") else 0,
            int(act.get("calories", 0) or 0),
            float(act.get("averageSpeed", 0) or 0),
            float(act.get("maxSpeed", 0) or 0),
            int(act.get("steps", 0) or 0),
            int(act.get("averageRunningCadence", 0) or 0),
            int(act.get("maxRunningCadence", 0)) if act.get("maxRunningCadence") else 0,
            float(act.get("averageBikePower", 0) or 0),
            float(act.get("maxBikePower", 0)) if act.get("maxBikePower") else 0,
            float(act.get("elevationGain", 0) or 0),
            float(act.get("elevationLoss", 0)) if act.get("elevationLoss") else 0,
            float(act.get("minElevation", 0)) if act.get("minElevation") else 0,
            float(act.get("maxElevation", 0)) if act.get("maxElevation") else 0,
            float(act.get("aerobicTrainingEffect", 0) or 0),
            float(act.get("anaerobicTrainingEffect", 0) or 0),
            act.get("description", ""),
            act.get("deviceName", ""),
            act_raw_json,  # RAW JSON from Garmin
        ))
        results["activities"] += 1
    except Exception as e:
        results["errors"] += 1

conn.commit()
print(f"  Activities: {results['activities']} synced")

# Training metrics
print("\n[3/3] Syncing training metrics...")
training = client.get_training_status()
if training:
    vo2 = training.get("mostRecentVO2Max", {})
    status = training.get("mostRecentTrainingStatus", {})

    # Handle nested structure
    if isinstance(vo2, dict) and "generic" in vo2:
        vo2 = vo2["generic"]

    if vo2:
        row_id = str(uuid.uuid4())
        today = date.today().isoformat()

        endurance = client.get_endurance_score()
        endurance_score = endurance.get("enduranceScoreDTO", {}).get("overallScore", 0) if endurance else 0

        hill = client.get_hill_score()
        hill_data = hill.get("periodAvgScore", {}) if hill else {}
        hill_score = list(hill_data.values())[0] if hill_data else 0

        # Training status
        status_text = ""
        if status:
            training_status = status.get("latestTrainingStatusData", {})
            if training_status:
                device_data = list(training_status.values())[0] if training_status else {}
                status_text = device_data.get("trainingStatusFeedbackPhrase", "")

        conn.execute("""
            INSERT OR REPLACE INTO health_training_metrics
            (id, date, vo2_max, vo2_max_precise, endurance_score, hill_score, training_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (row_id, today,
              vo2.get("vo2MaxValue", 0),
              vo2.get("vo2MaxPreciseValue", 0),
              endurance_score, hill_score, status_text))
        results["training"] += 1
        print(f"  VO2 Max: {vo2.get('vo2MaxValue')}")
        print(f"  VO2 Max (precise): {vo2.get('vo2MaxPreciseValue')}")
        print(f"  Fitness Age: {vo2.get('fitnessAge', 'N/A')}")
        print(f"  Endurance Score: {endurance_score}")
        print(f"  Hill Score: {hill_score}")
        print(f"  Training Status: {status_text}")

conn.commit()
conn.close()

print("\n" + "="*60)
print("SYNC COMPLETE!")
print("="*60)
print(f"Daily+Sleep:      {results['daily']} days")
print(f"Activities:       {results['activities']} workouts")
print(f"Training:         {results['training']} entries")
print(f"Errors:           {results['errors']}")

# Verify
print("\nVerifying data...")
conn = sqlite3.connect(str(Config().db_path))

cursor = conn.execute("SELECT COUNT(*) FROM health_daily")
daily_count = cursor.fetchone()[0]
print(f"health_daily: {daily_count} rows")

cursor = conn.execute("SELECT AVG(sleep_score) FROM health_daily WHERE sleep_score > 0")
avg_sleep_row = cursor.fetchone()
if avg_sleep_row and avg_sleep_row[0]:
    print(f"Average sleep score: {avg_sleep_row[0]:.1f}")
else:
    print("Average sleep score: No data")

cursor = conn.execute("SELECT date, steps, sleep_score FROM health_daily ORDER BY date DESC LIMIT 3")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} steps, sleep score {row[2]}")

cursor = conn.execute("SELECT COUNT(*) FROM health_activities")
activities_count = cursor.fetchone()[0]
print(f"\nhealth_activities: {activities_count} rows")

conn.close()
