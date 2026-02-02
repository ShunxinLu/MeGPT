"""
Garmin Sync Service - Incremental sync with checkpoint tracking and raw JSON storage.

This service handles automatic background sync for health data with:
- Checkpoint tracking using lastSyncTimestampGMT
- Only syncs days that have new data since last sync
- Automatically handles delayed data (when Garmin finally syncs, we'll catch it)
- Stores RAW JSON responses from Garmin API to preserve ALL data

Data Freshness Strategy:
- Store checkpoint of lastSyncTimestampGMT for each synced date
- On each sync, compare Garmin's lastSyncTimestampGMT with our checkpoint
- Only sync if Garmin's timestamp is newer (data has been updated)
- This automatically handles delayed data - when device syncs, we'll pick it up
- Store complete API response as JSON to ensure we capture ALL fields
"""
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add project root to path for imports
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from integrations.garmin_client import get_garmin_client
from config import Config
import logging

logger = logging.getLogger(__name__)

# Config: How many days back to check for updates
SYNC_LOOKBACK_DAYS = 7

# Config: How far back to do initial sync (set very high to get ALL data)
INITIAL_SYNC_DAYS = 365 * 3  # 3 years - should cover everything


def get_checkpoint_file() -> Path:
    """Get path to the sync checkpoint file."""
    checkpoint_dir = Path(Config().data_dir) / "sync_checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir / "garmin_sync.json"


def load_checkpoints() -> dict[str, str]:
    """Load stored sync checkpoints (date -> lastSyncTimestampGMT)."""
    checkpoint_file = get_checkpoint_file()
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load checkpoints: {e}")
    return {}


def save_checkpoints(checkpoints: dict[str, str]) -> None:
    """Save sync checkpoints to disk."""
    checkpoint_file = get_checkpoint_file()
    try:
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoints, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save checkpoints: {e}")


def update_checkpoint(date_str: str, last_sync_gmt: str | None) -> None:
    """Update checkpoint for a specific date."""
    if not last_sync_gmt:
        return
    checkpoints = load_checkpoints()
    checkpoints[date_str] = last_sync_gmt
    save_checkpoints(checkpoints)


def should_sync_date(date_str: str, garmin_last_sync: str | None, force: bool = False) -> tuple[bool, str]:
    """Check if a date should be synced based on checkpoint comparison.

    Args:
        date_str: Date to check (YYYY-MM-DD)
        garmin_last_sync: The lastSyncTimestampGMT from Garmin API for this date
        force: Skip checkpoint check and sync anyway

    Returns:
        (should_sync, reason) tuple
    """
    if force:
        return True, "Force sync requested"

    # Load our checkpoint
    checkpoints = load_checkpoints()
    checkpoint = checkpoints.get(date_str)

    if checkpoint is None:
        # No checkpoint - first time syncing this date
        return True, "No checkpoint (first sync)"

    # For older dates without lastSyncTimestampGMT, we can't track changes
    # Just skip if we already have data
    if not garmin_last_sync:
        return False, "No lastSyncTimestampGMT (older data, already synced)"

    # Compare timestamps (for recent data that has timestamps)
    try:
        # Parse both timestamps
        checkpoint_dt = datetime.fromisoformat(checkpoint.replace('Z', '+00:00'))
        garmin_dt = datetime.fromisoformat(garmin_last_sync.replace('Z', '+00:00'))

        if garmin_dt > checkpoint_dt:
            return True, f"Data updated (was {checkpoint}, now {garmin_last_sync})"
        else:
            return False, f"Data unchanged (last sync {checkpoint})"
    except Exception as e:
        logger.warning(f"Failed to compare timestamps for {date_str}: {e}")
        return True, "Timestamp comparison failed, syncing to be safe"


def sync_day(target_date: date, conn: sqlite3.Connection, force: bool = False) -> dict[str, Any]:
    """Sync data for a specific day with checkpoint-based incremental sync.

    Stores the RAW JSON response from Garmin API to preserve ALL data fields.

    Args:
        target_date: Date to sync
        conn: Database connection
        force: Skip checkpoint check and sync anyway

    Returns:
        Dict with sync result
    """
    result = {
        "date": target_date.isoformat(),
        "success": False,
        "synced": False,
        "skipped": False,
        "skip_reason": None,
        "last_sync_gmt": None,
    }

    date_str = target_date.isoformat()
    client = get_garmin_client()

    if not client.ensure_authenticated():
        result["skip_reason"] = "Not authenticated"
        return result

    try:
        stats = client.client.get_stats(date_str)
        if not stats:
            result["skip_reason"] = "No stats from Garmin"
            return result

        last_sync_str = stats.get("lastSyncTimestampGMT")
        result["last_sync_gmt"] = last_sync_str

        # Check if we need to sync based on checkpoint
        should_sync, reason = should_sync_date(date_str, last_sync_str, force=force)
        if not should_sync:
            result["skipped"] = True
            result["skip_reason"] = reason
            logger.info(f"Skipping {date_str}: {reason}")
            return result

        logger.info(f"Syncing {date_str}: {reason}")

        # Store RAW JSON from Garmin API - this preserves ALL fields
        raw_json = json.dumps(stats, ensure_ascii=False, default=str)

        # Get heart rates
        rhr = 0
        try:
            heart_rates = client.client.get_heart_rates(date_str)
            if heart_rates:
                rhr = heart_rates.get("restingHeartRate", 0)
        except Exception:
            pass

        # Get stress
        stress_avg = stress_max = stress_min = 0
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

        # Get sleep data
        sleep_score = 0
        sleep_seconds = 0
        deep_sec = light_sec = rem_sec = awake_sec = 0
        spo2_avg = 0

        try:
            sleep = client.client.get_sleep_data(date_str)
            if sleep and "dailySleepDTO" in sleep:
                dto = sleep["dailySleepDTO"]
                if dto:
                    sleep_scores = dto.get("sleepScores", {})
                    overall = sleep_scores.get("overall", {})
                    sleep_score = int(overall.get("value", 0) or 0)
                    sleep_seconds = int(dto.get("sleepTimeSeconds", 0) or 0)
                    deep_sec = int(dto.get("deepSleepSeconds", 0) or 0)
                    light_sec = int(dto.get("lightSleepSeconds", 0) or 0)
                    rem_sec = int(dto.get("remSleepSeconds", 0) or 0)
                    awake_sec = int(dto.get("awakeSleepSeconds", 0) or 0)
                    spo2_avg = float(dto.get("averageSpO2Value", 0) or 0)
        except Exception:
            pass

        # Check if record exists
        existing = conn.execute(
            "SELECT id FROM health_daily WHERE date = ?", (date_str,)
        ).fetchone()

        if existing:
            row_id = existing[0]
        else:
            row_id = str(uuid.uuid4())

        conn.execute("""
            INSERT OR REPLACE INTO health_daily
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
            int(stress_avg), int(stress_max), int(stress_min),
            int(bb_high), int(bb_low), int(bb_current),
            sleep_score, sleep_seconds,
            deep_sec, light_sec, rem_sec, awake_sec,
            spo2_avg,
            int(stats.get("floorsClimbed", 0) or 0),
            int(stats.get("intensityMinutes", 0) or 0),
            raw_json,  # Store complete Garmin API response
        ))

        # Update checkpoint after successful sync
        update_checkpoint(date_str, last_sync_str)

        result["success"] = True
        result["synced"] = True
        logger.info(f"Synced {date_str} (device sync: {last_sync_str})")

    except Exception as e:
        result["skip_reason"] = f"Error: {e}"
        logger.error(f"Failed to sync {date_str}: {e}")

    return result


def sync_todays_data(lookback_days: int = SYNC_LOOKBACK_DAYS, force: bool = False) -> dict[str, Any]:
    """Incremental sync - only syncs days with updated data since last sync.

    Args:
        lookback_days: How many days back to check for updates (default 7)
        force: Skip checkpoint checks and sync all days anyway

    Returns:
        Dict with sync results
    """
    result = {
        "success": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "synced_days": [],
        "skipped_days": [],
        "activities_synced": 0,
        "training_synced": False,
        "errors": [],
    }

    try:
        client = get_garmin_client()
        if not client.ensure_authenticated():
            result["errors"].append("Not authenticated")
            return result

        conn = sqlite3.connect(str(Config().db_path))
        today = date.today()

        # Check if this is first sync (no checkpoints)
        checkpoints = load_checkpoints()
        is_first_sync = len(checkpoints) == 0

        if is_first_sync and not force:
            # First sync - get more historical data
            lookback_days = INITIAL_SYNC_DAYS
            logger.info(f"First sync detected - syncing last {lookback_days} days")

        # Check each day in the lookback window
        for day_offset in range(lookback_days):
            sync_date = today - timedelta(days=day_offset)
            day_result = sync_day(sync_date, conn, force=force)

            if day_result["synced"]:
                result["synced_days"].append(day_result)
                # Log progress every 50 days
                if len(result["synced_days"]) % 50 == 0:
                    logger.info(f"Progress: {len(result['synced_days'])} days synced so far...")
            elif day_result["skipped"]:
                result["skipped_days"].append(day_result)
            else:
                result["errors"].append(f"{day_result['date']}: {day_result.get('skip_reason')}")

        # Sync recent activities (last 7 days)
        try:
            week_ago = (today - timedelta(days=7)).isoformat()
            activities = client.client.get_activities(0, 100)

            synced = 0
            for act in activities:
                act_date = act.get("startTimeLocal", "")[:10]
                if act_date >= week_ago:
                    activity_type = act.get("activityType", {})
                    type_key = activity_type.get("typeKey", "") if isinstance(activity_type, dict) else ""
                    type_id = activity_type.get("typeId", 0) if isinstance(activity_type, dict) else 0

                    # Store RAW JSON from Garmin API - preserves ALL activity fields
                    act_raw_json = json.dumps(act, ensure_ascii=False, default=str)

                    garmin_id = str(act.get("activityId", ""))
                    existing = conn.execute(
                        "SELECT id FROM health_activities WHERE garmin_activity_id = ?",
                        (garmin_id,)
                    ).fetchone()

                    if existing:
                        row_id = existing[0]
                    else:
                        row_id = str(uuid.uuid4())

                    conn.execute("""
                        INSERT OR REPLACE INTO health_activities
                        (id, garmin_activity_id, activity_type, activity_type_id, name,
                         start_time, duration_seconds, duration_min,
                         distance_meters, distance_km,
                         avg_heart_rate, max_heart_rate, min_heart_rate, calories,
                         avg_speed_m_s, max_speed_m_s, avg_pace,
                         steps, avg_cadence, max_cadence,
                         avg_power, max_power,
                         elevation_gain_m, elevation_loss_m, min_elevation_m, max_elevation_m,
                         aerobic_effect, anaerobic_effect,
                         description, device_name, summary, created_at, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                    """, (
                        row_id, garmin_id, type_key, type_id,
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
                        "",
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
                        "",
                        act_raw_json,  # Store complete Garmin API response
                    ))
                    synced += 1

            result["activities_synced"] = synced
            logger.info(f"Synced {synced} recent activities")

        except Exception as e:
            result["errors"].append(f"Activities error: {e}")

        # Sync training metrics
        try:
            training = client.get_training_status()
            if training:
                vo2 = training.get("mostRecentVO2Max", {})
                if isinstance(vo2, dict) and "generic" in vo2:
                    vo2 = vo2["generic"]

                if vo2:
                    endurance = client.get_endurance_score()
                    endurance_score = endurance.get("enduranceScoreDTO", {}).get("overallScore", 0) if endurance else 0

                    hill = client.get_hill_score()
                    hill_data = hill.get("periodAvgScore", {}) if hill else {}
                    hill_score = list(hill_data.values())[0] if hill_data else 0

                    status = training.get("mostRecentTrainingStatus", {})
                    status_text = ""
                    if status:
                        training_status = status.get("latestTrainingStatusData", {})
                        if training_status:
                            device_data = list(training_status.values())[0] if training_status else {}
                            status_text = device_data.get("trainingStatusFeedbackPhrase", "")

                    today_str = today.isoformat()
                    existing = conn.execute(
                        "SELECT id FROM health_training_metrics WHERE date = ?", (today_str,)
                    ).fetchone()

                    if existing:
                        row_id = existing[0]
                    else:
                        row_id = str(uuid.uuid4())

                    # Store RAW JSON from Garmin API - preserves ALL training fields
                    training_raw_json = json.dumps({
                        "training": training,
                        "endurance": endurance,
                        "hill": hill,
                    }, ensure_ascii=False, default=str)

                    conn.execute("""
                        INSERT OR REPLACE INTO health_training_metrics
                        (id, date, vo2_max, vo2_max_precise, endurance_score, hill_score, training_status, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (row_id, today_str,
                          vo2.get("vo2MaxValue", 0),
                          vo2.get("vo2MaxPreciseValue", 0),
                          endurance_score, hill_score, status_text, training_raw_json))
                    result["training_synced"] = True
                    logger.info("Synced training metrics")

        except Exception as e:
            result["errors"].append(f"Training metrics error: {e}")

        conn.commit()
        conn.close()

        result["success"] = len(result["errors"]) == 0

    except Exception as e:
        result["errors"].append(f"Sync failed: {e}")
        logger.error(f"Garmin sync failed: {e}")

    return result


def run_daily_sync(lookback_days: int = SYNC_LOOKBACK_DAYS, force: bool = False):
    """Run the daily Garmin incremental sync.

    Args:
        lookback_days: How many days back to check for updates
        force: Skip checkpoint checks and sync all days anyway
    """
    logger.info(f"Starting incremental Garmin sync (lookback: {lookback_days} days)...")
    if force:
        logger.info("Force sync - skipping checkpoint checks")

    result = sync_todays_data(lookback_days=lookback_days, force=force)

    if result["success"]:
        synced = [d["date"] for d in result["synced_days"]]
        skipped = [f'{d["date"]}: {d["skip_reason"]}' for d in result["skipped_days"]]
        logger.info(f"Incremental sync complete:")
        logger.info(f"  Synced: {synced}")
        if skipped:
            logger.info(f"  Skipped (unchanged): {skipped}")
        logger.info(f"  Activities: {result['activities_synced']}, Training: {result['training_synced']}")
    else:
        logger.error(f"Sync had errors: {result['errors']}")

    return result


def run_full_initial_sync():
    """Run a full initial sync of all historical data.

    Creates a backup before starting the sync.
    """
    from .backup_service import create_backup

    logger.info(f"Starting full initial sync ({INITIAL_SYNC_DAYS} days)...")

    # Create backup before full sync
    backup_path = create_backup("before_full_garmin_sync")
    logger.info(f"Backup created: {backup_path.name}")

    result = sync_todays_data(lookback_days=INITIAL_SYNC_DAYS, force=True)
    return result


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Sync Garmin health data with incremental checkpoint tracking")
    parser.add_argument("--force", action="store_true",
                       help="Force sync all days (ignore checkpoints)")
    parser.add_argument("--days", type=int, default=SYNC_LOOKBACK_DAYS,
                       help=f"Lookback days (default: {SYNC_LOOKBACK_DAYS})")
    parser.add_argument("--full", action="store_true",
                       help=f"Run full initial sync ({INITIAL_SYNC_DAYS} days)")
    parser.add_argument("--backup", action="store_true",
                       help="Create a backup and exit")
    parser.add_argument("--list-backups", action="store_true",
                       help="List all available backups")
    args = parser.parse_args()

    if args.list_backups:
        from .backup_service import list_backups
        backups = list_backups()
        print("\n" + "="*60)
        print("AVAILABLE BACKUPS")
        print("="*60)
        for b in backups:
            print(f"{b['name']} - {b['created']} - {b['size_mb']:.1f} MB")
        print("="*60)
    elif args.backup:
        from .backup_service import create_backup
        backup = create_backup("manual")
        print(f"Backup created: {backup}")
    elif args.full:
        result = run_full_initial_sync()
    else:
        result = run_daily_sync(lookback_days=args.days, force=args.force)

        # Print summary
        print("\n" + "="*60)
        print("GARMIN SYNC SUMMARY")
        print("="*60)
        print(f"Timestamp: {result['timestamp']}")
        print(f"Success: {result['success']}")
        print(f"\nSynced: {[d['date'] for d in result['synced_days']]}")
        skipped_str = [f'{d["date"]}: {d["skip_reason"]}' for d in result["skipped_days"]]
        print(f"Skipped (unchanged): {skipped_str if skipped_str else 'None'}")
        print(f"Activities synced: {result['activities_synced']}")
        print(f"Training synced: {result['training_synced']}")
        if result['errors']:
            print(f"Errors: {result['errors']}")
        print("="*60)
