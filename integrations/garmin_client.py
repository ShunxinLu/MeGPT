"""
Garmin Connect Client - Fetches ALL health data from Garmin Connect.

Uses the garminconnect library which provides comprehensive access to:
- Daily health metrics (steps, HR, sleep, stress, Body Battery, SpO2, respiration)
- Activities/workouts with GPS, HR, pace, power, splits data
- Sleep analysis with stages
- Body composition (weight, body fat)
- Training status, readiness, endurance score, hill score
- Heart rate variability (HRV)
- Hydration data
- Menstrual health data
- And much more...

Credentials stored securely in VaultManager.
Session tokens persisted at ~/.garth for ~1 year.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Try importing garminconnect first
try:
    import garminconnect
    GARMINCONNECT_AVAILABLE = True
except ImportError:
    GARMINCONNECT_AVAILABLE = False
    garminconnect = None
    logging.warning("garminconnect not installed. Run: pip install garminconnect")

# Fallback to garth for direct session access
try:
    import garth
    GARTH_AVAILABLE = True
except ImportError:
    GARTH_AVAILABLE = False
    garth = None
    logging.warning("garth not installed.")

from integrations.vault_manager import VaultManager

logger = logging.getLogger(__name__)

# Vault keys for Garmin credentials
KEY_GARMIN_USERNAME = "garmin_username"
KEY_GARMIN_PASSWORD = "garmin_password"

# Session directory (same as garth)
SESSION_DIR = Path("~/.garth").expanduser()

# In-memory store for pending MFA sessions
_pending_mfa_sessions: dict[str, dict[str, Any]] = {}


class GarminClient:
    """Client for Garmin Connect comprehensive health data."""

    def __init__(self, vault: VaultManager | None = None):
        """Initialize Garmin client.

        Args:
            vault: VaultManager instance for credential storage
        """
        if not GARMINCONNECT_AVAILABLE:
            raise RuntimeError("garminconnect library not installed. Run: pip install garminconnect")

        self.vault = vault or VaultManager()
        self.client: garminconnect.Garmin | None = None
        self.is_authenticated = False

    def _get_session_dir(self) -> Path:
        """Get the path to the garth session directory."""
        return SESSION_DIR

    def _init_garminconnect_client(self) -> garminconnect.Garmin:
        """Initialize Garmin client with existing session if available."""
        # Try to use existing garth session
        client = garminconnect.Garmin()

        # If session directory exists, try to load from it
        session_dir = self._get_session_dir()
        if session_dir.exists():
            try:
                # garminconnect can use the existing garth session
                client.login(tokenstore=str(session_dir))
                logger.info("Loaded existing session from garth tokenstore")
                return client
            except Exception as e:
                logger.info(f"Could not load existing session: {e}")

        return client

    def ensure_authenticated(self) -> bool:
        """Ensure client is authenticated, re-authenticating if needed."""
        if self.is_authenticated and self.client is not None:
            return True

        # Try to resume from existing session
        session_dir = self._get_session_dir()
        if session_dir.exists():
            try:
                self.client = self._init_garminconnect_client()
                # Verify by getting user profile
                self.client.get_user_profile()
                self.is_authenticated = True
                logger.info("Resumed existing Garmin session")
                return True
            except Exception as e:
                logger.info(f"Could not resume session: {e}")

        return False

    def authenticate(self, username: str | None = None, password: str | None = None,
                    otp: str | None = None) -> tuple[bool, str | None]:
        """Authenticate with Garmin Connect using saved session or credentials.

        Note: For interactive MFA support, use start_login() + submit_mfa_code() instead.

        Args:
            username: Garmin username (optional if stored)
            password: Garmin password (optional if stored)
            otp: Not used, kept for compatibility

        Returns:
            Tuple of (success, error_message)
        """
        # First try to resume from existing session
        if self.ensure_authenticated():
            return True, None

        try:
            # Get credentials from vault if not provided
            if not username:
                username = self.vault.retrieve_token(KEY_GARMIN_USERNAME)
            if not password:
                password = self.vault.retrieve_token(KEY_GARMIN_PASSWORD)

            if not username or not password:
                return False, "No credentials found. Please authenticate via web UI or CLI."

            # Create new client and login
            self.client = garminconnect.Garmin()
            self.client.login(username, password)

            # Save credentials
            self.vault.store_token(KEY_GARMIN_USERNAME, username)
            self.vault.store_token(KEY_GARMIN_PASSWORD, password)

            # Session is automatically saved by garminconnect to tokenstore
            self.is_authenticated = True
            logger.info("Garmin authentication successful")
            return True, None

        except Exception as e:
            logger.error(f"Garmin authentication failed: {e}")
            error_str = str(e)
            if "mfa" in error_str.lower():
                return False, "2FA required. Please use web UI or CLI for initial authentication."
            return False, error_str

    def start_login(self, username: str, password: str) -> dict[str, Any]:
        """Start Garmin login process (step 1 of 2FA flow)."""
        try:
            # First check if we already have a valid session
            if self.ensure_authenticated():
                return {"success": True, "needs_mfa": False}

            import garth
            result = garth.login(username, password, return_on_mfa=True)

            if isinstance(result, tuple) and result[0] == "needs_mfa":
                import uuid
                session_id = str(uuid.uuid4())
                mfa_data = result[1]

                _pending_mfa_sessions[session_id] = {
                    "client": mfa_data["client"],
                    "signin_params": mfa_data["signin_params"],
                    "username": username,
                    "password": password,
                }

                logger.info(f"MFA required. Session ID: {session_id}")
                return {
                    "success": False,
                    "needs_mfa": True,
                    "session_id": session_id,
                    "error": None,
                }

            # Login completed without MFA
            logger.info("Login completed without MFA")
            return {"success": True, "needs_mfa": False}

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return {"success": False, "needs_mfa": False, "error": str(e)}

    def submit_mfa_code(self, session_id: str, mfa_code: str) -> dict[str, Any]:
        """Submit MFA code to complete login (step 2 of 2FA flow)."""
        if session_id not in _pending_mfa_sessions:
            return {"success": False, "error": "Invalid or expired session"}

        auth_state = _pending_mfa_sessions[session_id]

        try:
            import garth
            import re

            client = auth_state["client"]
            signin_params = auth_state["signin_params"]

            # Extract CSRF token
            match = re.search(r'name="_csrf"\s+value="([^"]+)"', client.last_resp.text)
            if not match:
                match = re.search(r'"_csrf":"([^"]+)"', client.last_resp.text)
            csrf_token = match.group(1) if match else ""

            # Submit MFA code
            client.post(
                "sso",
                "/sso/verifyMFA/loginEnterMfaCode",
                params=signin_params,
                referrer=True,
                data={
                    "mfa-code": mfa_code,
                    "embed": "true",
                    "_csrf": csrf_token,
                    "fromPage": "setupEnterMfaCode",
                },
            )

            # Complete login
            from garth.sso import _complete_login
            _complete_login(client)

            # Save credentials
            self.vault.store_token(KEY_GARMIN_USERNAME, auth_state["username"])
            self.vault.store_token(KEY_GARMIN_PASSWORD, auth_state["password"])

            # Save session
            session_dir = self._get_session_dir()
            session_dir.mkdir(parents=True, exist_ok=True)
            garth.client = client
            garth.resume(session_dir)

            # Initialize garminconnect client
            self.client = garminconnect.Garmin()
            self.is_authenticated = True

            del _pending_mfa_sessions[session_id]

            logger.info("MFA verification successful")
            return {"success": True, "error": None}

        except Exception as e:
            logger.error(f"MFA verification failed: {e}")
            return {"success": False, "error": str(e)}

    # ========== COMPREHENSIVE DATA FETCHING METHODS ==========

    def get_todays_stats(self) -> dict[str, Any] | None:
        """Get comprehensive today's health summary."""
        if not self.ensure_authenticated():
            return None

        try:
            today = date.today().isoformat()
            logger.info(f"Fetching comprehensive stats for {today}")

            # Get user stats (steps, calories, distance, floors)
            stats = self.client.get_stats(today)

            # Get heart rates (resting, avg)
            heart_rates = self.client.get_heart_rates(today)

            # Get stress data
            stress = self.client.get_stress_data(today)

            # Get Body Battery
            body_battery = self.client.get_body_battery(today)

            # Get sleep data (last night)
            sleep_data = self.client.get_sleep_data(today)

            # Get SpO2
            try:
                spo2 = self.client.get_spo2_data(today)
            except Exception:
                spo2 = []

            # Get respiration
            try:
                respiration = self.client.get_respiration_data(today)
            except Exception:
                respiration = []

            # Get intensity minutes
            try:
                intensity = self.client.get_intensity_minutes_data(today)
            except Exception:
                intensity = []

            # Safe int conversion helper
            def safe_int(val, default=0):
                if val is None:
                    return default
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return default

            def safe_float(val, default=0.0):
                if val is None:
                    return default
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default

            return {
                "date": today,
                # Steps
                "steps": safe_int(stats.get("totalSteps")),
                "steps_goal": safe_int(stats.get("dailyStepGoal"), 10000),
                # Distance
                "distance_meters": safe_float(stats.get("totalDistanceMeters")),
                "distance_km": safe_float(stats.get("totalDistanceMeters")) / 1000,
                # Calories
                "calories_total": safe_int(stats.get("totalKilocalories")),
                "calories_active": safe_int(stats.get("activeKilocalories")),
                "calories_bmr": safe_int(stats.get("burnedKilocalories")),
                "calories_goal": safe_int(stats.get("dailyKilocalorieGoal"), 2000),
                # Floors
                "floors_climbed": safe_int(stats.get("floorsClimbed")),
                "floors_goal": safe_int(stats.get("dailyFloorGoal"), 10),
                # Heart rate
                "resting_heart_rate": safe_int(heart_rates.get("restingHeartRate")) if heart_rates else 0,
                "avg_heart_rate": safe_int(stats.get("averageHeartRate")),
                "max_heart_rate": safe_int(stats.get("maxHeartRate")),
                "min_heart_rate": safe_int(stats.get("minHeartRate")),
                # Stress
                "stress_avg": safe_int(stress.get("overallStressLevel")) if stress else 0,
                "stress_max": safe_int(stress.get("maxStressLevel")) if stress else 0,
                "stress_min": safe_int(stress.get("minStressLevel")) if stress else 0,
                # Body Battery
                "body_battery_high": safe_int(body_battery[0].get("highest")) if body_battery else 0,
                "body_battery_low": safe_int(body_battery[0].get("lowest")) if body_battery else 0,
                "body_battery_current": safe_int(body_battery[0].get("value")) if body_battery else 0,
                # Sleep
                "sleep_score": safe_int(sleep_data.get("sleepScore")) if sleep_data else 0,
                "sleep_seconds": safe_int(sleep_data.get("sleepTimeSeconds")) if sleep_data else 0,
                "deep_sleep_seconds": safe_int(sleep_data.get("deepSleepSeconds")) if sleep_data else 0,
                "light_sleep_seconds": safe_int(sleep_data.get("lightSleepSeconds")) if sleep_data else 0,
                "rem_sleep_seconds": safe_int(sleep_data.get("remSleepSeconds")) if sleep_data else 0,
                "awake_seconds": safe_int(sleep_data.get("awakeSeconds")) if sleep_data else 0,
                # SpO2
                "spo2_avg": safe_float(spo2[0].get("averageSpO2")) if spo2 else 0,
                "spo2_max": safe_float(spo2[0].get("maxSpO2")) if spo2 else 0,
                "spo2_min": safe_float(spo2[0].get("minSpO2")) if spo2 else 0,
                # Respiration
                "respiration_avg": safe_float(respiration[0].get("avgRespirationValue")) if respiration else 0,
                "respiration_max": safe_float(respiration[0].get("maxRespirationValue")) if respiration else 0,
                "respiration_min": safe_float(respiration[0].get("minRespirationValue")) if respiration else 0,
                # Intensity minutes
                "intensity_minutes_moderate": safe_int(intensity[0].get("moderateMinutes")) if intensity else 0,
                "intensity_minutes_vigorous": safe_int(intensity[0].get("vigorousMinutes")) if intensity else 0,
                "intensity_minutes_total": safe_int(intensity[0].get("intensityMinutesGoal")) if intensity else 0,
            }

        except Exception as e:
            logger.error(f"Failed to get comprehensive stats: {e}")
            return None

    def get_activities(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent workout activities with full details.

        Args:
            limit: Maximum number of activities (default 100)

        Returns:
            List of activity dicts with comprehensive data
        """
        if not self.ensure_authenticated():
            return []

        try:
            # Get activity list
            activities = self.client.get_activities(0, limit)  # start, limit

            result = []
            for activity in activities:
                # Extract activity type info
                activity_type = activity.get("activityType", {})
                type_key = activity_type.get("typeKey", "unknown") if isinstance(activity_type, dict) else "unknown"
                type_id = activity_type.get("typeId", 0) if isinstance(activity_type, dict) else 0

                result.append({
                    "garmin_activity_id": str(activity.get("activityId", "")),
                    "activity_type": type_key,
                    "activity_type_id": type_id,
                    "name": activity.get("activityName", ""),
                    "description": activity.get("description", ""),
                    "start_time": activity.get("startTimeLocal", ""),
                    "start_time_gmt": activity.get("startTimeGMT", ""),
                    "duration_seconds": float(activity.get("duration", 0)),
                    "duration_min": float(activity.get("duration", 0)) / 60,
                    "distance_meters": float(activity.get("distance", 0)),
                    "distance_km": float(activity.get("distance", 0)) / 1000,
                    "avg_heart_rate": int(activity.get("averageHR", 0)),
                    "max_heart_rate": int(activity.get("maxHR", 0)),
                    "calories": int(activity.get("calories", 0)),
                    "avg_speed_m_s": float(activity.get("averageSpeed", 0)),
                    "max_speed_m_s": float(activity.get("maxSpeed", 0)),
                    "avg_pace_min_km": (1 / float(activity.get("averageSpeed", 0))) / 60 if activity.get("averageSpeed") else 0,
                    "steps": int(activity.get("steps", 0)),
                    "avg_cadence": int(activity.get("averageRunningCadence", 0)),
                    "max_cadence": int(activity.get("maxRunningCadence", 0)),
                    "avg_power": float(activity.get("averageBikePower", 0)),
                    "max_power": float(activity.get("maxBikePower", 0)),
                    "elevation_gain_m": float(activity.get("elevationGain", 0)),
                    "elevation_loss_m": float(activity.get("elevationLoss", 0)),
                    "min_elevation_m": float(activity.get("minElevation", 0)),
                    "max_elevation_m": float(activity.get("maxElevation", 0)),
                    "aerobic_effect": float(activity.get("aerobicTrainingEffect", 0)),
                    "anaerobic_effect": float(activity.get("anaerobicTrainingEffect", 0)),
                    "training_effect_label": activity.get("trainingEffectLabel", ""),
                    "activity_id": str(activity.get("activityId", "")),
                    "parent_activity_id": str(activity.get("parentActivityId", "")),
                    "device_name": activity.get("deviceName", ""),
                })

            logger.info(f"Fetched {len(result)} activities")
            return result

        except Exception as e:
            logger.error(f"Failed to get activities: {e}")
            return []

    def get_activity_details(self, activity_id: str) -> dict[str, Any] | None:
        """Get full details for a specific activity including splits, HR zones, etc."""
        if not self.ensure_authenticated():
            return None

        try:
            # Get activity details
            details = self.client.get_activity_details(activity_id)

            # Get splits
            splits = self.client.get_activity_splits(activity_id)

            # Get heart rate zones
            try:
                hr_zones = self.client.get_activity_hr_in_timezones(activity_id)
            except Exception:
                hr_zones = None

            # Get power zones (if applicable)
            try:
                power_zones = self.client.get_activity_power_in_timezones(activity_id)
            except Exception:
                power_zones = None

            return {
                "details": details,
                "splits": splits,
                "hr_zones": hr_zones,
                "power_zones": power_zones,
            }

        except Exception as e:
            logger.error(f"Failed to get activity details: {e}")
            return None

    def get_sleep_data(self, sleep_date: date | None = None) -> dict[str, Any] | None:
        """Get detailed sleep data for a specific date."""
        if not self.ensure_authenticated():
            return None

        try:
            if sleep_date is None:
                now = datetime.now()
                if now.hour < 12:
                    sleep_date = (now - timedelta(days=1)).date()
                else:
                    sleep_date = now.date()

            date_str = sleep_date.isoformat()
            sleep_data = self.client.get_sleep_data(date_str)

            if not sleep_data:
                return None

            return {
                "date": date_str,
                "sleep_score": int(sleep_data.get("sleepScore", 0)),
                "sleep_seconds": int(sleep_data.get("sleepTimeSeconds", 0)),
                "deep_sleep_seconds": int(sleep_data.get("deepSleepSeconds", 0)),
                "light_sleep_seconds": int(sleep_data.get("lightSleepSeconds", 0)),
                "rem_sleep_seconds": int(sleep_data.get("remSleepSeconds", 0)),
                "awake_seconds": int(sleep_data.get("awakeSeconds", 0)),
                "deep_sleep_percentage": float(sleep_data.get("deepSleepPercentage", 0)),
                "light_sleep_percentage": float(sleep_data.get("lightSleepPercentage", 0)),
                "rem_sleep_percentage": float(sleep_data.get("remSleepPercentage", 0)),
                "awake_percentage": float(sleep_data.get("awakePercentage", 0)),
                "overall_awake_count": int(sleep_data.get("overallAwakeCount", 0)),
                "restless_seconds": int(sleep_data.get("restlessMomentsCount", 0)),
                "avg_sleep_stress": float(sleep_data.get("avgSleepStress", 0)),
                "bed_time_seconds": int(sleep_data.get("bedTimeSeconds", 0)),
                "sleep_goal_seconds": int(sleep_data.get("sleepGoalSeconds", 0)),
            }

        except Exception as e:
            logger.error(f"Failed to get sleep data: {e}")
            return None

    def get_hrv_data(self, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
        """Get heart rate variability data."""
        if not self.ensure_authenticated():
            return []

        try:
            if start_date is None:
                start_date = date.today() - timedelta(days=7)
            if end_date is None:
                end_date = date.today()

            # HRV data uses a single date array format
            hrv_data = self.client.get_hrv_data(start_date.isoformat())
            return hrv_data if hrv_data else []

        except Exception as e:
            logger.error(f"Failed to get HRV data: {e}")
            return []

    def get_body_composition(self, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
        """Get body composition data (weight, body fat, etc.)."""
        if not self.ensure_authenticated():
            return []

        try:
            if start_date is None:
                start_date = date.today() - timedelta(days=30)
            if end_date is None:
                end_date = date.today()

            data = self.client.get_body_composition(start_date.isoformat(), end_date.isoformat())
            return data if data else []

        except Exception as e:
            logger.error(f"Failed to get body composition: {e}")
            return []

    def get_training_status(self, cdate: date | None = None) -> dict[str, Any] | None:
        """Get current training status."""
        if not self.ensure_authenticated():
            return None

        try:
            if cdate is None:
                cdate = date.today()
            return self.client.get_training_status(cdate.isoformat())
        except Exception as e:
            logger.error(f"Failed to get training status: {e}")
            return None

    def get_training_readiness(self) -> dict[str, Any] | None:
        """Get morning training readiness."""
        if not self.ensure_authenticated():
            return None

        try:
            return self.client.get_morning_training_readiness()
        except Exception as e:
            logger.error(f"Failed to get training readiness: {e}")
            return None

    def get_endurance_score(self, startdate: date | None = None, enddate: date | None = None) -> dict[str, Any] | None:
        """Get endurance score."""
        if not self.ensure_authenticated():
            return None

        try:
            if startdate is None:
                startdate = date.today()
            if enddate is None:
                enddate = date.today()
            return self.client.get_endurance_score(startdate.isoformat(), enddate.isoformat())
        except Exception as e:
            logger.error(f"Failed to get endurance score: {e}")
            return None

    def get_hill_score(self, startdate: date | None = None, enddate: date | None = None) -> dict[str, Any] | None:
        """Get hill score."""
        if not self.ensure_authenticated():
            return None

        try:
            if startdate is None:
                startdate = date.today()
            if enddate is None:
                enddate = date.today()
            return self.client.get_hill_score(startdate.isoformat(), enddate.isoformat())
        except Exception as e:
            logger.error(f"Failed to get hill score: {e}")
            return None

    def sync_historical(self, days: int = 30) -> dict[str, int]:
        """Sync ALL historical health data for the specified number of days.

        Args:
            days: Number of days to sync (default 30)

        Returns:
            Dict with counts of synced items
        """
        if not self.ensure_authenticated():
            return {"error": "Not authenticated"}

        results = {
            "daily_stats": 0,
            "sleep": 0,
            "activities": 0,
            "hrv": 0,
            "body_composition": 0,
            "errors": 0,
        }

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        logger.info(f"Starting full sync from {start_date} to {end_date}")

        # Sync daily stats for each day
        for day_offset in range(days):
            sync_date = end_date - timedelta(days=day_offset)
            date_str = sync_date.isoformat()

            try:
                # Daily stats
                stats = self.client.get_stats(date_str)
                if stats:
                    from database import store_health_daily
                    store_health_daily({
                        "date": date_str,
                        "steps": int(stats.get("totalSteps", 0)),
                        "distance_meters": float(stats.get("totalDistanceMeters", 0)),
                        "calories_total": int(stats.get("totalKilocalories", 0)),
                        "calories_active": int(stats.get("activeKilocalories", 0)),
                        "resting_heart_rate": int(stats.get("restingHeartRate", 0)),
                        "avg_heart_rate": int(stats.get("averageHeartRate", 0)),
                        "max_heart_rate": int(stats.get("maxHeartRate", 0)),
                        "stress_avg": int(stats.get("avgStress", 0)),
                        "body_battery_high": 0,
                        "body_battery_low": 0,
                        "floors_climbed": int(stats.get("floorsClimbed", 0)),
                        "intensity_minutes": int(stats.get("intensityMinutes", 0)),
                    })
                    results["daily_stats"] += 1

                # Sleep data
                sleep = self.client.get_sleep_data(date_str)
                if sleep:
                    from database import store_health_sleep
                    store_health_sleep({
                        "date": date_str,
                        "sleep_score": int(sleep.get("sleepScore", 0)),
                        "sleep_seconds": int(sleep.get("sleepTimeSeconds", 0)),
                        "deep_sleep_seconds": int(sleep.get("deepSleepSeconds", 0)),
                        "light_sleep_seconds": int(sleep.get("lightSleepSeconds", 0)),
                        "rem_sleep_seconds": int(sleep.get("remSleepSeconds", 0)),
                    })
                    results["sleep"] += 1

            except Exception as e:
                logger.warning(f"Failed to sync {date_str}: {e}")
                results["errors"] += 1

        # Sync all activities
        try:
            activities = self.get_activities(limit=1000)
            from database import store_health_activity

            for activity in activities:
                try:
                    store_health_activity(activity)
                    results["activities"] += 1
                except Exception as e:
                    logger.warning(f"Failed to store activity {activity.get('garmin_activity_id')}: {e}")
                    results["errors"] += 1

        except Exception as e:
            logger.error(f"Failed to sync activities: {e}")
            results["errors"] += 1

        # Sync HRV data
        try:
            hrv_data = self.get_hrv_data(start_date, end_date)
            results["hrv"] = len(hrv_data)
        except Exception as e:
            logger.error(f"Failed to sync HRV: {e}")
            results["errors"] += 1

        # Sync body composition
        try:
            body_comp = self.get_body_composition(start_date, end_date)
            results["body_composition"] = len(body_comp)
        except Exception as e:
            logger.error(f"Failed to sync body composition: {e}")
            results["errors"] += 1

        logger.info(f"Sync complete: {results}")
        return results

    def disconnect(self) -> None:
        """Disconnect and clear credentials."""
        self.client = None
        self.is_authenticated = False

        # Clear vault credentials
        self.vault.delete_token(KEY_GARMIN_USERNAME)
        self.vault.delete_token(KEY_GARMIN_PASSWORD)

        # Remove session directory
        try:
            session_dir = self._get_session_dir()
            if session_dir.exists():
                import shutil
                shutil.rmtree(session_dir)
                logger.info(f"Removed session directory {session_dir}")
        except Exception as e:
            logger.warning(f"Could not remove session file: {e}")

        logger.info("Garmin disconnected and credentials cleared")


# Singleton instance for reuse
_garmin_client: GarminClient | None = None


def get_garmin_client() -> GarminClient:
    """Get or create singleton Garmin client instance."""
    global _garmin_client
    if _garmin_client is None:
        _garmin_client = GarminClient()
    return _garmin_client
