"use client";

import { useState, useEffect } from "react";
import {
  Heart,
  Activity,
  Moon,
  Zap,
  TrendingUp,
  Footprints,
  Flame,
  RefreshCw,
  Calendar,
  Settings,
} from "lucide-react";

type HealthDaily = {
  id: string;
  date: string;
  steps: number;
  distance_meters: number;
  calories_total: number;
  calories_active: number;
  resting_heart_rate: number;
  avg_heart_rate: number;
  max_heart_rate: number;
  stress_avg: number;
  body_battery_high: number;
  body_battery_low: number;
  floors_climbed: number;
  intensity_minutes: number;
};

type HealthSleep = {
  id: string;
  date: string;
  sleep_start: string;
  sleep_end: string;
  duration_seconds: number;
  deep_sleep_seconds: number;
  light_sleep_seconds: number;
  rem_sleep_seconds: number;
  awake_seconds: number;
  sleep_score: number;
};

type HealthActivity = {
  id: string;
  activity_type: string;
  name: string;
  start_time: string;
  duration_seconds: number;
  distance_meters: number;
  avg_heart_rate: number;
  max_heart_rate: number;
  calories: number;
  avg_pace: string;
};

// Fetch health data from API
async function fetchHealthDaily(date: string): Promise<HealthDaily | null> {
  try {
    const response = await fetch(`/api/garmin/health/daily?date=${date}`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchHealthSleep(date: string): Promise<HealthSleep | null> {
  try {
    const response = await fetch(`/api/garmin/health/sleep?date=${date}`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchActivities(limit: number = 5): Promise<HealthActivity[]> {
  try {
    const response = await fetch(`/api/garmin/activities?limit=${limit}`);
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

async function triggerSync(): Promise<boolean> {
  try {
    const response = await fetch("/api/garmin/sync", { method: "POST" });
    return response.ok;
  } catch {
    return false;
  }
}

async function checkGarminStatus(): Promise<{ connected: boolean }> {
  try {
    const response = await fetch("/api/garmin/status");
    if (!response.ok) return { connected: false };
    return await response.json();
  } catch {
    return { connected: false };
  }
}

export default function HealthPage() {
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [dailyData, setDailyData] = useState<HealthDaily | null>(null);
  const [sleepData, setSleepData] = useState<HealthSleep | null>(null);
  const [activities, setActivities] = useState<HealthActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [garminConnected, setGarminConnected] = useState(false);

  const formatDate = (date: Date) => {
    return date.toISOString().split("T")[0];
  };

  const formatTime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  };

  const formatDistance = (meters: number) => {
    if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
    return `${meters} m`;
  };

  const loadHealthData = async () => {
    setLoading(true);
    const dateStr = formatDate(selectedDate);

    const [daily, sleep, acts, status] = await Promise.all([
      fetchHealthDaily(dateStr),
      fetchHealthSleep(dateStr),
      fetchActivities(5),
      checkGarminStatus(),
    ]);

    setDailyData(daily);
    setSleepData(sleep);
    setActivities(acts);
    setGarminConnected(status.connected);
    setLoading(false);
  };

  const handleSync = async () => {
    setSyncing(true);
    const success = await triggerSync();
    if (success) {
      await loadHealthData();
    }
    setSyncing(false);
  };

  const handleDateChange = (days: number) => {
    const newDate = new Date(selectedDate);
    newDate.setDate(newDate.getDate() + days);
    setSelectedDate(newDate);
  };

  useEffect(() => {
    loadHealthData();
  }, [selectedDate]);

  const formatDateString = (date: Date) => {
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  };

  const getBodyBatteryColor = (high: number, low: number) => {
    const avg = (high + low) / 2;
    if (avg >= 80) return "text-green-500";
    if (avg >= 50) return "text-yellow-500";
    return "text-red-500";
  };

  const getStressColor = (stress: number) => {
    if (stress <= 25) return "text-green-500";
    if (stress <= 50) return "text-yellow-500";
    if (stress <= 75) return "text-orange-500";
    return "text-red-500";
  };

  // Empty state
  if (!loading && !dailyData && !garminConnected) {
    return (
      <div className="flex flex-col h-screen pt-20 bg-void">
        <div className="bg-white/95 backdrop-blur-md border-b border-gray-200 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div>
              <h1 className="font-semibold text-primary text-xl">Health</h1>
              <p className="text-sm text-tertiary">Connect your Garmin device to see your health data</p>
            </div>
          </div>
        </div>

        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <Heart className="w-24 h-24 text-tertiary mx-auto mb-6" />
            <h2 className="text-2xl font-semibold text-primary mb-3">Connect Garmin</h2>
            <p className="text-secondary mb-6">
              Link your Garmin Connect account to view your health metrics, sleep data, and activities.
            </p>
            <a
              href="/settings/providers"
              className="inline-flex items-center space-x-2 px-6 py-3 rounded-lg bg-primary hover:bg-primary/90 text-white font-medium"
            >
              <Settings className="w-5 h-5" />
              <span>Connect Garmin</span>
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen pt-20 bg-void">
      {/* Header */}
      <div className="bg-white/95 backdrop-blur-md border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="font-semibold text-primary text-xl">Health</h1>
            <p className="text-sm text-tertiary">Your daily health metrics and activities</p>
          </div>

          <div className="flex items-center space-x-3">
            {/* Date Selector */}
            <div className="flex items-center space-x-2 bg-gray-100 rounded-lg p-1">
              <button
                onClick={() => handleDateChange(-1)}
                className="p-2 rounded-md hover:bg-white transition-colors"
              >
                <Calendar className="w-4 h-4 text-tertiary" />
              </button>
              <span className="text-sm font-medium text-primary px-2">
                {formatDateString(selectedDate)}
              </span>
              <button
                onClick={() => handleDateChange(1)}
                disabled={selectedDate >= new Date()}
                className="p-2 rounded-md hover:bg-white transition-colors disabled:opacity-50"
              >
                <Calendar className="w-4 h-4 text-tertiary" />
              </button>
            </div>

            {/* Sync Button */}
            <button
              onClick={handleSync}
              disabled={syncing || loading}
              className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-white font-medium disabled:opacity-50 transition-all"
            >
              <RefreshCw className={`w-5 h-5 ${syncing ? "animate-spin" : ""}`} />
              <span>{syncing ? "Syncing..." : "Sync"}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <RefreshCw className="w-8 h-8 text-primary animate-spin" />
            </div>
          ) : dailyData ? (
            <>
              {/* Main Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                {/* Steps */}
                <div className="glass-card rounded-2xl p-6 border-l-4 border-blue-500">
                  <div className="flex items-center justify-between mb-4">
                    <Footprints className="w-8 h-8 text-blue-500" />
                    <span className="text-xs font-medium px-2 py-1 rounded-full bg-blue-500/10 text-blue-500">
                      Daily Goal
                    </span>
                  </div>
                  <p className="text-3xl font-bold text-primary">
                    {dailyData.steps.toLocaleString()}
                  </p>
                  <p className="text-sm text-tertiary">steps</p>
                  {dailyData.distance_meters > 0 && (
                    <p className="text-xs text-secondary mt-1">
                      {formatDistance(dailyData.distance_meters)}
                    </p>
                  )}
                </div>

                {/* Calories */}
                <div className="glass-card rounded-2xl p-6 border-l-4 border-orange-500">
                  <div className="flex items-center justify-between mb-4">
                    <Flame className="w-8 h-8 text-orange-500" />
                    <span className="text-xs font-medium px-2 py-1 rounded-full bg-orange-500/10 text-orange-500">
                      Active
                    </span>
                  </div>
                  <p className="text-3xl font-bold text-primary">
                    {dailyData.calories_active.toLocaleString()}
                  </p>
                  <p className="text-sm text-tertiary">active calories</p>
                  <p className="text-xs text-secondary mt-1">
                    {dailyData.calories_total.toLocaleString()} total
                  </p>
                </div>

                {/* Intensity Minutes */}
                <div className="glass-card rounded-2xl p-6 border-l-4 border-green-500">
                  <div className="flex items-center justify-between mb-4">
                    <Activity className="w-8 h-8 text-green-500" />
                    <span className="text-xs font-medium px-2 py-1 rounded-full bg-green-500/10 text-green-500">
                      Intensity
                    </span>
                  </div>
                  <p className="text-3xl font-bold text-primary">
                    {dailyData.intensity_minutes}
                  </p>
                  <p className="text-sm text-tertiary">intensity minutes</p>
                </div>

                {/* Floors */}
                <div className="glass-card rounded-2xl p-6 border-l-4 border-purple-500">
                  <div className="flex items-center justify-between mb-4">
                    <TrendingUp className="w-8 h-8 text-purple-500" />
                    <span className="text-xs font-medium px-2 py-1 rounded-full bg-purple-500/10 text-purple-500">
                      Elevation
                    </span>
                  </div>
                  <p className="text-3xl font-bold text-primary">
                    {dailyData.floors_climbed}
                  </p>
                  <p className="text-sm text-tertiary">floors climbed</p>
                </div>
              </div>

              {/* Heart Rate and Stress Row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                {/* Heart Rate */}
                <div className="glass-card rounded-2xl p-6">
                  <div className="flex items-center space-x-3 mb-4">
                    <Heart className="w-6 h-6 text-red-500" />
                    <h3 className="font-semibold text-primary">Heart Rate</h3>
                  </div>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-xs text-tertiary">Resting</p>
                      <p className="text-xl font-bold text-primary">
                        {dailyData.resting_heart_rate}
                      </p>
                      <p className="text-xs text-secondary">bpm</p>
                    </div>
                    <div>
                      <p className="text-xs text-tertiary">Average</p>
                      <p className="text-xl font-bold text-primary">
                        {dailyData.avg_heart_rate}
                      </p>
                      <p className="text-xs text-secondary">bpm</p>
                    </div>
                    <div>
                      <p className="text-xs text-tertiary">Max</p>
                      <p className="text-xl font-bold text-primary">
                        {dailyData.max_heart_rate}
                      </p>
                      <p className="text-xs text-secondary">bpm</p>
                    </div>
                  </div>
                </div>

                {/* Body Battery */}
                <div className="glass-card rounded-2xl p-6">
                  <div className="flex items-center space-x-3 mb-4">
                    <Zap className="w-6 h-6 text-yellow-500" />
                    <h3 className="font-semibold text-primary">Body Battery</h3>
                  </div>
                  <p className="text-4xl font-bold text-primary mb-2">
                    {dailyData.body_battery_low}-{dailyData.body_battery_high}
                  </p>
                  <p className="text-sm text-secondary">lowest - highest</p>
                </div>

                {/* Stress */}
                <div className="glass-card rounded-2xl p-6">
                  <div className="flex items-center space-x-3 mb-4">
                    <Activity className="w-6 h-6 text-teal-500" />
                    <h3 className="font-semibold text-primary">Stress</h3>
                  </div>
                  <p className="text-4xl font-bold text-primary mb-2">
                    {dailyData.stress_avg}
                  </p>
                  <p className="text-sm text-secondary">average (0-100)</p>
                </div>
              </div>

              {/* Sleep Card */}
              {sleepData && (
                <div className="glass-card rounded-2xl p-6 mb-8">
                  <div className="flex items-center space-x-3 mb-6">
                    <Moon className="w-6 h-6 text-indigo-500" />
                    <h3 className="font-semibold text-primary text-lg">Sleep</h3>
                    <span className="ml-auto text-2xl font-bold text-indigo-500">
                      {sleepData.sleep_score}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-5 gap-6">
                    <div>
                      <p className="text-xs text-tertiary">Total</p>
                      <p className="text-lg font-semibold text-primary">
                        {formatTime(sleepData.duration_seconds)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-tertiary">Deep</p>
                      <p className="text-lg font-semibold text-primary">
                        {formatTime(sleepData.deep_sleep_seconds)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-tertiary">Light</p>
                      <p className="text-lg font-semibold text-primary">
                        {formatTime(sleepData.light_sleep_seconds)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-tertiary">REM</p>
                      <p className="text-lg font-semibold text-primary">
                        {formatTime(sleepData.rem_sleep_seconds)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-tertiary">Awake</p>
                      <p className="text-lg font-semibold text-primary">
                        {formatTime(sleepData.awake_seconds)}
                      </p>
                    </div>
                  </div>

                  {/* Sleep bar visualization */}
                  <div className="mt-4 h-3 rounded-full overflow-hidden flex">
                    {sleepData.deep_sleep_seconds > 0 && (
                      <div
                        className="bg-indigo-900"
                        style={{
                          width: `${(sleepData.deep_sleep_seconds / sleepData.duration_seconds) * 100}%`,
                        }}
                        title="Deep Sleep"
                      />
                    )}
                    {sleepData.light_sleep_seconds > 0 && (
                      <div
                        className="bg-indigo-400"
                        style={{
                          width: `${(sleepData.light_sleep_seconds / sleepData.duration_seconds) * 100}%`,
                        }}
                        title="Light Sleep"
                      />
                    )}
                    {sleepData.rem_sleep_seconds > 0 && (
                      <div
                        className="bg-purple-400"
                        style={{
                          width: `${(sleepData.rem_sleep_seconds / sleepData.duration_seconds) * 100}%`,
                        }}
                        title="REM"
                      />
                    )}
                    {sleepData.awake_seconds > 0 && (
                      <div
                        className="bg-gray-400"
                        style={{
                          width: `${(sleepData.awake_seconds / sleepData.duration_seconds) * 100}%`,
                        }}
                        title="Awake"
                      />
                    )}
                  </div>
                  <div className="flex gap-4 mt-1 text-xs text-tertiary">
                    <span className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded bg-indigo-900"></div>Deep
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded bg-indigo-400"></div>Light
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded bg-purple-400"></div>REM
                    </span>
                    <span className="flex items-center gap-1">
                      <div className="w-2 h-2 rounded bg-gray-400"></div>Awake
                    </span>
                  </div>
                </div>
              )}

              {/* Recent Activities */}
              {activities.length > 0 && (
                <div className="glass-card rounded-2xl p-6">
                  <h3 className="font-semibold text-primary text-lg mb-4">Recent Activities</h3>
                  <div className="space-y-3">
                    {activities.map((activity) => (
                      <div
                        key={activity.id}
                        className="flex items-center justify-between p-4 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors"
                      >
                        <div className="flex items-center space-x-4">
                          <div className="w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center text-white font-bold">
                            {activity.activity_type?.charAt(0).toUpperCase() || "A"}
                          </div>
                          <div>
                            <p className="font-medium text-primary">{activity.name}</p>
                            <p className="text-sm text-tertiary">
                              {new Date(activity.start_time).toLocaleDateString("en-US", {
                                weekday: "short",
                                month: "short",
                                day: "numeric",
                              })} • {formatTime(activity.duration_seconds)}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="font-medium text-primary">
                            {formatDistance(activity.distance_meters)}
                          </p>
                          <p className="text-xs text-tertiary">
                            {activity.avg_heart_rate} bpm avg
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-20">
              <p className="text-secondary">No health data available for this date</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
