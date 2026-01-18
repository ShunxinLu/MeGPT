"use client";

import { useState, useEffect } from "react";
import { ArrowLeft, Shield, Check, AlertCircle, RotateCcw, Database, HardDrive, Server, Clock, Save } from "lucide-react";
import Link from "next/link";

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
            <div className="h-screen bg-void flex items-center justify-center">
                <div className="flex flex-col items-center gap-4">
                    <div className="w-10 h-10 border-2 border-violet-500 border-t-transparent rounded-full animate-spin"></div>
                    <p className="text-zinc-500 font-mono text-sm animate-pulse">Initializing system control...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="h-screen overflow-y-auto bg-void text-white relative">
            {/* Background Texture */}
            <div className="fixed inset-0 bg-noise opacity-[0.03] pointer-events-none"></div>

            {/* Header */}
            <div className="sticky top-0 z-10 border-b border-white/5 bg-black/80 backdrop-blur-xl p-4">
                <div className="max-w-4xl mx-auto flex items-center gap-4">
                    <Link
                        href="/"
                        className="p-2 hover:bg-white/10 rounded-lg transition-colors text-zinc-400 hover:text-white"
                    >
                        <ArrowLeft size={20} />
                    </Link>
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-violet-500/10">
                            <Shield className="text-violet-400" size={20} />
                        </div>
                        <h1 className="text-xl font-bold font-sans tracking-tight">System Backup & Recovery</h1>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-4xl mx-auto p-6 pb-20">

                {/* Environment Status */}
                <section className="mb-8">
                    <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4 font-mono ml-1">Current Environment</h2>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <div className="glass-panel p-4 rounded-xl flex flex-col gap-2">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs font-mono uppercase">
                                <Server size={14} /> Mode
                            </div>
                            <div className="mt-1">
                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${envInfo?.is_production
                                    ? "bg-red-500/10 text-red-400 border-red-500/20"
                                    : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                                    }`}>
                                    {envInfo?.is_production ? "PRODUCTION" : "DEVELOPMENT"}
                                </span>
                            </div>
                        </div>

                        <div className="glass-panel p-4 rounded-xl flex flex-col gap-2">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs font-mono uppercase">
                                <Database size={14} /> Collection
                            </div>
                            <div className="font-mono text-sm text-zinc-200 truncate">
                                {envInfo?.qdrant_collection}
                            </div>
                        </div>

                        <div className="glass-panel p-4 rounded-xl flex flex-col gap-2">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs font-mono uppercase">
                                <HardDrive size={14} /> Data Path
                            </div>
                            <div className="font-mono text-sm text-zinc-200 truncate" title={envInfo?.data_dir}>
                                {envInfo?.data_dir}
                            </div>
                        </div>

                        <div className="glass-panel p-4 rounded-xl flex flex-col gap-2">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs font-mono uppercase">
                                <Clock size={14} /> Retention
                            </div>
                            <div className="font-mono text-sm text-zinc-200">
                                {envInfo?.backup_retention_count} snapshots
                            </div>
                        </div>
                    </div>
                </section>

                {/* Actions */}
                <section className="mb-10">
                    <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 mb-4 font-mono ml-1">Control Operations</h2>

                    {message && (
                        <div className={`mb-6 p-4 rounded-xl flex items-center gap-3 border ${message.type === "success"
                                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                                : "bg-red-500/10 border-red-500/20 text-red-400"
                            }`}>
                            {message.type === "success" ? <Check size={18} /> : <AlertCircle size={18} />}
                            <span className="font-medium text-sm">{message.text}</span>
                        </div>
                    )}

                    <div className="bg-white/5 border border-white/10 rounded-2xl p-6 backdrop-blur-sm">
                        <div className="flex flex-wrap gap-4">
                            <button
                                onClick={createBackup}
                                disabled={actionLoading}
                                className="flex items-center gap-2 px-6 py-3 bg-violet-600 hover:bg-violet-500 text-white rounded-xl font-medium shadow-lg shadow-violet-500/20 transition-all hover:scale-105 active:scale-95 disabled:opacity-50 disabled:pointer-events-none"
                            >
                                <Save size={18} />
                                Create Snapshot
                            </button>
                            <button
                                onClick={rollback}
                                disabled={actionLoading || backups.length === 0}
                                className="flex items-center gap-2 px-6 py-3 bg-white/5 hover:bg-white/10 text-zinc-200 border border-white/5 hover:border-white/10 rounded-xl font-medium transition-all hover:scale-105 active:scale-95 disabled:opacity-50 disabled:pointer-events-none"
                            >
                                <RotateCcw size={18} />
                                Rollback to Latest
                            </button>
                        </div>
                        <p className="mt-4 text-xs text-zinc-500 font-mono">
                            * Creating a snapshot triggers a full backup of the vector database and conversation logs.
                        </p>
                    </div>
                </section>

                {/* Backup List */}
                <section>
                    <div className="flex items-center justify-between mb-4 px-1">
                        <h2 className="text-xs font-medium uppercase tracking-wider text-zinc-500 font-mono">Snapshot History</h2>
                        <span className="text-xs text-zinc-600 font-mono">{backups.length} entries</span>
                    </div>

                    {backups.length === 0 ? (
                        <div className="text-center py-20 rounded-3xl border border-dashed border-white/10 bg-white/[0.02]">
                            <Database size={48} className="mx-auto text-zinc-800 mb-4" />
                            <p className="text-zinc-600">No backups found in local storage</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {backups.map((backup) => (
                                <div
                                    key={backup.id}
                                    className="group flex flex-col sm:flex-row sm:items-center justify-between p-5 bg-white/[0.03] border border-white/5 rounded-2xl hover:border-violet-500/30 hover:bg-white/[0.05] transition-all duration-300"
                                >
                                    <div className="mb-4 sm:mb-0">
                                        <div className="flex items-center gap-3 mb-1">
                                            <span className="font-mono text-zinc-300">{backup.id}</span>
                                            {backup.id.includes("auto") && (
                                                <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">Auto</span>
                                            )}
                                        </div>
                                        <div className="text-xs text-zinc-500 font-mono flex items-center gap-3">
                                            <span>{new Date(backup.timestamp).toLocaleString()}</span>
                                            <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                                            <span>{backup.chat_count} chats</span>
                                            <span className="w-1 h-1 rounded-full bg-zinc-700"></span>
                                            <span>{backup.message_count} msgs</span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => restoreBackup(backup.id)}
                                        disabled={actionLoading}
                                        className="px-4 py-2 text-sm bg-white/5 hover:bg-white/10 text-zinc-400 hover:text-white rounded-lg transition-colors border border-white/5 hover:border-white/10 opacity-0 group-hover:opacity-100 sm:translate-x-4 group-hover:translate-x-0"
                                    >
                                        Restore
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </section>
            </div>
        </div>
    );
}
