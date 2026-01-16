"use client";

import { useState, useEffect } from "react";

interface EnvironmentInfo {
    env_mode: string;
    is_production: boolean;
    data_dir: string;
    qdrant_collection: string;
    backup_interval_hours: number;
    backup_retention_count: number;
}

interface BackupInfo {
    id: string;
    timestamp: string;
    env_mode: string;
    chat_count: number;
    message_count: number;
    memory_count: number;
}

export default function AdminPage() {
    const [envInfo, setEnvInfo] = useState<EnvironmentInfo | null>(null);
    const [backups, setBackups] = useState<BackupInfo[]>([]);
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState(false);
    const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [envRes, backupsRes] = await Promise.all([
                fetch("/api/admin/env"),
                fetch("/api/admin/backups"),
            ]);

            if (envRes.ok) setEnvInfo(await envRes.json());
            if (backupsRes.ok) setBackups(await backupsRes.json());
        } catch (error) {
            console.error("Failed to load admin data:", error);
        } finally {
            setLoading(false);
        }
    };

    const createBackup = async () => {
        setActionLoading(true);
        setMessage(null);
        try {
            const res = await fetch("/api/admin/backup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ description: "Manual backup" }),
            });

            if (res.ok) {
                const data = await res.json();
                setMessage({ type: "success", text: `Backup created: ${data.backup_id}` });
                loadData();
            } else {
                setMessage({ type: "error", text: "Backup failed" });
            }
        } catch (error) {
            setMessage({ type: "error", text: "Backup failed" });
        } finally {
            setActionLoading(false);
        }
    };

    const restoreBackup = async (backupId: string) => {
        if (!confirm(`Restore from backup ${backupId}? This will replace current data.`)) return;

        setActionLoading(true);
        setMessage(null);
        try {
            const res = await fetch(`/api/admin/restore/${backupId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ confirm: true }),
            });

            if (res.ok) {
                setMessage({ type: "success", text: `Restored from ${backupId}` });
                loadData();
            } else {
                setMessage({ type: "error", text: "Restore failed" });
            }
        } catch (error) {
            setMessage({ type: "error", text: "Restore failed" });
        } finally {
            setActionLoading(false);
        }
    };

    const rollback = async () => {
        if (!confirm("Rollback to the most recent backup? This will replace current data.")) return;

        setActionLoading(true);
        setMessage(null);
        try {
            const res = await fetch("/api/admin/rollback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ confirm: true }),
            });

            if (res.ok) {
                setMessage({ type: "success", text: "Rollback successful" });
                loadData();
            } else {
                setMessage({ type: "error", text: "Rollback failed" });
            }
        } catch (error) {
            setMessage({ type: "error", text: "Rollback failed" });
        } finally {
            setActionLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-950">
                <div className="text-gray-400">Loading admin panel...</div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-950 text-white p-8">
            <div className="max-w-4xl mx-auto">
                <h1 className="text-3xl font-bold mb-8">⚙️ Admin Panel</h1>

                {/* Environment Status */}
                <div className="bg-gray-900 rounded-xl p-6 mb-8">
                    <h2 className="text-xl font-semibold mb-4">Environment</h2>
                    {envInfo && (
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <span className="text-gray-400">Mode:</span>
                                <span className={`ml-2 px-3 py-1 rounded-full text-sm font-medium ${envInfo.is_production
                                        ? "bg-red-900/50 text-red-300 border border-red-700"
                                        : "bg-green-900/50 text-green-300 border border-green-700"
                                    }`}>
                                    {envInfo.is_production ? "🔴 PRODUCTION" : "🟢 DEVELOPMENT"}
                                </span>
                            </div>
                            <div>
                                <span className="text-gray-400">Collection:</span>
                                <span className="ml-2 text-gray-200">{envInfo.qdrant_collection}</span>
                            </div>
                            <div>
                                <span className="text-gray-400">Data Dir:</span>
                                <span className="ml-2 text-gray-200 text-sm">{envInfo.data_dir}</span>
                            </div>
                            <div>
                                <span className="text-gray-400">Retention:</span>
                                <span className="ml-2 text-gray-200">{envInfo.backup_retention_count} backups</span>
                            </div>
                        </div>
                    )}
                </div>

                {/* Actions */}
                <div className="bg-gray-900 rounded-xl p-6 mb-8">
                    <h2 className="text-xl font-semibold mb-4">Actions</h2>

                    {message && (
                        <div className={`mb-4 p-3 rounded-lg ${message.type === "success" ? "bg-green-900/50 text-green-300" : "bg-red-900/50 text-red-300"
                            }`}>
                            {message.text}
                        </div>
                    )}

                    <div className="flex gap-4">
                        <button
                            onClick={createBackup}
                            disabled={actionLoading}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-medium disabled:opacity-50"
                        >
                            📦 Create Backup
                        </button>
                        <button
                            onClick={rollback}
                            disabled={actionLoading || backups.length === 0}
                            className="px-4 py-2 bg-orange-600 hover:bg-orange-700 rounded-lg font-medium disabled:opacity-50"
                        >
                            🔄 Rollback to Latest
                        </button>
                    </div>
                </div>

                {/* Backup List */}
                <div className="bg-gray-900 rounded-xl p-6">
                    <h2 className="text-xl font-semibold mb-4">Backups ({backups.length})</h2>

                    {backups.length === 0 ? (
                        <p className="text-gray-400">No backups yet. Create one to get started.</p>
                    ) : (
                        <div className="space-y-3">
                            {backups.map((backup) => (
                                <div
                                    key={backup.id}
                                    className="flex items-center justify-between p-4 bg-gray-800 rounded-lg"
                                >
                                    <div>
                                        <div className="font-medium">{backup.id}</div>
                                        <div className="text-sm text-gray-400">
                                            {new Date(backup.timestamp).toLocaleString()} •
                                            {backup.chat_count} chats, {backup.message_count} msgs, {backup.memory_count} memories
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => restoreBackup(backup.id)}
                                        disabled={actionLoading}
                                        className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm disabled:opacity-50"
                                    >
                                        Restore
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Back Link */}
                <div className="mt-8">
                    <a href="/" className="text-blue-400 hover:underline">
                        ← Back to Chat
                    </a>
                </div>
            </div>
        </div>
    );
}
